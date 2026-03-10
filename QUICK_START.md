# Quick Start Guide

**Get up and running with Immich Manager in 5 minutes**

## What is Immich Manager?

Immich Manager is a production-ready ecosystem that adds essential features to your self-hosted Immich installation:

- 📊 **Server Manager**: Disk monitoring, automated backups, system alerts
- 📸 **Photo Curator**: AI-powered photo analysis and curation
- 🏥 **Health Monitor**: Self-healing service monitoring

## Prerequisites Checklist

Before starting, ensure you have:

- [ ] Ubuntu/Debian Linux
- [ ] sudo access
- [ ] 10GB+ free disk space

> **Note:** The installer automatically handles all software prerequisites (Python, Docker, Docker Compose, system libraries, etc.). You do not need to install them manually.

## Step 0: Set Up Storage Drives (Recommended)

If you are using multiple data drives, set up mergerfs + SnapRAID **before** running the Immich Manager installer. This creates a unified storage pool at `/mnt/storage` (or `/mnt/user`) for Immich's photo library.

```bash
git clone https://github.com/nfeuer/mergerfs-snapraid.git
cd mergerfs-snapraid
sudo ./setup-mergerfs-snapraid.sh
```

**What this does:**
- Merges multiple drives into a single pool (e.g. `/mnt/storage`)
- Adds parity protection against a single drive failure
- Sets up automated daily sync and weekly scrub (systemd timers)
- Drives do not need to be the same size

**Requirements for this step:**
- 2+ data drives
- 1 parity drive (must be >= the largest data drive)

