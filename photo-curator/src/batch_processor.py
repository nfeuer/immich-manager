"""
Batch photo processor with throttling, GPU support, and progress tracking.
Processes all user photos in configurable batches with inter-batch delays,
CPU threshold pausing, consecutive-failure failsafe, and detailed logging.
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from typing import Any, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    ok: int = 0
    failed: int = 0


class BatchProcessor:
    """
    Processes photos in throttled batches with progress tracking.
    Integrates with APScheduler for scheduled runs and exposes
    async methods for manual API-triggered runs.
    """

    def __init__(self, database, immich_client, analyzer, config: Dict[str, Any]):
        """
        Args:
            database: Database instance (sync sqlite3 wrapper)
            immich_client: ImmichClient with admin API key
            analyzer: PhotoAnalyzer instance (already GPU-initialized)
            config: The full batch_processing config section
        """
        self._db = database
        self._immich = immich_client
        self._analyzer = analyzer
        self._config = config
        self._current_task: Optional[asyncio.Task] = None
        self._current_job_id: Optional[str] = None

    # =========================================================================
    # Public API
    # =========================================================================

    async def start_job(self, mode: str, user_id: Optional[str] = None) -> str:
        """
        Start a new batch processing job.

        Args:
            mode: 'incremental' | 'missing_vectors' | 'full' | 'retry_errors'
            user_id: Optional user to restrict processing to. None = all users.

        Returns:
            job_id string.

        Raises:
            RuntimeError if a job is already running.
        """
        if self._current_task and not self._current_task.done():
            raise RuntimeError("A batch job is already running")

        job_id = str(uuid.uuid4())

        # Fetch photos eligible for processing (sync, run in thread)
        photos = await asyncio.to_thread(
            self._fetch_eligible_photos, mode, user_id
        )

        cadence = self._config.get("cadence", {})
        batch_size = cadence.get("batch_size", 25)
        total_batches = max(1, (len(photos) + batch_size - 1) // batch_size) if photos else 0

        # Create job record
        await asyncio.to_thread(
            self._create_job, job_id, mode, user_id, len(photos), total_batches
        )
        await asyncio.to_thread(
            self._log, job_id, 0,
            f"Job started: {mode} mode — {len(photos)} photos in {total_batches} batches",
            "info"
        )

        if not photos:
            await asyncio.to_thread(self._complete_job, job_id)
            await asyncio.to_thread(self._log, job_id, 0, "No eligible photos found — job complete", "info")
            return job_id

        # Launch background task
        self._current_job_id = job_id
        self._current_task = asyncio.create_task(
            self._run_batch_loop(job_id, photos)
        )

        return job_id

    async def cancel_job(self) -> bool:
        """
        Cancel the current running job.

        Returns True if a job was cancelled, False if nothing was running.
        """
        if not self._current_job_id:
            return False

        await asyncio.to_thread(
            self._set_job_status, self._current_job_id, "cancelled",
            "Cancelled by user request"
        )
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
        return True

    async def get_status(self) -> Dict[str, Any]:
        """Return current/latest job status + last 20 log entries."""

        def _fetch():
            with self._db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM batch_jobs ORDER BY started_at DESC LIMIT 1"
                )
                row = cursor.fetchone()
                if not row:
                    return {"status": "idle", "job": None, "logs": []}

                job = dict(row)

                cursor.execute(
                    """SELECT message, level, logged_at, batch_number
                       FROM batch_job_logs
                       WHERE job_id = ?
                       ORDER BY id DESC LIMIT 20""",
                    (job["id"],)
                )
                logs = [dict(r) for r in cursor.fetchall()]
                logs.reverse()

                return {"status": job["status"], "job": job, "logs": logs}

        return await asyncio.to_thread(_fetch)

    async def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the last N jobs (summary only)."""

        def _fetch():
            with self._db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT id, mode, status, total_photos, successful_photos,
                              failed_photos, started_at, completed_at, error_message
                       FROM batch_jobs
                       ORDER BY started_at DESC LIMIT ?""",
                    (limit,)
                )
                return [dict(r) for r in cursor.fetchall()]

        return await asyncio.to_thread(_fetch)

    async def get_errors(self, job_id: str) -> List[Dict[str, Any]]:
        """Return all per-photo errors for a given job."""

        def _fetch():
            with self._db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT asset_id, error_type, error_message,
                              batch_number, occurred_at
                       FROM batch_errors
                       WHERE job_id = ?
                       ORDER BY occurred_at ASC""",
                    (job_id,)
                )
                return [dict(r) for r in cursor.fetchall()]

        return await asyncio.to_thread(_fetch)

    async def run_scheduled(self):
        """
        Called by APScheduler every 5 minutes.
        Starts an incremental job only if within the configured time window
        and no job is currently running.
        """
        if not self._is_within_time_window():
            return
        if self._current_task and not self._current_task.done():
            return  # Already running

        mode = self._config.get("default_mode", "incremental")
        logger.info(f"Scheduled batch job starting ({mode} mode)")
        try:
            await self.start_job(mode=mode)
        except Exception as exc:
            logger.error(f"Scheduled batch job failed to start: {exc}")

    # =========================================================================
    # Internal: batch loop
    # =========================================================================

    async def _run_batch_loop(self, job_id: str, photos: List[Dict[str, Any]]):
        """Main processing loop. Runs as a background asyncio Task."""
        cadence = self._config.get("cadence", {})
        batch_size = cadence.get("batch_size", 25)
        delay = cadence.get("delay_between_batches", 5)
        max_cpu = cadence.get("max_cpu_percent", 80)

        errors_cfg = self._config.get("errors", {})
        max_fail_pct = errors_cfg.get("batch_failure_percent", 50)
        max_consec = errors_cfg.get("max_consecutive_failures", 3)

        consecutive_failures = 0
        total = len(photos)
        batches = [photos[i: i + batch_size] for i in range(0, total, batch_size)]
        total_batches = len(batches)

        try:
            for batch_num, batch in enumerate(batches, start=1):
                # Check for external cancellation
                current_status = await asyncio.to_thread(
                    self._get_job_status, job_id
                )
                if current_status in ("cancelled", "paused_error", "failed"):
                    return

                # Pause if CPU is over threshold
                await self._check_cpu_threshold(job_id, max_cpu)

                # Process the batch
                result = await self._process_batch(job_id, batch, batch_num)

                # Update progress counters
                await asyncio.to_thread(
                    self._update_progress, job_id, result.ok, result.failed, batch_num
                )

                # Evaluate failure rate for this batch
                fail_rate = (result.failed / len(batch)) * 100 if batch else 0
                if fail_rate >= max_fail_pct:
                    consecutive_failures += 1
                    await asyncio.to_thread(
                        self._log, job_id, batch_num,
                        f"Batch {batch_num}/{total_batches} failed "
                        f"({result.failed}/{len(batch)} errors, {fail_rate:.0f}%)",
                        "warning"
                    )
                    if consecutive_failures >= max_consec:
                        msg = (
                            f"Job paused: {consecutive_failures} consecutive batch failures. "
                            f"Review errors and restart with 'retry_errors' mode."
                        )
                        await asyncio.to_thread(
                            self._set_job_status, job_id, "paused_error", msg
                        )
                        await asyncio.to_thread(self._log, job_id, batch_num, msg, "error")
                        return
                else:
                    consecutive_failures = 0
                    await asyncio.to_thread(
                        self._log, job_id, batch_num,
                        f"Batch {batch_num}/{total_batches} — {result.ok} OK, {result.failed} failed",
                        "info"
                    )

                # Inter-batch delay (skip after last batch)
                if batch_num < total_batches:
                    await asyncio.sleep(delay)

            # All batches done
            await asyncio.to_thread(self._complete_job, job_id)
            await asyncio.to_thread(
                self._log, job_id, 0,
                f"Job completed — {total} photos processed", "info"
            )

        except asyncio.CancelledError:
            logger.info(f"Batch job {job_id} was cancelled")
            raise
        except Exception as exc:
            logger.error(f"Batch job {job_id} failed unexpectedly: {exc}")
            await asyncio.to_thread(self._fail_job, job_id, str(exc))
        finally:
            self._current_job_id = None

    async def _process_batch(
        self,
        job_id: str,
        batch: List[Dict[str, Any]],
        batch_num: int,
    ) -> BatchResult:
        """
        Process one batch. Each photo is wrapped in its own try/except so a
        single failure doesn't abort the rest of the batch.
        """
        result = BatchResult()

        for photo in batch:
            asset_id = photo.get("id", "unknown")
            user_id = photo.get("ownerId", "")
            year, month = self._parse_year_month(photo.get("fileCreatedAt", ""))

            tmp_path: Optional[str] = None
            try:
                # Download thumbnail for analysis
                tmp_path = await asyncio.to_thread(
                    self._immich.download_photo, asset_id, None, True
                )
                if not tmp_path:
                    raise ValueError("download_photo returned None")

                # Analyze (CPU/GPU-accelerated depending on device)
                scores = await asyncio.to_thread(
                    self._analyzer.analyze_photo, tmp_path
                )

                # Persist scores
                await asyncio.to_thread(
                    self._db.save_photo_score, asset_id, user_id, year, month, scores
                )
                result.ok += 1

            except Exception as exc:
                result.failed += 1
                error_type = type(exc).__name__
                await asyncio.to_thread(
                    self._record_error,
                    job_id, batch_num, asset_id, error_type, str(exc)
                )
                logger.debug(f"Photo {asset_id} failed: {error_type}: {exc}")

            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        return result

    async def _check_cpu_threshold(self, job_id: str, max_cpu: int):
        """
        Pause processing while CPU% is above threshold.
        Checks every 5 seconds and logs the first pause per threshold crossing.
        """
        logged = False
        while True:
            cpu_pct = psutil.cpu_percent(interval=1)
            if cpu_pct < max_cpu:
                break
            if not logged:
                await asyncio.to_thread(
                    self._log, job_id, 0,
                    f"CPU at {cpu_pct:.0f}% (threshold {max_cpu}%) — waiting...", "info"
                )
                logged = True
            await asyncio.sleep(5)

    # =========================================================================
    # Internal: photo selection by mode
    # =========================================================================

    def _fetch_eligible_photos(
        self,
        mode: str,
        user_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """
        Fetch the list of photos to process based on mode.
        Runs synchronously (called via asyncio.to_thread).
        """
        # Determine which users to fetch
        if user_id:
            users = [{"id": user_id}]
        else:
            try:
                users = self._immich.get_users()
            except Exception as exc:
                logger.error(f"Could not fetch users: {exc}")
                users = []

        # Collect all photos from Immich (last 10 years)
        current_year = datetime.now().year
        all_photos: List[Dict[str, Any]] = []
        for user in users:
            uid = user.get("id", "")
            for year in range(current_year - 10, current_year + 1):
                try:
                    photos = self._immich.get_photos_for_year(uid, year)
                    all_photos.extend(photos)
                except Exception as exc:
                    logger.warning(f"Could not fetch photos for user {uid} year {year}: {exc}")

        if mode == "full":
            return all_photos

        # Filter by mode using existing DB records
        with self._db._get_connection() as conn:
            cursor = conn.cursor()

            if mode == "incremental":
                cursor.execute("SELECT asset_id FROM photo_scores")
                scored = {row[0] for row in cursor.fetchall()}
                return [p for p in all_photos if p.get("id") not in scored]

            elif mode == "missing_vectors":
                cursor.execute(
                    """SELECT asset_id FROM photo_scores
                       WHERE blur_score IS NULL OR exposure_score IS NULL
                          OR composition_score IS NULL OR face_score IS NULL"""
                )
                needs_vectors = {row[0] for row in cursor.fetchall()}
                return [p for p in all_photos if p.get("id") in needs_vectors]

            elif mode == "retry_errors":
                # Retry assets that failed in the most recent failed/paused/cancelled job
                cursor.execute(
                    """SELECT DISTINCT asset_id FROM batch_errors
                       WHERE job_id = (
                           SELECT id FROM batch_jobs
                           WHERE status IN ('paused_error', 'failed', 'cancelled')
                           ORDER BY started_at DESC LIMIT 1
                       )"""
                )
                error_ids = {row[0] for row in cursor.fetchall()}
                return [p for p in all_photos if p.get("id") in error_ids]

        return all_photos

    # =========================================================================
    # Internal: time window
    # =========================================================================

    def _is_within_time_window(self) -> bool:
        """
        Check if the current local time falls within the configured schedule window.
        Supports overnight windows (e.g., 23:00 – 06:00).
        """
        schedule = self._config.get("schedule", {})
        if not schedule.get("enabled", False):
            return False

        start_str = schedule.get("time_window_start", "23:00")
        end_str = schedule.get("time_window_end", "06:00")

        try:
            sh, sm = map(int, start_str.split(":"))
            eh, em = map(int, end_str.split(":"))
        except ValueError:
            logger.warning(f"Invalid time window format: {start_str} – {end_str}")
            return False

        start = dtime(sh, sm)
        end = dtime(eh, em)
        now = datetime.now().time()

        if start <= end:
            return start <= now <= end
        # Overnight window
        return now >= start or now <= end

    # =========================================================================
    # Internal: DB helpers (sync, used via asyncio.to_thread)
    # =========================================================================

    @staticmethod
    def _parse_year_month(created_at: str):
        """Parse year and month from ISO 8601 timestamp string."""
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            return dt.year, dt.month
        except Exception:
            now = datetime.now()
            return now.year, now.month

    def _create_job(
        self,
        job_id: str,
        mode: str,
        user_id: Optional[str],
        total_photos: int,
        total_batches: int,
    ):
        with self._db._get_connection() as conn:
            conn.execute(
                """INSERT INTO batch_jobs
                       (id, user_id, mode, status, total_photos, total_batches)
                   VALUES (?, ?, ?, 'running', ?, ?)""",
                (job_id, user_id, mode, total_photos, total_batches),
            )

    def _log(self, job_id: str, batch_num: int, message: str, level: str = "info"):
        with self._db._get_connection() as conn:
            conn.execute(
                """INSERT INTO batch_job_logs (job_id, batch_number, message, level)
                   VALUES (?, ?, ?, ?)""",
                (job_id, batch_num, message, level),
            )

    def _update_progress(
        self, job_id: str, new_ok: int, new_failed: int, current_batch: int
    ):
        with self._db._get_connection() as conn:
            conn.execute(
                """UPDATE batch_jobs SET
                       processed_photos = processed_photos + ?,
                       successful_photos = successful_photos + ?,
                       failed_photos = failed_photos + ?,
                       current_batch = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (new_ok + new_failed, new_ok, new_failed, current_batch, job_id),
            )

    def _get_job_status(self, job_id: str) -> str:
        with self._db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM batch_jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            return row[0] if row else "unknown"

    def _set_job_status(self, job_id: str, status: str, message: Optional[str] = None):
        with self._db._get_connection() as conn:
            conn.execute(
                """UPDATE batch_jobs SET
                       status = ?,
                       error_message = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (status, message, job_id),
            )

    def _complete_job(self, job_id: str):
        with self._db._get_connection() as conn:
            conn.execute(
                """UPDATE batch_jobs SET
                       status = 'completed',
                       completed_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (job_id,),
            )

    def _fail_job(self, job_id: str, error: str):
        with self._db._get_connection() as conn:
            conn.execute(
                """UPDATE batch_jobs SET
                       status = 'failed',
                       error_message = ?,
                       completed_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (error, job_id),
            )

    def _pause_job(self, job_id: str, message: str):
        """Alias for _set_job_status with paused_error status."""
        self._set_job_status(job_id, "paused_error", message)

    def _record_error(
        self,
        job_id: str,
        batch_num: int,
        asset_id: str,
        error_type: str,
        error_message: str,
    ):
        with self._db._get_connection() as conn:
            conn.execute(
                """INSERT INTO batch_errors
                       (job_id, batch_number, asset_id, error_type, error_message)
                   VALUES (?, ?, ?, ?, ?)""",
                (job_id, batch_num, asset_id, error_type, error_message),
            )
