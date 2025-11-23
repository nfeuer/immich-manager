# Photo Curator Assistant

**AI-powered photo curation and management for Immich with seamless SSO integration**

## Overview

The Photo Curator is a FastAPI-based service that uses local AI models (OpenCV) to analyze photos, detect duplicates, and help users curate their photo libraries. It integrates with Immich's authentication system, so users log in once and have access to both Immich and the Curator.

## Features

### 🤖 AI Photo Analysis

**Local Processing - No API Costs**
- **Quality Scoring**: Automated assessment of photo quality
  - Blur detection (Laplacian variance)
  - Exposure analysis (histogram analysis)
  - Composition scoring (rule of thirds, symmetry)
  - Face detection and scoring (Haar cascades)

**Weighted Scoring System:**
```
Final Score = (30% Technical Quality) + (30% Faces) + (20% Aesthetic) + (20% Uniqueness)

Technical Quality = (Blur Score + Exposure Score) / 2
Faces Score = Face detection + face count bonus
Aesthetic = Composition score
Uniqueness = Perceptual hash comparison
```

### 📅 Monthly Curation
- Per-user curation sessions
- Configurable monthly targets (e.g., 50 best photos/month)
- AI-suggested selections based on quality scores
- User can add/remove photos from suggestions
- Progress tracking and statistics

### 🔍 Duplicate Detection
- Perceptual hash comparison (ImageHash)
- Side-by-side photo comparison UI
- Bulk deletion of duplicates
- Smart grouping by similarity

### 📊 Analytics Dashboard
- User upload statistics
- Photo quality trends
- Monthly activity reports
- Storage insights

### 🔐 Immich SSO Integration
- Seamless authentication using Immich credentials
- No separate login required
- Per-user API clients for secure photo access
- Respects Immich permissions and sharing settings

### 📧 Email Notifications
- Monthly curation reminders (opt-in)
- Customizable email preferences
- Quiet hours support
- Async email delivery

## Installation

### Prerequisites
- Python 3.9+
- Immich instance running and accessible
- OpenCV dependencies (installed automatically)

### Quick Install

```bash
cd /home/user/immich-manager
./scripts/20-install-photo-curator.sh
```

This will:
1. Create installation at `/opt/photo-curator`
2. Install Python dependencies (including OpenCV)
3. Copy configuration template
4. Initialize SQLite database
5. Install systemd service
6. Start the service

### Manual Installation

```bash
# Create installation directory
sudo mkdir -p /opt/photo-curator
sudo cp -r photo-curator/* /opt/photo-curator/

# Create virtual environment
cd /opt/photo-curator
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp config/config.yaml.example config/config.yaml
nano config/config.yaml

# Install systemd service
sudo cp /path/to/immich-manager/scripts/systemd/photo-curator.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable photo-curator
sudo systemctl start photo-curator
```

## Configuration

Configuration file location: `/opt/photo-curator/config/config.yaml`

### Minimal Configuration

```yaml
server:
  host: "0.0.0.0"
  port: 8081

immich:
  base_url: "http://localhost:2283"
  api_url: "http://localhost:2283/api"
  api_key: "admin-api-key-here"  # For background jobs only

curation:
  monthly_target: 50
  reminder_day: 1  # 1st of month
```

### Full Configuration Options

```yaml
server:
  host: "0.0.0.0"
  port: 8081
  debug: false

immich:
  base_url: "http://localhost:2283"           # Immich web UI URL
  api_url: "http://localhost:2283/api"        # Immich API URL
  api_key: ""                                 # Admin API key (for background jobs)

curation:
  monthly_target: 50                          # Photos to curate per month
  reminder_day: 1                             # Day of month for reminders (1-28)
  reminder_hour: 9                            # Hour to send reminders (0-23)

ai:
  use_local_models: true                      # Always true (no cloud APIs)

  # Quality scoring weights (must sum to 1.0)
  scoring:
    weights:
      technical_quality: 0.3                  # Blur + exposure
      faces: 0.3                              # Face detection
      aesthetic: 0.2                          # Composition
      uniqueness: 0.2                         # Perceptual hash

  # Duplicate detection
  duplicates:
    hash_size: 8                              # Perceptual hash size (8 or 16)
    similarity_threshold: 5                   # Hamming distance threshold

# Photo cache settings
cache:
  enabled: true
  path: "/tmp/photo-curator-cache"
  max_size_gb: 10                             # Max cache size
  ttl_hours: 24                               # Time to live

# Email notifications
notifications:
  email:
    enabled: true
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    smtp_user: "your-email@gmail.com"
    smtp_password: "your-app-password"
    from: "photo-curator@yourdomain.com"

    # Quiet hours (no emails sent)
    quiet_hours:
      enabled: false
      start: "22:00"
      end: "08:00"

# Database settings
database:
  path: "curator.db"

# Logging
logging:
  level: "INFO"
  file: "logs/curator.log"
```

