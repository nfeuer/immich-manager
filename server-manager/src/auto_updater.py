"""
Immich Auto-Updater

Watches for new releases, applies patch-level updates automatically (when
configured), takes a pre-update snapshot of the database and docker-compose
files, and rolls back automatically if the health check fails post-update.

Update policy
-------------
- Patch bump  (x.y.Z → x.y.Z+1): auto-applied when apply_patch_updates=True
- Minor bump  (x.Y.z):            alert only – requires manual /api/updates/apply
- Major bump  (X.y.z):            alert only – never auto-applied

Snapshot contents
-----------------
Each snapshot is stored in <backup_dir>/snapshots/snapshot_<timestamp>/
  immich_db_<ts>.sql.gz    — pg_dump of the Immich database
  immich_compose_<ts>.tar.gz — docker-compose.yml + .env
"""

import gzip
import logging
import shutil
import subprocess
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from .utils import CLEAN_ENV

logger = logging.getLogger(__name__)


def _is_patch_bump(from_v: str, to_v: str) -> bool:
    """Return True only when to_v is a patch increment of from_v (same major.minor)."""
    try:
        f = tuple(int(x) for x in from_v.split("."))
        t = tuple(int(x) for x in to_v.split("."))
        return len(f) == 3 and len(t) == 3 and f[0] == t[0] and f[1] == t[1] and t[2] > f[2]
    except (ValueError, IndexError):
        return False


