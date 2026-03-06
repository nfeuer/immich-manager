"""
Main FastAPI application for Immich Server Manager
"""

import sys
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import uvicorn
import asyncio
import requests as http_requests
import logging
import sdnotify

# Add project root to path for shared library
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from .config import load_config, Config
from .database import Database
from .monitoring import DiskMonitor, SystemMonitor, DockerMonitor
from .backup import BackupManager
from .alerts import AlertManager
from .update_checker import UpdateChecker
from .auto_updater import AutoUpdater
from .prometheus import generate_metrics
from .audit import ensure_audit_table, record_audit, get_audit_log
from .logging_config import setup_json_logging
from shared.auth import (
    Role, ensure_users_table, get_or_create_user, require_role,
    get_all_users, update_user_role, extract_token, validate_immich_token,
)

setup_json_logging()
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Immich Server Manager",
    description="Monitoring, backups, and management for Immich installations",
    version="1.0.0"
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# --- Authentication ---

def _get_allowed_origins() -> List[str]:
    """Build allowed origins from config at startup."""
    try:
        cfg = load_config()
        immich_url = cfg.immich.api_url.rsplit("/api", 1)[0]  # e.g. http://localhost:2283
        origins = [
            f"http://localhost:{cfg.server.port}",
            f"http://127.0.0.1:{cfg.server.port}",
            immich_url,
        ]
        return origins
    except Exception:
        return ["http://localhost:8080", "http://127.0.0.1:8080"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to every response."""
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


async def require_auth(request: Request) -> Dict[str, Any]:
    """
    Dependency that validates the request against Immich's auth system
    and attaches the local user (with role) to request state.
    """
    token = extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    immich_api_url = getattr(request.app.state, "immich_api_url", None)
    if not immich_api_url:
        raise HTTPException(status_code=503, detail="Immich API URL not configured")

    immich_user = validate_immich_token(immich_api_url, token)
    if not immich_user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Look up / create local user with role
    default_role = getattr(request.app.state, "default_role", "user")
    local_user, created = get_or_create_user(database, immich_user, default_role)

    if created and database:
        record_audit(database, "user_created",
                     user_id=immich_user.get("id"),
                     details=f"role={local_user['role']} bootstrap={local_user['role'] == 'admin'}",
                     ip_address=request.client.host if request.client else None)

    request.state._local_user = local_user
    immich_user["_local_user"] = local_user
    return immich_user


async def require_admin(request: Request) -> Dict[str, Any]:
    """Dependency that requires admin role. Server Manager is admin-only."""
    user = await require_auth(request)
    local_user = user.get("_local_user", {})
    if Role[local_user.get("role", "guest").upper()] < Role.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# Global state
config: Optional[Config] = None
database: Optional[Database] = None
disk_monitor: Optional[DiskMonitor] = None
system_monitor: Optional[SystemMonitor] = None
docker_monitor: Optional[DockerMonitor] = None
backup_manager: Optional[BackupManager] = None
alert_manager: Optional[AlertManager] = None
update_checker: Optional[UpdateChecker] = None
auto_updater: Optional[AutoUpdater] = None
scheduler: Optional[AsyncIOScheduler] = None


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    global config, database, disk_monitor, system_monitor, docker_monitor
    global backup_manager, alert_manager, update_checker, auto_updater, scheduler

    try:
        # Load configuration
        config = load_config()

        # Initialize database
        database = Database()
        ensure_audit_table(database)
        ensure_users_table(database)

        # Initialize monitors
        all_drives = config.storage.data_drives + config.storage.parity_drives
        disk_monitor = DiskMonitor(all_drives) if all_drives else DiskMonitor([])
        system_monitor = SystemMonitor()
        docker_monitor = DockerMonitor()

        # Initialize backup manager
        backup_manager = BackupManager(config.backup)

        # Initialize alert manager
        alert_manager = AlertManager(config.alerts)

        # Initialize update checker
        update_checker = UpdateChecker(docker_monitor)

        # Initialize auto-updater (only when enabled in config)
        if config.auto_update.enabled:
            auto_updater = AutoUpdater(
                config=config.auto_update,
                backup_manager=backup_manager,
                docker_monitor=docker_monitor,
                update_checker=update_checker,
                database=database,
                immich_api_url=config.immich.api_url,
            )

        # Store Immich API URL for auth validation
        app.state.immich_api_url = config.immich.api_url
        app.state.default_role = config.auth.default_role

        # Initialize scheduler
        scheduler = AsyncIOScheduler()

        # Schedule disk health checks
        scheduler.add_job(
            check_disk_health_job,
            'interval',
            seconds=config.monitoring.disk_check_interval,
            id='disk_health_check'
        )

        # Schedule system metrics collection
        scheduler.add_job(
            collect_metrics_job,
            'interval',
            seconds=config.monitoring.metrics_interval,
            id='system_metrics'
        )

        # Schedule backups
        if config.backup.enabled:
            trigger = CronTrigger.from_crontab(config.backup.schedule)
            scheduler.add_job(
                backup_job,
                trigger,
                id='backup'
            )

        # Schedule database cleanup (weekly)
        scheduler.add_job(
            cleanup_job,
            'cron',
            day_of_week='sun',
            hour=3,
            id='cleanup'
        )

        # Schedule Immich container health checks (every 5 minutes)
        scheduler.add_job(
            check_immich_health_job,
            'interval',
            seconds=300,
            id='immich_health_check'
        )

        # Check for Immich updates (daily at 10 AM)
        scheduler.add_job(
            check_immich_update_job,
            'cron',
            hour=10,
            id='immich_update_check'
        )

        # Clean up old snapshots (weekly, Sunday at 4 AM)
        if config.auto_update.enabled:
            scheduler.add_job(
                snapshot_cleanup_job,
                'cron',
                day_of_week='sun',
                hour=4,
                id='snapshot_cleanup'
            )

        # Watchdog heartbeat (every 30s, half of WatchdogSec=60)
        async def _watchdog_heartbeat():
            sd = sdnotify.SystemdNotifier(debug=False)
            sd.notify("WATCHDOG=1")

        scheduler.add_job(_watchdog_heartbeat, "interval", seconds=30, id="watchdog")

        scheduler.start()

        # Signal systemd that we are ready
        sd = sdnotify.SystemdNotifier(debug=False)
        sd.notify("READY=1")

        logger.info("Immich Server Manager started successfully")
        logger.info(f"Dashboard: http://{config.server.host}:{config.server.port}")

    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if scheduler:
        scheduler.shutdown()
    print("✓ Server Manager shut down")


# Background jobs
async def check_disk_health_job():
    """Background job to check disk health"""
    if not disk_monitor or not database or not alert_manager or not config:
        return

    try:
        disks = disk_monitor.check_all_disks()

        for disk in disks:
            # Record to database
            database.record_disk_health(disk['device'], disk)

            # Check thresholds and send alerts
            if disk.get('temperature') and disk['temperature'] > config.thresholds.disk_temp_critical:
                await alert_manager.send_alert(
                    f"Critical Temperature: {disk['device']}",
                    f"Temperature: {disk['temperature']}°C (Critical: {config.thresholds.disk_temp_critical}°C)",
                    "critical"
                )
                database.record_alert(
                    "critical",
                    "disk_health",
                    f"Critical temperature on {disk['device']}: {disk['temperature']}°C"
                )

            elif disk.get('temperature') and disk['temperature'] > config.thresholds.disk_temp_warning:
                await alert_manager.send_alert(
                    f"High Temperature: {disk['device']}",
                    f"Temperature: {disk['temperature']}°C (Warning: {config.thresholds.disk_temp_warning}°C)",
                    "warning"
                )

            # Check for disk errors
            if not disk.get('health_ok', True):
                alert_manager.send_disk_health_alert(disk)
                database.record_alert(
                    "warning",
                    "disk_health",
                    f"Disk health issues on {disk['device']}",
                    str(disk.get('warnings', []))
                )

    except Exception as e:
        print(f"Error in disk health check: {e}")


async def collect_metrics_job():
    """Background job to collect system metrics"""
    if not system_monitor or not database:
        return

    try:
        metrics = system_monitor.get_all_metrics()
        database.record_system_metrics(metrics)

        # Check thresholds
        if config and metrics.get('disk_usage_percent', 0) > config.thresholds.disk_space_critical:
            await alert_manager.send_alert(
                "Critical Disk Space",
                f"Disk usage: {metrics['disk_usage_percent']:.1f}%",
                "critical"
            )
            database.record_alert(
                "critical",
                "disk_space",
                f"Disk usage critical: {metrics['disk_usage_percent']:.1f}%"
            )
        elif config and metrics.get('disk_usage_percent', 0) > config.thresholds.disk_space_warning:
            await alert_manager.send_alert(
                "High Disk Usage",
                f"Disk usage: {metrics['disk_usage_percent']:.1f}% (threshold: {config.thresholds.disk_space_warning}%)",
                "warning"
            )

    except Exception as e:
        print(f"Error collecting metrics: {e}")


async def backup_job():
    """Background job to run backups"""
    if not backup_manager or not database or not alert_manager:
        return

    try:
        print(f"Starting scheduled backup at {datetime.now()}")
        result = backup_manager.run_full_backup()

        # Record to database
        database.record_backup(
            "scheduled",
            result['status'],
            file_path=result.get('database', {}).get('file_path'),
            size_bytes=result.get('database', {}).get('size_bytes'),
            duration_seconds=result.get('database', {}).get('duration_seconds'),
            error_message=result.get('database', {}).get('error')
        )

        # Send alert
        alert_manager.send_backup_alert(result['database'])

        print(f"Backup completed: {result['status']}")

    except Exception as e:
        print(f"Error in backup job: {e}")
        database.record_backup(
            "scheduled",
            "failed",
            error_message=str(e)
        )


async def cleanup_job():
    """Background job to clean up old data"""
    if not database:
        return

    try:
        database.cleanup_old_data(days=90)
        print("Database cleanup completed")
    except Exception as e:
        print(f"Error in cleanup job: {e}")


_immich_was_healthy: bool = True


async def check_immich_health_job():
    """Check if Immich containers are running and alert on state change."""
    global _immich_was_healthy
    if not docker_monitor or not alert_manager:
        return

    try:
        healthy = docker_monitor.check_immich_healthy()
        if not healthy and _immich_was_healthy:
            containers = docker_monitor.get_immich_containers()
            down = [c["name"] for c in containers if c.get("status") != "running"]
            await alert_manager.send_alert(
                "Immich Containers Down",
                f"One or more Immich containers are not running: {', '.join(down) if down else 'none found'}",
                "critical",
            )
            if database:
                database.record_alert(
                    "critical", "immich_health",
                    f"Immich containers down: {', '.join(down) if down else 'unknown'}"
                )
        elif healthy and not _immich_was_healthy:
            await alert_manager.send_alert(
                "Immich Containers Recovered",
                "All Immich containers are running again.",
                "info",
            )
        _immich_was_healthy = healthy
    except Exception as e:
        print(f"Error in Immich health check: {e}")


async def check_immich_update_job():
    """Check for Immich updates and auto-apply patch bumps when configured."""
    if not update_checker or not alert_manager or not database:
        return

    try:
        update_info = update_checker.check_for_update()
        if not update_info:
            return

        # Let auto-updater handle patch bumps when enabled
        if auto_updater:
            result = auto_updater.check_and_auto_apply(update_info)
            if result is not None:
                if result["status"] == "success":
                    msg = (
                        f"Immich auto-updated from v{result['from_version']} "
                        f"to v{result['to_version']} (snapshot {result['snapshot_id']} kept for rollback)."
                    )
                    await alert_manager.send_alert("Immich Auto-Updated", msg, "info")
                else:
                    msg = (
                        f"Immich auto-update to v{update_info['latest_version']} failed "
                        f"and was rolled back: {result.get('error', 'unknown error')}"
                    )
                    await alert_manager.send_alert("Immich Update Failed", msg, "critical")
                database.record_alert("info", "immich_update", msg)
                return  # handled – skip the alert-only path below

        # Alert-only: non-patch bump, or auto-updater disabled
        msg = (
            f"Immich v{update_info['latest_version']} is available "
            f"(currently running v{update_info['running_version']}).\n"
            f"Release notes: {update_info['release_url']}"
        )
        await alert_manager.send_alert("Immich Update Available", msg, "info")
        database.record_alert("info", "immich_update", msg)
        print(f"Immich update available: v{update_info['latest_version']}")
    except Exception as e:
        print(f"Error checking Immich updates: {e}")


async def snapshot_cleanup_job():
    """Remove snapshot directories older than retention_days."""
    if not auto_updater:
        return
    try:
        auto_updater.cleanup_old_snapshots()
    except Exception as e:
        print(f"Error cleaning up snapshots: {e}")


# API Endpoints
@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user: Dict = Depends(require_admin)):
    """Serve dashboard HTML (admin only)"""
    dashboard_path = Path(__file__).parent.parent / "static" / "dashboard.html"
    if dashboard_path.exists():
        return dashboard_path.read_text()
    else:
        return """
        <html>
            <head><title>Immich Server Manager</title></head>
            <body>
                <h1>Immich Server Manager</h1>
                <p>Dashboard coming soon...</p>
                <p>API Documentation: <a href="/docs">/docs</a></p>
            </body>
        </html>
        """


@app.get("/health")
@limiter.limit("30/minute")
async def health_check(request: Request):
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/status")
@limiter.limit("30/minute")
async def get_status(request: Request, user: Dict = Depends(require_admin)):
    """Get overall system status"""
    if not system_monitor or not docker_monitor:
        raise HTTPException(status_code=503, detail="Monitors not initialized")

    return {
        "timestamp": datetime.now().isoformat(),
        "system": system_monitor.get_all_metrics(),
        "immich_healthy": docker_monitor.check_immich_healthy(),
        "containers": docker_monitor.get_immich_containers()
    }


@app.get("/api/disks")
@limiter.limit("30/minute")
async def get_disk_health(request: Request, user: Dict = Depends(require_admin)):
    """Get current disk health"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return {
        "disks": database.get_latest_disk_health(),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/metrics")
@limiter.limit("30/minute")
async def get_metrics(request: Request, hours: int = 24, user: Dict = Depends(require_admin)):
    """Get system metrics for time range"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return {
        "metrics": database.get_system_metrics(hours),
        "hours": hours
    }


@app.get("/api/backups")
@limiter.limit("30/minute")
async def get_backups(request: Request, user: Dict = Depends(require_admin)):
    """Get backup history"""
    if not database or not backup_manager:
        raise HTTPException(status_code=503, detail="Services not initialized")

    return {
        "history": database.get_recent_backups(limit=20),
        "available": backup_manager.list_backups()
    }


@app.post("/api/backup/now")
@limiter.limit("2/minute")
async def trigger_backup(request: Request, background_tasks: BackgroundTasks, user: Dict = Depends(require_admin)):
    """Trigger immediate backup"""
    if not backup_manager:
        raise HTTPException(status_code=503, detail="Backup manager not initialized")

    background_tasks.add_task(backup_job)

    return {
        "status": "started",
        "message": "Backup started in background"
    }


@app.get("/api/alerts")
@limiter.limit("30/minute")
async def get_alerts(request: Request, acknowledged: bool = False, user: Dict = Depends(require_admin)):
    """Get alerts"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return {
        "alerts": database.get_alerts(acknowledged=acknowledged)
    }


