"""
Main FastAPI application for Photo Curator Assistant
Complete AI-powered photo curation with Immich authentication integration
"""

import sys
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
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
import sdnotify
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Add project root to path for shared library
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from .database import Database
from .immich_client import ImmichClient, PhotoCache
from .analyzer import PhotoAnalyzer
from .auth import ImmichAuth, get_current_user, get_current_user_optional, get_user_api_client
from .notifications import EmailNotifier
from .logging_config import setup_json_logging
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
    # Photo curator uses Tailwind CDN, Chart.js CDN, and Leaflet map tiles
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://unpkg.com; "
        "img-src 'self' data: blob: https://*.tile.openstreetmap.org; "
        "connect-src 'self'; "
        "font-src 'self' https://cdn.jsdelivr.net; "
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


@app.on_event("startup")
async def startup_event():
    """Initialize application"""
    global config, database, admin_immich_client, photo_cache, analyzer, scheduler, email_notifier

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

        # Initialize analyzer
        analyzer = PhotoAnalyzer(config)

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

        # Watchdog heartbeat (every 30s, half of WatchdogSec=60)
        async def _watchdog_heartbeat():
            sd = sdnotify.SystemdNotifier(debug=False)
            sd.notify("WATCHDOG=1")

        scheduler.add_job(_watchdog_heartbeat, "interval", seconds=30, id="watchdog")

        scheduler.start()
        logger.info(f"Scheduler started (monthly reminders at {reminder_time})")

        # Signal systemd that we are ready
        sd = sdnotify.SystemdNotifier(debug=False)
        sd.notify("READY=1")

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
        }
    else:
        immich_auth = app.state.immich_auth
        return {
            "authenticated": False,
            "login_url": f"{immich_auth.immich_url}/auth/login"
        }


async def require_user_page(request: Request) -> Dict:
    """Dependency for HTML page routes requiring at least USER role.

    Redirects to login if unauthenticated, returns 403 if insufficient role.
    """
    immich_auth = request.app.state.immich_auth
    user = immich_auth.get_user_from_request(request)
    if not user:
        raise HTTPException(
            status_code=302,
            headers={"Location": immich_auth.login_redirect_url(request)},
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
async def root(request: Request, user: Dict = Depends(require_user_page)):
    """Serve curator UI (requires User role)"""

    html_path = Path(__file__).parent.parent / "static" / "curator.html"
    if html_path.exists():
        return html_path.read_text()

    # Return placeholder if static file doesn't exist
    return f"""
    <html>
        <head>
            <title>Photo Curator</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: #f5f5f5;
                    padding: 20px;
                }}
                .container {{ max-width: 800px; margin: 0 auto; }}
                .card {{
                    background: white;
                    padding: 30px;
                    border-radius: 12px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    margin-bottom: 20px;
                }}
                h1 {{ color: #2563eb; margin-bottom: 10px; }}
                .user-info {{
                    background: #f0f9ff;
                    padding: 15px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                }}
                .button {{
                    background: #2563eb;
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 6px;
                    cursor: pointer;
                    text-decoration: none;
                    display: inline-block;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="card">
                    <h1>📸 Photo Curator</h1>
                    <div class="user-info">
                        <strong>Logged in as:</strong> {user.get('name', user.get('email'))}
                    </div>
                    <p>Select a month to start curating your photos</p>
                    <br>
                    <a href="/curate" class="button">Start Curating</a>
                    <a href="/docs" class="button" style="background:#6b7280">API Docs</a>
                </div>
            </div>
        </body>
    </html>
    """


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
    if not admin_immich_client or not analyzer or not database:
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

        # Create user-specific API client
        user_client = ImmichClient(app.state.immich_api_url, user_token)

        # Fetch photos from Immich (using user's credentials)
        photos = user_client.get_user_photos(user_id, year, month)

        if not photos:
            logger.warning(f"No photos found for {year}-{month:02d}")
            return

        logger.info(f"Analyzing {len(photos)} photos...")

        # Analyze each photo
        for i, photo in enumerate(photos):
            asset_id = photo['id']

            # Check if already analyzed
            existing_scores = database.get_photo_scores(user_id, year, month)
            if any(score['asset_id'] == asset_id for score in existing_scores):
                continue

            # Download photo (use thumbnail for speed)
            cached_path = photo_cache.get_cached_path(asset_id)
            if not cached_path:
                photo_path = user_client.download_photo(asset_id, use_thumbnail=True)
                if photo_path:
                    cached_path = photo_cache.add_to_cache(asset_id, photo_path)

            if cached_path:
                # Analyze photo
                scores = analyzer.analyze_photo(cached_path)

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

        # Find duplicates
        all_scores = database.get_photo_scores(user_id, year, month)
        photos_with_hash = [
            {'id': s['asset_id'], 'perceptual_hash': s['perceptual_hash']}
            for s in all_scores
            if s.get('perceptual_hash')
        ]

        duplicates = analyzer.find_duplicates(photos_with_hash)
        for dup_group in duplicates:
            database.save_duplicate_group(dup_group)

        logger.info(f"Analysis complete! Suggested {len(ai_suggested)} photos")
        logger.info(f"Found {len(duplicates)} duplicate groups")

        # Cluster face embeddings into identity groups
        _cluster_face_identities(user_id)

    except Exception as e:
        logger.error(f"Error in background analysis: {e}")


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

    # Get scores from database
    scores = database.get_photo_scores(user_id, year, month)

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

    return HTMLResponse(f"""
    <html><head><title>Shared Album</title></head>
    <body>
        <h1>Shared Album</h1>
        <p>Album ID: {share['album_id']}</p>
        <p>Can add photos: {bool(share['can_add_photos'])}</p>
        <p><a href="/api/shared/{share_token}/photos">View Photos (JSON)</a></p>
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
        if source_type == "google":
            importer = ImporterClass(Path(directory), immich_url, user_token)
        elif source_type == "apple":
            importer = ImporterClass(Path(directory), immich_url, user_token)
        elif source_type == "icloud":
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
        elif source_type == "apple":
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
            elif source_type == "apple":
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

@app.get("/import", response_class=HTMLResponse)
async def import_ui(request: Request, user: Dict = Depends(require_user_page)):
    """Serve import wizard UI."""
    html_path = Path(__file__).parent.parent / "static" / "import.html"
    if html_path.exists():
        return html_path.read_text()
    return HTMLResponse("<h1>Import page not found</h1>", status_code=404)


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
    if source_type not in ("google", "apple", "icloud"):
        raise HTTPException(status_code=400, detail="source_type must be google, apple, or icloud")
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
