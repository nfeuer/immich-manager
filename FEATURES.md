# Feature Registry

This file is the **single source of truth** for every feature in Immich Manager — what it does, where it lives, and how to validate it works.

**When you add a feature:** add an entry here. See [docs/ADDING_FEATURES.md](docs/ADDING_FEATURES.md) for the workflow.

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Implemented and tested |
| 🔄 | In progress |
| 📋 | Planned |

---

## Server Manager Features

### ✅ Disk Health Monitoring (SMART)
**Component:** `server-manager`
**Config:** `server-manager/config/config.yaml` → `storage.data_drives`
**API:** `GET /api/disks`

Collects SMART data every 5 minutes. Fires alerts on bad sectors, high temperature, or SMART failure.

**Validate:**
```bash
curl http://localhost:8080/api/disks | jq '.disks[] | {device, temperature, health_ok}'
# Each disk should show health_ok: true (unless there's a real issue)
sudo journalctl -u immich-server-manager | grep "SMART"
```

---

### ✅ Automated PostgreSQL Backups
**Component:** `server-manager`
**Config:** `server-manager/config/config.yaml` → `backup`
**API:** `POST /api/backup/now`, `GET /api/backups`

Daily pg_dump at 2 AM (configurable). Compressed with gzip, SHA256 checksummed, 30-day retention.

**Validate:**
```bash
curl -X POST http://localhost:8080/api/backup/now
sleep 60
curl http://localhost:8080/api/backups | jq '.backups[0] | {filename, success, verified}'
ls -lh /mnt/backups/immich/
```

---

### ✅ Backup Verification System
**Component:** `server-manager/src/backup_verifier.py`
**Config:** `server-manager/config/config.yaml` → `backup_verification`

Verifies SHA256 checksums, test-restores to a temp database, syncs offsite (S3 or Backblaze B2), and enforces a daily/weekly/monthly retention policy.

**Validate:**
```bash
cd server-manager
python verify-backup.py --verify
python verify-backup.py --history
```

---

### ✅ Immich Auto-Updater with Rollback
**Component:** `server-manager`
**Config:** `server-manager/config/config.yaml` → `updates`
**API:** `GET /api/updates/history`, `POST /api/updates/apply`, `GET /api/snapshots`, `POST /api/snapshots/{id}/rollback`

Watches GitHub for new Immich releases. Applies patch updates automatically, creates a snapshot first. Manual rollback available via API or dashboard.

**Validate:**
```bash
curl http://localhost:8080/api/updates/history | jq
curl http://localhost:8080/api/snapshots | jq '.snapshots[0]'
# To test rollback (use a real snapshot ID):
# curl -X POST http://localhost:8080/api/snapshots/1/rollback
```

---

### ✅ Discord Webhook Alerts
**Component:** `server-manager/src/alerts.py`
**Config:** `server-manager/config/config.yaml` → `alerts.discord`

Rich embeds with colour-coded severity (red=critical, orange=warning, blue=info). Quiet hours apply to non-critical alerts.

**Alert types:** disk temp, SMART errors, disk space, backup success/failure, restore events, container down/recovered, update available/applied/failed, rollback events, test alert.

**Validate:**
```bash
curl -X POST http://localhost:8080/api/test-alert
# Check your Discord channel for the test embed
```

---

### ✅ Email Alerts (SMTP)
**Component:** `server-manager/src/alerts.py`
**Config:** `server-manager/config/config.yaml` → `alerts.email`

Same alert types as Discord. Quiet hours respected. Uses aiosmtplib with TLS.

**Validate:**
```bash
curl -X POST http://localhost:8080/api/test-alert
# Check your inbox
sudo journalctl -u immich-server-manager | grep -i smtp
```

---

### ✅ System Metrics Collection
**Component:** `server-manager`
**API:** `GET /api/metrics?hours=24`

CPU, RAM, disk I/O collected every 60 seconds. Stored 90 days in SQLite.

**Validate:**
```bash
curl "http://localhost:8080/api/metrics?hours=1" | jq '.metrics | length'
# Should be > 0 after service has been running
```

---

### ✅ Server Manager Web Dashboard
**Component:** `server-manager/static/`
**Access:** `http://localhost:8080`

Real-time metrics display, disk health table, backup history, alert log, manual controls.

**Validate:** Open `http://localhost:8080` in a browser. Verify charts load and backup/alert data appears.

---

### 🔄 Prometheus Metrics Endpoint
**Component:** `server-manager`
**Status:** Prometheus endpoint implemented; Grafana dashboard config not yet created.

**Validate:**
```bash
curl http://localhost:8080/metrics
# Should return prometheus-format text
```

---

## Photo Curator Features

### ✅ AI Photo Quality Scoring
**Component:** `photo-curator/src/analyzer.py`
**API:** `POST /api/analyze/{year}/{month}`, `GET /api/photos/{year}/{month}`