@app.post("/api/alerts/{alert_id}/acknowledge")
@limiter.limit("30/minute")
async def acknowledge_alert(request: Request, alert_id: int, user: Dict = Depends(require_admin)):
    """Acknowledge an alert"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    database.acknowledge_alert(alert_id)

    return {"status": "ok"}


@app.post("/api/test-alert")
@limiter.limit("3/minute")
async def test_alert(request: Request, user: Dict = Depends(require_admin)):
    """Send test alert"""
    if not alert_manager:
        raise HTTPException(status_code=503, detail="Alert manager not initialized")

    await alert_manager.send_alert(
        "Test Alert",
        "This is a test alert from Immich Server Manager",
        "info"
    )

    return {"status": "sent"}


@app.get("/api/immich-update")
@limiter.limit("5/minute")
async def check_immich_update(request: Request, user: Dict = Depends(require_admin)):
    """Check if a newer Immich version is available on GitHub"""
    if not update_checker:
        raise HTTPException(status_code=503, detail="Update checker not initialized")

    running = update_checker.get_running_version()
    latest = update_checker.get_latest_github_version()

    result = {
        "running_version": running,
        "latest_version": latest,
        "update_available": False,
    }

    if running and latest:
        try:
            result["update_available"] = (
                update_checker._parse_version(latest) > update_checker._parse_version(running)
            )
        except (ValueError, TypeError):
            pass
        if result["update_available"]:
            result["release_url"] = f"https://github.com/immich-app/immich/releases/tag/v{latest}"

    return result


# --- Prometheus metrics ---

@app.get("/metrics", response_class=PlainTextResponse)
@limiter.limit("30/minute")
async def prometheus_metrics(request: Request):
    """Prometheus-compatible metrics endpoint (no auth — restrict via firewall)."""
    body = generate_metrics(system_monitor, docker_monitor, disk_monitor, database)
    return PlainTextResponse(body, media_type="text/plain; version=0.0.4; charset=utf-8")


# --- Audit log ---

@app.get("/api/audit")
@limiter.limit("15/minute")
async def get_audit(
    request: Request,
    limit: int = 100,
    action: Optional[str] = None,
    user: Dict = Depends(require_admin),
):
    """Get audit log entries."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return {"entries": get_audit_log(database, limit=limit, action_filter=action)}


