"""
Main FastAPI application for Immich Server Manager
"""

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

from .config import load_config, Config
from .database import Database
from .monitoring import DiskMonitor, SystemMonitor, DockerMonitor
from .backup import BackupManager
from .alerts import AlertManager
from .update_checker import UpdateChecker
from .prometheus import generate_metrics
from .audit import ensure_audit_table, record_audit, get_audit_log
from .logging_config import setup_json_logging

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
async def csrf_protection(request: Request, call_next):
    """Block cross-origin state-changing requests (CSRF protection).
    Safe methods (GET, HEAD, OPTIONS) and Bearer-token requests are exempt."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        # Bearer token requests are not vulnerable to CSRF
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            origin = request.headers.get("Origin") or request.headers.get("Referer", "")
            allowed = _get_allowed_origins()
            if origin and not any(origin.startswith(o) for o in allowed):
                logger.warning("CSRF blocked: origin=%s not in %s", origin, allowed)
                return JSONResponse(status_code=403, content={"detail": "Cross-origin request blocked"})
    return await call_next(request)


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
    Dependency that validates the request against Immich's auth system.
    Accepts either:
      - Cookie: immich_access_token
      - Header: Authorization: Bearer <token>
    """
    access_token = request.cookies.get("immich_access_token")
    if not access_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            access_token = auth_header[7:]

    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Validate with Immich
    immich_api_url = getattr(request.app.state, "immich_api_url", None)
    if not immich_api_url:
        raise HTTPException(status_code=503, detail="Immich API URL not configured")

    try:
        resp = http_requests.get(
            f"{immich_api_url}/auth/validateToken",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=5,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        user_resp = http_requests.get(
            f"{immich_api_url}/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=5,
        )
        if user_resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Could not fetch user info")

        return user_resp.json()

    except http_requests.RequestException as e:
        logger.error(f"Auth validation error: {e}")
        raise HTTPException(status_code=502, detail="Could not reach Immich for auth validation")

# Global state
config: Optional[Config] = None
database: Optional[Database] = None
disk_monitor: Optional[DiskMonitor] = None
system_monitor: Optional[SystemMonitor] = None
docker_monitor: Optional[DockerMonitor] = None
backup_manager: Optional[BackupManager] = None
alert_manager: Optional[AlertManager] = None
update_checker: Optional[UpdateChecker] = None
scheduler: Optional[AsyncIOScheduler] = None


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    global config, database, disk_monitor, system_monitor, docker_monitor
    global backup_manager, alert_manager, update_checker, scheduler

    try:
        # Load configuration
        config = load_config()

        # Initialize database
        database = Database()
        ensure_audit_table(database)

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

        # Store Immich API URL for auth validation
        app.state.immich_api_url = config.immich.api_url

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

        # Check for Immich updates (daily at 10 AM)
        scheduler.add_job(
            check_immich_update_job,
            'cron',
            hour=10,
            id='immich_update_check'
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


async def check_immich_update_job():
    """Background job to check for Immich updates on GitHub"""
    if not update_checker or not alert_manager or not database:
        return

    try:
        update_info = update_checker.check_for_update()
        if update_info:
            msg = (
                f"Immich v{update_info['latest_version']} is available "
                f"(currently running v{update_info['running_version']}).\n"
                f"Release notes: {update_info['release_url']}"
            )
            await alert_manager.send_alert(
                "Immich Update Available",
                msg,
                "info",
            )
            database.record_alert(
                "info",
                "immich_update",
                msg,
            )
            print(f"Immich update available: v{update_info['latest_version']}")
    except Exception as e:
        print(f"Error checking Immich updates: {e}")


# API Endpoints
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve dashboard HTML"""
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
async def get_status(request: Request, user: Dict = Depends(require_auth)):
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
async def get_disk_health(request: Request, user: Dict = Depends(require_auth)):
    """Get current disk health"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return {
        "disks": database.get_latest_disk_health(),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/metrics")
@limiter.limit("30/minute")
async def get_metrics(request: Request, hours: int = 24, user: Dict = Depends(require_auth)):
    """Get system metrics for time range"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return {
        "metrics": database.get_system_metrics(hours),
        "hours": hours
    }


@app.get("/api/backups")
@limiter.limit("30/minute")
async def get_backups(request: Request, user: Dict = Depends(require_auth)):
    """Get backup history"""
    if not database or not backup_manager:
        raise HTTPException(status_code=503, detail="Services not initialized")

    return {
        "history": database.get_recent_backups(limit=20),
        "available": backup_manager.list_backups()
    }


@app.post("/api/backup/now")
@limiter.limit("2/minute")
async def trigger_backup(request: Request, background_tasks: BackgroundTasks, user: Dict = Depends(require_auth)):
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
async def get_alerts(request: Request, acknowledged: bool = False, user: Dict = Depends(require_auth)):
    """Get alerts"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return {
        "alerts": database.get_alerts(acknowledged=acknowledged)
    }


@app.post("/api/alerts/{alert_id}/acknowledge")
@limiter.limit("30/minute")
async def acknowledge_alert(request: Request, alert_id: int, user: Dict = Depends(require_auth)):
    """Acknowledge an alert"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    database.acknowledge_alert(alert_id)

    return {"status": "ok"}


@app.post("/api/test-alert")
@limiter.limit("3/minute")
async def test_alert(request: Request, user: Dict = Depends(require_auth)):
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
async def check_immich_update(request: Request, user: Dict = Depends(require_auth)):
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
async def prometheus_metrics(request: Request, user: Dict = Depends(require_auth)):
    """Prometheus-compatible metrics endpoint. Requires auth (Immich token or Bearer)."""
    body = generate_metrics(system_monitor, docker_monitor, disk_monitor, database)
    return PlainTextResponse(body, media_type="text/plain; version=0.0.4; charset=utf-8")


# --- Audit log ---

@app.get("/api/audit")
@limiter.limit("15/minute")
async def get_audit(
    request: Request,
    limit: int = 100,
    action: Optional[str] = None,
    user: Dict = Depends(require_auth),
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
async def list_available_backups(request: Request, user: Dict = Depends(require_auth)):
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
    user: Dict = Depends(require_auth),
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
async def trigger_backup_audited(request: Request, background_tasks: BackgroundTasks, user: Dict = Depends(require_auth)):
    """Trigger immediate backup (with audit logging)."""
    if not backup_manager:
        raise HTTPException(status_code=503, detail="Backup manager not initialized")
    if database:
        record_audit(database, "backup_triggered", user_id=user.get("id"),
                     ip_address=request.client.host)
    background_tasks.add_task(backup_job)
    return {"status": "started", "message": "Backup started in background"}


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