Local scoring (no API costs): blur (Laplacian variance), exposure (histogram), face detection (Haar cascades), composition (rule of thirds), perceptual hash. Weighted final score 0–1.

**Validate:**
```bash
curl -X POST http://localhost:8081/api/analyze/2024/1 \
  -H "Cookie: immich_access_token=YOUR_TOKEN"
curl "http://localhost:8081/api/photos/2024/1?limit=5" \
  -H "Cookie: immich_access_token=YOUR_TOKEN" | jq '.photos[0] | {score, blur_score, face_count}'
```

---

### ✅ Monthly Photo Curation Workflow
**Component:** `photo-curator`
**API:** `POST /api/curation/{year}/{month}/update`, `POST /api/curation/{year}/{month}/complete`

Users review AI-ranked photos, adjust selections, then create an Immich album with one click.

**Validate:**
1. Open `http://localhost:8081` after logging into Immich
2. Click a month → Analyze → verify photos appear ranked by score
3. Complete curation → verify album appears in Immich

---

### ✅ Duplicate Detection
**Component:** `photo-curator/src/analyzer.py` (perceptual hash)
**API:** `GET /api/duplicates`, `POST /api/duplicates/delete`

Groups photos by perceptual hash similarity. Recommends which to keep (higher quality score). Side-by-side UI for review.

**Validate:**
```bash
curl "http://localhost:8081/api/duplicates?similarity=5" \
  -H "Cookie: immich_access_token=YOUR_TOKEN" | jq '.total_groups'
```

---

### ✅ User Preferences
**Component:** `photo-curator`
**API:** `GET /api/preferences`, `PUT /api/preferences`
**Access:** `/preferences` page

Per-user settings: monthly target photos, email reminder opt-in, reminder day.

**Validate:**
```bash
curl http://localhost:8081/api/preferences \
  -H "Cookie: immich_access_token=YOUR_TOKEN"
# Should return user's saved preferences
```

---

### ✅ Analytics Dashboard
**Component:** `photo-curator`
**Access:** `/analytics` (Immich SSO required)

Total users, curated photos, albums created, average quality score, upload trend chart (12 months), user activity bar chart, per-user stats table.

**Validate:**
1. Navigate to `http://localhost:8081/analytics` while logged in
2. Verify charts load and show data for your users

---

### ✅ Monthly Email Reminders
**Component:** `photo-curator/src/notifications.py`
**Config:** `photo-curator/config/config.yaml` → `notifications.email`

Sends on the 1st of each month to users who opted in. Requires SMTP config and user opt-in at `/preferences`.

**Validate:**
```bash
sudo journalctl -u photo-curator | grep -i "reminder"
# On 1st of month: "Monthly reminders sent to X users"
# Anytime: "Scheduler started (monthly reminders at 09:00)"
```

---

### ✅ Face Recognition
**Component:** `photo-curator/src/analyzer.py`
**Details:** 128-dimensional dlib embeddings, greedy identity clustering, user labelling and merge
**ML deps required:** `pip install -r photo-curator/requirements-ml.txt` (dlib, face_recognition)

**Validate:**
```bash
curl "http://localhost:8081/api/photos/2024/1" \
  -H "Cookie: immich_access_token=YOUR_TOKEN" | jq '[.photos[].face_count] | add'
# Should be > 0 if photos have faces
```

---

### ✅ Scene Detection
**Component:** `photo-curator/src/analyzer.py`
**Details:** MobileNetV2-Places365, 10 super-categories (indoor, outdoor, nature, urban, etc.)
**ML deps required:** `pip install -r photo-curator/requirements-ml.txt` (torch, torchvision)

**Validate:** Scene categories appear in photo analysis results (check `/api/photos/{year}/{month}` response).

---

### ✅ Guest Access Links
**Component:** `photo-curator`
**Details:** Temporary expiring share links for non-Immich users

**Validate:** Create a guest link from the UI and verify it expires after the configured duration.

---

### ✅ Role Management (RBAC)
**Component:** `shared/auth/`
**Details:** Admin, family member, and guest permission tiers

**Validate:** Log in as different user types and verify access controls are enforced.

---

### ✅ Web Import Wizard
**Component:** `photo-curator/static/import.html`, `photo-curator/src/main.py`
**API:** `POST /api/import/upload`, `POST /api/import/start`, `GET /api/import/jobs`, `GET /api/import/jobs/{id}`, `DELETE /api/import/jobs/{id}`
**Access:** `/import` (Immich SSO required)

Browser-based import wizard for Google Photos, Apple Photos, and iCloud exports. Any user can upload files via browser drag-and-drop; admins can also specify a server filesystem path for large libraries pre-transferred via SFTP/rsync. Background processing with real-time progress polling, cancellation support, and import history.

