# Immich Complete Ecosystem

**Production-ready monitoring, backups, curation, and remote access for Immich**

This project provides a complete, production-ready ecosystem around [Immich](https://immich.app), the self-hosted photo and video management solution. It adds essential features for running Immich in a family environment with 6+ users.

## 🎯 What This Provides

### 📊 Immich Server Manager
- **Disk Health Monitoring** - SMART data collection every 5 minutes
- **Automated Backups** - Daily PostgreSQL dumps with 30-day retention
- **Update Management** - Automated minor updates with rollback capability
- **System Monitoring** - CPU, RAM, disk I/O metrics with historical data
- **Alert System** - Email, webhook, and Discord notifications for critical issues
- **Web Dashboard** - Real-time metrics and manual controls

### 📸 Photo Curator Assistant
- **AI Quality Scoring** - Automatic photo quality assessment (local, no API costs)
- **Monthly Curation** - Per-user reminders and curated albums
- **Duplicate Detection** - Find and manage similar photos
- **Year-End Collaboration** - Family photo book creation tools

### 🌐 Remote Access
- **Cloudflare Tunnel** - Secure access from anywhere, no port forwarding
- **Automatic HTTPS** - Built-in SSL certificates
- **DDoS Protection** - Cloudflare's edge network protection

### 🔒 Security Hardening
- **fail2ban** - Automatic brute force protection
- **UFW Firewall** - Network access control
- **2FA Support** - Two-factor authentication guidance
- **Security Monitoring** - Continuous security status tracking

## 💰 Cost

**Total: $10-15/year**
- Domain name: $10-15/year
- Everything else: FREE (self-hosted)

## ⚡ Quick Start

### Prerequisites

- Ubuntu/Debian Linux
- Immich already installed and running
- Python 3.9+
- Docker and Docker Compose
- sudo access

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/immich-manager.git
cd immich-manager

# Run the installer
./install.sh
```

The installer will:
1. Check prerequisites
2. Install Server Manager (~10 minutes)
3. Install Photo Curator (~15 minutes)
4. Setup Remote Access (~15 minutes, requires domain)
5. Apply Security Hardening (~5 minutes)
6. Run comprehensive tests

## 📋 Detailed Installation

### Phase 0: Prerequisites Check

```bash
./scripts/00-check-prerequisites.sh
```

Validates:
- Operating system (Ubuntu/Debian)
- Python 3.9+
- Docker and Docker Compose
- Immich installation
- Disk space (10GB+ free)
- Required ports (8080, 8081)

### Phase 1: Server Manager

```bash
./scripts/10-install-server-manager.sh
```

Installs:
- Python virtual environment
- FastAPI application
- SQLite database
- systemd service
- Web dashboard

**Access:** http://localhost:8080

**Configuration:** `/opt/immich-server-manager/config/config.yaml`

### Phase 2: Photo Curator

```bash
./scripts/20-install-photo-curator.sh
```

Installs:
- Photo curation engine
- OpenCV and AI models
- Web interface
- systemd service

**Access:** http://localhost:8081

**Configuration:** `/opt/photo-curator/config/config.yaml`

### Phase 3: Remote Access

```bash
./scripts/30-install-remote-access.sh
```

**Requirements:**
1. Domain name ($10-15/year from Porkbun, Namecheap, etc.)
2. Free Cloudflare account
3. Domain added to Cloudflare
4. Nameservers updated

Sets up:
- Cloudflare Tunnel (cloudflared)
- DNS records
- Multi-service routing
- Automatic reconnection

**Access:**
- `https://yourdomain.com` → Immich
- `https://yourdomain.com/monitor/` → Server Manager
- `https://yourdomain.com/curator/` → Photo Curator

### Phase 4: Security Hardening

```bash
./scripts/40-security-hardening.sh
```

Configures:
- fail2ban with Immich monitoring
- UFW firewall rules
- Security monitoring scripts
- Security checklist

### Phase 5: Testing

```bash
./scripts/50-test-installation.sh
```

Tests all components and generates comprehensive report.

## 🔧 Configuration

### Server Manager

Edit `/opt/immich-server-manager/config/config.yaml`:

```yaml
immich:
  api_key: "your-api-key"  # Generate in Immich: Admin → API Keys

storage:
  data_drives:
    - "/dev/sda"
    - "/dev/sdb"

backup:
  enabled: true
  local_path: "/mnt/backups/immich"
  retention_days: 30

alerts:
  email:
    enabled: true
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    smtp_user: "your-email@gmail.com"
    smtp_password: "your-app-password"
    to:
      - "admin@yourdomain.com"
  discord:
    enabled: true
    webhook_url: "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"
    bot_name: "House of Feuer"
    server_name: "My Immich Server"  # optional label shown in embeds
  quiet_hours:
    enabled: true
    start: "22:00"
    end: "08:00"
```

**Test alerts (sends to all enabled channels):**
```bash
curl -X POST http://localhost:8080/api/test-alert
```

### Discord Alerts

Discord webhook alerts are sent as rich embeds with colour-coded severity levels:

| Colour | Severity | Description |
|--------|----------|-------------|
| 🔴 Red | Critical | Requires immediate attention |
| 🟠 Orange | Warning | Degraded but not yet failing |
| 🔵 Blue | Info | Informational notifications |

**Quiet hours** apply to warning and info alerts (22:00–08:00 by default). Critical alerts are always sent.

#### Alert types sent to Discord

| Alert | Severity | Trigger |
|-------|----------|---------|
| **Disk Temperature — Critical** | Critical | Drive temp exceeds `disk_temp_critical` threshold (default 50 °C) |
| **Disk Temperature — High** | Warning | Drive temp exceeds `disk_temp_warning` threshold (default 45 °C) |
| **Disk Health — SMART Errors** | Critical / Warning | Reallocated, pending, or uncorrectable sectors detected |
| **High Disk Usage** | Warning | Filesystem usage exceeds `disk_space_warning` (default 85 %) |
| **Critical Disk Space** | Critical | Filesystem usage exceeds `disk_space_critical` (default 95 %) |
| **Backup Completed** | Info | Scheduled or manual backup finished successfully |
| **Backup Failed** | Critical | Backup job errored out |
| **Backup Restored** | Info | Database successfully restored from a backup file |
| **Restore Failed** | Critical | Database restore operation failed |
| **Immich Containers Down** | Critical | One or more Immich Docker containers stopped unexpectedly |
| **Immich Containers Recovered** | Info | All containers are running again after a downtime event |
| **Immich Update Available** | Info | A new Immich release is available on GitHub |
| **Immich Auto-Updated** | Info | Patch update applied automatically (snapshot kept for rollback) |
| **Immich Update Failed** | Critical | Auto-update failed and was rolled back |
| **Immich Updated** | Info | Manual update applied successfully |
| **Rollback Completed** | Info | Immich rolled back to a previous snapshot |
| **Rollback Failed** | Critical | Snapshot rollback failed |
| **Test Alert** | Info | Sent via `POST /api/test-alert` to verify the integration |

### Photo Curator

Edit `/opt/photo-curator/config/config.yaml`:

```yaml
immich:
  api_key: "your-api-key"  # Same as Server Manager

curation:
  monthly_target: 50  # Photos to curate per month
  reminder_day: 1     # Day of month for reminders
```

## 📊 Monitoring & Maintenance

### Quick Health Check

```bash
./scripts/health-check.sh
```

Shows status of all services and recent backup.

### View Dashboards

- **Server Manager:** http://localhost:8080
  - System metrics
  - Disk health
  - Backup status
  - Alert history

- **Photo Curator:** http://localhost:8081
  - Photo quality scores
  - Curation progress
  - User activity

### Service Management

```bash
# View logs
sudo journalctl -u immich-server-manager -f
sudo journalctl -u photo-curator -f
sudo journalctl -u cloudflared -f

# Restart services
sudo systemctl restart immich-server-manager
sudo systemctl restart photo-curator
sudo systemctl restart cloudflared

# Check status
sudo systemctl status immich-server-manager
```

### Manual Backup

```bash
curl -X POST http://localhost:8080/api/backup/now
```

### Security Monitoring

```bash
/opt/immich-ecosystem/scripts/security-monitor.sh
```

Shows:
- fail2ban bans
- Recent login attempts
- Firewall status
- Service health

## 🔒 Security Best Practices

### Essential Steps

1. **Enable 2FA for all users** (CRITICAL!)
   - Login to Immich → Admin → Users
   - Enable 2FA for each user
   - Users must set up authenticator app on next login

2. **Use strong passwords**
   - Minimum 16 characters
   - Use a password manager

3. **Regular updates**
   ```bash
   sudo apt update && sudo apt upgrade
   ```

4. **Monitor alerts**
   - Check email alerts regularly
   - Review security logs weekly

5. **Test backups**
   - Verify backups are running
   - Test restore procedure quarterly

### Security Checklist

See `/opt/immich-ecosystem/security-checklist.txt` for complete checklist.

## 🔄 Backup & Restore

### Backup

Backups run automatically at 2 AM daily (configurable).

**Backup location:** `/mnt/backups/immich/`

**Manual backup:**
```bash
curl -X POST http://localhost:8080/api/backup/now
```

### Restore

```bash
# List available backups
ls -lh /mnt/backups/immich/

# Restore database (example)
BACKUP_FILE="/mnt/backups/immich/immich_db_20240101_020000.sql.gz"
gunzip -c $BACKUP_FILE | docker exec -i immich_postgres psql -U postgres immich
```

## 🚨 Troubleshooting

### Server Manager won't start

```bash
# Check logs
sudo journalctl -u immich-server-manager -n 50

# Verify configuration
cat /opt/immich-server-manager/config/config.yaml

# Test manually
cd /opt/immich-server-manager
source venv/bin/activate
python -m src.main
```

### Photo Curator errors

```bash
# Check OpenCV installation
cd /opt/photo-curator
source venv/bin/activate
python -c "import cv2; print(cv2.__version__)"

# Reinstall if needed
pip install --force-reinstall opencv-python
```

### Remote access not working

```bash
# Check tunnel status
sudo systemctl status cloudflared

# Check tunnel logs
sudo journalctl -u cloudflared -n 100

# Test DNS
dig yourdomain.com

# Verify local services are running
curl http://localhost:2283/api/server-info
```

### Port already in use

```bash
# Find what's using the port
sudo lsof -i :8080

# Change port in config
nano /opt/immich-server-manager/config/config.yaml
# Then restart: sudo systemctl restart immich-server-manager
```

### Disk health monitoring not working

```bash
# Install smartmontools
sudo apt install smartmontools

# Test manually
sudo smartctl -a /dev/sda

# Check if drives are detected
lsblk
```

## 📁 Project Structure

```
immich-manager/
├── install.sh                  # Master installation script
├── README.md                   # This file
│
├── scripts/
│   ├── lib/
│   │   └── state-manager.sh   # Installation state tracking
│   ├── systemd/                # Service files
│   ├── 00-check-prerequisites.sh
│   ├── 10-install-server-manager.sh
│   ├── 20-install-photo-curator.sh
│   ├── 30-install-remote-access.sh
│   ├── 40-security-hardening.sh
│   ├── 50-test-installation.sh
│   └── health-check.sh
│
├── server-manager/
│   ├── src/                    # Python application
│   ├── config/                 # Configuration templates
│   ├── static/                 # Web dashboard
│   └── requirements.txt
│
└── photo-curator/
    ├── src/                    # Python application
    ├── config/                 # Configuration templates
    ├── static/                 # Web interface
    └── requirements.txt
```

## 🔗 API Documentation

### Server Manager API

**Base URL:** http://localhost:8080

- `GET /health` - Health check
- `GET /api/status` - System status
- `GET /api/disks` - Disk health
- `GET /api/metrics?hours=24` - System metrics
- `GET /api/backups` - Backup history
- `POST /api/backup/now` - Trigger backup
- `GET /api/alerts` - Get alerts
- `POST /api/test-alert` - Send test alert
- `GET /api/snapshots` - List pre-update snapshots
- `POST /api/snapshots` - Create manual snapshot
- `POST /api/snapshots/{id}/rollback` - Roll back to a snapshot
- `GET /api/updates/history` - Update history
- `POST /api/updates/apply` - Trigger update to latest version

### Photo Curator API

**Base URL:** http://localhost:8081

- `GET /health` - Health check
- `GET /api/status` - Curator status
- `GET /api/users` - List users
- `GET /api/photos/{user_id}/monthly` - Monthly photos
- `POST /api/curate/{user_id}` - Curate photos

**Full API docs:** http://localhost:8080/docs and http://localhost:8081/docs

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- [Immich](https://immich.app) - The amazing self-hosted photo management solution
- [Cloudflare](https://cloudflare.com) - Free tunneling and DDoS protection
- [FastAPI](https://fastapi.tiangolo.com) - Modern Python web framework

## 📞 Support

- **Issues:** Open an issue on GitHub
- **Immich Discord:** https://discord.immich.app
- **Immich Docs:** https://immich.app/docs

## 🗺️ Roadmap

> **Effort scale:** XS (<1 day) | S (1–3 days) | M (3–7 days) | L (1–3 weeks) | XL (1+ months)

### ✅ Completed
- [x] Multi-site backup support (S3, Backblaze)
- [x] Prometheus metrics endpoint
- [x] Immich auto-updater — watches for new releases, applies patch updates, snapshot + rollback *(Effort: M)*
- [x] Discord webhook alerts — rich embeds with severity colours, quiet hours, all system events *(Effort: S)*

### 🔄 In Progress
- [~] Prometheus/Grafana integration — Prometheus done; Grafana dashboard config needed *(Effort: XS)*
- [~] Advanced AI features — Basic face detection done; face recognition + scene detection needed *(Effort: M–L)*

### 📋 Planned

#### Storage & Performance
- [ ] Per-user storage quotas — limits, warnings, and upload blocking per user *(Effort: M)*
- [ ] Video transcoding/compression — automated format conversion and size reduction *(Effort: M)*
- [ ] Smart cleanup assistant — surface old/low-quality photos for bulk deletion with space savings preview *(Effort: M)*

#### User & Access Management
- [ ] User onboarding flow — invite family members via email, auto-create Immich accounts *(Effort: M)*
- [ ] Guest access links — temporary expiring share links for non-Immich users *(Effort: S)*
- [ ] Role management — admin, family member, and guest permission tiers *(Effort: L)*

#### Automation & Intelligence
- [ ] Smart album rules engine — auto-populate albums by date, location, quality score, or face tags *(Effort: L)*
- [ ] Trip/event detection — cluster photos into trips using GPS + time gap analysis *(Effort: M)*
- [ ] "On this day" digest emails — photos from this date in past years *(Effort: S)*

#### Import & Export
- [ ] Additional import sources — Apple Photos, Facebook, Instagram, OneDrive *(Effort: L)*
- [ ] Photo book PDF export — generate printable PDF locally for upload to any print service *(Effort: L)*

#### Ops & Reliability
- [ ] Self-update for immich-manager — git pull + restart workflow to keep manager current *(Effort: S)*

#### Notifications & Reporting
- [ ] Email digest reports — weekly/monthly system health and curation stats summaries *(Effort: S)*

#### Mobile
- [ ] Mobile app for Photo Curator *(Effort: XL)*

## 📊 Stats

- **Installation time:** 30-60 minutes
- **Disk space required:** ~500MB (without photos)
- **Memory usage:** ~200MB (combined services)
- **CPU usage:** <5% idle, ~20% during backups
- **Supported users:** 6-20+ (tested with families)

---

**Made with ❤️ for the Immich community**

Star ⭐ this repo if you find it useful!