# --- Backup restore workflow ---

class RestoreRequest(BaseModel):
    backup_file: str


@app.get("/api/backups/available")
@limiter.limit("10/minute")
async def list_available_backups(request: Request, user: Dict = Depends(require_admin)):
    """List all backup files available for restore."""
    if not backup_manager:
        raise HTTPException(status_code=503, detail="Backup manager not initialized")
    return {"backups": backup_manager.list_backups()}


@app.post("/api/restore")
@limiter.limit("1/minute")
async def restore_backup(
    request: Request,
    restore_req: RestoreRequest,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(require_admin),
):
    """
    Restore Immich database from a backup file.

    This will:
      1. Verify the backup file exists and checksum is valid
      2. Stop Immich containers
      3. Restore the database
      4. Restart Immich containers
    """
    if not backup_manager or not docker_monitor or not database:
        raise HTTPException(status_code=503, detail="Services not initialized")

    backup_path = Path(restore_req.backup_file)
    if not backup_path.exists():
        # Also check backup directory
        backup_path = Path(backup_manager.backup_dir) / restore_req.backup_file
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="Backup file not found")

    user_id = user.get("id", "unknown")
    record_audit(database, "restore_initiated", user_id=user_id,
                 details=f"file={backup_path}", ip_address=request.client.host)

    background_tasks.add_task(_restore_background, str(backup_path), user_id)

    return {
        "status": "started",
        "message": f"Restore from {backup_path.name} started in background",
    }


