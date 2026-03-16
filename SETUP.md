# Immich Manager - Setup & Configuration Guide

This document contains all the configuration settings, required services, and setup steps for the Immich Manager ecosystem.

---

## 📋 Quick Start Checklist

**Before You Begin:**
- [ ] Ubuntu/Debian Linux with sudo access
- [ ] Storage drives set up (see [Drive Setup](#-drive-setup-mergerfs--snapraid) below)
- [ ] Run `./scripts/00-check-prerequisites.sh` — fixes any missing system deps
- [ ] Start Immich via Docker (see [Docker Setup](#-docker-setup-installing-immich) below)
- [ ] Domain name for Cloudflare Tunnel (optional but recommended)

> **Note:** Python, Docker Compose, and other software prerequisites are either detected by `00-check-prerequisites.sh` or installed automatically by the phase scripts. You do not need to install them manually.

**Required Setup:**
- [ ] Configure Immich API access
- [ ] Set up SMTP for email notifications (optional)
- [ ] Configure Cloudflare Tunnel (for remote access)
- [ ] Set curator URL for email links

---

## 🐳 Docker Setup: Installing Immich

This repo ships Docker Compose files for Immich in the `docker/` directory. Run these steps **before** `./install.sh`.

### 1. Run the Prerequisites Check

```bash
./scripts/00-check-prerequisites.sh
```

This script checks for Docker, Docker Compose, Python 3.9+, available ports, storage mounts, and more. It prints the exact `apt install` or config commands needed to fix anything that fails. Fix all failures and rerun until it passes cleanly (warnings are OK to proceed with).

### 2. Configure the Docker Environment

```bash
cp docker/.env.example docker/.env
nano docker/.env
```

Key variables to set:

| Variable | Description |
|----------|-------------|
| `IMMICH_DB_PASSWORD` | Strong random password — generate: `openssl rand -base64 32` |
| `IMMICH_UPLOAD_LOCATION` | Photo library storage path (e.g. `/mnt/storage/immich/library` or `./data/library`) |
| `IMMICH_VERSION` | `release` for latest, or pin to e.g. `v1.117.0` |
| `IMMICH_ML_GPU_ID` | GPU index for ML inference (default `0`). Comment out the `deploy:` block in `docker/immich.yml` for CPU-only. |

> Keep `docker/.env` out of version control — it's already in `.gitignore`.

### 3. Start Immich

```bash
docker compose --env-file docker/.env \
  -f docker/core.yml -f docker/immich.yml up -d
```

This creates four containers: `immich-server` (API + web UI on port 2283), `immich-ml` (CLIP / face recognition), `immich-postgres`, and `immich-redis`.

**Verify Immich is running:**

```bash
curl http://localhost:2283/api/server-info
```

Allow ~30 seconds for database initialization on first run. See [docs/DOCKER.md](docs/DOCKER.md) for everyday commands (logs, stop, update, GPU assignment).

### 4. First-Time Immich Setup

1. Open `http://localhost:2283` in your browser
2. Create your admin account
3. Go to your avatar → **Account Settings** → **API Keys** → create a key

You'll paste this API key into the config files in the next section.

---

## 🔧 Prerequisite Setup Steps

Complete these before running the install scripts.

### Immich API Key

The API key lets Immich Manager perform background operations (monthly reminders, server monitoring, backups) on your behalf.

1. Open your Immich web interface
2. Click your user avatar (top-right) → **Account Settings** → **API Keys**
3. Click **New API Key**, give it a name (e.g. `Immich Manager`), click **Create**
4. Copy the key — it is **only shown once**
5. After install, paste it into both config files:
   - `photo-curator/config/config.yaml` → `immich.api_key`
   - `server-manager/config/config.yaml` → `immich.api_key`

> **Security note:** This key has full admin access to Immich. Keep it out of version control.

---

### SMTP / Email (Optional)

Required only if you want monthly curation reminder emails sent to users. Skip this section if you don't need email notifications.

#### Gmail Setup (Recommended)

1. **Enable 2-Factor Authentication**
   - Go to: https://myaccount.google.com/security
   - Enable 2-Step Verification if not already on

2. **Create an App Password**
   - Go to: https://myaccount.google.com/apppasswords
   - Select **Mail** and **Other (Custom name)**
   - Name it `Immich Manager`
   - Copy the 16-character password (no spaces)

3. **Add to your config** (`photo-curator/config/config.yaml`):
   ```yaml
   notifications:
     email:
       enabled: true
       smtp_host: "smtp.gmail.com"
       smtp_port: 587
       smtp_user: "your-email@gmail.com"
       smtp_password: "abcd efgh ijkl mnop"  # App password from step 2
       from: "your-email@gmail.com"
   ```

**Alternative SMTP Providers:**
- **SendGrid**: `smtp.sendgrid.net:587` (API key as password)
- **Mailgun**: `smtp.mailgun.org:587`
- **Amazon SES**: `email-smtp.<region>.amazonaws.com:587`
- **Custom**: Use your own mail server

> See [Required API Keys & Services](#-required-api-keys--services) for additional detail on both of these.

---

## 💾 Drive Setup: mergerfs + SnapRAID

Before installing Immich Manager, set up your storage drives using [mergerfs-snapraid](https://github.com/nfeuer/mergerfs-snapraid). This creates a unified storage pool for Immich's photo library protected against drive failure.

### Why Do This First?

- Immich should store photos on dedicated data drives, not the OS disk
- mergerfs pools multiple drives into a single mount point (e.g. `/mnt/storage`)
- SnapRAID adds parity protection — one drive failure won't lose data
- The prerequisite check in `00-check-prerequisites.sh` looks for `/mnt/storage` or `/mnt/user`

### Steps

```bash
git clone https://github.com/nfeuer/mergerfs-snapraid.git
cd mergerfs-snapraid
sudo ./setup-mergerfs-snapraid.sh
```

The script will:
1. Detect available disks
2. Guide you through selecting data drives and a parity drive
3. Format drives (with safety confirmations)
4. Install mergerfs and SnapRAID
5. Configure `/etc/fstab` and `/etc/snapraid.conf`
6. Set up systemd timers for daily sync (2 AM) and weekly scrub (Sundays 3 AM)

### Requirements

- 2+ data drives (mixed sizes are fine)
- 1 parity drive (must be >= the size of your largest data drive)
- Root/sudo access

### After Setup

Your pool will be mounted at `/mnt/storage` (or `/mnt/user`). When installing Immich, point its upload path there (e.g. `/mnt/storage/immich`).

---

## 🔧 Configuration Files

### 1. Photo Curator Configuration
**File**: `photo-curator/config/config.yaml`

```yaml
# Copy from config.yaml.example and customize

server:
  host: "0.0.0.0"
  port: 8081
  workers: 2

immich:
  # Base URL for Immich (used for SSO authentication)
  base_url: "http://localhost:2283"

  # API URL for backend requests
  api_url: "http://localhost:2283/api"

  # API key (OPTIONAL - only needed for admin background jobs)
  # Get this from: Immich Web UI → Settings → API Keys → Create
  api_key: ""  # Leave empty if not using background jobs

ai:
  use_local_models: true
  model_path: "models/"
  batch_size: 10
  quality_threshold: 0.6

scoring:
  weights:
    technical_quality: 0.3
    faces: 0.3
    uniqueness: 0.2
    aesthetic: 0.2

curation:
  monthly_target: 50  # Default target photos per month for new users
  reminder_day: 1     # Always 1st of month
  reminder_time: "09:00"  # When to check daily for monthly reminders

notifications:
  email:
    enabled: false  # Set to true after configuring SMTP
    smtp_host: "smtp.gmail.com"  # Your SMTP server
    smtp_port: 587
    smtp_user: "your-email@gmail.com"
    smtp_password: "your-app-password"  # See "Email Setup" section below
    from: "photo-curator@yourdomain.com"
```

**TODO: Edit This File**
1. Copy `config.yaml.example` to `config.yaml`
2. Update `immich.base_url` if not using default
3. Add `immich.api_key` if using background jobs (get from Immich settings)
4. Configure SMTP settings (see Email Setup section)

---

### 2. Server Manager Configuration
**File**: `server-manager/config/config.yaml`

```yaml
server:
  host: "0.0.0.0"
  port: 8080

immich:
  api_url: "http://localhost:2283/api"
  api_key: ""  # Same as Photo Curator

backup:
  enabled: true
  schedule: "0 2 * * *"  # Daily at 2 AM (cron format)
  retention_days: 30
  backup_dir: "/mnt/backups/immich"  # Must have write permissions

monitoring:
  disk_check_interval: 3600  # Seconds (1 hour)
  alert_threshold_percent: 90
```

**TODO: Edit This File**
1. Copy `config.yaml.example` to `config.yaml`
2. Add `immich.api_key` from Immich settings
3. Set `backup.backup_dir` to your backup location
4. Adjust `backup.schedule` if needed (uses cron syntax)

---

## 🔑 Required API Keys & Services

### 1. Immich API Key
**What**: Admin API key for background operations
**Required For**: Monthly reminders, server monitoring, backups
**How to Get**:
1. Open Immich web interface
2. Click Settings (⚙️) → API Keys
3. Click "Create API Key"
4. Copy the key (shown only once!)
5. Paste into both config files

**Where to Add**:
- `photo-curator/config/config.yaml` → `immich.api_key`
- `server-manager/config/config.yaml` → `immich.api_key`

**Note**: Keep this secure! It has full admin access to Immich.

---

### 2. Email / SMTP Configuration
**What**: Email server for monthly reminders and notifications
**Required For**: Monthly curation reminders (optional feature)
**Recommended Provider**: Gmail with App Password

#### Gmail Setup (Recommended)
1. **Enable 2-Factor Authentication**
   - Go to: https://myaccount.google.com/security
   - Enable 2-Step Verification if not already enabled

2. **Create App Password**
   - Go to: https://myaccount.google.com/apppasswords
   - Select "Mail" and "Other (Custom name)"
   - Name it "Immich Photo Curator"
   - Copy the 16-character password (no spaces)

3. **Configure in config.yaml**
   ```yaml
   notifications:
     email:
       enabled: true
       smtp_host: "smtp.gmail.com"
       smtp_port: 587
       smtp_user: "your-email@gmail.com"
       smtp_password: "abcd efgh ijkl mnop"  # App password from step 2
       from: "your-email@gmail.com"
   ```

**Alternative SMTP Providers**:
- **SendGrid**: smtp.sendgrid.net:587 (API key as password)
- **Mailgun**: smtp.mailgun.org:587
- **Amazon SES**: email-smtp.region.amazonaws.com:587
- **Custom**: Use your own mail server

**TODO: Configure Email**
1. Get SMTP credentials from your provider
2. Update `photo-curator/config/config.yaml` → `notifications.email`
3. Set `enabled: true`
4. Test by opting in to monthly reminders in preferences

---

### 3. Cloudflare Tunnel (Optional but Recommended)
**What**: Secure remote access without opening ports
**Required For**: Remote access to curator, duplicates, preferences
**Cost**: Free

#### Setup Steps
1. **Install cloudflared**
   ```bash
   # Already included in scripts/30-install-remote-access.sh
   ```

2. **Authenticate with Cloudflare**
   ```bash
   cloudflared tunnel login
   ```
   - This opens browser to authenticate
   - Select your domain

3. **Configure Tunnel**
   - Edit `cloudflare-tunnel/config.yml`
   - Set your domain names:
     ```yaml
     tunnel: <tunnel-id>
     credentials-file: /root/.cloudflared/<tunnel-id>.json

     ingress:
       - hostname: photos.yourdomain.com
         service: http://localhost:2283
       - hostname: curator.yourdomain.com
         service: http://localhost:8081
       - hostname: manager.yourdomain.com
         service: http://localhost:8080
       - service: http_status:404
     ```

**TODO: Configure Cloudflare**
1. Run `scripts/30-install-remote-access.sh`
2. Authenticate with `cloudflared tunnel login`
3. Update domain names in tunnel config
4. Create DNS records in Cloudflare dashboard

**Domain Names Needed**:
- `photos.yourdomain.com` → Immich (main app)
- `curator.yourdomain.com` → Photo Curator
- `manager.yourdomain.com` → Server Manager (admin only)

---

## 🎯 New Features (Just Added)

### Analytics Dashboard
**Location**: `/analytics` (Immich SSO required)

**What It Shows**:
- Total users in the system
- Photos curated (completed sessions)
- Albums created
- Average quality score
- Upload trend over last 12 months (line chart)
- User activity comparison (bar chart)
- Detailed user statistics table

**How to Access**:
1. Log in to Photo Curator
2. Navigate to `/analytics` (or add link in curator UI)
3. Select time period (7, 30, 90, or 365 days)

**No Configuration Needed**: Works automatically with existing database

---

### Google Photos Migration Tool
**Location**: `migration-tools/google-photos-import.py`

**Purpose**: Import Google Takeout photos to Immich with metadata preservation

**Features**:
- Preserves capture dates
- Preserves GPS coordinates
- Preserves descriptions
- Resumable (tracks progress)
- Duplicate detection

**Usage**:
```bash
cd migration-tools

python google-photos-import.py \
  --takeout-dir ~/Downloads/Takeout \
  --immich-url http://localhost:2283 \
  --api-key YOUR_IMMICH_API_KEY

# Optional: Resume interrupted import
python google-photos-import.py \
  --takeout-dir ~/Downloads/Takeout \
  --immich-url http://localhost:2283 \
  --api-key YOUR_IMMICH_API_KEY \
  --resume
```

**Progress Tracking**: Saves to `import-progress.json` automatically

---

### Health Check Automation
**Location**: `health-monitor/src/main.py`

**Purpose**: Self-healing system monitoring

**What It Monitors**:
- Photo Curator service (HTTP + systemd)
- Server Manager service (HTTP + systemd)
- Disk space (configurable threshold)
- Database health (SQLite integrity)

**Auto-Healing**:
- Automatically restarts failed services
- Optimizes database if corrupted
- Sends alerts for critical issues

**Setup**:
```bash
# Install systemd service
sudo cp health-monitor/health-monitor.service /etc/systemd/system/
sudo cp health-monitor/health-monitor.timer /etc/systemd/system/

# Enable and start
sudo systemctl enable health-monitor.timer
sudo systemctl start health-monitor.timer

# Check status
sudo systemctl status health-monitor.timer
```

**Runs Every**: 15 minutes (configurable in timer file)

---

### Backup Verification System
**Location**: `server-manager/src/backup_verifier.py`

**Purpose**: Ensure backups are restorable and valid

**Features**:
- ✅ Checksum verification (SHA256)
- ✅ Test restore to temporary database
- ✅ Offsite sync (AWS S3 or Backblaze B2)
- ✅ Intelligent retention policy (daily/weekly/monthly)
- ✅ Email alerts on verification failure
- ✅ Verification history log

**Setup**:
1. **Configure in `server-manager/config/config.yaml`**:
   ```yaml
   backup_verification:
     backup_dir: "/mnt/backups/immich"
     offsite_sync:
       enabled: true
       type: "s3"  # or "backblaze"
       bucket: "my-immich-backups"
       region: "us-east-1"
       access_key: "YOUR_AWS_ACCESS_KEY"
       secret_key: "YOUR_AWS_SECRET_KEY"
   ```

2. **Install systemd timer** (runs monthly):
   ```bash
   sudo cp server-manager/backup-verification.service /etc/systemd/system/
   sudo cp server-manager/backup-verification.timer /etc/systemd/system/
   sudo systemctl enable backup-verification.timer
   sudo systemctl start backup-verification.timer
   ```

3. **Manual verification**:
   ```bash
   cd server-manager

   # Verify latest backup
   python verify-backup.py --verify

   # Apply retention policy
   python verify-backup.py --retention

   # View history
   python verify-backup.py --history

   # Force offsite sync
   python verify-backup.py --verify --offsite
   ```

**Retention Policy**:
- Daily: Keep 7 most recent backups
- Weekly: Keep 4 weekly backups (one per week)
- Monthly: Keep 12 monthly backups (one per month)

**Offsite Sync Options**:
- **AWS S3**: Full S3 bucket support
- **Backblaze B2**: Cost-effective alternative to S3

**Monitoring**:
- Verification results logged to `data/backup-verification.json`
- Email sent on verification failure (if configured)
- View history with `verify-backup.py --history`

---

## 📝 Code Changes Required

### 1. Update Curator URL in Email Links
**File**: `photo-curator/src/main.py`
**Line**: ~229
**Current**:
```python
curator_url = app.state.immich_base_url.replace('2283', '8081')  # Temporary
```

**TODO: Replace with**:
```python
curator_url = "https://curator.yourdomain.com"  # Your actual Cloudflare domain
```

**Why**: Email links need to point to your public domain, not localhost

---

### 2. Backup Directory Permissions
**Path**: Set in `server-manager/config/config.yaml` → `backup.backup_dir`

**TODO: Ensure Permissions**
```bash
# Create backup directory
sudo mkdir -p /mnt/backups/immich

# Give ownership to user running the service
sudo chown -R $USER:$USER /mnt/backups/immich

# Set permissions
chmod 755 /mnt/backups/immich
```

**Why**: Backup script needs write access to save backups

---

## 🚀 Installation & Startup

### Setup Scripts Overview

The `scripts/` directory contains numbered setup scripts that handle each installation phase. `./install.sh` runs them all in sequence, or you can run any script individually to install just that component.

| Script | What it does |
|--------|-------------|
| `scripts/00-check-prerequisites.sh` | Validates Docker, Python, ports, storage, internet. Prints fix commands for anything missing. Run this first. |
| `scripts/10-install-server-manager.sh` | Installs Server Manager + smartmontools (disk SMART monitoring). Creates systemd service. |
| `scripts/20-install-photo-curator.sh` | Installs Photo Curator + OpenCV system libs + ML/AI Python packages. Creates systemd service. |
| `scripts/30-install-remote-access.sh` | Installs `cloudflared` and configures a Cloudflare Tunnel for remote HTTPS access. Optional. |
| `scripts/40-security-hardening.sh` | Configures fail2ban, UFW firewall, and security monitoring. |
| `scripts/50-test-installation.sh` | Runs end-to-end tests to verify all services started correctly. |

### Run the Installer

```bash
./install.sh
```

Or run individual phases manually:

```bash
# 0. Prerequisites check (reports missing software + install commands)
./scripts/00-check-prerequisites.sh

# 1. Install Server Manager (also installs smartmontools)
./scripts/10-install-server-manager.sh

# 2. Install Photo Curator (also installs OpenCV system libs + ML/AI Python packages)
./scripts/20-install-photo-curator.sh

# 3. Configure Remote Access (Cloudflare)
./scripts/30-install-remote-access.sh

# 4. Security Hardening
./scripts/40-security-hardening.sh
```

> The install scripts automatically install system-level prerequisites (smartmontools, OpenCV libraries, ML dependencies) via `apt` and `pip`. You do not need to install these manually before running.

### Manual Startup (for testing)

```bash
# Photo Curator
cd photo-curator
python -m src.main

# Server Manager
cd server-manager
python -m src.main
```

### Production Startup (systemd services)

```bash
# Start services
sudo systemctl start photo-curator
sudo systemctl start server-manager

# Enable on boot
sudo systemctl enable photo-curator
sudo systemctl enable server-manager

# Check status
sudo systemctl status photo-curator
sudo systemctl status server-manager

# View logs
sudo journalctl -u photo-curator -f
sudo journalctl -u server-manager -f
```

---

## 🔐 Security Considerations

### 1. API Key Storage
- **Never** commit API keys to git
- Store in config files (already in `.gitignore`)
- Use environment variables if preferred

### 2. SMTP Password
- Use App Passwords, not your main account password
- Gmail App Passwords are automatically revocable
- Consider using dedicated email account

### 3. Cloudflare Tunnel
- Automatically encrypts traffic (TLS)
- No firewall rules needed
- Cloudflare handles DDoS protection
- Free tier includes basic protection

### 4. User Authentication
- All curator features require Immich SSO
- No separate user database
- Session validation via Immich API
- Auto-redirect to Immich login if not authenticated

---

## 📊 Feature Configuration

### Monthly Email Reminders
**Status**: Implemented, requires SMTP configuration
**How to Enable**:
1. Configure SMTP in `photo-curator/config/config.yaml`
2. Set `notifications.email.enabled: true`
3. Restart photo-curator service
4. Users opt-in via `/preferences` page

**Behavior**:
- Checks daily at configured time (default: 9 AM)
- Only sends on 1st of month
- Only sends to users who opted in
- Only sends if user has photos from previous month

**Testing**:
```bash
# Check logs for scheduler
sudo journalctl -u photo-curator | grep "reminder"

# Should see:
# "Scheduler started (monthly reminders at 09:00)"
# "Monthly reminders sent to X users" (on 1st of month)
```

---

### User Preferences
**Location**: `/preferences` (Immich SSO required)

**Available Settings**:
- ✅ Monthly curation reminders (email, opt-in)
- 🔜 Photo quality alerts (coming soon)
- 🔜 Memory Lane emails (coming soon)
- 🔜 Seasonal automations (coming soon)
- ⚠️ Storage warnings (always enabled, critical)
- ✅ Monthly target photos (default: 50)
- ✅ Duplicate warnings in UI

**Storage**: SQLite database per user

---

### Duplicate Detection
**Location**: `/duplicates` (Immich SSO required)

**How It Works**:
1. Perceptual hash computed during photo analysis
2. Similar hashes grouped as duplicates
3. User reviews groups side-by-side
4. Options:
   - Keep best quality (automatic selection)
   - Manual keep/delete
   - Batch deletion

**Configuration**: No configuration needed, works automatically

---

## 🐛 Troubleshooting

### Email Not Sending
**Check**:
1. SMTP credentials correct?
2. `notifications.email.enabled: true`?
3. User opted in at `/preferences`?
4. Check logs: `journalctl -u photo-curator | grep email`

**Gmail Issues**:
- Using App Password, not regular password?
- 2FA enabled on account?
- "Less secure apps" NOT needed with App Password

---

### Photos Not Loading
**Check**:
1. Immich API key valid?
2. `immich.api_url` correct in config?
3. Immich service running?
4. Check logs: `journalctl -u photo-curator | grep Immich`

---

### Monthly Reminders Not Working
**Check**:
1. Admin API key configured?
2. Email SMTP configured?
3. Users opted in?
4. Is it the 1st of the month?
5. Check scheduler: `journalctl -u photo-curator | grep scheduler`

---

## 📚 File Locations Reference

### Configuration Files
```
photo-curator/config/config.yaml       # Main curator config
server-manager/config/config.yaml      # Server manager config
cloudflare-tunnel/config.yml           # Tunnel configuration
```

### Database Files
```
photo-curator/data/curator.db          # SQLite database (auto-created)
photo-curator/models/                  # AI models (auto-downloaded)
/tmp/immich-curator-cache/             # Photo cache (auto-managed)
```

### Log Files
```
# Systemd logs (via journalctl)
sudo journalctl -u photo-curator -f
sudo journalctl -u server-manager -f

# Or check service logs directly
/var/log/syslog
```

### Backup Files
```
/mnt/backups/immich/                   # Configurable in server-manager
  ├── backup-2024-01-01.tar.gz
  ├── backup-2024-01-02.tar.gz
  └── ...
```

---

## 🎯 Post-Installation Checklist

**After Installation:**
- [ ] Access curator at `http://localhost:8081` or your domain
- [ ] Log in with Immich credentials
- [ ] Visit `/preferences` and configure email preferences
- [ ] Visit `/duplicates` to check for duplicate photos
- [ ] Visit `/analytics` to view system analytics dashboard
- [ ] Test monthly reminder (or wait for 1st of month)
- [ ] Check server manager at `http://localhost:8080`
- [ ] Verify backups running in server manager
- [ ] Configure Cloudflare Tunnel for remote access
- [ ] Update email link URL in code (line 229 of main.py)

**New Features Setup:**
- [ ] Install health monitor timer (`sudo systemctl enable health-monitor.timer`)
- [ ] Configure backup verification in `server-manager/config/config.yaml`
- [ ] Install backup verification timer (`sudo systemctl enable backup-verification.timer`)
- [ ] Test backup verification: `python verify-backup.py --verify`
- [ ] Configure offsite sync (S3/Backblaze) if desired
- [ ] Run Google Photos import if migrating (see SETUP.md for usage)

**User Onboarding (for family members):**
1. Send them Cloudflare Tunnel URL (e.g., `curator.yourdomain.com`)
2. They log in with their Immich credentials
3. They visit `/preferences` to:
   - Opt in to monthly reminders
   - Set their monthly target photos
4. On 1st of each month, they'll get reminder email

---

## 📞 Support & Documentation

**Questions?** Check:
1. This SETUP.md file
2. `claude.md` for future features
3. Individual README files in each component directory
4. Immich documentation: https://immich.app/docs

**Common Issues**:
- Email not working → Check SETUP.md "Email Setup" section
- Photos not loading → Verify Immich API key
- Can't access remotely → Configure Cloudflare Tunnel
- Monthly reminders not sending → Check all email prerequisites

---

## 🔄 Update & Maintenance

**Updating Configuration**:
```bash
# After editing config.yaml
sudo systemctl restart photo-curator
sudo systemctl restart server-manager
```

**Checking Service Status**:
```bash
sudo systemctl status photo-curator
sudo systemctl status server-manager
```

**Viewing Live Logs**:
```bash
sudo journalctl -u photo-curator -f
```

**Database Location**:
- SQLite database: `photo-curator/data/curator.db`
- Backup if needed before updates

---

## 📝 Quick Reference: What You Need

**To Get Started (Minimum)**:
- ✅ Immich running
- ✅ Copy config.yaml.example files

**For Monthly Reminders**:
- ✅ Immich API key
- ✅ SMTP credentials (Gmail App Password recommended)
- ✅ Update curator URL in code

**For Remote Access**:
- ✅ Cloudflare account (free)
- ✅ Domain name
- ✅ Run Cloudflare Tunnel setup

**For Backups**:
- ✅ Backup directory with write permissions
- ✅ Immich API key
- ✅ Enough disk space

---

*Last Updated: 2026-03-10*
*Questions? Check claude.md for additional feature documentation.*
