"""
Main FastAPI application for Immich Server Manager
"""

import os
import sys
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import json
import uvicorn
import asyncio
import subprocess
import requests as http_requests
import logging
import sdnotify

# Add project root to path for shared library
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from .config import load_config, save_config, Config, DiscordConfig, DigestConfig, QuietHoursConfig
from .database import Database
from .monitoring import DiskMonitor, SystemMonitor, DockerMonitor
from .backup import BackupManager
from .alerts import AlertManager
from .update_checker import UpdateChecker
from .auto_updater import AutoUpdater
from .digest import build_digest
from .prometheus import generate_metrics
from .audit import ensure_audit_table, record_audit, get_audit_log
from .logging_config import setup_json_logging
from .logs import get_log_snapshot, stream_log_lines
from .utils import CLEAN_ENV
from .ip_gate_middleware import IPGateMiddleware
from .ip_gate_routes import ip_gate_router
from shared.auth.ip_gate import ensure_ip_gate_tables as ensure_ip_gate_db
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
app.include_router(ip_gate_router)


# --- Authentication ---

def _get_allowed_origins() -> List[str]:
    """Build allowed origins from config at startup."""
    try:
        cfg, _ = load_config()
        immich_url = cfg.immich.api_url.rsplit("/api", 1)[0]
        origins = [
            f"http://localhost:{cfg.server.port}",
            f"http://127.0.0.1:{cfg.server.port}",
            immich_url,
        ]
        if cfg.server.public_url:
            origins.append(cfg.server.public_url.rstrip("/"))
        return origins
    except Exception:
        return ["http://localhost:8080", "http://127.0.0.1:8080"]


_ALLOWED_ORIGINS: List[str] = _get_allowed_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
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
            allowed = _ALLOWED_ORIGINS
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


app.add_middleware(IPGateMiddleware)


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
config_path: Optional[str] = None
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
    global config, config_path, database, disk_monitor, system_monitor, docker_monitor
    global backup_manager, alert_manager, update_checker, auto_updater, scheduler

    try:
        # Load configuration
        config, config_path = load_config()

        # Initialize database
        database = Database()
        ensure_audit_table(database)
        ensure_users_table(database)

        # Initialize IP gate
        ensure_ip_gate_db(database)
        app.state.ip_gate_db = database
        app.state.ip_gate_config = config.ip_gate
        app.state.public_url = config.server.public_url

        # Initialize monitors
        all_drives = config.storage.data_drives + config.storage.parity_drives
        disk_monitor = DiskMonitor(all_drives) if all_drives else DiskMonitor([])
        system_monitor = SystemMonitor()
        docker_monitor = DockerMonitor()

        # Initialize backup manager
        backup_manager = BackupManager(config.backup)

        # Initialize alert manager
        alert_manager = AlertManager(config.alerts)
        app.state.alert_manager = alert_manager

        # Initialize update checker
        update_checker = UpdateChecker(docker_monitor, immich_api_url=config.immich.api_url)

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

        # Store Immich API URL and key for auth validation
        app.state.immich_api_url = config.immich.api_url
        app.state.immich_api_key = config.immich.api_key
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

        # Scheduled Discord digest
        if config.alerts.digest.enabled:
            digest_trigger = CronTrigger.from_crontab(config.alerts.digest.schedule)
            scheduler.add_job(
                digest_job,
                digest_trigger,
                id='discord_digest'
            )

        # Watchdog heartbeat (every 30s, half of WatchdogSec=60)
        async def _watchdog_heartbeat():
            sd = sdnotify.SystemdNotifier(debug=False)
            sd.notify("WATCHDOG=1")

        scheduler.add_job(_watchdog_heartbeat, "interval", seconds=30, id="watchdog")

        # Schedule IP gate expiry checks (every 5 minutes)
        scheduler.add_job(
            _expire_ips_job,
            'interval',
            seconds=300,
            id='ip_gate_expiry'
        )

        # Schedule Cloudflare sync if enabled
        if config.ip_gate.cloudflare.enabled:
            from .ip_gate_cloudflare import CloudflareIPSync
            cf_sync = CloudflareIPSync(
                api_token=config.ip_gate.cloudflare.api_token,
                account_id=config.ip_gate.cloudflare.account_id,
                list_name=config.ip_gate.cloudflare.list_name,
            )
            app.state.cloudflare_sync = cf_sync
            scheduler.add_job(
                _cloudflare_sync_job,
                'interval',
                hours=config.ip_gate.cloudflare.reconciliation_interval_hours,
                id='cloudflare_sync'
            )

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
async def _expire_ips_job():
    """Expire trusted IPs that have passed their expiry time."""
    if not database:
        return
    from shared.auth.ip_gate import expire_stale_ips
    count = expire_stale_ips(database)
    if count > 0:
        logger.info("Expired %d stale trusted IPs", count)