async def _restore_background(backup_file: str, user_id: str):
    """Run the full restore workflow in the background."""
    try:
        logger.info(f"Starting restore from {backup_file}")

        # Stop Immich
        if docker_monitor:
            docker_monitor.stop_immich()

        # Restore
        result = backup_manager.restore_database(backup_file)

        # Restart Immich
        if docker_monitor:
            docker_monitor.start_immich()

        if result["status"] == "success":
            logger.info("Restore completed successfully")
            record_audit(database, "restore_completed", user_id=user_id,
                         details=f"file={backup_file}")
            if alert_manager:
                await alert_manager.send_alert(
                    "Backup Restored",
                    f"Database restored from {Path(backup_file).name}",
                    "info",
                )
        else:
            logger.error(f"Restore failed: {result.get('error')}")
            record_audit(database, "restore_failed", user_id=user_id,
                         details=result.get("error", "unknown"))
            if alert_manager:
                await alert_manager.send_alert(
                    "Restore Failed",
                    f"Restore failed: {result.get('error')}",
                    "critical",
                )

    except Exception as e:
        logger.error(f"Restore error: {e}")
        if database:
            record_audit(database, "restore_failed", user_id=user_id, details=str(e))


# Add audit recording to key existing actions
_original_trigger_backup = trigger_backup