See [mergerfs-snapraid](https://github.com/nfeuer/mergerfs-snapraid) for full details.

Once your storage pool is ready, proceed with the Immich Manager installation below.

---

## Installation (5 Minutes)

### 1. Install Immich

Immich must be running before the manager is installed.

**Verify Immich is running:**
```bash
curl http://localhost:2283/api/server-info
```

If not yet installed, follow the [Immich Docker Compose guide](https://immich.app/docs/install/docker-compose). Point the upload path at your storage pool (e.g. `/mnt/storage/immich`).

### 2. Clone Repository

```bash
git clone https://github.com/yourusername/immich-manager.git
cd immich-manager
```

### 3. Run Installer

```bash
./install.sh
```

The installer will:
1. Check prerequisites (and install any missing software automatically) ✓
2. Install Server Manager (includes smartmontools) ✓
3. Install Photo Curator (includes ML/AI libraries) ✓
4. Optionally set up remote access
5. Apply security hardening

**Installation takes about 30-60 minutes total** (ML/AI library downloads are the main time cost).

### 4. Configure Services

#### Server Manager Configuration

Edit `/opt/immich-server-manager/config/config.yaml`:

```yaml
immich:
  api_key: "your-api-key-here"  # Get from Immich: Admin → API Keys

storage:
  data_drives:
    - "/dev/sda"  # Your data drive(s)

alerts:
  email:
    enabled: true
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    smtp_user: "your-email@gmail.com"
    smtp_password: "your-app-password"
    to:
      - "admin@example.com"
```

**Get Immich API Key:**
1. Login to Immich web interface
2. Go to Admin Settings → API Keys
3. Click "New API Key"
4. Copy the key and paste into config.yaml

**Gmail App Password:**
1. Enable 2FA on Gmail
2. Go to Google Account → Security → 2-Step Verification
3. Click "App passwords"
4. Generate password for "Mail"
5. Use this password in config.yaml

#### Photo Curator Configuration

Edit `/opt/photo-curator/config/config.yaml`:

```yaml
immich:
  api_key: "same-as-server-manager"

curation:
  monthly_target: 50  # Photos to curate per month
  reminder_day: 1     # Day of month for reminders
```

### 5. Restart Services

```bash
sudo systemctl restart immich-server-manager
sudo systemctl restart photo-curator
```

### 6. Verify Installation

```bash
# Check services are running
sudo systemctl status immich-server-manager
sudo systemctl status photo-curator

# Check health endpoints
curl http://localhost:8080/health
curl http://localhost:8081/health
```

## Quick Feature Tour

### Server Manager (http://localhost:8080)

**View Dashboard:**
1. Open browser to http://localhost:8080
2. View real-time metrics, disk health, backup status

**Trigger Manual Backup:**
```bash
curl -X POST http://localhost:8080/api/backup/now
```

**View Recent Backups:**
```bash
curl http://localhost:8080/api/backups | jq '.backups[0:5]'
```

**Check Disk Health:**
```bash
curl http://localhost:8080/api/disks | jq '.disks[] | {device, temperature, health_ok}'
```

**Test Email Alerts:**
```bash
curl -X POST http://localhost:8080/api/test-alert
```

### Photo Curator (http://localhost:8081)

**Access Curator:**
1. Login to Immich first (http://localhost:2283)
2. Navigate to http://localhost:8081
3. You'll be automatically authenticated

**Analyze Photos:**
1. Click "Curate" for a month
2. Click "Analyze Photos"
3. Wait for AI analysis to complete (~2 seconds per photo)
4. Review top-scored photos

**Create Curated Album:**
1. Review AI suggestions (highlighted photos)
2. Add/remove photos as desired
3. Click "Create Album"
4. Album appears in Immich

**Find Duplicates:**
1. Click "Duplicates" tab
2. Click "Scan for Duplicates"
3. Review side-by-side comparisons
4. Select photos to delete
5. Click "Delete Selected"

### Health Monitor

The health monitor runs automatically every 15 minutes.

**Check Status:**
```bash
sudo systemctl status health-monitor.timer
```

**View Recent Runs:**
```bash
sudo journalctl -u health-monitor.service -n 50
```

**Run Manual Check:**
```bash
sudo systemctl start health-monitor.service
```

## Common Tasks

### View Service Logs

```bash
# Follow logs in real-time
sudo journalctl -u immich-server-manager -f
sudo journalctl -u photo-curator -f

# View last 100 lines
sudo journalctl -u immich-server-manager -n 100
```

### Restart Services

```bash
sudo systemctl restart immich-server-manager
sudo systemctl restart photo-curator
```

### Update Configuration

After editing config files, always restart the service:

```bash
# Edit config
sudo nano /opt/immich-server-manager/config/config.yaml

# Restart
sudo systemctl restart immich-server-manager
```

### Check Backup Status

```bash
# List backups
ls -lh /mnt/backups/immich/

# Check backup records
curl http://localhost:8080/api/backups | jq '.backups[0:5]'
```

### Test Restore Backup

```bash
# Get latest backup
BACKUP_FILE=$(ls -t /mnt/backups/immich/*.sql.gz | head -1)

# Test restore (creates temp database)
cd /opt/immich-server-manager
./verify-backup.py "$BACKUP_FILE"
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs for errors
sudo journalctl -u immich-server-manager -n 50

# Test manually
cd /opt/immich-server-manager
source venv/bin/activate
python -m src.main
```

### Email Alerts Not Working

```bash
# Test SMTP configuration
curl -X POST http://localhost:8080/api/test-alert

# Check logs
sudo journalctl -u immich-server-manager | grep -i smtp

# Verify Gmail App Password (not regular password)
```

### Photo Curator Authentication Issues

```bash
# Verify Immich is accessible
curl http://localhost:2283/api/server-info

# Check Photo Curator can reach Immich
cd /opt/photo-curator
source venv/bin/activate
python -c "import requests; print(requests.get('http://localhost:2283/api/server-info').json())"
```

### Disk Monitoring Not Working

```bash
# smartmontools is installed automatically by the installer, but if missing:
sudo apt install smartmontools

# Test manually
sudo smartctl -a /dev/sda

# Give service sudo access for smartctl
sudo visudo
# Add: username ALL=(ALL) NOPASSWD: /usr/sbin/smartctl
```

## Next Steps

### Set Up Remote Access (Optional)

If you want to access Immich from outside your home network:

```bash
./scripts/30-install-remote-access.sh
```

**Requirements:**
- Domain name ($10-15/year)
- Free Cloudflare account

**See**: [SETUP.md](SETUP.md#remote-access) for detailed instructions

### Security Hardening

Apply security best practices:

```bash
./scripts/40-security-hardening.sh
```

This configures:
- fail2ban (brute force protection)
- UFW firewall
- Security monitoring

### Enable 2FA for Immich Users

**Critical for security:**

1. Login to Immich as admin
2. Go to Admin → Users
3. For each user, enable "Require 2FA"
4. Users must set up authenticator app on next login

## Documentation

### Quick Reference

- **README.md** - Project overview and installation
- **SETUP.md** - Detailed configuration guide
- **ARCHITECTURE.md** - System architecture and design
- **API.md** - Complete API reference

### Component Documentation

- **server-manager/README.md** - Server Manager details
- **photo-curator/README.md** - Photo Curator details
- **health-monitor/README.md** - Health Monitor details

### Getting Help

- **Issues**: https://github.com/yourusername/immich-manager/issues
- **Immich Discord**: https://discord.immich.app
- **Immich Docs**: https://immich.app/docs

## Tips for Success

### 1. Start with Monitoring

Get Server Manager running first and verify:
- Disk monitoring is working
- Backups are running
- Email alerts are configured

### 2. Test Backups

Trigger a manual backup and verify it completes:
```bash
curl -X POST http://localhost:8080/api/backup/now
```

Check backup was created:
```bash
ls -lh /mnt/backups/immich/
```

### 3. Try Photo Curator

Start with a small month (few photos) to test the workflow:
1. Analyze photos
2. Review suggestions
3. Create album

### 4. Monitor Health

Check health monitor logs weekly:
```bash
sudo journalctl -u health-monitor.service --since "1 week ago"
```

### 5. Regular Maintenance

**Weekly:**
- Check dashboard for any alerts
- Verify backups are running
- Review health monitor summary email

**Monthly:**
- Review storage usage
- Test backup restore
- Update system packages

**Quarterly:**
- Review security checklist
- Update Immich and Manager components
- Clean up old logs and metrics

## System Requirements

**Minimum:**
- 2 CPU cores
- 4 GB RAM
- 50 GB disk space

**Recommended:**
- 4 CPU cores
- 8 GB RAM
- 100 GB disk space (for photos + backups)

**For large libraries (50,000+ photos):**
- 8 CPU cores
- 16 GB RAM
- SSD for database

## Performance Expectations

**Backup Times:**
- Small database (<1GB): 30-60 seconds
- Medium database (1-5GB): 2-5 minutes
- Large database (10GB+): 10-20 minutes

**Photo Analysis:**
- Per photo: 1-2 seconds
- 100 photos: 2-3 minutes
- 1000 photos: 20-30 minutes

**Resource Usage:**
- Server Manager: ~50-100 MB RAM, <1% CPU idle
- Photo Curator: ~100-200 MB RAM, <1% CPU idle
- Health Monitor: ~20-30 MB RAM during runs

## Support

If you run into issues:

1. **Check logs first:**
   ```bash
   sudo journalctl -u immich-server-manager -n 100
   ```

2. **Search existing issues:**
   https://github.com/yourusername/immich-manager/issues

3. **Ask on Immich Discord:**
   https://discord.immich.app

4. **Create new issue:**
   Include logs, configuration (redact secrets), and error messages

## What's Next?

Now that you have Immich Manager running:

- ✅ Automated daily backups
- ✅ Disk health monitoring
- ✅ AI-powered photo curation
- ✅ Self-healing monitoring

**Enjoy your production-ready Immich installation!**

---

**Made with ❤️ for the Immich community**

Star ⭐ this repo if you find it useful!
