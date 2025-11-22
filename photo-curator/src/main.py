"""
Main FastAPI application for Photo Curator Assistant
Complete AI-powered photo curation with Immich integration
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import uvicorn
import yaml
import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .database import Database
from .immich_client import ImmichClient, PhotoCache
from .analyzer import PhotoAnalyzer

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Photo Curator Assistant",
    description="AI-powered photo curation for Immich",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
config: Optional[Dict] = None
database: Optional[Database] = None
immich_client: Optional[ImmichClient] = None
photo_cache: Optional[PhotoCache] = None
analyzer: Optional[PhotoAnalyzer] = None
scheduler: Optional[AsyncIOScheduler] = None


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
    global config, database, immich_client, photo_cache, analyzer, scheduler

    try:
        # Load configuration
        config_path = Path("config/config.yaml")
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
        else:
            logger.warning("No config file found, using defaults")
            config = {
                "server": {"host": "0.0.0.0", "port": 8081},
                "immich": {"api_url": "http://localhost:2283/api", "api_key": ""},
                "ai": {"use_local_models": True}
            }

        # Initialize database
        database = Database()

        # Initialize Immich client
        immich_config = config.get("immich", {})
        if immich_config.get("api_key"):
            immich_client = ImmichClient(
                immich_config["api_url"],
                immich_config["api_key"]
            )
            if immich_client.check_connection():
                logger.info("✓ Connected to Immich API")
            else:
                logger.warning("⚠ Cannot connect to Immich API")
        else:
            logger.warning("⚠ No Immich API key configured")

        # Initialize photo cache
        photo_cache = PhotoCache()

        # Initialize analyzer
        analyzer = PhotoAnalyzer(config)

        # Initialize scheduler (for background jobs)
        scheduler = AsyncIOScheduler()
        scheduler.start()

        logger.info("✓ Photo Curator started successfully")
        logger.info(f"✓ Web UI: http://{config['server']['host']}:{config['server']['port']}")

    except Exception as e:
        logger.error(f"✗ Startup error: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if scheduler:
        scheduler.shutdown()


# Web UI
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve curator UI"""
    html_path = Path(__file__).parent.parent / "static" / "curator.html"
    if html_path.exists():
        return html_path.read_text()

    # Return placeholder if static file doesn't exist
    return """
    <html>
        <head>
            <title>Photo Curator</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: #f5f5f5;
                    padding: 20px;
                }
                .container { max-width: 1400px; margin: 0 auto; }
                .header {
                    background: white;
                    padding: 30px;
                    border-radius: 12px;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }
                h1 { color: #2563eb; margin-bottom: 10px; }
                .subtitle { color: #666; }
                .card {
                    background: white;
                    padding: 20px;
                    border-radius: 12px;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }
                .button {
                    background: #2563eb;
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 6px;
                    cursor: pointer;
                    text-decoration: none;
                    display: inline-block;
                    margin: 5px;
                }
                .button:hover { background: #1d4ed8; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📸 Photo Curator Assistant</h1>
                    <p class="subtitle">AI-powered photo curation for Immich</p>
                </div>

                <div class="card">
                    <h2>Quick Start</h2>
                    <p>Select a month to start curating:</p>
                    <br>
                    <a href="/curate" class="button">Start Curating</a>
                    <a href="/docs" class="button" style="background:#6b7280">API Docs</a>
                </div>

                <div class="card">
                    <h2>How It Works</h2>
                    <ol style="line-height:2">
                        <li><strong>AI Analysis:</strong> Photos are scored based on quality, faces, and composition</li>
                        <li><strong>Smart Suggestions:</strong> Top 50 photos are pre-selected for you</li>
                        <li><strong>Your Control:</strong> Review, add, or remove photos as you like</li>
                        <li><strong>Create Album:</strong> Save your curated selection to Immich</li>
                    </ol>
                </div>
            </div>
        </body>
    </html>
    """


# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/status")
async def get_status():
    """Get curator status"""
    immich_connected = False
    if immich_client:
        immich_connected = immich_client.check_connection()

    stats = database.get_statistics() if database else {}

    return {
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "immich_connected": immich_connected,
        "statistics": stats
    }


@app.get("/api/users")
async def get_users():
    """Get list of users from Immich"""
    if not immich_client:
        raise HTTPException(status_code=503, detail="Immich client not configured")

    users = immich_client.get_users()

    # Add progress info
    for user in users:
        progress = database.get_user_progress(user['id'])
        user['curation_progress'] = progress

    return {"users": users}


@app.post("/api/analyze/{user_id}/{year}/{month}")
async def analyze_month(
    user_id: str,
    year: int,
    month: int,
    background_tasks: BackgroundTasks
):
    """Analyze all photos for a user/month"""
    if not immich_client or not analyzer or not database:
        raise HTTPException(status_code=503, detail="Services not initialized")

    # Start background analysis
    background_tasks.add_task(
        analyze_user_month_background,
        user_id,
        year,
        month
    )

    return {
        "status": "started",
        "message": f"Analysis started for {year}-{month:02d}",
        "user_id": user_id
    }


async def analyze_user_month_background(user_id: str, year: int, month: int):
    """Background task to analyze photos"""
    try:
        logger.info(f"Starting analysis for user {user_id}, {year}-{month:02d}")

        # Fetch photos from Immich
        photos = immich_client.get_user_photos(user_id, year, month)

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
                photo_path = immich_client.download_photo(asset_id, use_thumbnail=True)
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


@app.get("/api/photos/{user_id}/{year}/{month}")
async def get_monthly_photos(user_id: str, year: int, month: int):
    """Get photos with scores for a month"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    # Get scores from database
    scores = database.get_photo_scores(user_id, year, month)

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


@app.post("/api/curation/{user_id}/{year}/{month}/update")
async def update_curation(
    user_id: str,
    year: int,
    month: int,
    selection: CurationSelection
):
    """Update user's curation selections"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

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


@app.post("/api/curation/{user_id}/{year}/{month}/complete")
async def complete_curation(
    user_id: str,
    year: int,
    month: int,
    album_data: AlbumCreate
):
    """Complete curation and create album in Immich"""
    if not database or not immich_client:
        raise HTTPException(status_code=503, detail="Services not initialized")

    try:
        # Create album in Immich
        album = immich_client.create_album(
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


@app.get("/api/progress/{user_id}")
async def get_user_progress(user_id: str):
    """Get user's curation progress"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    progress = database.get_user_progress(user_id)
    preferences = database.get_user_preferences(user_id)

    return {
        "user_id": user_id,
        "progress": progress,
        "preferences": preferences
    }


@app.get("/api/stats")
async def get_statistics():
    """Get overall statistics"""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return database.get_statistics()


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
