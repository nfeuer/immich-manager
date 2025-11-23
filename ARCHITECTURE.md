# Immich Manager Architecture

**Comprehensive technical architecture documentation**

## Table of Contents

1. [System Overview](#system-overview)
2. [Component Architecture](#component-architecture)
3. [Data Flow](#data-flow)
4. [Database Design](#database-design)
5. [Authentication & Authorization](#authentication--authorization)
6. [API Architecture](#api-architecture)
7. [Deployment Architecture](#deployment-architecture)
8. [Security Architecture](#security-architecture)
9. [Monitoring & Observability](#monitoring--observability)
10. [Scalability Considerations](#scalability-considerations)

## System Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Immich Manager Ecosystem                      │
└─────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  Server Manager  │      │  Photo Curator   │      │  Health Monitor  │
│   (Port 8080)    │      │   (Port 8081)    │      │   (Systemd)      │
│                  │      │                  │      │                  │
│  - Monitoring    │      │  - AI Analysis   │      │  - Auto-healing  │
│  - Backups       │      │  - Curation      │      │  - Checks        │
│  - Alerts        │      │  - Duplicates    │      │  - Restarts      │
└────────┬─────────┘      └────────┬─────────┘      └────────┬─────────┘
         │                         │                         │
         │                         │                         │
         └─────────────────────────┼─────────────────────────┘
                                   │
                                   ▼
                     ┌─────────────────────────┐
                     │   Immich Instance       │
                     │   (Port 2283)           │
                     │                         │
                     │  - Web UI               │
                     │  - API Server           │
                     │  - PostgreSQL           │
                     │  - Photo Storage        │
                     └─────────────────────────┘
                                   │
                                   ▼
                     ┌─────────────────────────┐
                     │  Cloudflare Tunnel      │
                     │  (Optional)             │
                     │                         │
                     │  - Remote Access        │
                     │  - HTTPS                │
                     │  - DDoS Protection      │
                     └─────────────────────────┘
```

### Design Principles

1. **Microservices Architecture**: Each component is independent and can be deployed/updated separately
2. **Loose Coupling**: Components communicate via HTTP APIs or systemd signals
3. **Single Responsibility**: Each service has a clear, focused purpose
4. **Self-Healing**: Automatic recovery from common failure scenarios
5. **Security First**: Defense in depth with multiple security layers
6. **Observability**: Comprehensive logging and monitoring built-in

## Component Architecture

### 1. Server Manager

**Purpose**: System monitoring, backups, and alerting

**Technology Stack**:
- **Framework**: FastAPI (Python 3.9+)
- **Web Server**: Uvicorn (ASGI)
- **Database**: SQLite (aiosqlite)
- **Scheduling**: APScheduler
- **Monitoring**: psutil, smartctl, docker-py

**Architecture**:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Server Manager (main.py)                     │
│                      FastAPI Application                         │
└───────┬──────────────────────────────────────────────────────────┘
        │
        ├─── Config (config.py)
        │    └─── YAML config loader with validation
        │
        ├─── Database (database.py)
        │    └─── SQLite async operations
        │         ├─── disk_health table
        │         ├─── system_metrics table
        │         ├─── backup_records table
        │         └─── alerts table
        │
        ├─── Monitoring (monitoring.py)
        │    ├─── DiskMonitor
        │    │    └─── SMART data via smartctl subprocess
        │    ├─── SystemMonitor
        │    │    └─── CPU/RAM/IO via psutil
        │    └─── DockerMonitor
        │         └─── Docker API (docker-py)
        │
        ├─── Backup (backup.py)
        │    ├─── BackupManager
        │    │    ├─── pg_dump via Docker exec
        │    │    ├─── Compression (gzip)
        │    │    ├─── Checksums (SHA256)
        │    │    └─── Retention enforcement
        │    │
        │    └─── BackupVerifier (backup_verifier.py)
        │         ├─── Test restore
        │         └─── Integrity validation
        │
        ├─── Alerts (alerts.py)
        │    ├─── AlertManager
        │    │    ├─── Email (aiosmtplib)
        │    │    ├─── Webhooks (requests)
        │    │    └─── Quiet hours logic
        │    │
        │    └─── Alert threshold evaluation
        │
        └─── Scheduler (APScheduler)
             ├─── Disk health: Interval(300s)
             ├─── System metrics: Interval(60s)
             └─── Backups: CronTrigger(configurable)
```

**Key Design Decisions**:

- **SQLite over PostgreSQL**: Lightweight, no external dependencies, sufficient for single-server
- **Async/await**: Non-blocking I/O for better performance
- **Background jobs**: APScheduler for reliable scheduling without cron
- **Direct subprocess calls**: SMART data requires direct smartctl access

### 2. Photo Curator

**Purpose**: AI-powered photo analysis and curation

**Technology Stack**:
- **Framework**: FastAPI (Python 3.9+)
- **Image Processing**: OpenCV, Pillow, ImageHash
- **Machine Learning**: scikit-image (local processing)
- **Authentication**: Immich SSO integration
- **Database**: SQLite

**Architecture**:

```
┌─────────────────────────────────────────────────────────────────┐
│                   Photo Curator (main.py)                        │
│                   FastAPI Application                            │
└───────┬──────────────────────────────────────────────────────────┘
        │
        ├─── Auth (auth.py)
        │    ├─── ImmichAuth
        │    │    ├─── Token validation
        │    │    └─── User info fetching
        │    │
        │    └─── Dependency injection for endpoints
        │
        ├─── Immich Client (immich_client.py)
        │    ├─── ImmichClient (per-user instances)
        │    │    ├─── Photo fetching
        │    │    ├─── Album operations
        │    │    └─── Asset management
        │    │
        │    └─── PhotoCache
        │         ├─── Temporary storage
        │         ├─── LRU eviction
        │         └─── Cleanup scheduler
        │
        ├─── Analyzer (analyzer.py)
        │    └─── PhotoAnalyzer
        │         ├─── Blur detection (Laplacian variance)
        │         ├─── Exposure analysis (histogram)
        │         ├─── Face detection (Haar cascades)
        │         ├─── Composition scoring (rule of thirds)
        │         ├─── Perceptual hashing (pHash)
        │         └─── Weighted scoring
        │
        ├─── Database (database.py)
        │    └─── SQLite operations
        │         ├─── user_preferences
        │         ├─── curation_sessions
        │         ├─── photo_analysis
        │         └─── duplicate_groups
        │
        ├─── Notifications (notifications.py)
        │    └─── EmailNotifier
        │         ├─── Monthly reminders
        │         ├─── Async SMTP
        │         └─── Template rendering
        │
        └─── Scheduler (APScheduler)
             ├─── Monthly reminders
             └─── Cache cleanup
```

**Key Design Decisions**:

- **Local AI models**: No API costs, privacy-preserving, works offline
- **OpenCV over TensorFlow**: Lighter weight, sufficient for quality scoring
- **Haar cascades**: Fast face detection without GPU requirements
- **Perceptual hashing**: Efficient duplicate detection
- **Cookie-based auth**: Seamless SSO with Immich
- **Per-user API clients**: Respects Immich permissions

### 3. Health Monitor

**Purpose**: Self-healing system monitoring

**Technology Stack**:
- **Runtime**: Python 3.9+ script (not a server)
- **Scheduler**: systemd timer (every 15 minutes)
- **Process Management**: systemctl
- **HTTP Client**: requests

**Architecture**:

```
┌─────────────────────────────────────────────────────────────────┐
│                   systemd Timer (Every 15 min)                   │
└───────┬──────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Health Monitor (main.py)                         │
│                 Python Script (single execution)                 │
└───────┬──────────────────────────────────────────────────────────┘
        │
        ├─── HealthMonitor class
        │    │
        │    ├─── check_service_http(service, url)
        │    │    └─── HTTP GET with timeout
        │    │
        │    ├─── check_service_systemd(service_name)
        │    │    └─── systemctl is-active
        │    │
        │    ├─── restart_service(service_name)
        │    │    ├─── systemctl restart
        │    │    └─── Cooldown tracking
        │    │
        │    ├─── check_disk_space(paths)
        │    │    └─── df -h parsing
        │    │
        │    ├─── optimize_database(db_path)
        │    │    └─── sqlite3 VACUUM
        │    │
        │    ├─── cleanup_cache(cache_path)
        │    │    └─── Remove old files
        │    │
        │    └─── send_weekly_summary()
        │         └─── Email report
        │
        └─── Result logging
             └─── journalctl output
```

**Key Design Decisions**:

- **Systemd timer over cron**: Better logging, service dependencies
- **Script over daemon**: Simpler, no state to manage
- **Cooldown mechanism**: Prevents restart loops
- **Multiple verification**: HTTP + systemd for reliability

## Data Flow

### Backup Data Flow

```
1. APScheduler triggers backup (CronTrigger)
   │
   ▼
2. BackupManager.create_backup()
   │
   ├─── Generate filename: immich_db_YYYYMMDD_HHMMSS.sql.gz
   │
   ├─── Execute: docker exec immich_postgres pg_dump -U postgres immich
   │    │
   │    └─── Stream to gzip compression
   │
   ├─── Calculate SHA256 checksum
   │
   ├─── Save to local path: /mnt/backups/immich/
   │
   ├─── Record in database: backup_records table
   │    ├─── filename
   │    ├─── timestamp
   │    ├─── size_bytes
   │    ├─── checksum
   │    └─── success=true
   │
   ├─── Apply retention policy
   │    ├─── Keep 7 daily backups
   │    ├─── Keep 4 weekly backups (Sundays)
   │    ├─── Keep 6 monthly backups (1st of month)
   │    └─── Delete older backups
   │
   ├─── (Optional) Sync to S3/B2
   │    └─── boto3.upload_file()
   │
   └─── (Optional) Verify backup
        ├─── Create temp PostgreSQL container
        ├─── Restore backup to temp DB
        ├─── Verify table counts
        └─── Destroy temp container
```

### Photo Analysis Data Flow

```
1. User initiates analysis: POST /api/analyze/2024/1
   │
   ▼
2. Fetch photos from Immich API
   │
   ├─── GET /api/assets?year=2024&month=1
   │    └─── Uses user's access token (per-user client)
   │
   └─── Returns list of asset IDs + metadata
        │
        ▼
3. For each photo:
   │
   ├─── Download photo
   │    ├─── GET /api/assets/{id}/thumbnail?size=preview
   │    └─── Save to PhotoCache (/tmp/photo-curator-cache/)
   │
   ├─── Load with OpenCV
   │    └─── cv2.imread(cache_path)
   │
   ├─── Run analysis
   │    │
   │    ├─── Blur detection
   │    │    ├─── Convert to grayscale
   │    │    ├─── Calculate Laplacian
   │    │    ├─── Compute variance
   │    │    └─── Normalize to 0-1
   │    │
   │    ├─── Exposure analysis
   │    │    ├─── Calculate histogram
   │    │    ├─── Check for clipping
   │    │    └─── Score contrast
   │    │
   │    ├─── Face detection
   │    │    ├─── Load Haar cascade
   │    │    ├─── Detect faces
   │    │    ├─── Count faces
   │    │    └─── Score based on count
   │    │
   │    ├─── Composition
   │    │    ├─── Rule of thirds grid
   │    │    └─── Check interest points
   │    │
   │    └─── Perceptual hash
   │         ├─── Load with Pillow
   │         ├─── imagehash.phash()
   │         └─── Convert to string
   │
   ├─── Calculate weighted score
   │    └─── 30% technical + 30% faces + 20% aesthetic + 20% unique
   │
   └─── Store in database
        └─── INSERT INTO photo_analysis (user_id, photo_id, scores...)
        │
        ▼
4. Return results
   │
   ├─── Sort by score (descending)
   ├─── Select top N (monthly_target)
   └─── Return as JSON
```

### Authentication Data Flow

```
1. User visits Photo Curator (http://localhost:8081)
   │
   ▼
2. Check for immich_access_token cookie
   │
   ├─── Cookie exists?
   │    │
   │    ├─── YES:
   │    │    │
   │    │    ├─── Validate token with Immich
   │    │    │    └─── GET /api/auth/validateToken
   │    │    │         └─── Headers: Authorization: Bearer <token>
   │    │    │
   │    │    ├─── Token valid?
   │    │    │    │
   │    │    │    ├─── YES:
   │    │    │    │    ├─── Fetch user info
   │    │    │    │    │    └─── GET /api/users/me
   │    │    │    │    │
   │    │    │    │    ├─── Create per-user ImmichClient
   │    │    │    │    │    └─── Stores token for subsequent requests
   │    │    │    │    │
   │    │    │    │    └─── Allow access
   │    │    │    │
   │    │    │    └─── NO:
   │    │    │         └─── Redirect to Immich login
   │    │    │
   │    │    └─── Continue with authenticated user
   │    │
   │    └─── NO:
   │         └─── Redirect to Immich login
   │              │
   │              ├─── User logs into Immich
   │              ├─── Immich sets immich_access_token cookie
   │              └─── Redirect back to Curator
```

### Alert Data Flow

```
1. Monitoring detects issue
   │
   ├─── Example: Disk temperature > threshold
   │    ├─── DiskMonitor.check_disk_health()
   │    └─── temperature = 55°C, threshold = 50°C
   │
   ▼
2. Create alert
   │
   ├─── Alert severity determination
   │    ├─── temperature > critical (60°C) → CRITICAL
   │    └─── temperature > warning (50°C) → WARNING
   │
   ├─── Store in database
   │    └─── INSERT INTO alerts (timestamp, severity, type, message, details)
   │
   └─── Trigger AlertManager
        │
        ▼
3. AlertManager.send_alert()
   │
   ├─── Check quiet hours
   │    ├─── Current time in quiet hours? → Skip
   │    └─── Otherwise → Continue
   │
   ├─── Prepare message
   │    ├─── Template: "Disk {device} temperature {temp}°C exceeds {threshold}°C"
   │    └─── Add context: device info, SMART data
   │
   ├─── Send via email
   │    ├─── SMTP connection (aiosmtplib)
   │    ├─── TLS encryption
   │    └─── Async send
   │
   └─── (Optional) Send webhook
        ├─── POST to configured URL
        ├─── JSON payload
        └─── Retry on failure (3 attempts)
```

## Database Design

### Server Manager Database Schema

**File**: `server-manager.db` (SQLite)

```sql
-- Disk health tracking
CREATE TABLE disk_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    device TEXT NOT NULL,
    smart_status INTEGER NOT NULL,      -- 0=fail, 1=pass
    model TEXT,
    serial TEXT,
    temperature INTEGER,                 -- Celsius
    power_on_hours INTEGER,
    power_cycle_count INTEGER,
    reallocated_sectors INTEGER,
    pending_sectors INTEGER,
    uncorrectable_sectors INTEGER,
    health_ok INTEGER NOT NULL,          -- 0=fail, 1=ok
    warnings TEXT                        -- JSON array of warnings
);

CREATE INDEX idx_disk_health_timestamp ON disk_health(timestamp);
CREATE INDEX idx_disk_health_device ON disk_health(device);

-- System metrics
CREATE TABLE system_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    cpu_percent REAL,
    memory_percent REAL,
    memory_used_gb REAL,
    memory_total_gb REAL,
    disk_read_mb REAL,
    disk_write_mb REAL
);

CREATE INDEX idx_system_metrics_timestamp ON system_metrics(timestamp);

-- Backup records
CREATE TABLE backup_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    filename TEXT NOT NULL,
    size_bytes INTEGER,
    checksum TEXT,                       -- SHA256
    success INTEGER NOT NULL,            -- 0=fail, 1=success
    duration_seconds REAL,
    error_message TEXT,
    verified INTEGER DEFAULT 0,          -- 0=not verified, 1=verified
    offsite_synced INTEGER DEFAULT 0     -- 0=not synced, 1=synced
);

CREATE INDEX idx_backup_timestamp ON backup_records(timestamp);

-- Alerts
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    severity TEXT NOT NULL,              -- warning, critical
    type TEXT NOT NULL,                  -- disk_health, backup_failed, etc.
    message TEXT NOT NULL,
    details TEXT,                        -- JSON additional info
    acknowledged INTEGER DEFAULT 0,      -- 0=not acked, 1=acked
    acknowledged_at TEXT
);

CREATE INDEX idx_alerts_timestamp ON alerts(timestamp);
CREATE INDEX idx_alerts_severity ON alerts(severity);
CREATE INDEX idx_alerts_acknowledged ON alerts(acknowledged);
```

### Photo Curator Database Schema

**File**: `curator.db` (SQLite)

```sql
-- User preferences
CREATE TABLE user_preferences (
    user_id TEXT PRIMARY KEY,
    monthly_target INTEGER DEFAULT 50,
    email_reminders INTEGER DEFAULT 0,  -- 0=disabled, 1=enabled
    reminder_day INTEGER DEFAULT 1,     -- 1-28
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Curation sessions
CREATE TABLE curation_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    completed INTEGER DEFAULT 0,        -- 0=in progress, 1=completed
    photos_analyzed INTEGER,
    photos_selected INTEGER,
    target INTEGER,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(user_id, year, month)
);

CREATE INDEX idx_curation_user ON curation_sessions(user_id);
CREATE INDEX idx_curation_completed ON curation_sessions(completed);

-- Photo analysis results
CREATE TABLE photo_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    photo_id TEXT NOT NULL,
    score REAL NOT NULL,
    technical_quality REAL,
    blur_score REAL,
    exposure_score REAL,
    composition_score REAL,
    face_score REAL,
    face_count INTEGER DEFAULT 0,
    perceptual_hash TEXT,
    width INTEGER,
    height INTEGER,
    analyzed_at TEXT NOT NULL,
    UNIQUE(user_id, photo_id)
);

CREATE INDEX idx_photo_user ON photo_analysis(user_id);
CREATE INDEX idx_photo_score ON photo_analysis(score DESC);
CREATE INDEX idx_photo_hash ON photo_analysis(perceptual_hash);

-- Duplicate groups
CREATE TABLE duplicate_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    hash_group TEXT NOT NULL,           -- Perceptual hash
    photo_ids TEXT NOT NULL,            -- JSON array of photo IDs
    similarity INTEGER,                  -- Hamming distance
    created_at TEXT NOT NULL
);

CREATE INDEX idx_duplicates_user ON duplicate_groups(user_id);
```

### Data Retention Policies

**Server Manager**:
- Disk health: Keep 90 days
- System metrics: Keep 90 days
- Backup records: Keep indefinitely (small)
- Alerts: Keep 365 days

**Photo Curator**:
- User preferences: Keep indefinitely
- Curation sessions: Keep indefinitely
- Photo analysis: Keep indefinitely (enables re-curation)
- Duplicate groups: Keep 30 days (regenerate as needed)

**Cleanup Queries**:

```sql
-- Server Manager cleanup
DELETE FROM disk_health WHERE timestamp < datetime('now', '-90 days');
DELETE FROM system_metrics WHERE timestamp < datetime('now', '-90 days');
DELETE FROM alerts WHERE timestamp < datetime('now', '-365 days') AND acknowledged = 1;

-- Photo Curator cleanup
DELETE FROM duplicate_groups WHERE created_at < datetime('now', '-30 days');
```

## Authentication & Authorization

### Immich SSO Integration

**Architecture**:

```
┌─────────────────────────────────────────────────────────────────┐
│                         Immich Server                            │
│                                                                  │
│  ┌────────────────┐                                             │
│  │  Auth Service  │                                             │
│  └────────┬───────┘                                             │
│           │                                                      │
│           ├─── POST /api/auth/login                             │
│           │    └─── Returns: accessToken, user info             │
│           │                                                      │
│           ├─── POST /api/auth/validateToken                     │
│           │    └─── Validates: Bearer token or cookie           │
│           │                                                      │
│           └─── GET /api/users/me                                │
│                └─── Returns: user details                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                           ▲
                           │ HTTP requests
                           │
┌──────────────────────────┴──────────────────────────────────────┐
│                    Photo Curator                                 │
│                                                                  │
│  ┌─────────────────┐                                            │
│  │  ImmichAuth     │                                            │
│  │  (auth.py)      │                                            │
│  └────────┬────────┘                                            │
│           │                                                      │
│           ├─── get_current_user() dependency                    │
│           │    ├─── Extract immich_access_token cookie          │
│           │    ├─── Validate with Immich API                    │
│           │    ├─── Cache user info (5 min TTL)                 │
│           │    └─── Return User object or 401                   │
│           │                                                      │
│           └─── get_user_api_client() dependency                 │
│                ├─── Get current user                            │
│                ├─── Create per-user ImmichClient                │
│                └─── Return client instance                      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Token Flow**:

1. **User Login** (Immich Web UI)
   - User enters credentials
   - Immich validates and issues JWT access token
   - Token stored in `immich_access_token` cookie (HttpOnly)

2. **Cookie Propagation**
   - Cookie is domain-scoped (e.g., `yourdomain.com`)
   - Works across subdomains if configured
   - Cloudflare Tunnel preserves cookies

3. **Curator Authentication**
   - Every API request includes cookie
   - `get_current_user()` dependency extracts token
   - Validates with Immich: `POST /api/auth/validateToken`
   - Caches user info to reduce Immich API calls

4. **Per-User API Client**
   - Each user gets isolated `ImmichClient` instance
   - Client uses user's token for all Immich API calls
   - Respects Immich permissions (shared albums, etc.)

**Security Features**:

- No password storage in Curator (delegates to Immich)
- No separate user database
- Tokens validated on every request
- Per-user data isolation
- Cookie is HttpOnly (prevents XSS)
- Short token TTL (Immich default: 1 hour)

### Server Manager Authentication

**Current**: None (assumes trusted network)

**Recommended for Production**:

```python
# Add API key authentication
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    if api_key != os.getenv("SERVER_MANAGER_API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

# Protect endpoints
@app.get("/api/status", dependencies=[Depends(verify_api_key)])
async def get_status():
    ...
```

## API Architecture

### RESTful Design Principles

**Resource Naming**:
- Plural nouns: `/api/photos`, `/api/backups`, `/api/alerts`
- Hierarchical: `/api/curation/{year}/{month}/update`
- Actions as separate endpoints: `/api/backup/now`, `/api/duplicates/delete`

**HTTP Methods**:
- `GET`: Retrieve resources
- `POST`: Create resources or trigger actions
- `PUT`: Update resources (full replacement)
- `PATCH`: Partial updates (not currently used)
- `DELETE`: Delete resources

**Status Codes**:
- `200 OK`: Successful GET/POST/PUT
- `201 Created`: Resource created
- `400 Bad Request`: Invalid input
- `401 Unauthorized`: Missing/invalid auth
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

**Response Format**:

```json
{
  "status": "success",
  "data": { ... },
  "message": "Optional message",
  "timestamp": "2024-01-15T10:00:00Z"
}
```

Error format:
```json
{
  "status": "error",
  "error": {
    "code": "INVALID_INPUT",
    "message": "Year must be between 2000 and 2100",
    "details": { ... }
  },
  "timestamp": "2024-01-15T10:00:00Z"
}
```

### API Versioning

**Current**: No versioning (v1 implicit)

**Future**: URL-based versioning

```
/api/v1/photos
/api/v2/photos
```

### Rate Limiting

**Not implemented** (trusted network assumption)

**Recommended for Production**:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.get("/api/analyze/{year}/{month}")
@limiter.limit("10/minute")
async def analyze_photos(year: int, month: int):
    ...
```

## Deployment Architecture

### Systemd Services

```
┌─────────────────────────────────────────────────────────────────┐
│                         systemd (PID 1)                          │
└───────┬──────────────────────────────────────────────────────────┘
        │
        ├─── immich-server-manager.service
        │    ├─── Type: simple
        │    ├─── WorkingDirectory: /opt/immich-server-manager
        │    ├─── ExecStart: venv/bin/python -m src.main
        │    ├─── Restart: on-failure
        │    ├─── RestartSec: 10s
        │    └─── Wants: network-online.target
        │
        ├─── photo-curator.service
        │    ├─── Type: simple
        │    ├─── WorkingDirectory: /opt/photo-curator
        │    ├─── ExecStart: venv/bin/python -m src.main
        │    ├─── Restart: on-failure
        │    ├─── RestartSec: 10s
        │    └─── Wants: network-online.target
        │
        ├─── health-monitor.timer
        │    ├─── OnBootSec: 5min
        │    ├─── OnUnitActiveSec: 15min
        │    └─── Triggers: health-monitor.service
        │
        └─── health-monitor.service
             ├─── Type: oneshot
             └─── ExecStart: /opt/health-monitor/venv/bin/python -m src.main
```

### Directory Structure

```
/opt/
├── immich-server-manager/
│   ├── venv/                    # Python virtual environment
│   ├── src/                     # Source code
│   ├── static/                  # Web dashboard
│   ├── config/
│   │   └── config.yaml          # Configuration
│   ├── logs/                    # Application logs
│   └── server-manager.db        # SQLite database
│
├── photo-curator/
│   ├── venv/
│   ├── src/
│   ├── static/
│   ├── config/
│   │   └── config.yaml
│   ├── logs/
│   └── curator.db
│
└── health-monitor/
    ├── venv/
    ├── src/
    ├── config/
    │   └── config.yaml
    └── logs/

/etc/systemd/system/
├── immich-server-manager.service
├── photo-curator.service
├── health-monitor.service
└── health-monitor.timer

/var/log/
└── (systemd journal logs)

/mnt/backups/immich/
└── immich_db_*.sql.gz           # Database backups
```

### Network Ports

```
Port 2283  → Immich Web UI & API
Port 8080  → Server Manager
Port 8081  → Photo Curator
```

**Firewall Rules** (UFW):

```bash
# Allow Immich (internal only)
sudo ufw allow from 192.168.0.0/16 to any port 2283

# Allow Manager & Curator (internal only)
sudo ufw allow from 192.168.0.0/16 to any port 8080
sudo ufw allow from 192.168.0.0/16 to any port 8081

# External access via Cloudflare Tunnel (no ports opened)
```

### Cloudflare Tunnel Routing

```yaml
tunnel: <tunnel-id>
credentials-file: /root/.cloudflared/<tunnel-id>.json

ingress:
  # Route root to Immich
  - hostname: photos.yourdomain.com
    service: http://localhost:2283

  # Route /monitor to Server Manager
  - hostname: photos.yourdomain.com
    path: /monitor/*
    service: http://localhost:8080

  # Route /curator to Photo Curator
  - hostname: photos.yourdomain.com
    path: /curator/*
    service: http://localhost:8081

  # Catch-all
  - service: http_status:404
```

## Security Architecture

### Defense in Depth

**Layer 1: Network Security**
- UFW firewall (default deny)
- Cloudflare DDoS protection
- No direct port exposure to internet
- Internal network isolation

**Layer 2: Application Security**
- Immich SSO (no password storage)
- Token-based authentication
- HTTPS via Cloudflare Tunnel
- CORS restrictions

**Layer 3: Data Security**
- Database encryption at rest (optional)
- Backup encryption (optional)
- Secure credential storage
- File permission restrictions

**Layer 4: Monitoring & Response**
- fail2ban (brute force protection)
- Health monitoring
- Alert system
- Audit logging

### Threat Model

**Threats Mitigated**:
- ✅ Brute force attacks (fail2ban)
- ✅ DDoS attacks (Cloudflare)
- ✅ Unauthorized access (authentication)
- ✅ Data loss (backups + verification)
- ✅ Service failures (auto-healing)

**Threats NOT Mitigated** (require additional hardening):
- ❌ Zero-day vulnerabilities (keep software updated)
- ❌ Supply chain attacks (pin dependencies)
- ❌ Insider threats (audit logs, MFA)
- ❌ Physical access (encrypt backups)

### Secrets Management

**Current** (basic):
- Secrets in `config.yaml`
- File permissions: `chmod 600`
- Owner: root

**Recommended** (production):

```bash
# Use environment variables
export IMMICH_API_KEY=$(cat /run/secrets/immich_api_key)
export SMTP_PASSWORD=$(cat /run/secrets/smtp_password)

# systemd service with secrets
[Service]
EnvironmentFile=/etc/immich-manager/secrets.env
```

## Monitoring & Observability

### Logging Strategy

**Log Levels**:
- `DEBUG`: Detailed diagnostic info
- `INFO`: General informational messages
- `WARNING`: Unexpected behavior, not errors
- `ERROR`: Errors that need attention
- `CRITICAL`: System-level failures

**Log Destinations**:
- systemd journal (primary)
- Application log files (secondary)
- Email alerts (critical only)

**Log Rotation**:

```bash
# systemd handles journal rotation automatically
# Config: /etc/systemd/journald.conf
SystemMaxUse=500M
MaxRetentionSec=30day
```

### Metrics Collection

**Collected Metrics**:
- System: CPU, RAM, disk I/O
- Disk: SMART data, temperature
- Backups: Success rate, duration, size
- Services: Uptime, request count, response time
- Photos: Analysis count, quality scores

**Metrics Storage**:
- SQLite (short-term: 90 days)
- Consider: Export to Prometheus/InfluxDB

### Alerting Strategy

**Alert Severity Levels**:

1. **INFO**: Informational only (weekly summary)
2. **WARNING**: Requires attention (email)
3. **CRITICAL**: Immediate action needed (email + webhook)

**Alert Types**:
- Disk health degradation
- High resource usage
- Backup failures
- Service outages
- Database corruption

**Alert Channels**:
- Email (primary)
- Webhooks (Slack/Discord)
- Weekly summaries

## Scalability Considerations

### Current Limitations

- **Single Server**: All components on one machine
- **SQLite**: Not suitable for high concurrency
- **Local Processing**: CPU-bound photo analysis
- **No Load Balancing**: Single instance of each service

### Scaling Strategies

**Vertical Scaling** (recommended for 6-20 users):
- More CPU cores (faster photo analysis)
- More RAM (larger cache)
- Faster disks (SSD for database)

**Horizontal Scaling** (if needed for 50+ users):

```
┌────────────────────────────────────────────────────────────┐
│                    Load Balancer (nginx)                    │
└─────┬────────────────────────────────────┬─────────────────┘
      │                                    │
      ▼                                    ▼
┌──────────────┐                    ┌──────────────┐
│  Curator 1   │                    │  Curator 2   │
└──────┬───────┘                    └──────┬───────┘
       │                                   │
       └───────────┬───────────────────────┘
                   ▼
         ┌──────────────────┐
         │  PostgreSQL DB   │
         │  (shared state)  │
         └──────────────────┘
```

**Database Scaling**:

- Switch to PostgreSQL for multi-instance deployments
- Connection pooling (pgbouncer)
- Read replicas for analytics

**Photo Analysis Scaling**:

- Async task queue (Celery + Redis)
- Worker pool for parallel processing
- GPU acceleration (if using deep learning)

## Future Architecture Improvements

1. **Microservices Communication**
   - Event bus (Redis Pub/Sub or NATS)
   - Service discovery
   - Circuit breakers

2. **Enhanced Monitoring**
   - Prometheus metrics export
   - Grafana dashboards
   - Distributed tracing (OpenTelemetry)

3. **High Availability**
   - Multi-instance deployments
   - Database replication
   - Health checks with failover

4. **API Gateway**
   - Unified API endpoint
   - Authentication middleware
   - Rate limiting

5. **Container Orchestration**
   - Docker Compose for local dev
   - Kubernetes for production (if needed)

## Summary

The Immich Manager ecosystem follows a **microservices architecture** with:

- **3 independent services** (Server Manager, Photo Curator, Health Monitor)
- **Local-first design** (SQLite, no cloud dependencies)
- **Self-healing capabilities** (automatic recovery)
- **Security by default** (Immich SSO, HTTPS, firewall)
- **Observable** (comprehensive logging and metrics)
- **Scalable** (vertical scaling sufficient for most use cases)

The architecture prioritizes:
1. **Simplicity** over complexity
2. **Reliability** over features
3. **Privacy** over convenience
4. **Self-hosting** over cloud services

This design is proven for family deployments (6-20 users) and can scale to larger deployments with minimal modifications.
