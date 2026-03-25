"""
Main FastAPI application for Photo Curator Assistant
Complete AI-powered photo curation with Immich authentication integration
"""

import sys
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Literal, Optional, Any
import json
import os
import uvicorn
import yaml
import logging
import asyncio
import re
import threading
import uuid
import shutil
import importlib.util
import html as html_lib
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Add project root to path for shared library
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from .database import Database
from .immich_client import ImmichClient, PhotoCache
from .analyzer import PhotoAnalyzer
from .auth import ImmichAuth, get_current_user, get_current_user_optional, get_user_api_client
from .notifications import EmailNotifier
from .logging_config import setup_json_logging
from .batch_processor import BatchProcessor
from .gpu_utils import GPUManager
from .dedup_scanner import DedupScanner
from shared.auth import (
    Role, ensure_users_table, require_role,
    get_all_users, update_user_role,
)

setup_json_logging()
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Photo Curator Assistant",
    description="AI-powered photo curation for Immich with SSO",
    version="2.0.0"
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Serve React frontend assets — must be declared before route handlers
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")


class NotAuthenticatedException(Exception):
    def __init__(self, immich_login_url: str, curator_url: str):
        self.immich_login_url = immich_login_url
        self.curator_url = curator_url


@app.exception_handler(NotAuthenticatedException)
async def not_authenticated_handler(request: Request, exc: NotAuthenticatedException):
    html = f"""<!DOCTYPE html>
<html>
<head><title>Login Required</title>
<style>
  body {{ font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #0f172a; color: #e2e8f0; }}
  .box {{ text-align: center; padding: 2rem; background: #1e293b; border-radius: 1rem; max-width: 400px; }}
  h2 {{ margin-bottom: 0.5rem; }}
  p {{ color: #94a3b8; margin-bottom: 1.5rem; }}
  a.btn {{ display: inline-block; padding: 0.75rem 1.5rem; border-radius: 0.5rem; text-decoration: none; font-weight: bold; margin: 0.25rem; }}
  .primary {{ background: #6366f1; color: white; }}
  .secondary {{ background: #334155; color: #e2e8f0; }}
</style>
</head>
<body><div class="box">
  <h2>Sign in required</h2>
  <p>Log into Immich, then return to Photo Curator.</p>
  <a class="btn primary" href="{exc.immich_login_url}" target="_blank">Open Immich Login</a>
  <a class="btn secondary" href="{exc.curator_url}">I've logged in &rarr;</a>
</div></body>
</html>"""
    return HTMLResponse(content=html, status_code=401)

# CORS - restrict to known origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:2283",
        "http://127.0.0.1:2283",
    ],
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
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# Global state
config: Optional[Dict] = None
database: Optional[Database] = None
admin_immich_client: Optional[ImmichClient] = None  # Admin client for background jobs
photo_cache: Optional[PhotoCache] = None
analyzer: Optional[PhotoAnalyzer] = None
scheduler: Optional[AsyncIOScheduler] = None
email_notifier: Optional[EmailNotifier] = None
batch_processor: Optional[BatchProcessor] = None
gpu_manager: Optional[GPUManager] = None
dedup_scanner: Optional[DedupScanner] = None

_ENV_VAR_PATTERN = re.compile(r'\$\{([^}]+)\}')


def _resolve_env_vars(obj):
    """Recursively resolve ${ENV_VAR} and ${ENV_VAR:-default} in config values."""
    if isinstance(obj, str):
        def _replace(match):
            expr = match.group(1)
            if ':-' in expr:
                var_name, default = expr.split(':-', 1)
            else:
                var_name, default = expr, ''
            return os.environ.get(var_name.strip(), default)
        return _ENV_VAR_PATTERN.sub(_replace, obj)
    elif isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(item) for item in obj]
    return obj


# Request models
class CurationSelection(BaseModel):
    """User's curation selections"""
    selected: List[str]  # All selected asset IDs
    added: List[str]  # Asset IDs user added
    removed: List[str]  # Asset IDs user removed from AI suggestions


class AlbumCreate(BaseModel):
    """Album creation request"""
    asset_ids: List[str]
    album_name: str
    description: Optional[str] = None


class EventAlbumCreate(BaseModel):
    """Request to create an album from a detected event suggestion"""
    album_name: str


@app.on_event("startup")
async def startup_event():
    """Initialize application"""
    global config, database, admin_immich_client, photo_cache, analyzer, scheduler, email_notifier, batch_processor, gpu_manager, dedup_scanner

    try:
        # Load configuration
        config_path = Path("config/config.yaml")
        if config_path.exists():
            with open(config_path) as f:
                config = _resolve_env_vars(yaml.safe_load(f))
        else:
            logger.warning("No config file found, using defaults")
            config = {
                "server": {"host": "0.0.0.0", "port": 8081},
                "immich": {
                    "base_url": "http://localhost:2283",
                    "api_url": "http://localhost:2283/api",
                    "api_key": ""  # Only needed for admin operations
                },
                "ai": {"use_local_models": True},
                "notifications": {"email": {"enabled": False}}
            }

        # Initialize database
        database = Database()
        ensure_users_table(database)
        app.state.database = database
        dedup_scanner = DedupScanner(database, config.get('dedup', {}))
        app.state.dedup_scanner = dedup_scanner
        logger.info(f"[DB] Database path: {Path(database.db_path).resolve()}")
        app.state.default_role = config.get("auth", {}).get("default_role", "user")
        app.state.guest_link_default_expiry_days = config.get("auth", {}).get("guest_link_default_expiry_days", 30)

        # Initialize Immich authentication
        immich_config = config.get("immich", {})
        immich_base_url = immich_config.get("base_url", "http://localhost:2283")
        app.state.immich_auth = ImmichAuth(immich_base_url)
        app.state.immich_api_url = immich_config.get("api_url", f"{immich_base_url}/api")
        app.state.immich_base_url = immich_base_url  # Store for email links

        # Initialize admin Immich client (for background jobs only)
        if immich_config.get("api_key"):
            admin_immich_client = ImmichClient(
                immich_config["api_url"],
                immich_config["api_key"]
            )
            if admin_immich_client.check_connection():
                logger.info("✓ Connected to Immich API (admin)")
            else:
                logger.warning("⚠ Cannot connect to Immich API")
        else:
            logger.warning("⚠ No admin API key configured (optional, only needed for background jobs)")

        # Initialize photo cache
        photo_cache = PhotoCache()

        # Initialize GPU manager
        gpu_config = config.get("batch_processing", {}).get("gpu", {"enabled": True, "device": "cuda:0"})
        gpu_manager = GPUManager(gpu_config)
        device = gpu_manager.init()

        # Initialize analyzer (GPU-aware)
        analyzer = PhotoAnalyzer(config, device=device)

        # Initialize email notifier
        # ADMIN TODO: Configure SMTP settings in config/config.yaml
        # Set notifications.email.enabled = true and fill in:
        # - smtp_host (e.g., "smtp.gmail.com")
        # - smtp_port (e.g., 587)
        # - smtp_user (your email)
        # - smtp_password (app password for Gmail, not regular password)
        # - from (sender email address)
        email_config = config.get("notifications", {}).get("email", {})
        email_notifier = EmailNotifier(email_config)
        if email_notifier.enabled:
            logger.info("✓ Email notifications enabled")
        else:
            logger.info("ℹ Email notifications disabled (configure in config.yaml to enable)")

        # Initialize scheduler (for background jobs)
        scheduler = AsyncIOScheduler()

        # Schedule monthly reminder job
        # ADMIN TODO: This will run daily at 9 AM and check if it's the 1st of the month
        # Customize the time in config.yaml under curation.reminder_time
        reminder_time = config.get("curation", {}).get("reminder_time", "09:00")
        hour, minute = map(int, reminder_time.split(":"))

        scheduler.add_job(
            send_monthly_reminders,
            'cron',
            hour=hour,
            minute=minute,
            id='monthly_reminders',
            replace_existing=True
        )

        # Initialize batch processor (requires admin client)
        if admin_immich_client:
            batch_config = config.get("batch_processing", {})
            batch_processor = BatchProcessor(database, admin_immich_client, analyzer, batch_config)

            # Schedule batch processing if enabled
            if batch_config.get("schedule", {}).get("enabled", False):
                scheduler.add_job(
                    batch_processor.run_scheduled,
                    'cron',
                    minute='*/5',
                    id='batch_scheduled',
                    replace_existing=True
                )
                logger.info("Batch processing scheduler enabled (checking every 5 min)")
            else:
                logger.info("Batch processing scheduler disabled (enable in config.yaml)")
        else:
            logger.warning("⚠ Batch processing disabled (no admin API key configured)")

        scheduler.start()
        logger.info(f"Scheduler started (monthly reminders at {reminder_time})")

        logger.info("Photo Curator started successfully (with Immich SSO)")
        logger.info(f"Web UI: http://{config['server']['host']}:{config['server']['port']}")
        logger.info(f"Immich URL: {immich_base_url}")

    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if scheduler:
        scheduler.shutdown()
    if batch_processor:
        await batch_processor.cancel_job()