## API Endpoints

Base URL: `http://localhost:8081`

### Authentication

#### `GET /api/auth/check`
Check if user is authenticated with Immich.

**Cookies Required:** `immich_access_token`

**Response:**
```json
{
  "authenticated": true,
  "user_id": "abc-123",
  "email": "user@example.com",
  "name": "John Doe"
}
```

### Curation

#### `POST /api/analyze/{year}/{month}`
Analyze photos for a specific month and generate quality scores.

**Parameters:**
- `year`: Year (e.g., 2024)
- `month`: Month (1-12)

**Request Body:**
```json
{
  "force_reanalysis": false
}
```

**Response:**
```json
{
  "status": "completed",
  "total_photos": 234,
  "analyzed": 234,
  "top_photos": 50,
  "processing_time_seconds": 45.2
}
```

#### `GET /api/photos/{year}/{month}`
Get analyzed photos with scores for a specific month.

**Response:**
```json
{
  "photos": [
    {
      "id": "photo-id-123",
      "score": 0.87,
      "technical_quality": 0.92,
      "blur_score": 0.95,
      "exposure_score": 0.89,
      "face_score": 0.85,
      "face_count": 3,
      "composition_score": 0.78,
      "width": 4032,
      "height": 3024,
      "megapixels": 12.2,
      "taken_at": "2024-01-15T14:30:00Z",
      "thumbnail_url": "/api/thumbnail/photo-id-123"
    }
  ],
  "suggested_selections": ["photo-id-123", "photo-id-456"],
  "total": 234,
  "target": 50
}
```

#### `POST /api/curation/{year}/{month}/update`
Update user's curation selections.

**Request Body:**
```json
{
  "selected": ["photo-id-123", "photo-id-456"],
  "added": ["photo-id-789"],
  "removed": ["photo-id-321"]
}
```

#### `POST /api/curation/{year}/{month}/complete`
Finalize curation and create album.

**Request Body:**
```json
{
  "asset_ids": ["photo-id-123", "photo-id-456"],
  "album_name": "January 2024 Highlights",
  "description": "Best photos from January"
}
```

**Response:**
```json
{
  "status": "completed",
  "album_id": "album-abc-123",
  "photo_count": 50
}
```

### Duplicates

#### `GET /api/duplicates`
Find duplicate photos using perceptual hashing.

**Query Parameters:**
- `similarity` (optional): Hamming distance threshold (default: 5)

**Response:**
```json
{
  "duplicate_groups": [
    {
      "hash": "abc123def456",
      "photos": [
        {
          "id": "photo-1",
          "score": 0.85,
          "file_size": 2345678,
          "taken_at": "2024-01-15T14:30:00Z"
        },
        {
          "id": "photo-2",
          "score": 0.82,
          "file_size": 2345600,
          "taken_at": "2024-01-15T14:30:01Z"
        }
      ],
      "similarity": 2
    }
  ],
  "total_duplicates": 45,
  "potential_space_saved_mb": 234.5
}
```

#### `POST /api/duplicates/delete`
Delete duplicate photos.

**Request Body:**
```json
{
  "photo_ids": ["photo-2", "photo-5", "photo-8"]
}
```

**Response:**
```json
{
  "deleted": 3,
  "failed": 0,
  "space_freed_mb": 15.6
}
```

### User Preferences