async def _cloudflare_sync_job():
    """Reconcile Cloudflare IP list with local trusted admin IPs."""
    if not database:
        return
    cf_sync = getattr(app.state, "cloudflare_sync", None)
    if not cf_sync:
        return
    from shared.auth.ip_gate import list_ips_by_status
    admin_ips = [
        ip["ip_address"] for ip in list_ips_by_status(database, "trusted")
        if ip.get("access_level") == "admin"
    ]
    success = cf_sync.sync(admin_ips)
    if not success and alert_manager:
        alert_manager.send_discord(
            "Cloudflare Sync Failed",
            "Failed to reconcile Cloudflare IP list. Check logs for details.",
            "warning",
        )


async def check_disk_health_job():
    """Background job to check disk health"""
    if not disk_monitor or not database or not alert_manager or not config:
        return

    try:
        disks = await asyncio.to_thread(disk_monitor.check_all_disks)

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
                await alert_manager.send_disk_health_alert(disk)
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
        metrics = await asyncio.to_thread(system_monitor.get_all_metrics)
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
        result = await asyncio.to_thread(backup_manager.run_full_backup)

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
        await alert_manager.send_backup_alert(result['database'])

        if result['status'] == 'failed':
            print(f"Backup completed: failed — {result.get('database', {}).get('error', 'unknown error')}")
        else:
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


async def digest_job():
    """Background job to send scheduled Discord digest."""
    if not alert_manager or not database or not system_monitor or not config:
        return

    try:
        title, description, fields, color = await build_digest(
            database=database,
            system_monitor=system_monitor,
            disk_monitor=disk_monitor,
            docker_monitor=docker_monitor,
            config=config,
            sections=config.alerts.digest.sections,
        )
        success = alert_manager.send_discord_digest(title, description, fields, color)
        if success:
            logger.info("Discord digest sent successfully")
        else:
            logger.warning("Discord digest failed to send")
    except Exception as e:
        logger.error(f"Error in digest job: {e}")


# API Endpoints
@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user: Dict = Depends(require_admin)):
    """Serve React dashboard (admin only)"""
    index_path = Path(__file__).parent.parent / "frontend" / "dist" / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=503, detail="Dashboard not built. Run: cd frontend && npm run build")
    return index_path.read_text()


@app.get("/ip-challenge", response_class=HTMLResponse)
async def ip_challenge_page(request: Request):
    """Serve the IP challenge page (no auth required)."""
    index_path = Path(__file__).parent.parent / "frontend" / "dist" / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=503, detail="Dashboard not built. Run: cd frontend && npm run build")
    return index_path.read_text()


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


@app.post("/api/digest/trigger")
@limiter.limit("3/minute")
async def trigger_digest(request: Request, user: Dict = Depends(require_admin)):
    """Manually trigger a Discord digest."""
    if not alert_manager or not database or not system_monitor:
        raise HTTPException(status_code=503, detail="Required services not initialized")

    sections = (
        config.alerts.digest.sections
        if config
        else ["system", "backups", "containers", "alerts"]
    )
    title, description, fields, color = await build_digest(
        database=database,
        system_monitor=system_monitor,
        disk_monitor=disk_monitor,
        docker_monitor=docker_monitor,
        config=config,
        sections=sections,
    )
    success = alert_manager.send_discord_digest(title, description, fields, color)

    if not success:
        raise HTTPException(status_code=502, detail="Failed to send digest to Discord")

    return {"status": "sent"}


# --- Discord config management ---

class DiscordConfigUpdate(BaseModel):
    """Request body for updating Discord-related configuration."""
    discord: Optional[Dict[str, Any]] = None
    digest: Optional[Dict[str, Any]] = None
    quiet_hours: Optional[Dict[str, Any]] = None