# Background job for monthly reminders
async def send_monthly_reminders():
    """
    Send monthly curation reminders to users who have opted in
    Runs daily but only sends on the 1st of each month
    """
    try:
        now = datetime.now()

        # Only send on the 1st of the month
        if now.day != 1:
            return

        logger.info("Running monthly reminder job...")

        if not database or not admin_immich_client or not email_notifier or not email_notifier.enabled:
            logger.warning("Monthly reminders skipped (email not configured or no admin API key)")
            return

        # Get all users from Immich
        users = admin_immich_client.get_users()

        year = now.year
        month = now.month - 1 if now.month > 1 else 12
        if month == 12:
            year -= 1

        sent_count = 0
        for user in users:
            user_id = user.get('id')
            user_email = user.get('email')
            user_name = user.get('name') or user_email.split('@')[0]

            if not user_email:
                continue

            # Check user preferences
            prefs = database.get_user_preferences(user_id)
            preferences_dict = prefs.get('preferences', {}) if isinstance(prefs.get('preferences'), dict) else {}
            email_prefs = preferences_dict.get('email_notifications', {})

            # Only send if user has opted in
            if not email_prefs.get('monthly_reminders', False):
                continue

            # Get photo count for last month
            photos = database.get_photo_scores(user_id, year, month)
            photo_count = len(photos)

            if photo_count == 0:
                continue

            # ADMIN TODO: Replace 'localhost' with your actual curator URL
            # This should match your Cloudflare Tunnel domain
            # Example: "https://curator.yourdomain.com"
            curator_url = app.state.immich_base_url.replace('2283', '8081')  # Temporary

            # Send reminder
            success = email_notifier.send_monthly_reminder(
                user_email,
                user_name,
                year,
                month,
                photo_count,
                curator_url
            )

            if success:
                sent_count += 1

        logger.info(f"Monthly reminders sent to {sent_count} users")

    except Exception as e:
        logger.error(f"Error sending monthly reminders: {e}")


# Authentication check endpoint
@app.get("/api/auth/check")
async def check_auth(user: Optional[Dict] = Depends(get_current_user_optional)):
    """Check if user is authenticated, including role info"""
    immich_auth = app.state.immich_auth
    if user:
        local = user.get("_local_user", {})
        return {
            "authenticated": True,
            "user": {
                "id": user.get("id"),
                "email": user.get("email"),
                "name": user.get("name")
            },
            "role": local.get("role", "user"),
            "logout_url": f"{immich_auth.immich_url}/auth/logout",
        }
    else:
        return {
            "authenticated": False,
            "login_url": f"{immich_auth.immich_url}/auth/login"
        }


@app.get("/logout")
async def logout(request: Request):
    """Redirect to Immich logout page"""
    immich_auth = request.app.state.immich_auth
    return RedirectResponse(url=f"{immich_auth.immich_url}/auth/logout")


async def require_user_page(request: Request):
    """Dependency for HTML page routes requiring at least USER role.

    Redirects to login if unauthenticated, returns 403 if insufficient role.
    """
    immich_auth = request.app.state.immich_auth
    user = immich_auth.get_user_from_request(request)
    if not user:
        raise NotAuthenticatedException(
            immich_login_url=f"{immich_auth.immich_url}/auth/login",
            curator_url=str(request.url),
        )
    db = getattr(request.app.state, "database", None)
    if db:
        from shared.auth import get_or_create_user
        default_role = getattr(request.app.state, "default_role", "user")
        local_user, _ = get_or_create_user(db, user, default_role)
        request.state._local_user = local_user
        user["_local_user"] = local_user
        if Role[local_user["role"].upper()] < Role.USER:
            raise HTTPException(status_code=403, detail="User access required")
    return user


# Web UI
@app.get("/", response_class=HTMLResponse)
async def serve_spa(request: Request):
    """Serve React SPA entry point."""
    index_path = Path(__file__).resolve().parent.parent / "frontend" / "dist" / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text())
    return HTMLResponse(content="<p>Frontend not built. Run: cd photo-curator/frontend && npm run build</p>", status_code=503)


# API Endpoints (all require authentication)
@app.get("/health")
@limiter.limit("30/minute")
async def health_check(request: Request):
    """Health check endpoint (no auth required)"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/thumbnail/{asset_id}")
@limiter.limit("200/minute")
async def proxy_thumbnail(request: Request, asset_id: str, user: Dict = Depends(get_current_user)):
    """Proxy thumbnail requests so user tokens are never exposed in URLs."""
    from fastapi.responses import Response
    import requests as http_requests

    try:
        resp = http_requests.get(
            f"{app.state.immich_api_url}/assets/{asset_id}/thumbnail",
            headers={"Authorization": f"Bearer {user['access_token']}"},
            timeout=10,
        )
        resp.raise_for_status()
        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "image/jpeg"),
            headers={"Cache-Control": "private, max-age=3600"},
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Thumbnail not found")


@app.get("/api/status")
@limiter.limit("30/minute")
async def get_status(request: Request, user: Dict = Depends(get_current_user)):
    """Get curator status for authenticated user"""
    stats = database.get_statistics() if database else {}
    user_progress = database.get_user_progress(user['id']) if database else {}

    return {
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "user": {
            "id": user['id'],
            "email": user['email'],
            "name": user.get('name')
        },
        "progress": user_progress,
        "statistics": stats
    }


@app.post("/api/analyze/{year}/{month}")
@limiter.limit("5/minute")
async def analyze_month(
    request: Request,
    year: int,
    month: int,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Analyze all photos for authenticated user's month (requires User role)"""
    if not analyzer or not database:
        raise HTTPException(status_code=503, detail="Services not initialized")

    user_id = user['id']

    # Start background analysis
    background_tasks.add_task(
        analyze_user_month_background,
        user_id,
        year,
        month,
        user['access_token']  # Use user's token
    )

    return {
        "status": "started",
        "message": f"Analysis started for {year}-{month:02d}",
        "user_id": user_id
    }


async def analyze_user_month_background(user_id: str, year: int, month: int, user_token: str):
    """Background task to analyze photos using user's credentials"""
    try:
        logger.info(f"Starting analysis for user {user_id}, {year}-{month:02d}")

        # Prefer admin client (API key) over user bearer token — bearer tokens cause 400 in Immich v2.x
        logger.info(f"[ANALYZE] Using Immich API URL: {app.state.immich_api_url}")
        user_client = admin_immich_client or ImmichClient(app.state.immich_api_url, user_token, use_bearer=True)

        # Verify Immich is reachable before proceeding
        reachable = await asyncio.to_thread(user_client.check_connection)
        logger.info(f"[ANALYZE] Immich reachable: {reachable}")

        # Fetch photos from Immich — blocking network I/O, run off the event loop
        photos = await asyncio.to_thread(user_client.get_user_photos, user_id, year, month)

        if not photos:
            logger.warning(f"[ANALYZE] No photos returned from Immich for {year}-{month:02d} (user={user_id})")
            return

        logger.info(f"[ANALYZE] Fetched {len(photos)} photos from Immich, starting ML analysis...")

        # Build set of already-analyzed asset IDs once before the loop
        existing_scores = database.get_photo_scores(user_id, year, month)
        analyzed_ids = {score['asset_id'] for score in existing_scores}

        # Analyze each photo — all blocking I/O and CPU work runs in a thread
        # so the event loop (and watchdog heartbeat) stays responsive.
        for i, photo in enumerate(photos):
            asset_id = photo['id']

            # Check if already analyzed
            if asset_id in analyzed_ids:
                continue

            # Download photo (use thumbnail for speed) — blocking network I/O
            cached_path = photo_cache.get_cached_path(asset_id)
            if not cached_path:
                photo_path = await asyncio.to_thread(
                    user_client.download_photo, asset_id, None, True
                )
                if photo_path:
                    cached_path = photo_cache.add_to_cache(asset_id, photo_path)

            if cached_path:
                # Analyze photo — blocking CPU-heavy ML inference
                scores = await asyncio.to_thread(analyzer.analyze_photo, cached_path)

                if scores.get('success'):
                    # Save core quality scores
                    database.save_photo_score(asset_id, user_id, year, month, scores)

                    # Save face embeddings (face recognition)
                    for fi, face_data in enumerate(scores.get('face_embeddings', [])):
                        from .face_recognition_engine import FaceRecognitionEngine  # noqa: PLC0415
                        database.save_face_embedding(
                            asset_id=asset_id,
                            user_id=user_id,
                            face_index=fi,
                            embedding_bytes=FaceRecognitionEngine.embedding_to_bytes(
                                face_data['embedding']
                            ),
                            bbox=face_data['bbox'],
                            confidence=face_data.get('confidence'),
                        )

                    # Save scene classification
                    scene = scores.get('scene')
                    if scene:
                        import json as _json  # noqa: PLC0415
                        database.save_scene_classification(
                            asset_id=asset_id,
                            user_id=user_id,
                            scene_category=scene['scene_category'],
                            scene_subcategory=scene.get('scene_subcategory'),
                            confidence=scene.get('confidence'),
                            top3_json=_json.dumps(scene.get('top3_scenes', [])),
                        )

                    if (i + 1) % 10 == 0:
                        logger.info(f"Analyzed {i + 1}/{len(photos)} photos")

        # Create curation session with top photos
        top_photos = database.get_top_photos(user_id, year, month, limit=50)
        ai_suggested = [p['asset_id'] for p in top_photos]

        database.create_curation_session(
            user_id,
            year,
            month,
            len(photos),
            ai_suggested
        )

        # Find duplicates — blocking CPU work
        all_scores = database.get_photo_scores(user_id, year, month)
        photos_with_hash = [
            {'id': s['asset_id'], 'perceptual_hash': s['perceptual_hash']}
            for s in all_scores
            if s.get('perceptual_hash')
        ]

        duplicates = await asyncio.to_thread(analyzer.find_duplicates, photos_with_hash)
        for dup_group in duplicates:
            database.save_duplicate_group(dup_group)

        logger.info(f"Analysis complete! Suggested {len(ai_suggested)} photos")
        logger.info(f"Found {len(duplicates)} duplicate groups")

        # Cluster face embeddings into identity groups
        _cluster_face_identities(user_id)

    except Exception as e:
        logger.error(f"[ANALYZE] Error in background analysis: {e}", exc_info=True)


