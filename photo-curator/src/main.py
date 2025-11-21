"""
Main FastAPI application for Photo Curator Assistant
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import uvicorn
import yaml

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


@app.on_event("startup")
async def startup_event():
    """Initialize application"""
    global config

    try:
        # Load configuration
        config_path = Path("config/config.yaml")
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
        else:
            config = {
                "server": {"host": "0.0.0.0", "port": 8081},
                "immich": {"api_url": "http://localhost:2283/api", "api_key": ""}
            }

        print("✓ Photo Curator started successfully")
        print(f"✓ Web UI: http://{config['server']['host']}:{config['server']['port']}")

    except Exception as e:
        print(f"✗ Startup error: {e}")
        raise


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve curator UI"""
    return """
    <html>
        <head>
            <title>Photo Curator</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                    background: #f5f5f5;
                }
                .header {
                    background: white;
                    padding: 20px;
                    border-radius: 10px;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                h1 {
                    color: #2563eb;
                    margin: 0 0 10px 0;
                }
                .subtitle {
                    color: #666;
                    margin: 0;
                }
                .card {
                    background: white;
                    padding: 20px;
                    border-radius: 10px;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                .feature {
                    padding: 15px;
                    border-left: 3px solid #2563eb;
                    margin: 10px 0;
                    background: #f8fafc;
                }
                .feature h3 {
                    margin: 0 0 5px 0;
                    color: #1f2937;
                }
                .feature p {
                    margin: 0;
                    color: #6b7280;
                    font-size: 14px;
                }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📸 Photo Curator Assistant</h1>
                <p class="subtitle">AI-powered photo curation for Immich</p>
            </div>

            <div class="card">
                <h2>Welcome!</h2>
                <p>The Photo Curator helps you organize and curate your photo library.</p>
            </div>

            <div class="card">
                <h2>Features</h2>

                <div class="feature">
                    <h3>🤖 AI Quality Scoring</h3>
                    <p>Automatically scores photos based on technical quality, faces, and aesthetics</p>
                </div>

                <div class="feature">
                    <h3>📅 Monthly Curation</h3>
                    <p>Get reminded to curate your best photos each month</p>
                </div>

                <div class="feature">
                    <h3>🎨 Duplicate Detection</h3>
                    <p>Find and manage similar or duplicate photos</p>
                </div>

                <div class="feature">
                    <h3>📚 Year-End Collaboration</h3>
                    <p>Work with family to create photo books at year end</p>
                </div>
            </div>

            <div class="card">
                <h2>API Documentation</h2>
                <p>Visit <a href="/docs">/docs</a> for full API documentation</p>
            </div>
        </body>
    </html>
    """


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/status")
async def get_status():
    """Get curator status"""
    return {
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "immich_connected": config.get("immich", {}).get("api_url") != ""
    }


@app.get("/api/users")
async def get_users():
    """Get list of users for curation"""
    # In a full implementation, this would fetch from Immich API
    return {
        "users": [],
        "message": "Connect to Immich API to see users"
    }


@app.get("/api/photos/{user_id}/monthly")
async def get_monthly_photos(user_id: str, year: int, month: int):
    """Get photos for a user for a specific month"""
    # In a full implementation, this would fetch and score photos
    return {
        "user_id": user_id,
        "year": year,
        "month": month,
        "photos": [],
        "message": "Photo scoring not yet implemented"
    }


@app.post("/api/curate/{user_id}")
async def curate_photos(user_id: str, photo_ids: List[str]):
    """Mark photos as curated for a user"""
    # In a full implementation, this would create albums in Immich
    return {
        "status": "success",
        "user_id": user_id,
        "curated_count": len(photo_ids)
    }


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