class AutoUpdater:
    """Manages Immich container updates with snapshot / rollback capability."""

    def __init__(
        self,
        config,             # AutoUpdateConfig
        backup_manager,     # BackupManager
        docker_monitor,     # DockerMonitor
        update_checker,     # UpdateChecker
        database,           # Database
        immich_api_url: str = "http://localhost:2283/api",
    ):
        self.config = config
        self.backup_manager = backup_manager
        self.docker_monitor = docker_monitor
        self.update_checker = update_checker
        self.database = database
        self.immich_api_url = immich_api_url

        self._snapshot_dir = Path(backup_manager.backup_dir) / "snapshots"
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Snapshot                                                             #
    # ------------------------------------------------------------------ #

    def take_snapshot(self, trigger: str = "manual") -> Dict[str, Any]:
        """
        Create a pre-update snapshot: DB dump + docker-compose files.

        Returns a dict with keys: status, id, version_before, db_backup_path,
        compose_backup_path (or status/error on failure).
        """
        version = self.update_checker.get_running_version() or "unknown"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap_dir = self._snapshot_dir / f"snapshot_{ts}"
        snap_dir.mkdir(parents=True, exist_ok=True)

        db_path: Optional[str] = None
        compose_path: Optional[str] = None

        # DB dump
        try:
            db_file = snap_dir / f"immich_db_{ts}.sql.gz"
            self._dump_postgres(db_file)
            db_path = str(db_file)
        except Exception as e:
            logger.error(f"Snapshot DB dump failed: {e}")
            shutil.rmtree(snap_dir, ignore_errors=True)
            return {"status": "failed", "error": f"DB dump failed: {e}"}

        # Compose archive (non-fatal – the DB snapshot is the critical piece)
        try:
            compose_file = snap_dir / f"immich_compose_{ts}.tar.gz"
            self._archive_compose(Path(self.config.docker_compose_path), compose_file)
            compose_path = str(compose_file)
        except Exception as e:
            logger.warning(f"Snapshot compose archive failed (non-fatal): {e}")

        snapshot_id = self.database.record_snapshot(
            trigger=trigger,
            version_before=version,
            db_backup_path=db_path,
            compose_backup_path=compose_path,
        )

        logger.info(f"Snapshot {snapshot_id} created (version={version}, trigger={trigger})")
        return {
            "status": "success",
            "id": snapshot_id,
            "version_before": version,
            "db_backup_path": db_path,
            "compose_backup_path": compose_path,
        }

    def _dump_postgres(self, dest: Path) -> None:
        """Run pg_dump inside the postgres container and gzip the output."""
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=postgres", "--format", "{{.Names}}"],
            capture_output=True, text=True, check=True, env=CLEAN_ENV,
        )
        container = result.stdout.strip().split("\n")[0]
        if not container:
            raise RuntimeError("PostgreSQL container not found")

        proc = subprocess.run(
            ["docker", "exec", container, "pg_dump", "-U", "postgres", "immich"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, env=CLEAN_ENV,
        )
        with gzip.open(dest, "wb") as gz_out:
            gz_out.write(proc.stdout)

    def _archive_compose(self, src_dir: Path, dest: Path) -> None:
        """Create a tar.gz of docker-compose.yml and .env from src_dir."""
        candidates = ["docker-compose.yml", "docker-compose.yaml", ".env"]
        files_to_archive = [f for f in candidates if (src_dir / f).exists()]
        if not files_to_archive:
            raise FileNotFoundError(f"No compose files found in {src_dir}")
        with tarfile.open(dest, "w:gz") as tar:
            for fname in files_to_archive:
                tar.add(src_dir / fname, arcname=fname)

    # ------------------------------------------------------------------ #
    # Update                                                               #
    # ------------------------------------------------------------------ #

    def apply_update(self, target_version: str) -> Dict[str, Any]:
        """
        Full update workflow:
          snapshot → docker compose pull → up -d → health check
          → auto-rollback on failure.
        """
        running_version = self.update_checker.get_running_version() or "unknown"
        compose_path = Path(self.config.docker_compose_path)

        history_id = self.database.record_update_history(
            from_version=running_version,
            to_version=target_version,
            status="in_progress",
        )

        # Snapshot
        snap = self.take_snapshot(trigger="auto_update")
        if snap["status"] != "success":
            self.database.complete_update_history(
                history_id, "failed", error_message=snap.get("error")
            )
            return {"status": "failed", "error": snap.get("error")}
        snapshot_id = snap["id"]

        # Pull new images
        try:
            logger.info(f"Pulling Immich images for v{target_version}")
            subprocess.run(
                ["docker", "compose", "pull"],
                cwd=str(compose_path), check=True,
                capture_output=True, timeout=300, env=CLEAN_ENV,
            )
        except Exception as e:
            error = f"docker compose pull failed: {e}"
            logger.error(error)
            self.database.complete_update_history(
                history_id, "failed", error_message=error, snapshot_id=snapshot_id
            )
            return {"status": "failed", "error": error}

        # Recreate containers
        try:
            logger.info("Restarting Immich containers with new images")
            subprocess.run(
                ["docker", "compose", "up", "-d", "--remove-orphans"],
                cwd=str(compose_path), check=True,
                capture_output=True, timeout=120, env=CLEAN_ENV,
            )
        except Exception as e:
            error = f"docker compose up failed: {e}"
            logger.error(error)
            self._do_rollback(snapshot_id)
            self.database.complete_update_history(
                history_id, "rolled_back", error_message=error, snapshot_id=snapshot_id
            )
            return {"status": "failed", "error": error, "rolled_back": True}

        # Health check
        if not self._verify_immich_healthy(self.config.health_check_timeout):
            error = f"Immich did not become healthy within {self.config.health_check_timeout}s"
            logger.error(error)
            self._do_rollback(snapshot_id)
            self.database.complete_update_history(
                history_id, "rolled_back", error_message=error, snapshot_id=snapshot_id
            )
            return {"status": "failed", "error": error, "rolled_back": True}

        logger.info(f"Immich updated: v{running_version} → v{target_version}")
        self.database.complete_update_history(
            history_id, "success", snapshot_id=snapshot_id
        )
        return {
            "status": "success",
            "from_version": running_version,
            "to_version": target_version,
            "snapshot_id": snapshot_id,
        }

    def _verify_immich_healthy(self, timeout_s: int) -> bool:
        """Poll Immich /api/server-info until HTTP 200 or timeout."""
        url = self.immich_api_url.rstrip("/") + "/server-info"
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(5)
        return False

    # ------------------------------------------------------------------ #
    # Rollback                                                             #
    # ------------------------------------------------------------------ #

    def rollback_to_snapshot(self, snapshot_id: int) -> Dict[str, Any]:
        """
        Roll back to a snapshot: restore DB, restore compose files, restart containers.
        """
        snapshots = self.database.get_snapshots()
        snap = next((s for s in snapshots if s["id"] == snapshot_id), None)
        if not snap:
            return {"status": "failed", "error": f"Snapshot {snapshot_id} not found"}

        history_id = self.database.record_update_history(
            from_version=self.update_checker.get_running_version() or "unknown",
            to_version=snap["version_before"],
            status="in_progress",
        )

        errors: List[str] = []

        # Stop Immich
        try:
            self.docker_monitor.stop_immich()
        except Exception as e:
            logger.warning(f"Stop immich warning during rollback: {e}")

        # Restore DB
        if snap.get("db_backup_path"):
            result = self.backup_manager.restore_database(snap["db_backup_path"])
            if result["status"] != "success":
                errors.append(f"DB restore failed: {result.get('error')}")
        else:
            errors.append("No DB backup path in snapshot")

        # Restore compose files
        if snap.get("compose_backup_path"):
            try:
                compose_dest = Path(self.config.docker_compose_path)
                with tarfile.open(snap["compose_backup_path"], "r:gz") as tar:
                    tar.extractall(path=compose_dest)
            except Exception as e:
                logger.warning(f"Compose restore warning: {e}")

        # Start Immich
        try:
            self.docker_monitor.start_immich()
        except Exception as e:
            errors.append(f"Start immich failed: {e}")

        # Verify health
        healthy = self._verify_immich_healthy(self.config.health_check_timeout)
        if not healthy:
            errors.append("Immich did not come back healthy after rollback")

        status = "rolled_back" if not errors else "failed"
        self.database.update_snapshot_status(snapshot_id, "used")
        self.database.complete_update_history(
            history_id,
            status,
            error_message="; ".join(errors) if errors else None,
            snapshot_id=snapshot_id,
        )

        if errors:
            logger.error(f"Rollback to snapshot {snapshot_id} had issues: {errors}")
            return {"status": "failed", "errors": errors}

        logger.info(f"Rolled back to snapshot {snapshot_id} (version={snap['version_before']})")
        return {"status": "success", "version_restored": snap["version_before"]}

    def _do_rollback(self, snapshot_id: int) -> None:
        """Convenience wrapper for automatic rollback after a failed update."""
        logger.warning(f"Auto-rolling back to snapshot {snapshot_id}")
        try:
            # Stop → restore DB → restore compose → start
            snap_list = self.database.get_snapshots()
            snap = next((s for s in snap_list if s["id"] == snapshot_id), None)
            if not snap:
                logger.error(f"Cannot auto-rollback: snapshot {snapshot_id} not found")
                return

            self.docker_monitor.stop_immich()

            if snap.get("db_backup_path"):
                self.backup_manager.restore_database(snap["db_backup_path"])

            if snap.get("compose_backup_path"):
                try:
                    with tarfile.open(snap["compose_backup_path"], "r:gz") as tar:
                        tar.extractall(path=Path(self.config.docker_compose_path))
                except Exception as e:
                    logger.warning(f"Compose restore during auto-rollback: {e}")

            self.docker_monitor.start_immich()
            self.database.update_snapshot_status(snapshot_id, "used")
        except Exception as e:
            logger.error(f"Auto-rollback failed: {e}")

    # ------------------------------------------------------------------ #
    # Scheduled entry point                                                #
    # ------------------------------------------------------------------ #

    def check_and_auto_apply(self, update_info: dict) -> Optional[Dict[str, Any]]:
        """
        Called by the scheduler when an update is available.

        Auto-applies patch bumps when apply_patch_updates=True.
        Returns result dict if action was taken, None if alert-only.
        """
        running = update_info.get("running_version", "")
        latest = update_info.get("latest_version", "")

        if self.config.apply_patch_updates and _is_patch_bump(running, latest):
            logger.info(f"Auto-applying patch update v{running} → v{latest}")
            return self.apply_update(latest)

        # Minor / major bump, or auto-apply disabled: let caller send alert
        return None

    # ------------------------------------------------------------------ #
    # Snapshot cleanup                                                     #
    # ------------------------------------------------------------------ #

    def cleanup_old_snapshots(self) -> None:
        """Remove snapshot directories older than snapshot_retention_days."""
        cutoff = time.time() - self.config.snapshot_retention_days * 86400
        for snap_dir in self._snapshot_dir.iterdir():
            if snap_dir.is_dir() and snap_dir.stat().st_mtime < cutoff:
                try:
                    shutil.rmtree(snap_dir)
                    logger.info(f"Removed old snapshot dir: {snap_dir.name}")
                except Exception as e:
                    logger.warning(f"Could not remove snapshot dir {snap_dir}: {e}")