#### `GET /api/preferences`
Get user's curation preferences.

**Response:**
```json
{
  "monthly_target": 50,
  "email_reminders": true,
  "reminder_day": 1,
  "last_curation": "2024-01-01T00:00:00Z"
}
```

#### `PUT /api/preferences`
Update user preferences.

**Request Body:**
```json
{
  "monthly_target": 75,
  "email_reminders": true,
  "reminder_day": 5
}
```

### Analytics

#### `GET /api/analytics`
Get user analytics and statistics.

**Response:**
```json
{
  "total_photos": 12543,
  "average_quality_score": 0.73,
  "photos_by_month": {
    "2024-01": 234,
    "2024-02": 189
  },
  "curation_progress": {
    "months_completed": 3,
    "total_curated": 150,
    "target_percentage": 60
  },
  "quality_distribution": {
    "excellent": 1234,
    "good": 5678,
    "fair": 3456,
    "poor": 2175
  },
  "faces_detected": 4567,
  "duplicates_found": 234
}
```

#### `GET /api/progress`
Get curation progress overview.

**Response:**
```json
{
  "sessions": [
    {
      "year": 2024,
      "month": 1,
      "completed": true,
      "photos_selected": 52,
      "target": 50,
      "completed_at": "2024-01-05T10:30:00Z"
    }
  ],
  "overall_progress": 75.5
}
```

### Status

#### `GET /health`
Service health check.

#### `GET /api/status`
Detailed service status.

**Response:**
```json
{
  "status": "running",
  "version": "2.0.0",
  "immich_connected": true,
  "cache_size_mb": 234.5,
  "database_size_mb": 12.3,
  "active_users": 6
}
```

## Architecture

### Components

```
┌──────────────────────────────────────────────────┐
│         FastAPI Application (main.py)            │
│      HTTP Server & API Endpoints                 │
└────────┬─────────────────────────────────────────┘
         │
         ├─── ImmichAuth (auth.py)
         │    ├─── Token validation
         │    └─── User info fetching
         │
         ├─── ImmichClient (immich_client.py)
         │    ├─── Per-user API clients
         │    ├─── Photo fetching
         │    └─── Album management
         │
         ├─── PhotoCache (immich_client.py)
         │    └─── Temporary photo storage
         │
         ├─── PhotoAnalyzer (analyzer.py)
         │    ├─── Blur detection (Laplacian)
         │    ├─── Exposure analysis (histogram)
         │    ├─── Face detection (Haar cascades)
         │    ├─── Composition scoring
         │    └─── Perceptual hashing
         │
         ├─── Database (database.py)
         │    └─── SQLite operations
         │
         ├─── EmailNotifier (notifications.py)
         │    └─── Async SMTP client
         │
         └─── APScheduler
              ├─── Monthly reminders
              └─── Cache cleanup
```

### Database Schema

**SQLite Database:** `curator.db`

**Tables:**

1. **user_preferences**
   - user_id (TEXT PRIMARY KEY)
   - monthly_target (INTEGER DEFAULT 50)
   - email_reminders (INTEGER DEFAULT 0)
   - reminder_day (INTEGER DEFAULT 1)
   - created_at (TEXT)
   - updated_at (TEXT)

2. **curation_sessions**
   - id (INTEGER PRIMARY KEY)
   - user_id (TEXT)
   - year (INTEGER)
   - month (INTEGER)
   - completed (INTEGER DEFAULT 0)
   - photos_analyzed (INTEGER)
   - photos_selected (INTEGER)
   - target (INTEGER)
   - created_at (TEXT)
   - completed_at (TEXT)

3. **photo_analysis**
   - id (INTEGER PRIMARY KEY)
   - user_id (TEXT)
   - photo_id (TEXT)
   - score (REAL)
   - technical_quality (REAL)
   - blur_score (REAL)
   - exposure_score (REAL)
   - composition_score (REAL)
   - face_score (REAL)
   - face_count (INTEGER)
   - perceptual_hash (TEXT)
   - width (INTEGER)
   - height (INTEGER)
   - analyzed_at (TEXT)
   - UNIQUE(user_id, photo_id)