@app.get("/api/config/discord")
@limiter.limit("10/minute")
async def get_discord_config(request: Request, user: Dict = Depends(require_admin)):
    """Return current Discord, digest, and quiet-hours configuration."""
    if not config:
        raise HTTPException(status_code=503, detail="Configuration not loaded")

    return {
        "discord": config.alerts.discord.model_dump(),
        "digest": config.alerts.digest.model_dump(),
        "quiet_hours": config.alerts.quiet_hours.model_dump(),
    }


@app.put("/api/config/discord")
@limiter.limit("10/minute")
async def update_discord_config(
    request: Request,
    body: DiscordConfigUpdate,
    user: Dict = Depends(require_admin),
):
    """Update Discord, digest, and/or quiet-hours configuration and persist to disk."""
    if not config or not config_path:
        raise HTTPException(status_code=503, detail="Configuration not loaded")

    old_digest_schedule = config.alerts.digest.schedule
    old_digest_enabled = config.alerts.digest.enabled

    # Apply updates to in-memory config
    if body.discord is not None:
        config.alerts.discord = DiscordConfig(**{
            **config.alerts.discord.model_dump(),
            **body.discord,
        })
    if body.digest is not None:
        config.alerts.digest = DigestConfig(**{
            **config.alerts.digest.model_dump(),
            **body.digest,
        })
    if body.quiet_hours is not None:
        config.alerts.quiet_hours = QuietHoursConfig(**{
            **config.alerts.quiet_hours.model_dump(),
            **body.quiet_hours,
        })

    # Keep alert_manager in sync (it holds a reference to config.alerts)
    if alert_manager:
        alert_manager.config = config.alerts

    # Reschedule digest job if schedule or enabled state changed
    if scheduler:
        new_schedule = config.alerts.digest.schedule
        new_enabled = config.alerts.digest.enabled

        if old_digest_enabled and (not new_enabled or new_schedule != old_digest_schedule):
            try:
                scheduler.remove_job('discord_digest')
            except Exception:
                pass

        if new_enabled and (not old_digest_enabled or new_schedule != old_digest_schedule):
            try:
                scheduler.remove_job('discord_digest')
            except Exception:
                pass
            scheduler.add_job(
                digest_job,
                CronTrigger.from_crontab(new_schedule),
                id='discord_digest',
            )

    # Persist to YAML
    save_config(config, config_path)

    if database:
        record_audit(
            database, "config_updated",
            user_id=user.get("id"),
            details="Discord/digest/quiet-hours config updated via UI",
            ip_address=request.client.host if request.client else None,
        )

    return {
        "discord": config.alerts.discord.model_dump(),
        "digest": config.alerts.digest.model_dump(),
        "quiet_hours": config.alerts.quiet_hours.model_dump(),
    }


