# Immich Manager API Documentation

**Comprehensive REST API reference for all Immich Manager services**

## Table of Contents

1. [Overview](#overview)
2. [Server Manager API](#server-manager-api)
3. [Photo Curator API](#photo-curator-api)
4. [Authentication](#authentication)
5. [Error Handling](#error-handling)
6. [Rate Limiting](#rate-limiting)
7. [Examples](#examples)

## Overview

The Immich Manager ecosystem exposes two main REST APIs:

| Service | Base URL | Port | Auth Required |
|---------|----------|------|---------------|
| Server Manager | `http://localhost:8080` | 8080 | No* |
| Photo Curator | `http://localhost:8081` | 8081 | Yes |

*Note: Server Manager currently has no authentication. Recommended to add API key authentication for production use.

### Common Response Format

**Success Response**:
```json
{
  "status": "success",
  "data": { ... },
  "timestamp": "2024-01-15T10:00:00Z"
}
```

**Error Response**:
```json
{
  "status": "error",
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": { ... }
  },
  "timestamp": "2024-01-15T10:00:00Z"
}
```

### API Documentation

Interactive API documentation (Swagger UI) is available at:
- Server Manager: http://localhost:8080/docs
- Photo Curator: http://localhost:8081/docs

## Server Manager API

Base URL: `http://localhost:8080`

### Health & Status

#### GET /health

Health check endpoint for monitoring.

**Response: 200 OK**
```json
{
  "status": "ok"
}
```

**Example**:
```bash
curl http://localhost:8080/health
```

---

#### GET /api/status

Get overall system status and service information.

**Response: 200 OK**
```json
{
  "status": "healthy",
  "uptime_seconds": 86400,
  "version": "1.0.0",
  "services": {
    "database": "connected",
    "immich": "running",
    "monitoring": "active",
    "scheduler": "running"
  },
  "last_backup": "2024-01-15T02:00:00Z",
  "next_backup": "2024-01-16T02:00:00Z",
  "monitored_disks": 2,
  "active_alerts": 0
}
```

**Example**:
```bash
curl http://localhost:8080/api/status
```

---

### Disk Monitoring

#### GET /api/disks

Get SMART health data for all configured disks.

**Response: 200 OK**
```json
{
  "disks": [
    {
      "device": "/dev/sda",
      "model": "Samsung SSD 870 EVO 1TB",
      "serial": "S5H2NS0R123456",
      "capacity_bytes": 1000204886016,
      "capacity_gb": 931,
      "smart_status": true,
      "temperature": 35,
      "power_on_hours": 12543,
      "power_cycle_count": 487,
      "reallocated_sectors": 0,
      "pending_sectors": 0,
      "uncorrectable_sectors": 0,
      "health_ok": true,
      "warnings": []
    },
    {
      "device": "/dev/sdb",
      "model": "WD Red 4TB",
      "serial": "WD-WCC4E123456",
      "capacity_bytes": 4000787030016,
      "capacity_gb": 3726,
      "smart_status": true,
      "temperature": 42,
      "power_on_hours": 25678,
      "power_cycle_count": 234,
      "reallocated_sectors": 2,
      "pending_sectors": 0,
      "uncorrectable_sectors": 0,
      "health_ok": false,
      "warnings": [
        "Reallocated sectors: 2"
      ]
    }
  ],
  "total_disks": 2,
  "healthy_disks": 1,
  "warning_disks": 1,
  "failed_disks": 0
}
```

**Example**:
```bash
curl http://localhost:8080/api/disks | jq
```

---

#### GET /api/disks/{device}

Get SMART health data for a specific disk.

**Path Parameters**:
- `device` (string): Device path (e.g., `sda`, `sdb`)

**Response: 200 OK**
```json
{
  "device": "/dev/sda",
  "model": "Samsung SSD 870 EVO 1TB",
  "smart_status": true,
  "temperature": 35,
  ...
}
```

**Response: 404 Not Found**
```json
{
  "error": {
    "code": "DISK_NOT_FOUND",
    "message": "Disk /dev/sdc is not configured for monitoring"
  }
}
```

**Example**:
```bash
curl http://localhost:8080/api/disks/sda
```

---

### System Metrics

#### GET /api/metrics

Get historical system metrics.

**Query Parameters**:
- `hours` (integer, optional): Number of hours of data to return. Default: 24. Max: 720 (30 days).
- `interval` (integer, optional): Data point interval in minutes. Default: 5.

**Response: 200 OK**
```json
{
  "metrics": [
    {
      "timestamp": "2024-01-15T10:00:00Z",
      "cpu_percent": 12.5,
      "memory_percent": 45.2,
      "memory_used_gb": 7.2,
      "memory_total_gb": 16.0,
      "disk_read_mb": 234.5,
      "disk_write_mb": 456.7
    },
    {
      "timestamp": "2024-01-15T10:05:00Z",
      "cpu_percent": 15.3,
      "memory_percent": 46.1,
      "memory_used_gb": 7.4,
      "memory_total_gb": 16.0,
      "disk_read_mb": 189.2,
      "disk_write_mb": 523.1
    }
  ],
  "period": {
    "start": "2024-01-14T10:00:00Z",
    "end": "2024-01-15T10:00:00Z",
    "hours": 24,
    "data_points": 288
  },
  "summary": {
    "avg_cpu_percent": 13.8,
    "max_cpu_percent": 45.2,
    "avg_memory_percent": 45.7,
    "max_memory_percent": 52.3,
    "total_disk_read_gb": 12.4,
    "total_disk_write_gb": 23.6
  }
}
```

**Example**:
```bash
# Get last 24 hours (default)
curl http://localhost:8080/api/metrics

# Get last 7 days
curl "http://localhost:8080/api/metrics?hours=168"

# Get last hour with 1-minute intervals
curl "http://localhost:8080/api/metrics?hours=1&interval=1"
```

---

### Backup Management

#### GET /api/backups

List all backups with details.

**Query Parameters**:
- `limit` (integer, optional): Max number of backups to return. Default: 100.
- `verified_only` (boolean, optional): Only return verified backups. Default: false.

**Response: 200 OK**
```json
{
  "backups": [
    {
      "id": 123,
      "filename": "immich_db_20240115_020000.sql.gz",
      "timestamp": "2024-01-15T02:00:00Z",
      "size_bytes": 1234567890,
      "size_mb": 1177.4,
      "checksum": "sha256:abc123def456...",
      "success": true,
      "duration_seconds": 45.2,
      "verified": true,
      "offsite_synced": true,
      "local_path": "/mnt/backups/immich/immich_db_20240115_020000.sql.gz"
    },
    {
      "id": 122,
      "filename": "immich_db_20240114_020000.sql.gz",
      "timestamp": "2024-01-14T02:00:00Z",
      "size_bytes": 1230456789,
      "size_mb": 1173.5,
      "checksum": "sha256:def456abc789...",
      "success": true,
      "duration_seconds": 43.8,
      "verified": true,
      "offsite_synced": true,
      "local_path": "/mnt/backups/immich/immich_db_20240114_020000.sql.gz"
    }
  ],
  "total_backups": 45,
  "total_size_gb": 52.3,
  "oldest_backup": "2023-12-01T02:00:00Z",
  "newest_backup": "2024-01-15T02:00:00Z"
}
```

**Example**:
```bash
# List all backups
curl http://localhost:8080/api/backups

# List last 10 backups
curl "http://localhost:8080/api/backups?limit=10"

# List only verified backups
curl "http://localhost:8080/api/backups?verified_only=true"
```

---

#### POST /api/backup/now

Trigger an immediate backup (in addition to scheduled backups).

**Request Body**: None required

**Optional Body**:
```json
{
  "verify": true,
  "sync_offsite": true
}
```

**Response: 202 Accepted**
```json
{
  "status": "started",
  "message": "Backup initiated",
  "job_id": "backup-20240115-103045",
  "estimated_duration_seconds": 45
}
```

**Example**:
```bash
# Trigger backup
curl -X POST http://localhost:8080/api/backup/now

# Trigger backup with verification
curl -X POST http://localhost:8080/api/backup/now \
  -H "Content-Type: application/json" \
  -d '{"verify": true, "sync_offsite": true}'
```

---

#### GET /api/backup/{backup_id}

Get details of a specific backup.

**Path Parameters**:
- `backup_id` (integer): Backup record ID

**Response: 200 OK**
```json
{
  "id": 123,
  "filename": "immich_db_20240115_020000.sql.gz",
  "timestamp": "2024-01-15T02:00:00Z",
  "size_bytes": 1234567890,
  "checksum": "sha256:abc123...",
  "success": true,
  "duration_seconds": 45.2,
  "verified": true,
  "verification_timestamp": "2024-01-15T02:01:00Z",
  "offsite_synced": true,
  "offsite_sync_timestamp": "2024-01-15T02:02:00Z"
}
```

**Example**:
```bash
curl http://localhost:8080/api/backup/123
```

---

### Alert Management

#### GET /api/alerts

Get alert history.

**Query Parameters**:
- `limit` (integer, optional): Max alerts to return. Default: 100.
- `severity` (string, optional): Filter by severity (`warning` or `critical`).
- `acknowledged` (boolean, optional): Filter by acknowledgment status.
- `since` (string, optional): ISO 8601 timestamp. Only return alerts after this time.

**Response: 200 OK**
```json
{
  "alerts": [
    {
      "id": 42,
      "timestamp": "2024-01-15T10:30:00Z",
      "severity": "warning",
      "type": "disk_temperature",
      "message": "Disk /dev/sda temperature 55°C exceeds warning threshold (50°C)",
      "details": {
        "device": "/dev/sda",
        "temperature": 55,
        "threshold": 50
      },
      "acknowledged": false,
      "acknowledged_at": null
    },
    {
      "id": 41,
      "timestamp": "2024-01-14T15:20:00Z",
      "severity": "critical",
      "type": "backup_failed",
      "message": "Database backup failed: Connection timeout",
      "details": {
        "error": "Connection to PostgreSQL container timed out after 30s"
      },
      "acknowledged": true,
      "acknowledged_at": "2024-01-14T15:25:00Z"
    }
  ],
  "total_alerts": 127,
  "unacknowledged_count": 3
}
```

**Example**:
```bash
# Get all alerts
curl http://localhost:8080/api/alerts

# Get unacknowledged alerts only
curl "http://localhost:8080/api/alerts?acknowledged=false"

# Get critical alerts from last 24 hours
curl "http://localhost:8080/api/alerts?severity=critical&since=2024-01-14T10:00:00Z"
```

---

#### POST /api/alerts/{alert_id}/acknowledge

Mark an alert as acknowledged.

**Path Parameters**:
- `alert_id` (integer): Alert ID

**Response: 200 OK**
```json
{
  "status": "success",
  "message": "Alert 42 acknowledged",
  "alert": {
    "id": 42,
    "acknowledged": true,
    "acknowledged_at": "2024-01-15T10:35:00Z"
  }
}
```

**Example**:
```bash
curl -X POST http://localhost:8080/api/alerts/42/acknowledge
```

---

#### POST /api/test-alert

Send a test alert to verify email/webhook configuration.

**Request Body** (optional):
```json
{
  "severity": "warning",
  "channel": "email"
}
```

**Response: 200 OK**
```json
{
  "status": "sent",
  "message": "Test alert sent successfully",
  "recipients": ["admin@example.com"],
  "channels": ["email"]
}
```

**Response: 500 Internal Server Error**
```json
{
  "status": "error",
  "error": {
    "code": "SMTP_ERROR",
    "message": "Failed to send email: Connection refused",
    "details": {
      "smtp_host": "smtp.gmail.com",
      "smtp_port": 587
    }
  }
}
```

**Example**:
```bash
curl -X POST http://localhost:8080/api/test-alert
```

---

### Dashboard

#### GET /

Serve the web dashboard (HTML).

**Response: 200 OK** (HTML page)

**Example**:
Open in browser: http://localhost:8080

---

## Photo Curator API

Base URL: `http://localhost:8081`

**Authentication Required**: All endpoints (except /health) require Immich authentication via cookie.

### Authentication

#### GET /api/auth/check

Check if user is authenticated with Immich.

**Authentication**: Required (immich_access_token cookie)

**Response: 200 OK**
```json
{
  "authenticated": true,
  "user": {
    "id": "abc-123-def-456",
    "email": "user@example.com",
    "name": "John Doe",
    "isAdmin": false
  }
}
```

**Response: 401 Unauthorized**
```json
{
  "authenticated": false,
  "message": "No authentication token found"
}
```

**Example**:
```bash
curl http://localhost:8081/api/auth/check \
  -H "Cookie: immich_access_token=YOUR_TOKEN"
```

---

### Health & Status

#### GET /health

Health check endpoint (no authentication required).

**Response: 200 OK**
```json
{
  "status": "ok"
}
```

**Example**:
```bash
curl http://localhost:8081/health
```

---

#### GET /api/status

Get service status and statistics.

**Authentication**: Required

**Response: 200 OK**
```json
{
  "status": "running",
  "version": "2.0.0",
  "uptime_seconds": 345600,
  "immich_connected": true,
  "immich_version": "v1.92.0",
  "cache": {
    "size_mb": 234.5,
    "files": 1234,
    "path": "/tmp/photo-curator-cache"
  },
  "database": {
    "size_mb": 12.3,
    "path": "/opt/photo-curator/curator.db"
  },
  "statistics": {
    "total_users": 6,
    "total_photos_analyzed": 45678,
    "total_curation_sessions": 24,
    "active_sessions": 2
  }
}
```

**Example**:
```bash
curl http://localhost:8081/api/status \
  -H "Cookie: immich_access_token=YOUR_TOKEN"
```

---

### Photo Analysis

#### POST /api/analyze/{year}/{month}

Analyze photos for a specific month using AI.

**Authentication**: Required

**Path Parameters**:
- `year` (integer): Year (2000-2100)
- `month` (integer): Month (1-12)

**Request Body** (optional):
```json
{
  "force_reanalysis": false
}
```

**Response: 200 OK**
```json
{
  "status": "completed",
  "year": 2024,
  "month": 1,
  "total_photos": 234,
  "analyzed": 234,
  "already_analyzed": 0,
  "top_photos": 50,
  "processing_time_seconds": 45.2,
  "average_score": 0.73,
  "suggested_selections": ["photo-abc-123", "photo-def-456", ...]
}
```

**Response: 202 Accepted** (if analysis takes too long)
```json
{
  "status": "processing",
  "message": "Analysis started in background",
  "job_id": "analysis-2024-01-abc123",
  "estimated_completion": "2024-01-15T10:15:00Z"
}
```

**Response: 400 Bad Request**
```json
{
  "error": {
    "code": "INVALID_DATE",
    "message": "Year must be between 2000 and 2100"
  }
}
```

**Example**:
```bash
# Analyze January 2024
curl -X POST http://localhost:8081/api/analyze/2024/1 \
  -H "Cookie: immich_access_token=YOUR_TOKEN"

# Force re-analysis
curl -X POST http://localhost:8081/api/analyze/2024/1 \
  -H "Cookie: immich_access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"force_reanalysis": true}'
```

---

#### GET /api/photos/{year}/{month}

Get analyzed photos with scores for a specific month.

**Authentication**: Required

**Path Parameters**:
- `year` (integer): Year
- `month` (integer): Month

**Query Parameters**:
- `sort` (string, optional): Sort order (`score_desc`, `score_asc`, `date_desc`, `date_asc`). Default: `score_desc`.
- `limit` (integer, optional): Max photos to return. Default: all.
- `min_score` (float, optional): Minimum quality score (0.0-1.0).

**Response: 200 OK**
```json
{
  "photos": [
    {
      "id": "photo-abc-123",
      "score": 0.87,
      "technical_quality": 0.92,
      "blur_score": 0.95,
      "exposure_score": 0.89,
      "composition_score": 0.78,
      "face_score": 0.85,
      "face_count": 3,
      "perceptual_hash": "abc123def456",
      "width": 4032,
      "height": 3024,
      "megapixels": 12.2,
      "file_size_mb": 4.5,
      "taken_at": "2024-01-15T14:30:00Z",
      "thumbnail_url": "/api/thumbnail/photo-abc-123",
      "original_url": "/api/photo/photo-abc-123"
    }
  ],
  "total_photos": 234,
  "returned_photos": 50,
  "year": 2024,
  "month": 1,
  "target": 50,
  "suggested_selections": ["photo-abc-123", "photo-def-456", ...],
  "average_score": 0.73
}
```

**Example**:
```bash
# Get all analyzed photos for January 2024
curl http://localhost:8081/api/photos/2024/1 \
  -H "Cookie: immich_access_token=YOUR_TOKEN"

# Get top 25 photos only
curl "http://localhost:8081/api/photos/2024/1?limit=25" \
  -H "Cookie: immich_access_token=YOUR_TOKEN"

# Get photos with score >= 0.8
curl "http://localhost:8081/api/photos/2024/1?min_score=0.8" \
  -H "Cookie: immich_access_token=YOUR_TOKEN"
```

---

### Curation

#### POST /api/curation/{year}/{month}/update

Update user's photo selections for curation.

**Authentication**: Required

**Path Parameters**:
- `year` (integer): Year
- `month` (integer): Month

**Request Body**:
```json
{
  "selected": ["photo-abc-123", "photo-def-456", "photo-ghi-789"],
  "added": ["photo-ghi-789"],
  "removed": ["photo-xyz-999"]
}
```

**Response: 200 OK**
```json
{
  "status": "updated",
  "year": 2024,
  "month": 1,
  "selected_count": 52,
  "target": 50
}
```

**Example**:
```bash
curl -X POST http://localhost:8081/api/curation/2024/1/update \
  -H "Cookie: immich_access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "selected": ["photo-1", "photo-2", "photo-3"],
    "added": ["photo-3"],
    "removed": ["photo-4"]
  }'
```

---

#### POST /api/curation/{year}/{month}/complete

Finalize curation and create Immich album.

**Authentication**: Required

**Path Parameters**:
- `year` (integer): Year
- `month` (integer): Month

**Request Body**:
```json
{
  "asset_ids": ["photo-abc-123", "photo-def-456"],
  "album_name": "January 2024 Highlights",
  "description": "Best photos from January 2024"
}
```

**Response: 200 OK**
```json
{
  "status": "completed",
  "album": {
    "id": "album-xyz-789",
    "name": "January 2024 Highlights",
    "description": "Best photos from January 2024",
    "asset_count": 52,
    "created_at": "2024-01-15T10:00:00Z",
    "url": "http://localhost:2283/albums/album-xyz-789"
  },
  "curation_session": {
    "year": 2024,
    "month": 1,
    "completed": true,
    "completed_at": "2024-01-15T10:00:00Z"
  }
}
```

**Example**:
```bash
curl -X POST http://localhost:8081/api/curation/2024/1/complete \
  -H "Cookie: immich_access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_ids": ["photo-1", "photo-2"],
    "album_name": "January 2024",
    "description": "Best of January"
  }'
```

---

### Duplicates

#### GET /api/duplicates

Find duplicate photos using perceptual hashing.

**Authentication**: Required

**Query Parameters**:
- `similarity` (integer, optional): Hamming distance threshold (0-64). Lower = more similar. Default: 5.
- `min_group_size` (integer, optional): Minimum photos in duplicate group. Default: 2.

**Response: 200 OK**
```json
{
  "duplicate_groups": [
    {
      "id": 1,
      "hash": "abc123def456",
      "similarity": 2,
      "photos": [
        {
          "id": "photo-1",
          "score": 0.85,
          "file_size_mb": 4.5,
          "width": 4032,
          "height": 3024,
          "taken_at": "2024-01-15T14:30:00Z",
          "thumbnail_url": "/api/thumbnail/photo-1"
        },
        {
          "id": "photo-2",
          "score": 0.82,
          "file_size_mb": 4.4,
          "width": 4032,
          "height": 3024,
          "taken_at": "2024-01-15T14:30:01Z",
          "thumbnail_url": "/api/thumbnail/photo-2"
        }
      ],
      "recommended_keep": "photo-1",
      "recommended_delete": ["photo-2"]
    }
  ],
  "total_groups": 23,
  "total_duplicates": 45,
  "potential_space_saved_mb": 234.5
}
```

**Example**:
```bash
# Find duplicates with default similarity
curl http://localhost:8081/api/duplicates \
  -H "Cookie: immich_access_token=YOUR_TOKEN"

# Find exact duplicates only (similarity=0)
curl "http://localhost:8081/api/duplicates?similarity=0" \
  -H "Cookie: immich_access_token=YOUR_TOKEN"
```

---

#### POST /api/duplicates/delete

Delete selected duplicate photos from Immich.

**Authentication**: Required

**Request Body**:
```json
{
  "photo_ids": ["photo-2", "photo-5", "photo-8"]
}
```

**Response: 200 OK**
```json
{
  "status": "completed",
  "deleted": 3,
  "failed": 0,
  "space_freed_mb": 15.6,
  "deleted_photos": ["photo-2", "photo-5", "photo-8"],
  "failed_photos": []
}
```

**Response: 207 Multi-Status** (partial success)
```json
{
  "status": "partial",
  "deleted": 2,
  "failed": 1,
  "space_freed_mb": 10.2,
  "deleted_photos": ["photo-2", "photo-5"],
  "failed_photos": [
    {
      "id": "photo-8",
      "error": "Photo not found or already deleted"
    }
  ]
}
```

**Example**:
```bash
curl -X POST http://localhost:8081/api/duplicates/delete \
  -H "Cookie: immich_access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"photo_ids": ["photo-2", "photo-5"]}'
```

---

### User Preferences

#### GET /api/preferences

Get current user's preferences.

**Authentication**: Required

**Response: 200 OK**
```json
{
  "user_id": "abc-123",
  "monthly_target": 50,
  "email_reminders": true,
  "reminder_day": 1,
  "last_curation": "2024-01-01T00:00:00Z",
  "created_at": "2023-06-15T10:00:00Z",
  "updated_at": "2024-01-01T09:00:00Z"
}
```

**Example**:
```bash
curl http://localhost:8081/api/preferences \
  -H "Cookie: immich_access_token=YOUR_TOKEN"
```

---

#### PUT /api/preferences

Update current user's preferences.

**Authentication**: Required

**Request Body**:
```json
{
  "monthly_target": 75,
  "email_reminders": true,
  "reminder_day": 5
}
```

**Response: 200 OK**
```json
{
  "status": "updated",
  "preferences": {
    "user_id": "abc-123",
    "monthly_target": 75,
    "email_reminders": true,
    "reminder_day": 5,
    "updated_at": "2024-01-15T10:30:00Z"
  }
}
```

**Example**:
```bash
curl -X PUT http://localhost:8081/api/preferences \
  -H "Cookie: immich_access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "monthly_target": 75,
    "email_reminders": true,
    "reminder_day": 5
  }'
```

---

### Analytics

#### GET /api/analytics

Get user analytics and statistics.

**Authentication**: Required

**Query Parameters**:
- `period` (string, optional): Time period (`month`, `year`, `all`). Default: `all`.

**Response: 200 OK**
```json
{
  "user_id": "abc-123",
  "total_photos": 12543,
  "average_quality_score": 0.73,
  "photos_by_month": {
    "2024-01": 234,
    "2023-12": 189,
    "2023-11": 267
  },
  "quality_distribution": {
    "excellent": {"count": 1234, "percentage": 9.8, "range": "0.9-1.0"},
    "good": {"count": 5678, "percentage": 45.3, "range": "0.7-0.9"},
    "fair": {"count": 3456, "percentage": 27.6, "range": "0.5-0.7"},
    "poor": {"count": 2175, "percentage": 17.3, "range": "0.0-0.5"}
  },
  "curation_progress": {
    "total_sessions": 12,
    "completed_sessions": 10,
    "in_progress_sessions": 2,
    "total_curated_photos": 520,
    "average_per_month": 52,
    "target_per_month": 50
  },
  "faces_detected": 4567,
  "photos_with_faces": 2345,
  "average_faces_per_photo": 1.95,
  "duplicates_found": 234,
  "storage_saved_mb": 1234.5
}
```

**Example**:
```bash
# Get all-time analytics
curl http://localhost:8081/api/analytics \
  -H "Cookie: immich_access_token=YOUR_TOKEN"

# Get this year's analytics
curl "http://localhost:8081/api/analytics?period=year" \
  -H "Cookie: immich_access_token=YOUR_TOKEN"
```

---

#### GET /api/progress

Get curation progress overview.

**Authentication**: Required

**Response: 200 OK**
```json
{
  "user_id": "abc-123",
  "sessions": [
    {
      "year": 2024,
      "month": 1,
      "completed": true,
      "photos_analyzed": 234,
      "photos_selected": 52,
      "target": 50,
      "completion_percentage": 104,
      "started_at": "2024-01-05T10:00:00Z",
      "completed_at": "2024-01-05T10:30:00Z"
    },
    {
      "year": 2023,
      "month": 12,
      "completed": true,
      "photos_analyzed": 189,
      "photos_selected": 48,
      "target": 50,
      "completion_percentage": 96,
      "started_at": "2024-01-02T14:00:00Z",
      "completed_at": "2024-01-02T14:25:00Z"
    }
  ],
  "overall_progress": 75.5,
  "months_completed": 10,
  "months_total": 12
}
```

**Example**:
```bash
curl http://localhost:8081/api/progress \
  -H "Cookie: immich_access_token=YOUR_TOKEN"
```

---

## Authentication

### Immich SSO (Photo Curator)

Photo Curator uses Immich's existing authentication system.

**Authentication Flow**:

1. User logs into Immich
2. Immich sets `immich_access_token` cookie
3. User accesses Curator with same cookie
4. Curator validates token with Immich API

**Cookie Format**:
```
immich_access_token=<JWT_TOKEN>; Path=/; HttpOnly; SameSite=Lax
```

**Token Validation**:

```bash
# Validate token
curl http://localhost:2283/api/auth/validateToken \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Getting a Token** (for API testing):

```bash
# Login to Immich
TOKEN=$(curl -X POST http://localhost:2283/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "your-password"
  }' | jq -r .accessToken)

# Use token in requests
curl http://localhost:8081/api/status \
  -H "Cookie: immich_access_token=$TOKEN"
```

## Error Handling

### Error Response Format

All errors follow this structure:

```json
{
  "status": "error",
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {
      "field": "Additional context"
    }
  },
  "timestamp": "2024-01-15T10:00:00Z"
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_INPUT` | 400 | Request validation failed |
| `UNAUTHORIZED` | 401 | Authentication required |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `NOT_FOUND` | 404 | Resource not found |
| `ALREADY_EXISTS` | 409 | Resource already exists |
| `IMMICH_ERROR` | 502 | Immich API error |
| `SMTP_ERROR` | 500 | Email sending failed |
| `DATABASE_ERROR` | 500 | Database operation failed |
| `FILESYSTEM_ERROR` | 500 | File operation failed |

### Example Errors

**Invalid Input**:
```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "Validation error",
    "details": {
      "year": "Year must be between 2000 and 2100",
      "month": "Month must be between 1 and 12"
    }
  }
}
```

**Authentication Error**:
```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or expired authentication token"
  }
}
```

**Immich API Error**:
```json
{
  "error": {
    "code": "IMMICH_ERROR",
    "message": "Failed to fetch photos from Immich",
    "details": {
      "immich_status": 500,
      "immich_error": "Internal server error"
    }
  }
}
```

## Rate Limiting

**Current Status**: Not implemented

**Recommended** for production:

- 100 requests/minute per IP for Server Manager
- 60 requests/minute per user for Photo Curator
- 1 analysis request per 5 minutes per user

**Implementation Example**:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/analyze/{year}/{month}")
@limiter.limit("1/5minutes")
async def analyze_photos(year: int, month: int):
    ...
```

## Examples

### Complete Workflow Examples

#### Server Manager: Monitor Disk Health

```bash
#!/bin/bash

# Check all disks
echo "Checking disk health..."
curl -s http://localhost:8080/api/disks | jq '.disks[] | {device, temperature, health_ok}'

# Get alerts for unhealthy disks
echo "Checking for disk alerts..."
curl -s http://localhost:8080/api/alerts?type=disk_health&acknowledged=false
```

#### Server Manager: Trigger and Verify Backup

```bash
#!/bin/bash

# Trigger backup
echo "Starting backup..."
curl -s -X POST http://localhost:8080/api/backup/now | jq

# Wait for backup to complete
sleep 60

# Check latest backup
echo "Verifying backup..."
curl -s http://localhost:8080/api/backups?limit=1 | jq '.backups[0] | {filename, success, verified}'
```

#### Photo Curator: Complete Monthly Curation

```bash
#!/bin/bash

TOKEN="your-immich-token-here"

# Analyze photos
echo "Analyzing January 2024 photos..."
curl -s -X POST http://localhost:8081/api/analyze/2024/1 \
  -H "Cookie: immich_access_token=$TOKEN" | jq

# Get top photos
echo "Fetching top-scored photos..."
TOP_PHOTOS=$(curl -s "http://localhost:8081/api/photos/2024/1?limit=50" \
  -H "Cookie: immich_access_token=$TOKEN" | jq -r '.suggested_selections')

# Create album
echo "Creating album..."
curl -s -X POST http://localhost:8081/api/curation/2024/1/complete \
  -H "Cookie: immich_access_token=$TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"asset_ids\": $TOP_PHOTOS,
    \"album_name\": \"January 2024 Highlights\",
    \"description\": \"Auto-curated best photos\"
  }" | jq
```

#### Photo Curator: Find and Delete Duplicates

```bash
#!/bin/bash

TOKEN="your-immich-token-here"

# Find duplicates
echo "Finding duplicate photos..."
DUPLICATES=$(curl -s "http://localhost:8081/api/duplicates?similarity=5" \
  -H "Cookie: immich_access_token=$TOKEN")

echo "$DUPLICATES" | jq '.duplicate_groups[] | {hash, count: (.photos | length)}'

# Get IDs of photos to delete (lower quality in each group)
TO_DELETE=$(echo "$DUPLICATES" | jq -r '.duplicate_groups[].recommended_delete[]')

# Delete duplicates
echo "Deleting $( echo "$TO_DELETE" | wc -l) duplicate photos..."
curl -s -X POST http://localhost:8081/api/duplicates/delete \
  -H "Cookie: immich_access_token=$TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"photo_ids\": $(echo $TO_DELETE | jq -R -s -c 'split("\n")[:-1]')}" | jq
```

## Support & Resources

- **Interactive API Docs**:
  - Server Manager: http://localhost:8080/docs
  - Photo Curator: http://localhost:8081/docs

- **Source Code**: See component-specific README files

- **Issues**: https://github.com/yourusername/immich-manager/issues

## Version History

- **v1.0.0** (2024-01): Initial release
  - Server Manager API
  - Photo Curator API with Immich SSO

- **v2.0.0** (2024-01): Enhanced features
  - Duplicate detection
  - Analytics dashboard
  - Email notifications