**Validate:**
```bash
# Check the import page loads
curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/import \
  -H "Cookie: immich_access_token=YOUR_TOKEN"
# Should return 200

# List import jobs
curl http://localhost:8081/api/import/jobs \
  -H "Cookie: immich_access_token=YOUR_TOKEN" | jq '.jobs'

# Start a server-path import (admin only)
curl -X POST http://localhost:8081/api/import/start \
  -H "Cookie: immich_access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_type":"google","server_path":"/path/to/Takeout"}' | jq
```

---

## Health Monitor Features

### ✅ Self-Healing Service Monitor
**Component:** `health-monitor/src/main.py`
**Schedule:** systemd timer, every 15 minutes

Checks Photo Curator and Server Manager via HTTP + systemd. Automatically restarts failed services. Cooldown prevents restart loops.

**Validate:**
```bash
sudo systemctl status health-monitor.timer
sudo journalctl -u health-monitor.service -n 50
# Should show periodic health check results
```

---

### ✅ Database Optimization
**Component:** `health-monitor/src/main.py`

Runs SQLite VACUUM on curator and manager databases during health checks.

**Validate:** Check health monitor logs for "Optimized database" entries.

---

## Remote Access & Security Features

### ✅ Cloudflare Tunnel Remote Access
**Component:** `scripts/30-install-remote-access.sh`, `cloudflare-tunnel/config.yml`

HTTPS remote access with no port-forwarding. Routes `yourdomain.com` → Immich, `/monitor/` → Server Manager, `/curator/` → Photo Curator.

**Validate:**
```bash
sudo systemctl status cloudflared
curl https://yourdomain.com/api/server-info
```

---

### ✅ Security Hardening
**Component:** `scripts/40-security-hardening.sh`

fail2ban (brute force protection), UFW firewall rules, security monitoring scripts, security checklist.

**Validate:**
```bash
sudo systemctl status fail2ban
sudo ufw status
/opt/immich-ecosystem/scripts/security-monitor.sh
```

---

## Migration Tools

### ✅ Google Photos Migration Tool
**Component:** `migration-tools/google-photos-import.py`

Imports Google Takeout archives to Immich with metadata preservation (capture dates, GPS, descriptions). Resumable via progress file. Duplicate detection.

**Validate:**
```bash
cd migration-tools
python google-photos-import.py --help
# Run with a small test Takeout folder first
python google-photos-import.py \
  --takeout-dir ~/test-takeout \
  --immich-url http://localhost:2283 \
  --api-key YOUR_KEY
```

---

### ✅ Apple Photos Migration Tool
**Component:** `migration-tools/apple-photos-import.py`

Imports Apple Photos.app exports to Immich. Reads EXIF metadata (capture dates, GPS) from JPEG/PNG/HEIC files using Pillow. Detects and skips Live Photo companion `.MOV` files by default. Resumable.

**Validate:**
```bash
cd migration-tools
python apple-photos-import.py --help
# Export a small album from Photos.app first, then test:
python apple-photos-import.py \
  --photos-dir ~/Desktop/ApplePhotosExport \
  --immich-url http://localhost:2283 \
  --api-key YOUR_KEY
```

---

### ✅ iCloud Photos Migration Tool
**Component:** `migration-tools/icloud-import.py`

Imports iCloud data exports (from privacy.apple.com) to Immich. Reads EXIF metadata from files; falls back to year/month inferred from export directory names when EXIF is absent. Auto-detects the photos folder within Apple's export structure. Resumable.

**Validate:**
```bash
cd migration-tools
python icloud-import.py --help
# Point at the extracted Apple data export:
python icloud-import.py \
  --export-dir ~/Downloads/Apple_Media_Services \
  --immich-url http://localhost:2283 \
  --api-key YOUR_KEY
```

---

## Planned Features

| Feature | Notes |
|---------|-------|
| 📋 Per-user storage quotas | Limits, warnings, upload blocking |
| 📋 Video transcoding/compression | Automated format conversion |
| 📋 Smart cleanup assistant | Surface old/low-quality photos for bulk deletion |
| 📋 User onboarding flow | Invite family members via email |
| 📋 Smart album rules engine | Auto-populate by date, location, quality, face tags |
| 📋 Trip/event detection | GPS + time gap clustering |
| 📋 "On this day" digest emails | Photos from this date in past years |
| 📋 Additional import sources | Facebook, Instagram, OneDrive, Amazon Photos |
| 📋 Photo book PDF export | Printable PDF for local upload to print services |
| 📋 Self-update for immich-manager | git pull + restart workflow |
| 📋 Email digest reports | Weekly/monthly health and curation summaries |
| 📋 Grafana dashboard | Config for Prometheus data already collected |
| 📋 Mobile app for Photo Curator | XL effort |

---

*When a planned feature is implemented, move it to the appropriate implemented section above and add validation steps.*