@app.get("/api/immich-update")
@limiter.limit("5/minute")
async def check_immich_update(request: Request, user: Dict = Depends(require_admin)):
    """Legacy diagnostic endpoint. Uses Docker image tag fallback only (not Immich API).
    Not used by the frontend update flow — see /api/updates/status instead."""
    if not update_checker:
        raise HTTPException(status_code=503, detail="Update checker not initialized")

    loop = asyncio.get_running_loop()
    running, latest = await asyncio.gather(
        loop.run_in_executor(None, update_checker.get_running_version),
        loop.run_in_executor(None, update_checker.get_latest_github_version),
    )

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
    With auto_updater enabled: takes a snapshot first and rolls back on failure.
    Without auto_updater: runs docker compose pull && up -d directly.
    """
    if not update_checker:
        raise HTTPException(status_code=503, detail="Update checker not initialized")

    loop = asyncio.get_running_loop()
    running, latest = await asyncio.gather(
        loop.run_in_executor(None, update_checker.get_running_version),
        loop.run_in_executor(None, update_checker.get_latest_github_version),
    )

    if not latest:
        raise HTTPException(status_code=503, detail="Could not fetch latest Immich version from GitHub")

    if running == latest:
        return {"status": "up_to_date", "version": running}

    record_audit(database, "update_triggered", user_id=user.get("id"),
                 details=f"target_version={latest}",
                 ip_address=request.client.host if request.client else None)

    def _emit(step: str, message: str) -> None:
        _update_progress.append(json.dumps({"step": step, "message": message}))

    if auto_updater:
        # Full update with snapshot + auto-rollback
        async def _run_with_snapshot():
            global _update_progress, _update_in_progress
            _update_progress = []
            _update_in_progress = True

            _emit("snapshot", "Creating pre-update snapshot...")
            result = await asyncio.get_running_loop().run_in_executor(
                None, auto_updater.apply_update, latest
            )
            logger.info(f"Manual update result: {result}")

            if result["status"] == "success":
                _emit("done", f"Updated to v{result['to_version']} successfully")
            else:
                if result.get("rolled_back"):
                    _emit("rolled_back", f"Update failed and was rolled back: {result.get('error')}")
                else:
                    _emit("error", f"Update failed: {result.get('error')}")

            _update_in_progress = False

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

        background_tasks.add_task(_run_with_snapshot)
        return {
            "status": "started",
            "message": f"Update to v{latest} started in background (snapshot will be taken first)",
            "target_version": latest,
        }

    else:
        # Simple update: docker compose pull && up -d (no snapshot)
        if not config:
            raise HTTPException(status_code=503, detail="Config not initialized")
        compose_path = Path(config.immich.docker_compose_path)

        async def _run_simple():
            global _update_progress, _update_in_progress
            _update_progress = []
            _update_in_progress = True
            loop = asyncio.get_running_loop()

            _emit("pull", f"Pulling latest Immich images (v{latest})...")
            try:
                await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        ["docker", "compose", "pull"],
                        cwd=str(compose_path), check=True,
                        capture_output=True, timeout=300, env=CLEAN_ENV,
                    )
                )
            except Exception as e:
                _emit("error", f"docker compose pull failed: {e}")
                _update_in_progress = False
                return

            _emit("restart", "Restarting containers with new images...")
            try:
                await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        ["docker", "compose", "up", "-d", "--remove-orphans"],
                        cwd=str(compose_path), check=True,
                        capture_output=True, timeout=120, env=CLEAN_ENV,
                    )
                )
            except Exception as e:
                _emit("error", f"docker compose up failed: {e}")
                _update_in_progress = False
                return

            _emit("done", f"Update to v{latest} applied successfully")
            _update_in_progress = False

            if alert_manager:
                await alert_manager.send_alert(
                    "Immich Updated",
                    f"Immich updated to v{latest} via docker compose pull",
                    "info",
                )

        background_tasks.add_task(_run_simple)
        return {
            "status": "started",
            "message": f"Update to v{latest} started in background",
            "target_version": latest,
        }


# --- Valid service identifiers ---
_VALID_SERVICES = {
    "immich_server", "immich_machine_learning", "immich_postgres", "immich_redis",
    "server_manager", "photo_curator", "system",
}

_DOCKER_SERVICES = {"immich_server", "immich_machine_learning", "immich_postgres", "immich_redis"}
_SYSTEMD_SERVICES = {"server_manager": "immich-server-manager", "photo_curator": "photo-curator"}


# --- Log endpoints ---

@app.get("/api/logs/{service}")
@limiter.limit("30/minute")
async def get_logs_snapshot(request: Request, service: str, lines: int = 200, user: Dict = Depends(require_admin)):
    """Get a log snapshot for a service."""
    if service not in _VALID_SERVICES:
        raise HTTPException(status_code=422, detail=f"Unknown service: {service}")
    return {"lines": get_log_snapshot(service, lines=lines)}


@app.get("/api/logs/{service}/stream")
async def stream_logs(request: Request, service: str, user: Dict = Depends(require_admin)):
    """Stream live log lines for a service via SSE."""
    if service not in _VALID_SERVICES:
        raise HTTPException(status_code=422, detail=f"Unknown service: {service}")

    async def event_generator():
        loop = asyncio.get_running_loop()
        gen = stream_log_lines(service)
        while True:
            if await request.is_disconnected():
                break
            try:
                line = await loop.run_in_executor(None, next, gen)
                yield {"data": line}
            except StopIteration:
                break
            except Exception as exc:
                logger.warning("Log stream error for %s: %s", service, exc)
                break

    return EventSourceResponse(event_generator())


# --- Service restart endpoints ---

@app.post("/api/services/{service}/restart")
@limiter.limit("10/minute")
async def restart_service(request: Request, service: str, user: Dict = Depends(require_admin)):
    """Restart a single service or container."""
    if service not in _VALID_SERVICES or service == "system":
        raise HTTPException(status_code=422, detail=f"Cannot restart service: {service}")

    user_id = user.get("id", "unknown")
    ip = request.client.host if request.client else None

    try:
        if service in _DOCKER_SERVICES:
            import docker as docker_sdk
            client = docker_sdk.from_env()
            name_filter = service.replace("_", "-")
            matches = client.containers.list(filters={"name": name_filter})
            if not matches:
                raise HTTPException(status_code=404, detail=f"Container for {service} not found")
            matches[0].restart()
        elif service in _SYSTEMD_SERVICES:
            unit = _SYSTEMD_SERVICES[service]
            subprocess.run(["systemctl", "restart", unit], check=True, timeout=30, env=CLEAN_ENV)
        else:
            raise HTTPException(status_code=422, detail=f"Cannot restart service: {service}")

        if database:
            record_audit(database, "service_restarted", user_id=user_id,
                         details=f"service={service}", ip_address=ip)

        return {"status": "restarted", "service": service}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to restart %s: %s", service, exc)
        raise HTTPException(status_code=500, detail=f"Restart failed: {exc}")


@app.post("/api/services/restart-all")
@limiter.limit("3/minute")
async def restart_all_services(request: Request, user: Dict = Depends(require_admin)):
    """Restart the full Immich stack via docker compose."""
    if not config:
        raise HTTPException(status_code=503, detail="Config not initialized")

    compose_path = Path(config.immich.docker_compose_path)
    user_id = user.get("id", "unknown")
    ip = request.client.host if request.client else None

    try:
        subprocess.run(
            ["docker", "compose", "restart"],
            cwd=str(compose_path), check=True, capture_output=True, timeout=120, env=CLEAN_ENV,
        )
        if database:
            record_audit(database, "services_restarted_all", user_id=user_id, ip_address=ip)
        return {"status": "restarted", "service": "all"}
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode() if exc.stderr else ""
        logger.error("docker compose restart failed: %s", stderr)
        raise HTTPException(status_code=500, detail=f"docker compose restart failed: {stderr}")
    except Exception as exc:
        logger.error("restart-all error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# --- Update status / apply-stream endpoints ---

@app.get("/api/updates/status")
@limiter.limit("10/minute")
async def get_update_status(request: Request, user: Dict = Depends(require_admin)):
    """Return current vs latest Immich version and update history."""
    if not update_checker:
        raise HTTPException(status_code=503, detail="Update checker not initialized")

    loop = asyncio.get_running_loop()
    (current, immich_reachable), latest = await asyncio.gather(
        loop.run_in_executor(None, update_checker.get_running_version_with_reachability),
        loop.run_in_executor(None, update_checker.get_latest_github_version),
    )

    update_available = False
    changelog_url = None
    if immich_reachable and current and latest:
        try:
            update_available = (
                update_checker._parse_version(latest) > update_checker._parse_version(current)
            )
            if update_available:
                changelog_url = f"https://github.com/immich-app/immich/releases/tag/v{latest}"
        except (ValueError, TypeError):
            pass

    history = []
    if database:
        history = database.get_update_history(limit=10)

    return {
        "current_version": current,
        "latest_version": latest,
        "update_available": update_available,
        "immich_reachable": immich_reachable,
        "changelog_url": changelog_url,
        "history": history,
    }


# Track in-flight update progress for SSE
_update_progress: List[Dict[str, str]] = []
_update_in_progress: bool = False


@app.get("/api/updates/apply/stream")
async def stream_update_progress(request: Request, user: Dict = Depends(require_admin)):
    """Stream update progress events via SSE."""
    async def event_generator():
        sent = 0
        while True:
            if await request.is_disconnected():
                break
            while sent < len(_update_progress):
                yield {"data": _update_progress[sent]}
                sent += 1
            if not _update_in_progress and sent >= len(_update_progress):
                break
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


app.mount(
    "/assets",
    StaticFiles(directory=Path(__file__).parent.parent / "frontend" / "dist" / "assets"),
    name="assets",
)


def main():
    """Run the server"""
    try:
        config, _ = load_config()
        dev_mode = os.environ.get("DEV_MODE", "").lower() in ("1", "true", "yes")

        uvicorn.run(
            "src.main:app",
            host=config.server.host,
            port=config.server.port,
            workers=1 if dev_mode else config.server.workers,
            log_level=config.server.log_level.lower(),
            reload=dev_mode,
            reload_dirs=["src", "../shared"] if dev_mode else None,
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