@app.post("/api/backup/now", response_model=None)
@limiter.limit("2/minute")
async def trigger_backup_audited(request: Request, background_tasks: BackgroundTasks, user: Dict = Depends(require_admin)):
    """Trigger immediate backup (with audit logging)."""
    if not backup_manager:
        raise HTTPException(status_code=503, detail="Backup manager not initialized")
    if database:
        record_audit(database, "backup_triggered", user_id=user.get("id"),
                     ip_address=request.client.host)
    background_tasks.add_task(backup_job)
    return {"status": "started", "message": "Backup started in background"}


class RoleUpdate(BaseModel):
    role: str  # "admin", "user", or "guest"


@app.get("/api/auth/check")
@limiter.limit("30/minute")
async def check_auth(request: Request, user: Dict = Depends(require_admin)):
    """Check authentication and return role info."""
    local = user.get("_local_user", {})
    return {
        "authenticated": True,
        "user": {"id": user.get("id"), "email": user.get("email"), "name": user.get("name")},
        "role": local.get("role", "user"),
    }


@app.get("/api/admin/users")
@limiter.limit("15/minute")
async def list_users(request: Request, user: Dict = Depends(require_admin)):
    """List all local users with roles."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return {"users": get_all_users(database)}


@app.put("/api/admin/users/{user_id}/role")
@limiter.limit("10/minute")
async def change_user_role(
    request: Request,
    user_id: int,
    body: RoleUpdate,
    user: Dict = Depends(require_admin),
):
    """Change a user's role (admin only)."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    try:
        success = update_user_role(database, user_id, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not success:
        raise HTTPException(status_code=400, detail="Cannot remove the last admin")
    record_audit(
        database, "role_changed",
        user_id=user.get("id"),
        details=f"target_user_id={user_id} new_role={body.role}",
        ip_address=request.client.host if request.client else None,
    )
    return {"status": "updated"}


# --- Auto-updater endpoints ---

@app.get("/api/snapshots")
@limiter.limit("15/minute")
async def list_snapshots(request: Request, user: Dict = Depends(require_admin)):
    """List pre-update snapshots available for rollback."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return {"snapshots": database.get_snapshots()}


@app.post("/api/snapshots")
@limiter.limit("2/hour")
async def create_snapshot(
    request: Request,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(require_admin),
):
    """Create a manual snapshot of the current Immich DB and compose files."""
    if not auto_updater:
        raise HTTPException(status_code=503, detail="Auto-updater not enabled in config")
    if database:
        record_audit(database, "snapshot_triggered", user_id=user.get("id"),
                     ip_address=request.client.host if request.client else None)

    async def _run():
        result = auto_updater.take_snapshot(trigger="manual")
        logger.info(f"Manual snapshot result: {result}")

    background_tasks.add_task(_run)
    return {"status": "started", "message": "Snapshot creation started in background"}


@app.post("/api/snapshots/{snapshot_id}/rollback")
@limiter.limit("1/hour")
async def rollback_snapshot(
    request: Request,
    snapshot_id: int,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(require_admin),
):
    """Roll back Immich to a previous snapshot."""
    if not auto_updater or not database:
        raise HTTPException(status_code=503, detail="Auto-updater not enabled in config")

    snapshots = database.get_snapshots()
    if not any(s["id"] == snapshot_id for s in snapshots):
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")

    record_audit(database, "rollback_initiated", user_id=user.get("id"),
                 details=f"snapshot_id={snapshot_id}",
                 ip_address=request.client.host if request.client else None)

    async def _run():
        result = auto_updater.rollback_to_snapshot(snapshot_id)
        logger.info(f"Rollback to snapshot {snapshot_id}: {result}")
        if alert_manager:
            if result["status"] == "success":
                await alert_manager.send_alert(
                    "Rollback Completed",
                    f"Immich rolled back to v{result.get('version_restored')} (snapshot {snapshot_id})",
                    "info",
                )
            else:
                await alert_manager.send_alert(
                    "Rollback Failed",
                    f"Rollback to snapshot {snapshot_id} failed: {result.get('errors')}",
                    "critical",
                )

    background_tasks.add_task(_run)
    return {"status": "started", "message": f"Rollback to snapshot {snapshot_id} started in background"}


@app.get("/api/updates/history")
@limiter.limit("15/minute")
async def get_update_history(request: Request, user: Dict = Depends(require_admin)):
    """Get Immich update history."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return {"history": database.get_update_history()}


@app.post("/api/updates/apply")
@limiter.limit("1/hour")
async def apply_update(
    request: Request,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(require_admin),
):
    """
    Manually trigger an update to the latest available Immich version.
    Takes a snapshot first; rolls back automatically on health-check failure.
    """
    if not auto_updater or not update_checker:
        raise HTTPException(status_code=503, detail="Auto-updater not enabled in config")

    latest = update_checker.get_latest_github_version()
    if not latest:
        raise HTTPException(status_code=503, detail="Could not fetch latest Immich version from GitHub")

    running = update_checker.get_running_version()
    if running == latest:
        return {"status": "up_to_date", "version": running}

    record_audit(database, "update_triggered", user_id=user.get("id"),
                 details=f"target_version={latest}",
                 ip_address=request.client.host if request.client else None)

    async def _run():
        result = auto_updater.apply_update(latest)
        logger.info(f"Manual update result: {result}")
        if alert_manager:
            if result["status"] == "success":
                await alert_manager.send_alert(
                    "Immich Updated",
                    f"Immich updated from v{result['from_version']} to v{result['to_version']}",
                    "info",
                )
            else:
                msg = f"Immich update to v{latest} failed: {result.get('error')}"
                if result.get("rolled_back"):
                    msg += " (automatically rolled back)"
                await alert_manager.send_alert("Immich Update Failed", msg, "critical")

    background_tasks.add_task(_run)
    return {
        "status": "started",
        "message": f"Update to v{latest} started in background (snapshot will be taken first)",
        "target_version": latest,
    }


def main():
    """Run the server"""
    try:
        config = load_config()

        uvicorn.run(
            "src.main:app",
            host=config.server.host,
            port=config.server.port,
            workers=config.server.workers,
            log_level=config.server.log_level.lower(),
            reload=False
        )
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Please create config/config.yaml from config.yaml.example")
        exit(1)
    except Exception as e:
        print(f"Error starting server: {e}")
        exit(1)


if __name__ == "__main__":
    main()