4. **duplicate_groups**
   - id (INTEGER PRIMARY KEY)
   - user_id (TEXT)
   - hash_group (TEXT)
   - photo_ids (TEXT - JSON array)
   - similarity (INTEGER)
   - created_at (TEXT)

### Authentication Flow

```
1. User visits http://localhost:8081
2. Curator checks for immich_access_token cookie
3. If missing → Redirect to Immich login
4. User logs into Immich
5. Immich sets immich_access_token cookie
6. User returns to Curator
7. Curator validates token with Immich API
8. Curator fetches user info from /api/users/me
9. Per-user ImmichClient created
10. User can access Curator features
```

### Photo Analysis Pipeline

```
1. User initiates analysis for month (e.g., January 2024)
2. Curator fetches photos from Immich API
3. For each photo:
   a. Download from Immich
   b. Cache locally
   c. OpenCV analysis:
      - Calculate blur score (Laplacian variance)
      - Analyze exposure (histogram)
      - Detect faces (Haar cascades)
      - Score composition (rule of thirds)
   d. Generate perceptual hash (ImageHash)
   e. Calculate weighted final score
   f. Store in database
4. Return top N photos based on scores
5. User reviews and adjusts selections
6. User finalizes → Create Immich album
```

## Usage

### Web Interface

#### Access Curator
1. Navigate to `http://localhost:8081`
2. If not logged in, you'll be redirected to Immich
3. Log in with Immich credentials
4. Return to Curator dashboard

#### Curate Photos
1. Click "Curate" for a month
2. Click "Analyze Photos" to start AI analysis
3. Review AI-suggested photos (highlighted)
4. Add/remove photos as desired
5. Click "Create Album" to finalize

#### Find Duplicates
1. Click "Duplicates" tab
2. Click "Scan for Duplicates"
3. Review side-by-side comparisons
4. Select photos to delete
5. Click "Delete Selected"

#### View Analytics
1. Click "Analytics" tab
2. View upload trends, quality distribution
3. See curation progress over time

### API Usage

#### Authenticate
```bash
# Get token from Immich
TOKEN=$(curl -X POST http://localhost:2283/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password"}' \
  | jq -r .accessToken)

# Use token in requests
curl http://localhost:8081/api/status \
  -H "Cookie: immich_access_token=$TOKEN"
```

#### Analyze Photos
```bash
curl -X POST http://localhost:8081/api/analyze/2024/1 \
  -H "Cookie: immich_access_token=$TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"force_reanalysis": false}'
```

### Service Management

```bash
# Start service
sudo systemctl start photo-curator

# Stop service
sudo systemctl stop photo-curator

# Restart service
sudo systemctl restart photo-curator

# View status
sudo systemctl status photo-curator

# View logs
sudo journalctl -u photo-curator -f
```

## Troubleshooting

### OpenCV Import Errors

```bash
# Reinstall OpenCV
cd /opt/photo-curator
source venv/bin/activate
pip install --force-reinstall opencv-python

# Verify installation
python -c "import cv2; print(cv2.__version__)"
```

### Authentication Issues

```bash
# Check Immich is accessible
curl http://localhost:2283/api/server-info

# Verify token validation endpoint
curl http://localhost:2283/api/auth/validateToken \
  -H "Authorization: Bearer YOUR_TOKEN"

# Check cookie settings (must be same domain)
# If using Cloudflare Tunnel, ensure proper routing
```

### Face Detection Not Working

```bash
# Verify Haar cascade files
python -c "import cv2; print(cv2.data.haarcascades)"

# Should output path like: /opt/photo-curator/venv/lib/python3.x/site-packages/cv2/data/

# List available cascades
ls -la $(python -c "import cv2; print(cv2.data.haarcascades)")
```

### Photo Downloads Failing

```bash
# Check Immich API key
curl http://localhost:2283/api/users/me \
  -H "x-api-key: YOUR_API_KEY"

# Verify network connectivity
curl -I http://localhost:2283

# Check disk space for cache
df -h /tmp/photo-curator-cache
```

### Email Notifications Not Sending

