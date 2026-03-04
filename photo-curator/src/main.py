"""
Main FastAPI application for Photo Curator Assistant
Complete AI-powered photo curation with Immich authentication integration
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import os
import uvicorn
import yaml
import logging
import asyncio
import re
import sdnotify
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .database import Database
from .immich_client import ImmichClient, PhotoCache
from .analyzer import PhotoAnalyzer
from .auth import ImmichAuth, get_current_user, get_current_user_optional, get_user_api_client
from .notifications import EmailNotifier
from .logging_config import setup_json_logging

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


_ALLOWED_ORIGINS = [
    "http://localhost:8081",
    "http://127.0.0.1:8081",
    "http://localhost:2283",
    "http://127.0.0.1:2283",
]


@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    """Block cross-origin state-changing requests (CSRF protection)."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            origin = request.headers.get("Origin") or request.headers.get("Referer", "")
            if origin and not any(origin.startswith(o) for o in _ALLOWED_ORIGINS):
                logger.warning("CSRF blocked: origin=%s", origin)
                return JSONResponse(status_code=403, content={"detail": "Cross-origin request blocked"})
    return await call_next(request)


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
    """Check if user is authenticated"""
    if user:
        return {
            "authenticated": True,
            "user": {
                "id": user.get("id"),
                "email": user.get("email"),
                "name": user.get("name")
            }
        }
    else:
        immich_auth = app.state.immich_auth
        return {
            "authenticated": False,
            "login_url": f"{immich_auth.immich_url}/auth/login"
        }


# Web UI
@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user: Optional[Dict] = Depends(get_current_user_optional)):
    """Serve curator UI"""

    # If not authenticated, redirect to Immich login
    if not user:
        immich_auth = app.state.immich_auth
        login_url = immich_auth.login_redirect_url(request)
        return RedirectResponse(url=login_url)

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
    user: Dict = Depends(get_current_user)
):
    """Analyze all photos for authenticated user's month"""
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
                    # Save to database
                    database.save_photo_score(asset_id, user_id, year, month, scores)

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
    user: Dict = Depends(get_current_user)
):
    """Update authenticated user's curation selections"""
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
    user: Dict = Depends(get_current_user)
):
    """Complete curation and create album in Immich (using user's credentials)"""
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
async def preferences_ui(request: Request, user: Optional[Dict] = Depends(get_current_user_optional)):
    """Serve preferences UI"""
    if not user:
        immich_auth = app.state.immich_auth
        login_url = immich_auth.login_redirect_url(request)
        return RedirectResponse(url=login_url)

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
    user: Dict = Depends(get_current_user)
):
    """Update user preferences"""
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
async def analytics_ui(request: Request, user: Optional[Dict] = Depends(get_current_user_optional)):
    """Serve analytics dashboard (accessible to all authenticated users)"""
    if not user:
        immich_auth = app.state.immich_auth
        login_url = immich_auth.login_redirect_url(request)
        return RedirectResponse(url=login_url)

    html_path = Path(__file__).parent.parent / "static" / "analytics.html"
    if html_path.exists():
        return html_path.read_text()

    return HTMLResponse("<h1>Analytics Dashboard not found</h1>", status_code=404)


@app.get("/api/analytics")
@limiter.limit("15/minute")
async def get_analytics(request: Request, period: int = 30, user: Dict = Depends(get_current_user)):
    """Get analytics data (accessible to all authenticated users)"""
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
async def duplicates_ui(request: Request, user: Optional[Dict] = Depends(get_current_user_optional)):
    """Serve duplicate manager UI"""
    if not user:
        immich_auth = app.state.immich_auth
        login_url = immich_auth.login_redirect_url(request)
        return RedirectResponse(url=login_url)

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
    user: Dict = Depends(get_current_user)
):
    """Delete duplicate photos from Immich (user must own the assets)"""
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
async def year_in_review_ui(request: Request, user: Optional[Dict] = Depends(get_current_user_optional)):
    """Serve Year in Review page."""
    if not user:
        return RedirectResponse(url=app.state.immich_auth.login_redirect_url(request))
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
async def map_ui(request: Request, user: Optional[Dict] = Depends(get_current_user_optional)):
    """Serve photo map page."""
    if not user:
        return RedirectResponse(url=app.state.immich_auth.login_redirect_url(request))
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
):
    """Invite another Immich user to contribute picks to your curation."""
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
):
    """
    Contribute a photo pick to a shared curation session.
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
