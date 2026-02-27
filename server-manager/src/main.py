"""
Main FastAPI application for Immich Server Manager
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import uvicorn
import asyncio
import requests as http_requests
import logging

from .config import load_config, Config
from .database import Database
from .monitoring import DiskMonitor, SystemMonitor, DockerMonitor
from .backup import BackupManager
from .alerts import AlertManager

logger = logging.getLogger(__name__)


app = FastAPI(
    title="Immich Server Manager",
    description="Monitoring, backups, and management for Immich installations",
    version="1.0.0"
)


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
scheduler: Optional[AsyncIOScheduler] = None


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    global config, database, disk_monitor, system_monitor, docker_monitor
    global backup_manager, alert_manager, scheduler

    try:
        # Load configuration
        config = load_config()

        # Initialize database
        database = Database()

        # Initialize monitors
        all_drives = config.storage.data_drives + config.storage.parity_drives
        disk_monitor = DiskMonitor(all_drives) if all_drives else DiskMonitor([])
        system_monitor = SystemMonitor()
        docker_monitor = DockerMonitor()

        # Initialize backup manager
        backup_manager = BackupManager(config.backup)

        # Initialize alert manager
        alert_manager = AlertManager(config.alerts)

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

        scheduler.start()

        print("✓ Immich Server Manager started successfully")
        print(f"✓ Dashboard: http://{config.server.host}:{config.server.port}")

    except FileNotFoundError as e:
        print(f"✗ Configuration error: {e}")
        raise
    except Exception as e:
        print(f"✗ Startup error: {e}")
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
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/status")
async def get_status(user: Dict = Depends(require_auth)):
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
async def get_disk_health(user: Dict = Depends(require_auth)):
    """Get current disk health"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return {
        "disks": database.get_latest_disk_health(),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/metrics")
async def get_metrics(hours: int = 24, user: Dict = Depends(require_auth)):
    """Get system metrics for time range"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return {
        "metrics": database.get_system_metrics(hours),
        "hours": hours
    }


@app.get("/api/backups")
async def get_backups(user: Dict = Depends(require_auth)):
    """Get backup history"""
    if not database or not backup_manager:
        raise HTTPException(status_code=503, detail="Services not initialized")

    return {
        "history": database.get_recent_backups(limit=20),
        "available": backup_manager.list_backups()
    }


@app.post("/api/backup/now")
async def trigger_backup(background_tasks: BackgroundTasks, user: Dict = Depends(require_auth)):
    """Trigger immediate backup"""
    if not backup_manager:
        raise HTTPException(status_code=503, detail="Backup manager not initialized")

    background_tasks.add_task(backup_job)

    return {
        "status": "started",
        "message": "Backup started in background"
    }


@app.get("/api/alerts")
async def get_alerts(acknowledged: bool = False, user: Dict = Depends(require_auth)):
    """Get alerts"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return {
        "alerts": database.get_alerts(acknowledged=acknowledged)
    }


@app.post("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int, user: Dict = Depends(require_auth)):
    """Acknowledge an alert"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    database.acknowledge_alert(alert_id)

    return {"status": "ok"}


@app.post("/api/test-alert")
async def test_alert(user: Dict = Depends(require_auth)):
    """Send test alert"""
    if not alert_manager:
        raise HTTPException(status_code=503, detail="Alert manager not initialized")

    await alert_manager.send_alert(
        "Test Alert",
        "This is a test alert from Immich Server Manager",
        "info"
    )

    return {"status": "sent"}


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