```bash
# Test SMTP configuration
cd /opt/photo-curator
source venv/bin/activate
python -c "
from src.notifications import EmailNotifier
import yaml
with open('config/config.yaml') as f:
    config = yaml.safe_load(f)
notifier = EmailNotifier(config['notifications']['email'])
asyncio.run(notifier.send_test_email('test@example.com'))
"
```

## Security Considerations

### Authentication
- All requests must include valid Immich token
- Tokens validated on every request
- Per-user data isolation
- No separate user database

### API Key Storage
- Admin API key only used for background jobs
- Never exposed to frontend
- Store securely: `chmod 600 config/config.yaml`

### Photo Cache
- Temporary cache in `/tmp` (cleared on reboot)
- Automatic cleanup of old files
- Configurable size limits
- Only cached during active analysis

### Network Security
- Bind to localhost only if no remote access needed
- Use reverse proxy (nginx/Cloudflare) for HTTPS
- Never expose port 8081 directly to internet
- Set proper CORS origins in production

## Development

### Project Structure

```
photo-curator/
├── src/
│   ├── __init__.py
│   ├── main.py              # FastAPI app & endpoints
│   ├── auth.py              # Immich SSO integration
│   ├── immich_client.py     # Immich API client
│   ├── analyzer.py          # Photo analysis (OpenCV)
│   ├── database.py          # SQLite operations
│   └── notifications.py     # Email notifications
├── static/
│   ├── curator.html         # Main curation UI
│   ├── preferences.html     # User preferences
│   ├── duplicates.html      # Duplicate detection UI
│   └── analytics.html       # Analytics dashboard
├── config/
│   └── config.yaml.example  # Configuration template
├── requirements.txt          # Python dependencies
└── README.md                # This file
```

### Running in Development

```bash
cd /opt/photo-curator
source venv/bin/activate

# Run with auto-reload
uvicorn src.main:app --reload --host 0.0.0.0 --port 8081

# Or use Python directly
python -m src.main
```

### Testing Photo Analysis

```bash
# Test individual photo
cd /opt/photo-curator
source venv/bin/activate
python -c "
from src.analyzer import PhotoAnalyzer
analyzer = PhotoAnalyzer()
result = analyzer.analyze_photo('/path/to/photo.jpg')
print(result)
"
```

### Adding New Analysis Features

1. Add method to `PhotoAnalyzer` class in `analyzer.py`
2. Update `analyze_photo()` to call new method
3. Update weighted scoring if needed
4. Add new fields to `photo_analysis` table
5. Update API response models
6. Update UI to display new metrics

## Performance

### Resource Usage
- **Memory**: 100-200 MB idle, up to 1 GB during analysis
- **CPU**: <1% idle, 50-80% during analysis (one core)
- **Disk**: Cache can use up to configured limit (default 10 GB)

### Analysis Speed
- ~1-2 seconds per photo (local processing)
- Batch processing of 100 photos: ~2-3 minutes
- Face detection adds ~0.5 seconds per photo

### Optimization Tips

```yaml
# Reduce cache TTL for faster cleanup
cache:
  ttl_hours: 12  # Instead of 24

# Adjust perceptual hash size for faster duplicate detection
ai:
  duplicates:
    hash_size: 8  # Instead of 16 (faster but less accurate)

# Reduce scoring complexity
ai:
  skip_face_detection: true  # If not needed
```

## Known Limitations

- Face detection uses basic Haar cascades (not deep learning)
- Cannot detect specific faces (no face recognition)
- Analysis requires downloading photos locally
- Only works with JPEG/PNG/HEIC formats
- Large libraries (50,000+ photos) may take hours to analyze

## Future Enhancements

- [ ] Deep learning models for better face detection
- [ ] Scene detection (beach, mountains, indoor, etc.)
- [ ] Object detection (pets, cars, food)
- [ ] Smart event clustering (birthdays, vacations)
- [ ] Year-end review automation
- [ ] Mobile app for curation on-the-go

## License

MIT License - See LICENSE file in repository root.

## Support

- **Issues**: https://github.com/yourusername/immich-manager/issues
- **Immich Discord**: https://discord.immich.app
- **Main Documentation**: See root README.md