@app.get("/api/photos/{year}/{month}")
@limiter.limit("30/minute")
async def get_monthly_photos(
    request: Request,
    year: int,
    month: int,
    user: Dict = Depends(get_current_user)
):
    """Get photos with scores for authenticated user's month"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    user_id = user['id']

    logger.info(f"[PHOTOS] Loading photos for user={user_id} {year}-{month:02d}")

    # Get scores from database
    scores = database.get_photo_scores(user_id, year, month)

    logger.info(f"[PHOTOS] Found {len(scores)} scored photos in DB for user={user_id} {year}-{month:02d}")
    if not scores:
        # Check if there are ANY photos for this user at all
        from .database import Database as _DB
        with database._get_connection() as _conn:
            _row = _conn.execute(
                "SELECT COUNT(*) as total FROM photo_scores WHERE user_id = ?", (user_id,)
            ).fetchone()
            logger.info(f"[PHOTOS] Total photos in DB for this user across all months: {_row['total']}")
            _row2 = _conn.execute("SELECT COUNT(*) as total FROM photo_scores").fetchone()
            logger.info(f"[PHOTOS] Total photos in DB across ALL users: {_row2['total']}")

    # Create user-specific API client for thumbnail URLs
    user_client = ImmichClient(app.state.immich_api_url, user['access_token'])

    # Add thumbnail URLs to each photo
    for photo in scores:
        photo['thumbnail_url'] = user_client.get_thumbnail_url(photo['asset_id'])

    # Get curation session
    session = database.get_curation_session(user_id, year, month)

    # Get duplicates
    duplicates = database.get_duplicates_for_user(user_id, year, month)

    return {
        "user_id": user_id,
        "year": year,
        "month": month,
        "total_photos": len(scores),
        "photos": scores,
        "session": session,
        "duplicates": duplicates
    }


@app.get("/api/photos/{year}/{month}/raw")
@limiter.limit("30/minute")
async def get_raw_photos(
    request: Request,
    year: int,
    month: int,
    current_user: Dict = Depends(get_current_user),
):
    """Fetch photos for a month directly from Immich, no analysis required."""
    immich_api_url = app.state.immich_api_url
    # Prefer admin client (API key) over user bearer token — bearer tokens cause 400 in Immich v2.x
    user_client = admin_immich_client or ImmichClient(immich_api_url, current_user["access_token"], use_bearer=True)
    photos = await asyncio.to_thread(
        user_client.get_user_photos, current_user["id"], year, month
    )
    db = app.state.database
    if db:
        scores = db.get_photo_scores(current_user["id"], year, month)
        scored_ids = {s["asset_id"] for s in scores}
    else:
        scored_ids = set()
    return {
        "photos": [
            {
                "asset_id": p["id"],
                "thumbnail_url": f"/api/thumbnail/{p['id']}",
                "width": p.get("exifInfo", {}).get("exifImageWidth"),
                "height": p.get("exifInfo", {}).get("exifImageHeight"),
                "taken_at": p.get("fileCreatedAt"),
                "scored": p["id"] in scored_ids,
            }
            for p in photos
        ],
        "total": len(photos),
        "scored_count": sum(1 for p in photos if p["id"] in scored_ids),
    }


@app.get("/api/progress/year/{year}")
@limiter.limit("60/minute")
async def get_year_progress(
    request: Request,
    year: int,
    current_user: Dict = Depends(get_current_user),
):
    """Return curation status for all 12 months of a year."""
    db = app.state.database
    progress = db.get_year_progress(current_user["id"], year)
    return progress


@app.post("/api/curation/{year}/{month}/update")
@limiter.limit("20/minute")
async def update_curation(
    request: Request,
    year: int,
    month: int,
    selection: CurationSelection,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Update authenticated user's curation selections (requires User role)"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    user_id = user['id']

    database.update_curation_session(
        user_id,
        year,
        month,
        selected=selection.selected,
        added=selection.added,
        removed=selection.removed
    )

    return {
        "status": "updated",
        "selected_count": len(selection.selected)
    }


@app.post("/api/curation/{year}/{month}/complete")
@limiter.limit("5/minute")
async def complete_curation(
    request: Request,
    year: int,
    month: int,
    album_data: AlbumCreate,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Complete curation and create album in Immich (requires User role)"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    user_id = user['id']

    try:
        # Create user-specific API client
        user_client = ImmichClient(app.state.immich_api_url, user['access_token'])

        # Create album in Immich (as the user)
        album = user_client.create_album(
            album_data.album_name,
            album_data.asset_ids,
            album_data.description
        )

        if not album:
            raise HTTPException(status_code=500, detail="Failed to create album")

        # Mark session as complete
        database.complete_curation_session(
            user_id,
            year,
            month,
            album['id'],
            album_data.album_name
        )

        return {
            "status": "completed",
            "album": album,
            "asset_count": len(album_data.asset_ids)
        }

    except Exception as e:
        logger.error(f"Error completing curation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/progress")
@limiter.limit("30/minute")
async def get_user_progress(request: Request, user: Dict = Depends(get_current_user)):
    """Get authenticated user's curation progress"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    user_id = user['id']
    progress = database.get_user_progress(user_id)
    preferences = database.get_user_preferences(user_id)

    return {
        "user_id": user_id,
        "progress": progress,
        "preferences": preferences
    }


@app.get("/api/stats")
@limiter.limit("30/minute")
async def get_statistics(request: Request, user: Dict = Depends(get_current_user)):
    """Get overall statistics (accessible to all authenticated users)"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return database.get_statistics()


# User Preferences
@app.get("/preferences", response_class=HTMLResponse)
async def preferences_ui(request: Request, user: Dict = Depends(require_user_page)):
    """Serve preferences UI (requires User role)"""

    html_path = Path(__file__).parent.parent / "static" / "preferences.html"
    if html_path.exists():
        return html_path.read_text()

    return HTMLResponse("<h1>Preferences not found</h1>", status_code=404)


class UserPreferences(BaseModel):
    """User preferences update"""
    email_notifications: Dict[str, bool]
    monthly_target: int
    ui_suggestions: Dict[str, bool]


@app.get("/api/preferences")
@limiter.limit("30/minute")
async def get_preferences(request: Request, user: Dict = Depends(get_current_user)):
    """Get user preferences"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    user_id = user['id']
    prefs = database.get_user_preferences(user_id)

    # Parse stored preferences
    preferences_dict = prefs.get('preferences', {})
    if isinstance(preferences_dict, str):
        import json
        preferences_dict = json.loads(preferences_dict)

    return {
        "user_id": user_id,
        "email_notifications": preferences_dict.get('email_notifications', {
            "monthly_reminders": False,
            "quality_alerts": False,
            "memory_lane": False,
            "seasonal_automations": False,
            "storage_warnings": True
        }),
        "monthly_target": prefs.get('monthly_target', 50),
        "ui_suggestions": preferences_dict.get('ui_suggestions', {
            "sharing_suggestions": False,
            "event_detection": False,
            "duplicate_warnings": True
        })
    }


@app.put("/api/preferences")
@limiter.limit("10/minute")
async def update_preferences(
    request: Request,
    preferences: UserPreferences,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Update user preferences (requires User role)"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    user_id = user['id']

    # Save preferences to database
    database.save_user_preferences(
        user_id,
        monthly_target=preferences.monthly_target,
        preferences={
            "email_notifications": preferences.email_notifications,
            "ui_suggestions": preferences.ui_suggestions
        }
    )

    return {
        "status": "updated",
        "message": "Preferences saved successfully"
    }


# Analytics Dashboard (Admin)
@app.get("/analytics", response_class=HTMLResponse)
async def analytics_ui(request: Request, user: Dict = Depends(require_user_page)):
    """Serve analytics dashboard (requires User role)"""

    html_path = Path(__file__).parent.parent / "static" / "analytics.html"
    if html_path.exists():
        return html_path.read_text()

    return HTMLResponse("<h1>Analytics Dashboard not found</h1>", status_code=404)


@app.get("/api/analytics")
@limiter.limit("15/minute")
async def get_analytics(
    request: Request,
    period: int = 30,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.ADMIN)),
):
    """Get analytics data (admin only)"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    try:
        analytics = database.get_analytics_data(period_days=period)

        # If admin API client available, enrich with user names
        if admin_immich_client:
            try:
                users = admin_immich_client.get_users()
                user_map = {u['id']: u for u in users}

                # Add user names to stats
                for stat in analytics.get('user_stats', []):
                    user_data = user_map.get(stat['user_id'])
                    if user_data:
                        stat['user_name'] = user_data.get('name') or user_data.get('email', 'Unknown')
                        stat['user_email'] = user_data.get('email', 'Unknown')
                    else:
                        stat['user_name'] = stat['user_id'][:8] + '...'
                        stat['user_email'] = 'Unknown'

                # Add user labels to activity data
                for activity in analytics.get('user_activity', []):
                    user_data = user_map.get(activity['user_id'])
                    if user_data:
                        activity['label'] = user_data.get('name') or user_data.get('email', 'Unknown')
                    else:
                        activity['label'] = activity['user_id'][:8] + '...'

            except Exception as e:
                logger.warning(f"Could not enrich analytics with user data: {e}")

        return analytics

    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Duplicate Management
@app.get("/duplicates", response_class=HTMLResponse)
async def duplicates_ui(request: Request, user: Dict = Depends(require_user_page)):
    """Serve duplicate manager UI (requires User role)"""

    html_path = Path(__file__).parent.parent / "static" / "duplicates.html"
    if html_path.exists():
        return html_path.read_text()

    return HTMLResponse("<h1>Duplicate Manager not found</h1>", status_code=404)


class DuplicateDelete(BaseModel):
    """Duplicate deletion request"""
    asset_ids: List[str]


@app.post("/api/duplicates/delete")
@limiter.limit("5/minute")
async def delete_duplicates(
    request: Request,
    delete_request: DuplicateDelete,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Delete duplicate photos from Immich (requires User role)"""
    try:
        # Create user-specific API client
        user_client = ImmichClient(app.state.immich_api_url, user['access_token'])

        deleted_count = 0
        failed_count = 0

        for asset_id in delete_request.asset_ids:
            try:
                # Delete from Immich
                response = user_client.session.delete(
                    f"{user_client.api_url}/assets",
                    json={"ids": [asset_id]}
                )
                response.raise_for_status()
                deleted_count += 1

                # Remove from database
                if database:
                    database.delete_photo_score(asset_id)

            except Exception as e:
                logger.error(f"Failed to delete asset {asset_id}: {e}")
                failed_count += 1

        return {
            "status": "completed",
            "deleted": deleted_count,
            "failed": failed_count,
            "total": len(delete_request.asset_ids)
        }

    except Exception as e:
        logger.error(f"Error deleting duplicates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ====================================================================
# Standalone Dedup Scanner
# ====================================================================

class DedupDeepScanRequest(BaseModel):
    date_from: str  # ISO date: YYYY-MM-DD
    date_to: str


class DedupEstimateRequest(BaseModel):
    date_from: str
    date_to: str


class DedupResolveRequest(BaseModel):
    keep_asset_id: str


@app.post("/api/dedup/scan/estimate")
async def dedup_estimate(
    request: Request,
    body: DedupEstimateRequest,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    db = app.state.database
    scanner = getattr(app.state, 'dedup_scanner', None)
    if not db or not scanner:
        raise HTTPException(status_code=503, detail="Service not initialized")
    user_client = ImmichClient(app.state.immich_api_url, user['access_token'], use_bearer=True)
    result = await scanner.estimate(
        user['id'], body.date_from, body.date_to, user_client
    )
    return result


@app.post("/api/dedup/scan/deep")
async def dedup_start_deep(
    request: Request,
    body: DedupDeepScanRequest,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    db = app.state.database
    scanner = getattr(app.state, 'dedup_scanner', None)
    if not db or not scanner:
        raise HTTPException(status_code=503, detail="Service not initialized")
    if scanner.is_running():
        raise HTTPException(
            status_code=409,
            detail={"error": "scan_already_running", "scan_id": scanner.current_scan_id()}
        )
    user_client = ImmichClient(app.state.immich_api_url, user['access_token'], use_bearer=True)
    scan_id = await scanner.start_deep_scan(user['id'], body.date_from, body.date_to, user_client)
    return {"scan_id": scan_id, "status": "running"}


@app.post("/api/dedup/scan/quick")
async def dedup_start_quick(
    request: Request,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    db = app.state.database
    scanner = getattr(app.state, 'dedup_scanner', None)
    if not db or not scanner:
        raise HTTPException(status_code=503, detail="Service not initialized")
    if scanner.is_running():
        raise HTTPException(
            status_code=409,
            detail={"error": "scan_already_running", "scan_id": scanner.current_scan_id()}
        )
    user_client = ImmichClient(app.state.immich_api_url, user['access_token'], use_bearer=True)
    scan_id = await scanner.start_quick_scan(user['id'], user_client)
    return {"scan_id": scan_id, "status": "running"}


@app.get("/api/dedup/scan/status")
async def dedup_scan_status(
    request: Request,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    db = app.state.database
    if not db:
        raise HTTPException(status_code=503, detail="Service not initialized")
    scan = db.get_dedup_scan_status(user['id'])
    if not scan:
        return {"status": "idle"}
    phase = DedupScanner.derive_phase(
        scan['status'], scan.get('hashed', 0), scan.get('total_assets', 0)
    )
    return {**scan, "phase": phase}


@app.delete("/api/dedup/scan")
async def dedup_cancel_scan(
    request: Request,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    scanner = getattr(app.state, 'dedup_scanner', None)
    if not scanner:
        return {"cancelled": False}
    cancelled = await scanner.cancel()
    return {"cancelled": cancelled}


@app.get("/api/dedup/groups")
async def dedup_get_groups(
    request: Request,
    include_resolved: bool = False,
    limit: int = 50,
    offset: int = 0,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    db = app.state.database
    if not db:
        raise HTTPException(status_code=503, detail="Service not initialized")
    limit = min(limit, 200)
    return db.get_dedup_groups(user['id'], include_resolved=include_resolved, limit=limit, offset=offset)


@app.post("/api/dedup/groups/{group_id}/resolve")
@limiter.limit("30/minute")
async def dedup_resolve_group(
    request: Request,
    group_id: int,
    body: DedupResolveRequest,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    db = app.state.database
    if not db:
        raise HTTPException(status_code=503, detail="Service not initialized")
    result = db.get_dedup_groups(user['id'])
    group = next((g for g in result['groups'] if g['id'] == group_id), None)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    asset_ids = json.loads(group['asset_ids']) if isinstance(group['asset_ids'], str) else group['asset_ids']
    to_delete = [aid for aid in asset_ids if aid != body.keep_asset_id]

    user_client = ImmichClient(app.state.immich_api_url, user['access_token'], use_bearer=True)
    deleted = 0
    try:
        for asset_id in to_delete:
            resp = user_client.session.delete(
                f"{user_client.api_url}/assets", json={"ids": [asset_id]}
            )
            resp.raise_for_status()
            db.delete_photo_score(asset_id)
            deleted += 1
    except Exception as e:
        logger.error(f"Immich delete failed during group resolve: {e}")
        return {"resolved": False, "error": "immich_delete_failed", "detail": str(e)}

    db.resolve_dedup_group(group_id)
    return {"resolved": True, "deleted_count": deleted}


@app.delete("/api/dedup/groups/{group_id}")
async def dedup_dismiss_group(
    request: Request,
    group_id: int,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    db = app.state.database
    if not db:
        raise HTTPException(status_code=503, detail="Service not initialized")
    db.dismiss_dedup_group(group_id)
    return {"dismissed": True}


# ====================================================================
# Year in Review
# ====================================================================

@app.get("/year-in-review", response_class=HTMLResponse)
async def year_in_review_ui(request: Request, user: Dict = Depends(require_user_page)):
    """Serve Year in Review page (requires User role)."""
    html_path = Path(__file__).parent.parent / "static" / "year-in-review.html"
    if html_path.exists():
        return html_path.read_text()
    return HTMLResponse("<h1>Year in Review page not found</h1>", status_code=404)


@app.get("/api/year-in-review/{year}")
@limiter.limit("10/minute")
async def get_year_in_review(request: Request, year: int, user: Dict = Depends(get_current_user)):
    """Get annual summary for the authenticated user."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return database.get_year_in_review(user["id"], year)


# ====================================================================
# Photo Map View
# ====================================================================

@app.get("/map", response_class=HTMLResponse)
async def map_ui(request: Request, user: Dict = Depends(require_user_page)):
    """Serve photo map page (requires User role)."""
    html_path = Path(__file__).parent.parent / "static" / "map.html"
    if html_path.exists():
        return html_path.read_text()
    return HTMLResponse("<h1>Map page not found</h1>", status_code=404)


@app.get("/api/photos/map")
@limiter.limit("15/minute")
async def get_map_data(
    request: Request,
    year: Optional[int] = None,
    month: Optional[int] = None,
    user: Dict = Depends(get_current_user),
):
    """Get geotagged photos for map display."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return {"photos": database.get_photos_with_location(user["id"], year, month)}


# ====================================================================
# Family Mode — Shared Curation
# ====================================================================

class ShareInvite(BaseModel):
    collaborator_id: str


class SharedPick(BaseModel):
    asset_id: str


@app.post("/api/curation/{year}/{month}/share")
@limiter.limit("10/minute")
async def invite_collaborator(
    request: Request,
    year: int,
    month: int,
    invite: ShareInvite,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Invite another Immich user to contribute picks (requires User role)."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    database.invite_collaborator(user["id"], year, month, invite.collaborator_id)
    return {"status": "invited", "collaborator_id": invite.collaborator_id}


@app.get("/api/curation/{year}/{month}/collaborators")
@limiter.limit("30/minute")
async def get_collaborators(
    request: Request, year: int, month: int,
    user: Dict = Depends(get_current_user),
):
    """List collaborators for a shared curation session."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return {"collaborators": database.get_collaborators(user["id"], year, month)}


@app.get("/api/shared-sessions")
@limiter.limit("30/minute")
async def get_shared_sessions(request: Request, user: Dict = Depends(get_current_user)):
    """Get curation sessions where this user has been invited."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return {"sessions": database.get_shared_sessions(user["id"])}


@app.post("/api/curation/{year}/{month}/shared-pick")
@limiter.limit("30/minute")
async def add_shared_pick(
    request: Request,
    year: int,
    month: int,
    pick: SharedPick,
    owner_id: str = "",
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """
    Contribute a photo pick to a shared curation session (requires User role).
    ``owner_id`` query param specifies whose session to contribute to.
    """
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    if not owner_id:
        raise HTTPException(status_code=400, detail="owner_id query parameter required")

    # Verify the user is actually a collaborator
    collabs = database.get_collaborators(owner_id, year, month)
    if user["id"] not in collabs:
        raise HTTPException(status_code=403, detail="You are not a collaborator on this session")

    database.add_shared_selection(owner_id, year, month, user["id"], pick.asset_id)
    return {"status": "added", "asset_id": pick.asset_id}


@app.get("/api/curation/{year}/{month}/shared-selections")
@limiter.limit("30/minute")
async def get_shared_selections(
    request: Request, year: int, month: int,
    user: Dict = Depends(get_current_user),
):
    """Get all collaborator picks for the owner's session."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return {"selections": database.get_shared_selections(user["id"], year, month)}


# ====================================================================
# Album Sharing — Guest Share Link Endpoints (no auth required)
# ====================================================================

@app.get("/shared/{share_token}", response_class=HTMLResponse)
@limiter.limit("30/minute")
async def view_shared_album(request: Request, share_token: str):
    """View a shared album via guest link (no authentication required)."""
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    share = database.get_share_by_token(share_token)
    if not share:
        raise HTTPException(status_code=410, detail="This share link has expired or been revoked")

    # Log access
    database.log_share_access(
        share["id"],
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent", ""),
    )

    html_path = Path(__file__).parent.parent / "static" / "shared-album.html"
    if html_path.exists():
        return html_path.read_text()

    album_id_safe = html_lib.escape(str(share['album_id']))
    can_add_safe = html_lib.escape(str(bool(share['can_add_photos'])))
    token_safe = html_lib.escape(share_token)
    return HTMLResponse(f"""
    <html><head><title>Shared Album</title></head>
    <body>
        <h1>Shared Album</h1>
        <p>Album ID: {album_id_safe}</p>
        <p>Can add photos: {can_add_safe}</p>
        <p><a href="/api/shared/{token_safe}/photos">View Photos (JSON)</a></p>
    </body></html>
    """)


@app.get("/api/shared/{share_token}")
@limiter.limit("30/minute")
async def get_shared_album_info(request: Request, share_token: str):
    """Get shared album metadata via guest link."""
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    share = database.get_share_by_token(share_token)
    if not share:
        raise HTTPException(status_code=410, detail="This share link has expired or been revoked")

    database.log_share_access(
        share["id"],
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent", ""),
    )

    return {
        "album_id": share["album_id"],
        "can_add_photos": bool(share["can_add_photos"]),
        "guest_label": share.get("guest_label"),
        "expires_at": share.get("expires_at"),
    }


@app.get("/api/shared/{share_token}/photos")
@limiter.limit("30/minute")
async def get_shared_album_photos(request: Request, share_token: str):
    """List photos in a shared album (contributions)."""
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    share = database.get_share_by_token(share_token)
    if not share:
        raise HTTPException(status_code=410, detail="This share link has expired or been revoked")

    contributions = database.get_contributions(share["album_id"])
    return {"album_id": share["album_id"], "photos": contributions}


class GuestPhotoAdd(BaseModel):
    asset_id: str
    contributor_name: str


@app.post("/api/shared/{share_token}/photos")
@limiter.limit("30/minute")
async def add_photo_to_shared_album(
    request: Request, share_token: str, body: GuestPhotoAdd,
):
    """Add a photo to a shared album (guest or user via share link)."""
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    share = database.get_share_by_token(share_token)
    if not share:
        raise HTTPException(status_code=410, detail="This share link has expired or been revoked")

    if not share["can_add_photos"]:
        raise HTTPException(status_code=403, detail="This share does not allow adding photos")

    if not body.contributor_name.strip():
        raise HTTPException(status_code=422, detail="contributor_name is required")

    database.add_contribution(
        share["album_id"], body.asset_id, share["id"], body.contributor_name.strip(),
    )
    return {"status": "added", "asset_id": body.asset_id}


@app.delete("/api/shared/{share_token}/photos/{asset_id}")
@limiter.limit("30/minute")
async def delete_own_contribution(request: Request, share_token: str, asset_id: str):
    """Delete a photo contribution (only if the share token matches the contributor)."""
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    share = database.get_share_by_token(share_token)
    if not share:
        raise HTTPException(status_code=410, detail="This share link has expired or been revoked")

    deleted = database.delete_contribution(share["album_id"], asset_id, share["id"])
    if not deleted:
        raise HTTPException(status_code=403, detail="You can only delete photos you added")

    return {"status": "deleted", "asset_id": asset_id}


# ====================================================================
# Album Sharing — Management Endpoints (authenticated users)
# ====================================================================

class CreateShareRequest(BaseModel):
    shared_with_user_id: Optional[str] = None
    guest_label: Optional[str] = None
    can_add_photos: bool = False
    expires_in_days: Optional[int] = None


class UpdateShareRequest(BaseModel):
    can_add_photos: Optional[bool] = None
    expires_in_days: Optional[int] = None


class RoleUpdate(BaseModel):
    role: str  # "admin", "user", or "guest"


class ServerPathImport(BaseModel):
    source_type: str  # "google", "apple", "icloud"
    server_path: str  # Filesystem path on server


# ------------------------------------------------------------------
# Import job cancellation events (module-level, shared across requests)
# ------------------------------------------------------------------
_import_cancel_events: Dict[int, threading.Event] = {}

IMPORT_STAGING_BASE = Path("data/import-staging")

BLOCKED_SERVER_PATHS = frozenset([
    "/", "/etc", "/root", "/var", "/usr", "/bin", "/sbin",
    "/boot", "/dev", "/proc", "/sys",
])


@app.post("/api/albums/{album_id}/shares")
@limiter.limit("10/minute")
async def create_album_share(
    request: Request,
    album_id: str,
    body: CreateShareRequest,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Create a share link for an album (user share or guest link)."""
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    expires_at = None
    if body.shared_with_user_id:
        # User share — never expires
        expires_at = None
    else:
        # Guest link — configurable expiration
        days = body.expires_in_days
        if days is None:
            days = getattr(request.app.state, "guest_link_default_expiry_days", 30)
        if days and days > 0:
            expires_at = (datetime.now() + timedelta(days=days)).isoformat()

    share = database.create_share(
        album_id=album_id,
        owner_id=user["id"],
        shared_with_user_id=body.shared_with_user_id,
        guest_label=body.guest_label,
        can_add_photos=body.can_add_photos,
        expires_at=expires_at,
    )

    # Build the share URL for guest links
    base_url = str(request.base_url).rstrip("/")
    share["share_url"] = f"{base_url}/shared/{share['share_token']}"

    return share


@app.get("/api/albums/{album_id}/shares")
@limiter.limit("15/minute")
async def list_album_shares(
    request: Request,
    album_id: str,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """List all shares for an album (owner or admin only)."""
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    shares = database.get_album_shares(album_id)
    local_user = user.get("_local_user", {})

    # Only album owner or admin can see shares
    if shares and shares[0]["owner_id"] != user["id"]:
        if Role[local_user.get("role", "guest").upper()] < Role.ADMIN:
            raise HTTPException(status_code=403, detail="Only album owner or admin can view shares")

    return {"shares": shares}


@app.put("/api/albums/{album_id}/shares/{share_id}")
@limiter.limit("10/minute")
async def update_album_share(
    request: Request,
    album_id: str,
    share_id: int,
    body: UpdateShareRequest,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Update share settings (can_add_photos, expiration)."""
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    expires_at = None
    if body.expires_in_days is not None:
        if body.expires_in_days > 0:
            expires_at = (datetime.now() + timedelta(days=body.expires_in_days)).isoformat()

    updated = database.update_share(
        share_id, user["id"],
        can_add_photos=body.can_add_photos,
        expires_at=expires_at,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Share not found or not owned by you")

    return {"status": "updated"}


@app.delete("/api/albums/{album_id}/shares/{share_id}")
@limiter.limit("10/minute")
async def revoke_album_share(
    request: Request,
    album_id: str,
    share_id: int,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Revoke a share link."""
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    revoked = database.revoke_share(share_id, user["id"])
    if not revoked:
        raise HTTPException(status_code=404, detail="Share not found or not owned by you")

    return {"status": "revoked"}


@app.get("/api/albums/{album_id}/contributions")
@limiter.limit("15/minute")
async def get_album_contributions(
    request: Request,
    album_id: str,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """See who added which photos to a shared album."""
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    return {"contributions": database.get_contributions(album_id)}


@app.delete("/api/albums/{album_id}/contributions/{contribution_id}")
@limiter.limit("10/minute")
async def delete_album_contribution(
    request: Request,
    album_id: str,
    contribution_id: int,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Delete any contribution (album owner or admin only)."""
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    deleted = database.delete_contribution_as_owner(contribution_id, album_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Contribution not found")

    return {"status": "deleted"}


@app.get("/api/albums/shared-with-me")
@limiter.limit("15/minute")
async def get_albums_shared_with_me(
    request: Request,
    user: Dict = Depends(get_current_user),
):
    """Get albums shared with the current authenticated user."""
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    return {"shares": database.get_shared_albums_for_user(user["id"])}


@app.get("/api/albums/{album_id}/shares/{share_id}/access-log")
@limiter.limit("10/minute")
async def get_share_access_log(
    request: Request,
    album_id: str,
    share_id: int,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """View access log for a share link (owner or admin only)."""
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    return {"access_log": database.get_share_access_log(share_id)}


# ====================================================================
# Admin — User Management
# ====================================================================

@app.get("/api/admin/users")
@limiter.limit("15/minute")
async def list_users(
    request: Request,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.ADMIN)),
):
    """List all local users with roles (admin only)."""
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return {"users": get_all_users(database)}


@app.put("/api/admin/users/{user_id}/role")
@limiter.limit("10/minute")
async def change_user_role(
    request: Request,
    user_id: int,
    body: RoleUpdate,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.ADMIN)),
):
    """Change a user's role (admin only)."""
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")
    try:
        success = update_user_role(database, user_id, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not success:
        raise HTTPException(status_code=400, detail="Cannot remove the last admin")
    return {"status": "updated"}


def _cluster_face_identities(user_id: str):
    """
    Re-cluster all face embeddings for *user_id* into identity groups.

    Runs synchronously inside the background analysis task.  For typical
    family libraries (<10 000 faces) this completes in well under a second.
    """
    if not database:
        return
    try:
        from .face_recognition_engine import FaceRecognitionEngine  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        rows = database.get_face_embeddings_for_user(user_id)
        if not rows:
            return

        db_ids = [r["id"] for r in rows]
        embeddings = [
            FaceRecognitionEngine.bytes_to_embedding(r["embedding"])
            for r in rows
        ]

        threshold = (
            config.get("ai", {}).get("face_clustering_threshold", 0.6)
            if config else 0.6
        )
        assignment = FaceRecognitionEngine.cluster_embeddings(
            embeddings, embedding_ids=db_ids, threshold=threshold
        )

        # Map cluster_id → existing or newly created identity_id
        cluster_to_identity: Dict[int, int] = {}
        for db_id, cluster_id in assignment.items():
            if cluster_id not in cluster_to_identity:
                identity_id = database.create_face_identity(user_id)
                cluster_to_identity[cluster_id] = identity_id
            database.assign_face_to_identity(db_id, cluster_to_identity[cluster_id])

        # Update photo counts per identity
        for identity_id in cluster_to_identity.values():
            photos = database.get_photos_by_identity(identity_id, user_id)
            database.update_face_identity_photo_count(identity_id, len(photos))

        logger.info(
            f"Face clustering: {len(embeddings)} embeddings → "
            f"{len(cluster_to_identity)} identities for user {user_id}"
        )
    except ImportError:
        logger.debug("face_recognition not installed, skipping clustering")
    except Exception as e:
        logger.error(f"Face clustering error for user {user_id}: {e}")


# ---------------------------------------------------------------------------
# Request/response models for face recognition and scene detection endpoints
# ---------------------------------------------------------------------------

class IdentityLabelRequest(BaseModel):
    label: str


class MergeIdentitiesRequest(BaseModel):
    source_identity_id: int
    target_identity_id: int


# ---------------------------------------------------------------------------
# Face Recognition endpoints
# ---------------------------------------------------------------------------

@app.get("/api/faces/identities")
@limiter.limit("30/minute")
async def get_face_identities(
    request: Request,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """List all detected people (identity clusters) for the authenticated user."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    identities = database.get_face_identities(user["id"])
    # Strip binary embedding blobs before returning JSON
    for ident in identities:
        ident.pop("representative_embedding", None)
    return {"identities": identities}


@app.get("/api/faces/identities/{identity_id}/photos")
@limiter.limit("30/minute")
async def get_identity_photos(
    request: Request,
    identity_id: int,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Get all photos containing a specific detected person."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    user_id = user["id"]
    identity = database.get_face_identity(identity_id, user_id)
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found")
    photos = database.get_photos_by_identity(identity_id, user_id)

    # Enrich with thumbnail URLs
    user_client = ImmichClient(app.state.immich_api_url, user["access_token"])
    for photo in photos:
        photo["thumbnail_url"] = user_client.get_thumbnail_url(photo["asset_id"])

    return {
        "identity_id": identity_id,
        "label": identity.get("label"),
        "photo_count": identity.get("photo_count", 0),
        "photos": photos,
    }


@app.put("/api/faces/identities/{identity_id}")
@limiter.limit("30/minute")
async def label_face_identity(
    request: Request,
    identity_id: int,
    body: IdentityLabelRequest,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Name a detected face cluster (e.g. 'Mom', 'Alice')."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    updated = database.update_face_identity_label(identity_id, user["id"], body.label)
    if not updated:
        raise HTTPException(status_code=404, detail="Identity not found")
    return {"status": "updated", "identity_id": identity_id, "label": body.label}


@app.post("/api/faces/identities/merge")
@limiter.limit("10/minute")
async def merge_face_identities(
    request: Request,
    body: MergeIdentitiesRequest,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Merge two identity clusters that represent the same person."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    success = database.merge_face_identities(
        user["id"], body.source_identity_id, body.target_identity_id
    )
    if not success:
        raise HTTPException(
            status_code=404,
            detail="One or both identities not found or not owned by you",
        )
    return {
        "status": "merged",
        "target_identity_id": body.target_identity_id,
    }


@app.get("/api/faces/photo/{asset_id}")
@limiter.limit("30/minute")
async def get_photo_faces(
    request: Request,
    asset_id: str,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Get all detected faces (with identity labels) for a specific photo."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    faces = database.get_face_embeddings_for_asset(asset_id)
    # Never expose raw embedding bytes in the API
    for face in faces:
        face.pop("embedding", None)
    return {"asset_id": asset_id, "faces": faces}


# ---------------------------------------------------------------------------
# Scene Detection endpoints
# ---------------------------------------------------------------------------

@app.get("/api/scenes/categories")
@limiter.limit("30/minute")
async def get_scene_categories(
    request: Request,
    year: Optional[int] = None,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Get available scene categories with photo counts for the authenticated user."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    distribution = database.get_scene_distribution(user["id"], year=year)
    categories = [
        {"category": cat, "count": count}
        for cat, count in distribution.items()
    ]
    return {"categories": categories, "year": year}


@app.get("/api/scenes/{category}/photos")
@limiter.limit("30/minute")
async def get_scene_photos(
    request: Request,
    category: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Get photos classified under a given scene super-category."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    photos = database.get_photos_by_scene(
        user["id"], category, year=year, month=month
    )
    user_client = ImmichClient(app.state.immich_api_url, user["access_token"])
    for photo in photos:
        photo["thumbnail_url"] = user_client.get_thumbnail_url(photo["asset_id"])
    return {
        "category": category,
        "year": year,
        "month": month,
        "total": len(photos),
        "photos": photos,
    }


@app.get("/api/scenes/distribution")
@limiter.limit("30/minute")
async def get_scene_distribution(
    request: Request,
    year: Optional[int] = None,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Get scene distribution chart data for the authenticated user."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    distribution = database.get_scene_distribution(user["id"], year=year)
    return {
        "year": year,
        "distribution": distribution,
        "labels": list(distribution.keys()),
        "values": list(distribution.values()),
    }


# ------------------------------------------------------------------
# Import helpers & background task
# ------------------------------------------------------------------

def _load_importer_class(source_type: str):
    """Dynamically load an importer class from the migration-tools directory."""
    base = Path(__file__).resolve().parent.parent.parent / "migration-tools"
    file_map = {
        "google": ("google-photos-import.py", "GooglePhotosImporter"),
        "apple": ("apple-photos-import.py", "ApplePhotosImporter"),
        "icloud": ("icloud-import.py", "ICloudImporter"),
        "folder": ("folder-import.py", "FolderImporter"),
    }
    filename, class_name = file_map[source_type]
    spec = importlib.util.spec_from_file_location(
        f"migration_{source_type}", base / filename
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, class_name)


def _run_import_sync(
    job_id: int,
    user_id: str,
    user_token: str,
    source_type: str,
    directory: str,
    import_method: str,
):
    """Run an import job synchronously (called via BackgroundTasks)."""
    try:
        immich_url = app.state.immich_base_url
        ImporterClass = _load_importer_class(source_type)

        # Create importer — SSO token works as api_key for Immich API
        if source_type in ("google", "apple", "icloud", "folder"):
            importer = ImporterClass(Path(directory), immich_url, user_token)
        else:
            database.update_import_job_status(job_id, "failed", f"Unknown source: {source_type}")
            return

        # Override progress file so it doesn't pollute cwd
        importer.progress_file = Path(directory) / f"{source_type}-import-progress.json"

        # -- Scan phase --
        database.update_import_job_status(job_id, "scanning")

        if source_type == "google":
            photos_dir = importer.find_google_photos_dir()
            if not photos_dir:
                database.update_import_job_status(job_id, "failed", "Could not find Google Photos directory in export")
                return
            photo_files = [
                f for f in photos_dir.rglob("*")
                if importer.is_supported_file(f) and not str(f).endswith(".json")
            ]
        elif source_type in ("apple", "folder"):
            photo_files = importer._scan_files()
        else:  # icloud
            photos_root = importer.find_photos_root()
            from pathlib import Path as _P  # already imported, but for clarity
            icloud_exts = {
                '.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff', '.bmp',
                '.heic', '.heif', '.dng', '.raw', '.arw', '.cr2', '.cr3', '.nef',
                '.mp4', '.mov', '.avi', '.mkv', '.m4v',
            }
            photo_files = [
                p for p in photos_root.rglob("*")
                if p.is_file() and p.suffix.lower() in icloud_exts
            ]

        importer.stats["total_files"] = len(photo_files)
        database.update_import_job_progress(job_id, {**importer.stats, "status": "running"})

        if not photo_files:
            database.update_import_job_status(job_id, "completed", "No files found to import")
            return

        # -- Upload loop --
        cancel_event = _import_cancel_events.get(job_id)
        for i, photo_path in enumerate(photo_files):
            if cancel_event and cancel_event.is_set():
                database.update_import_job_status(job_id, "cancelled")
                break

            if source_type == "google":
                metadata_json = importer.find_photo_metadata(photo_path)
                metadata = importer.extract_metadata(metadata_json) if metadata_json else None
                importer.upload_file(photo_path, metadata)
            elif source_type in ("apple", "folder"):
                importer._upload_file(photo_path)
            else:  # icloud
                importer._upload_file(photo_path, photos_root)

            # Update DB every 10 files
            if (i + 1) % 10 == 0:
                database.update_import_job_progress(job_id, importer.stats)
        else:
            # Loop completed without cancel
            database.update_import_job_progress(
                job_id, {**importer.stats, "status": "completed"}
            )
            database.update_import_job_status(job_id, "completed")

    except Exception as e:
        logger.error(f"Import job {job_id} failed: {e}", exc_info=True)
        database.update_import_job_status(job_id, "failed", str(e))
    finally:
        _import_cancel_events.pop(job_id, None)
        # Clean up staging dir for browser uploads
        if import_method == "upload":
            shutil.rmtree(directory, ignore_errors=True)


# ------------------------------------------------------------------
# Import endpoints
# ------------------------------------------------------------------


@app.post("/api/import/upload")
@limiter.limit("10/minute")
async def upload_import_files(
    request: Request,
    source_type: str = Form(...),
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Upload files via browser and start an import job."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    if source_type not in ("google", "apple", "icloud", "folder"):
        raise HTTPException(status_code=400, detail="source_type must be google, apple, icloud, or folder")
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Create staging directory
    staging_dir = IMPORT_STAGING_BASE / user["id"] / str(uuid.uuid4())
    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        for upload_file in files:
            # webkitdirectory uploads include relative paths in filename
            relative_path = Path(upload_file.filename) if upload_file.filename else Path(f"file_{uuid.uuid4()}")
            dest = staging_dir / relative_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                while chunk := await upload_file.read(1024 * 1024):
                    f.write(chunk)
    except Exception as e:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"File save failed: {e}")

    job_id = database.create_import_job(
        user_id=user["id"],
        source_type=source_type,
        import_method="upload",
        staging_dir=str(staging_dir),
    )
    _import_cancel_events[job_id] = threading.Event()

    background_tasks.add_task(
        _run_import_sync,
        job_id, user["id"], user["access_token"],
        source_type, str(staging_dir), "upload",
    )

    return {"job_id": job_id, "status": "started", "file_count": len(files)}


@app.post("/api/import/start")
@limiter.limit("5/minute")
async def start_server_path_import(
    request: Request,
    body: ServerPathImport,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.ADMIN)),
):
    """Start an import from a server filesystem path (admin only)."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    if body.source_type not in ("google", "apple", "icloud"):
        raise HTTPException(status_code=400, detail="source_type must be google, apple, or icloud")

    server_path = Path(body.server_path)
    if not server_path.exists() or not server_path.is_dir():
        raise HTTPException(status_code=400, detail="Server path does not exist or is not a directory")

    resolved = str(server_path.resolve())
    if resolved in BLOCKED_SERVER_PATHS:
        raise HTTPException(status_code=400, detail="Path not allowed")

    job_id = database.create_import_job(
        user_id=user["id"],
        source_type=body.source_type,
        import_method="server_path",
        server_path=resolved,
    )
    _import_cancel_events[job_id] = threading.Event()

    background_tasks.add_task(
        _run_import_sync,
        job_id, user["id"], user["access_token"],
        body.source_type, resolved, "server_path",
    )

    return {"job_id": job_id, "status": "started"}


@app.get("/api/import/jobs")
@limiter.limit("30/minute")
async def list_import_jobs(
    request: Request,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """List all import jobs for the authenticated user."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    jobs = database.get_import_jobs_for_user(user["id"])
    return {"jobs": jobs}


@app.get("/api/import/jobs/{job_id}")
@limiter.limit("60/minute")
async def get_import_job_status(
    request: Request,
    job_id: int,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Get status and progress of an import job."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    job = database.get_import_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return job


@app.delete("/api/import/jobs/{job_id}")
@limiter.limit("10/minute")
async def cancel_import_job(
    request: Request,
    job_id: int,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Cancel a running import job."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    job = database.get_import_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    if job["status"] not in ("pending", "scanning", "running"):
        raise HTTPException(status_code=400, detail="Job is not running")

    cancel_event = _import_cancel_events.get(job_id)
    if cancel_event:
        cancel_event.set()
    else:
        database.update_import_job_status(job_id, "cancelled")

    return {"status": "cancelling", "job_id": job_id}


# ── Event / Trip Detection ────────────────────────────────────────────────────

MIN_EVENT_PHOTOS = 20  # Clusters smaller than this are silently ignored

# Scene category → descriptive kind label (single-day / multi-day variants)
_SCENE_KIND: Dict[str, tuple] = {
    # (single-day label, multi-day label)
    "beach":    ("Beach Day",     "Beach Trip"),
    "mountain": ("Hike",          "Mountain Trip"),
    "urban":    ("City Day",      "City Trip"),
    "nature":   ("Nature Walk",   "Nature Trip"),
    "food":     ("Dining Out",    "Food Tour"),
    "sports":   ("Sports Event",  "Sports Trip"),
    "night":    ("Night Out",     "Night Trip"),
    "event":    ("Event",         "Trip"),
    "indoor":   ("Gathering",     "Trip"),
    "outdoor":  ("Day Out",       "Outdoor Trip"),
}
# Minimum fraction of classified photos that must share a scene to use it
_SCENE_DOMINANCE_THRESHOLD = 0.40

# Simple in-memory cache: (rounded_lat, rounded_lon) → location string
_geocode_cache: Dict[tuple, Optional[str]] = {}


def _reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """Return a human-readable location label via Nominatim (free, no API key).

    Rounds coordinates to ~1 km precision before caching so nearby points
    share the same cache entry.  Returns None on any error so callers can
    gracefully fall back to a date-only title.
    """
    import time as _time
    key = (round(lat, 2), round(lon, 2))
    if key in _geocode_cache:
        return _geocode_cache[key]

    try:
        import requests as _req
        r = _req.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 10},
            headers={"User-Agent": "immich-photo-curator/1.0"},
            timeout=4,
        )
        r.raise_for_status()
        addr = r.json().get("address", {})
        city = (
            addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("county")
        )
        country = addr.get("country_code", "").upper()
        label = f"{city}, {country}" if city and country else city or None
        _geocode_cache[key] = label
        _time.sleep(0.5)  # Nominatim rate limit: 1 req/s
        return label
    except Exception:
        _geocode_cache[key] = None
        return None


def _cluster_photos_into_events(
    assets: List[Dict],
    user_id: str,
    db,  # Database instance — used for scene, face, and score queries
) -> List[Dict]:
    """Cluster a list of Immich assets into trip/event suggestions.

    Two-pass algorithm:
    Pass 1 — split into photo sessions wherever consecutive photos are > 4 hours apart.
             This groups photos taken in a single continuous outing (e.g. morning hike,
             evening dinner).
    Pass 2 — merge adjacent sessions that are < 24 hours apart end-to-start.
             This keeps multi-day trips together: overnight gaps (8–12 h) between
             Day 1 and Day 2 photos don't split a trip into separate albums.
             A true gap ≥ 24 hours means a genuinely different event.

    After merging, skip clusters with fewer than MIN_EVENT_PHOTOS total photos.

    Each qualifying cluster is enriched with:
    - Scene distribution (beach, mountain, urban…) → descriptive kind label
    - Labeled face identities → participants list ("Mom", "John", …)
    - GPS median → Nominatim reverse-geocoded location label
    - Best-scored thumbnail (actual AI score, not just "first scored photo")
    """
    def _parse_ts(asset: Dict) -> Optional[datetime]:
        for field in ("fileCreatedAt", "localDateTime", "takenAt"):
            val = asset.get(field)
            if val:
                try:
                    ts = val.rstrip("Z").replace("T", " ")
                    return datetime.fromisoformat(ts)
                except ValueError:
                    pass
        return None

    # Attach parsed timestamps and drop photos we can't date
    dated = []
    for a in assets:
        ts = _parse_ts(a)
        if ts:
            dated.append((ts, a))

    if not dated:
        return []

    dated.sort(key=lambda x: x[0])

    # Pass 1: split into photo sessions (4-hour intra-session gap)
    sessions: List[List[tuple]] = []
    current: List[tuple] = [dated[0]]
    for ts, asset in dated[1:]:
        gap_h = (ts - current[-1][0]).total_seconds() / 3600
        if gap_h > 4:
            sessions.append(current)
            current = [(ts, asset)]
        else:
            current.append((ts, asset))
    sessions.append(current)

    # Pass 2: merge sessions separated by < 24 hours (handles overnight trip gaps)
    merged: List[List[tuple]] = [sessions[0]]
    for session in sessions[1:]:
        prev_end = merged[-1][-1][0]
        this_start = session[0][0]
        gap_h = (this_start - prev_end).total_seconds() / 3600
        if gap_h < 24:
            merged[-1].extend(session)   # same trip
        else:
            merged.append(session)       # genuinely different event

    clusters = merged

    def _day(ts: datetime) -> str:
        return str(ts.day)

    events = []
    for cluster in clusters:
        if len(cluster) < MIN_EVENT_PHOTOS:
            continue

        start_ts, _ = cluster[0]
        end_ts, _ = cluster[-1]
        asset_ids = [a["id"] for _, a in cluster]
        delta_days = (end_ts.date() - start_ts.date()).days

        # ── Format date string ────────────────────────────────────────────
        if delta_days == 0:
            date_str = f"{start_ts.strftime('%B')} {_day(start_ts)}, {start_ts.year}"
        elif start_ts.month == end_ts.month and start_ts.year == end_ts.year:
            date_str = f"{start_ts.strftime('%B')} {_day(start_ts)}–{_day(end_ts)}, {start_ts.year}"
        else:
            date_str = (
                f"{start_ts.strftime('%b')} {_day(start_ts)}"
                f" – {end_ts.strftime('%b')} {_day(end_ts)}, {end_ts.year}"
            )

        # ── Scene-based kind label ────────────────────────────────────────
        # Query which scene categories appear across the cluster's photos.
        scene_dist = db.get_scene_distribution_for_assets(user_id, asset_ids)
        classified_count = sum(scene_dist.values())
        kind = "Trip" if delta_days >= 2 else "Event"  # fallback
        if classified_count > 0:
            dominant_scene = max(scene_dist, key=scene_dist.get)
            dominance = scene_dist[dominant_scene] / classified_count
            if dominance >= _SCENE_DOMINANCE_THRESHOLD and dominant_scene in _SCENE_KIND:
                single_label, multi_label = _SCENE_KIND[dominant_scene]
                kind = multi_label if delta_days >= 2 else single_label

        # ── GPS → location label ─────────────────────────────────────────
        lats, lons = [], []
        for _, a in cluster:
            exif = a.get("exifInfo") or {}
            lat = exif.get("latitude")
            lon = exif.get("longitude")
            if lat is not None and lon is not None:
                lats.append(float(lat))
                lons.append(float(lon))

        location_label = None
        if lats:
            lats.sort(); lons.sort()
            mid = len(lats) // 2
            location_label = _reverse_geocode(lats[mid], lons[mid])

        # ── Face participants ─────────────────────────────────────────────
        participants = db.get_labeled_faces_for_assets(user_id, asset_ids)

        # ── Build title ───────────────────────────────────────────────────
        # Format: "{Location · }{Kind} · {Date}"
        # e.g. "Paris, FR · Beach Trip · June 2–7, 2024"
        #      "Mountain Hike · March 15, 2024"
        parts = []
        if location_label:
            parts.append(location_label)
        parts.append(kind)
        parts.append(date_str)
        title = " · ".join(parts)

        # ── Best thumbnail ────────────────────────────────────────────────
        # Pick highest-scored photo; fall back to first asset in cluster.
        best_id = db.get_best_scored_asset(user_id, asset_ids) or asset_ids[0]

        events.append({
            "title": title,
            "start_date": start_ts.isoformat(),
            "end_date": end_ts.isoformat(),
            "photo_count": len(cluster),
            "thumbnail_asset_id": best_id,
            "asset_ids": asset_ids,
            "participants": participants,
        })

    return events


@app.get("/events", response_class=HTMLResponse)
async def events_ui(request: Request, user: Dict = Depends(require_user_page)):
    """Serve the Events & Trips page."""
    with open(Path(__file__).parent.parent / "static" / "events.html") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/events")
@limiter.limit("30/minute")
async def get_event_suggestions(
    request: Request,
    user: Dict = Depends(get_current_user),
):
    """Return saved (non-dismissed) event suggestions for the current user."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    suggestions = database.get_event_suggestions(user["id"])
    return {"events": suggestions}


@app.post("/api/events/detect")
@limiter.limit("5/minute")
async def detect_events(
    request: Request,
    year: Optional[int] = None,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Run event/trip detection for the user and persist results.

    Pass ?year=2024 to scan a specific year; defaults to current year.
    Returns the updated list of non-dismissed suggestions.
    """
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    scan_year = year or datetime.now().year
    user_id = user["id"]

    try:
        user_client = admin_immich_client or ImmichClient(app.state.immich_api_url, user["access_token"])
        assets = user_client.get_photos_for_year(user_id, scan_year)

        events = _cluster_photos_into_events(assets, user_id, database)
        database.save_event_suggestions(user_id, events)

        suggestions = database.get_event_suggestions(user_id)
        return {"events": suggestions, "detected": len(events), "scanned": len(assets)}

    except Exception as e:
        logger.error(f"Event detection failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/events/{event_id}/dismiss")
@limiter.limit("30/minute")
async def dismiss_event_suggestion(
    request: Request,
    event_id: int,
    user: Dict = Depends(get_current_user),
):
    """Permanently hide an event suggestion. It will not reappear on re-scan."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    ok = database.dismiss_event_suggestion(user["id"], event_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return {"status": "dismissed"}


@app.post("/api/events/{event_id}/create-album")
@limiter.limit("10/minute")
async def create_album_from_event(
    request: Request,
    event_id: int,
    body: EventAlbumCreate,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    """Create an Immich album from a detected event suggestion."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    suggestions = database.get_event_suggestions(user["id"])
    suggestion = next((s for s in suggestions if s["id"] == event_id), None)
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    try:
        user_client = ImmichClient(app.state.immich_api_url, user["access_token"])
        album = user_client.create_album(
            body.album_name,
            suggestion["asset_ids"],
            description=f"Auto-detected: {suggestion['title']}",
        )
        if not album:
            raise HTTPException(status_code=500, detail="Failed to create album in Immich")

        database.mark_event_album_created(user["id"], event_id, album["id"])

        return {"status": "created", "album": album, "photo_count": suggestion["photo_count"]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create album from event {event_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/processing", response_class=HTMLResponse)
async def processing_page(request: Request, user: Dict = Depends(require_user_page)):
    """Serve batch processing UI (requires User role)."""
    html_path = Path(__file__).parent.parent / "static" / "processing.html"
    if html_path.exists():
        return html_path.read_text()
    return HTMLResponse("<h1>Processing page not found</h1>", status_code=404)


# =============================================================================
# Batch Processing API
# =============================================================================

class BatchStartRequest(BaseModel):
    mode: str = "incremental"  # incremental | missing_vectors | full | retry_errors
    user_id: Optional[str] = None


class BatchConfigSave(BaseModel):
    batch_size: Optional[int] = None
    delay_between_batches: Optional[int] = None
    max_cpu_percent: Optional[int] = None
    schedule_enabled: Optional[bool] = None
    time_window_start: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    time_window_end: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    default_mode: Optional[Literal["incremental", "missing_vectors", "full", "retry_errors"]] = None


@app.get("/api/batch/status")
@limiter.limit("60/minute")
async def batch_status(
    request: Request,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.ADMIN)),
):
    """Get current batch job status + last 20 log entries."""
    if not batch_processor:
        raise HTTPException(503, "Batch processor not available (admin API key required)")
    return await batch_processor.get_status()


@app.post("/api/batch/start")
@limiter.limit("5/minute")
async def batch_start(
    request: Request,
    body: BatchStartRequest,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.ADMIN)),
):
    """Start a batch processing job."""
    if not batch_processor:
        raise HTTPException(503, "Batch processor not available (admin API key required)")
    valid_modes = {"incremental", "missing_vectors", "full", "retry_errors"}
    if body.mode not in valid_modes:
        raise HTTPException(400, f"Invalid mode. Must be one of: {', '.join(valid_modes)}")
    try:
        job_id = await batch_processor.start_job(mode=body.mode, user_id=body.user_id)
        return {"job_id": job_id, "mode": body.mode, "message": "Batch job started"}
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/batch/cancel")
@limiter.limit("10/minute")
async def batch_cancel(
    request: Request,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.ADMIN)),
):
    """Cancel the current running batch job."""
    if not batch_processor:
        raise HTTPException(503, "Batch processor not available (admin API key required)")
    cancelled = await batch_processor.cancel_job()
    if cancelled:
        return {"message": "Batch job cancelled"}
    return {"message": "No running job to cancel"}


@app.get("/api/batch/history")
@limiter.limit("30/minute")
async def batch_history(
    request: Request,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.ADMIN)),
):
    """Return the last 10 completed/failed/cancelled batch jobs."""
    if not batch_processor:
        raise HTTPException(503, "Batch processor not available (admin API key required)")
    return await batch_processor.get_history(limit=10)


@app.get("/api/batch/errors/{job_id}")
@limiter.limit("30/minute")
async def batch_errors(
    request: Request,
    job_id: str,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.ADMIN)),
):
    """Return all per-photo errors for a specific job."""
    if not batch_processor:
        raise HTTPException(503, "Batch processor not available (admin API key required)")
    errors = await batch_processor.get_errors(job_id)
    return {"job_id": job_id, "errors": errors, "count": len(errors)}


@app.post("/api/batch/config")
@limiter.limit("10/minute")
async def batch_config_save(
    request: Request,
    body: BatchConfigSave,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.ADMIN)),
):
    """Save batch processing config to config.yaml."""
    config_path = Path("config/config.yaml")
    if not config_path.exists():
        raise HTTPException(404, "config/config.yaml not found")

    with open(config_path) as f:
        current_config = yaml.safe_load(f)

    # Update nested config values
    bp = current_config.setdefault("batch_processing", {})
    cadence = bp.setdefault("cadence", {})
    schedule = bp.setdefault("schedule", {})

    if body.batch_size is not None:
        cadence["batch_size"] = body.batch_size
    if body.delay_between_batches is not None:
        cadence["delay_between_batches"] = body.delay_between_batches
    if body.max_cpu_percent is not None:
        cadence["max_cpu_percent"] = body.max_cpu_percent
    if body.schedule_enabled is not None:
        schedule["enabled"] = body.schedule_enabled
    if body.time_window_start is not None:
        schedule["time_window_start"] = body.time_window_start
    if body.time_window_end is not None:
        schedule["time_window_end"] = body.time_window_end
    if body.default_mode is not None:
        bp["default_mode"] = body.default_mode

    with open(config_path, "w") as f:
        yaml.dump(current_config, f, default_flow_style=False, allow_unicode=True)

    # Update live config in batch_processor
    if batch_processor:
        batch_processor._config = bp

    return {"message": "Config saved. Cadence settings take effect immediately. GPU/worker settings require restart."}


@app.get("/api/batch/gpu-status")
@limiter.limit("30/minute")
async def batch_gpu_status(
    request: Request,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.ADMIN)),
):
    """Return GPU detection status and VRAM info."""
    if not gpu_manager:
        return {"cuda_available": False, "device_name": "CPU", "initialized": False}
    return gpu_manager.get_status()


def main():
    """Run the server"""
    try:
        # Load config
        config_path = Path("config/config.yaml")
        if config_path.exists():
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
        else:
            cfg = {
                "server": {"host": "0.0.0.0", "port": 8081, "workers": 2}
            }

        uvicorn.run(
            "src.main:app",
            host=cfg["server"]["host"],
            port=cfg["server"]["port"],
            workers=cfg["server"].get("workers", 2),
            log_level="info",
            reload=False
        )
    except Exception as e:
        print(f"Error starting server: {e}")
        exit(1)


if __name__ == "__main__":
    main()
