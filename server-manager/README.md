# Immich Server Manager

**Comprehensive monitoring, backup, and alerting system for Immich installations**

## Overview

The Server Manager is a FastAPI-based service that provides production-grade monitoring and backup capabilities for self-hosted Immich instances. It runs as a systemd service and provides a web dashboard for monitoring and management.

## Features

### 📊 System Monitoring
- **Disk Health Monitoring**: SMART data collection every 5 minutes
  - Temperature tracking
  - Reallocated sector detection
  - Power-on hours and cycle counts
  - Automatic health alerts

- **System Metrics**: CPU, RAM, and disk I/O tracking
  - 1-minute collection intervals
  - Historical data storage (SQLite)
  - Trend analysis and charts

- **Docker Monitoring**: Immich container status
  - Container health checks
  - Resource usage tracking
  - Automatic restart detection

### 💾 Automated Backups
- **PostgreSQL Database Backups**
  - Scheduled daily backups (configurable via cron)
  - Compressed with gzip
  - SHA256 checksum verification
  - Retention policy (daily/weekly/monthly)

- **Backup Verification**
  - Test restore to temporary database
  - Integrity validation
  - Automated verification reports

- **Offsite Sync** (Optional)
  - AWS S3 integration
  - Backblaze B2 support
  - Automatic sync after successful backup

### 🚨 Alert System
- **Multi-channel Notifications**
  - Email via SMTP
  - Webhook support (Slack, Discord, etc.)
  - Configurable quiet hours

- **Alert Types**
  - Disk health warnings
  - Backup failures
  - High resource usage
  - Container failures

### 🌐 Web Dashboard
- Real-time metrics visualization
- Backup history and status
- Alert management
- Manual backup triggers

## Installation

### Prerequisites
- Python 3.9+
- Docker and Docker Compose
- Immich instance running
- `smartmontools` for disk monitoring

### Quick Install

The installer script handles everything:

```bash
cd /home/user/immich-manager
./scripts/10-install-server-manager.sh
```

This will:
1. Create Python virtual environment at `/opt/immich-server-manager`
2. Install dependencies from `requirements.txt`
3. Copy configuration template
4. Set up SQLite database
5. Install systemd service
6. Start the service

### Manual Installation

```bash
# Create installation directory
sudo mkdir -p /opt/immich-server-manager
sudo cp -r server-manager/* /opt/immich-server-manager/

# Create virtual environment
cd /opt/immich-server-manager
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp config/config.yaml.example config/config.yaml
nano config/config.yaml

# Install systemd service
sudo cp /path/to/immich-manager/scripts/systemd/immich-server-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable immich-server-manager
sudo systemctl start immich-server-manager
```

## Configuration

Configuration file location: `/opt/immich-server-manager/config/config.yaml`

### Minimal Configuration

```yaml
immich:
  api_url: "http://localhost:2283/api"
  api_key: "your-api-key-here"  # Generate in Immich Admin → API Keys

storage:
  data_drives:
    - "/dev/sda"
    - "/dev/sdb"

backup:
  enabled: true
  local_path: "/mnt/backups/immich"
  schedule: "0 2 * * *"  # 2 AM daily

alerts:
  email:
    enabled: true
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    smtp_user: "your-email@gmail.com"
    smtp_password: "your-app-password"
    from: "immich-alerts@yourdomain.com"
    to:
      - "admin@yourdomain.com"
```

### Full Configuration Options

```yaml
server:
  host: "0.0.0.0"
  port: 8080
  debug: false

immich:
  api_url: "http://localhost:2283/api"
  api_key: ""
  docker_container: "immich_postgres"

monitoring:
  disk_check_interval: 300  # 5 minutes in seconds
  metrics_interval: 60      # 1 minute in seconds

storage:
  data_drives:              # Primary data drives
    - "/dev/sda"
  parity_drives: []         # Parity drives (if using unRAID, etc.)

backup:
  enabled: true
  schedule: "0 2 * * *"     # Cron format: minute hour day month weekday
  local_path: "/mnt/backups/immich"
  retention:
    daily: 7                # Keep 7 daily backups
    weekly: 4               # Keep 4 weekly backups
    monthly: 6              # Keep 6 monthly backups

  # Optional: Offsite backup
  offsite:
    enabled: false
    provider: "s3"          # "s3" or "b2"
    bucket: "my-backups"

    # For AWS S3
    aws_access_key: ""
    aws_secret_key: ""
    aws_region: "us-east-1"

    # For Backblaze B2
    b2_key_id: ""
    b2_application_key: ""

  # Verification settings
  verification:
    enabled: true
    test_restore: true      # Actually restore to temp DB to verify

alerts:
  email:
    enabled: true
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    smtp_user: "your-email@gmail.com"
    smtp_password: "app-password-here"
    from: "immich-alerts@yourdomain.com"
    to:
      - "admin@yourdomain.com"

    # Quiet hours (no alerts sent during this time)
    quiet_hours:
      enabled: false
      start: "22:00"
      end: "08:00"

  webhook:
    enabled: false
    url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

  # Threshold configurations
  thresholds:
    cpu_warning: 80         # CPU % threshold for warning
    cpu_critical: 95        # CPU % threshold for critical alert
    memory_warning: 80      # Memory % threshold
    memory_critical: 90
    disk_warning: 80        # Disk space % threshold
    disk_critical: 90
    temperature_warning: 50 # Disk temperature in Celsius
    temperature_critical: 60

database:
  path: "server-manager.db"

logging:
  level: "INFO"             # DEBUG, INFO, WARNING, ERROR
  file: "logs/server-manager.log"
```

## API Endpoints

Base URL: `http://localhost:8080`

### Health & Status

#### `GET /health`
Health check endpoint (returns 200 OK).

#### `GET /api/status`
Get overall system status.

**Response:**
```json
{
  "status": "healthy",
  "uptime": 86400,
  "services": {
    "database": "connected",
    "immich": "running",
    "monitoring": "active"
  },
  "last_backup": "2024-01-15T02:00:00Z"
}
```

### Disk Monitoring

#### `GET /api/disks`
Get SMART health data for all configured disks.

**Response:**
```json
{
  "disks": [
    {
      "device": "/dev/sda",
      "model": "Samsung SSD 870",
      "serial": "S5H2NS0R123456",
      "smart_status": true,
      "temperature": 35,
      "power_on_hours": 12543,
      "health_ok": true,
      "warnings": []
    }
  ]
}
```

### System Metrics

#### `GET /api/metrics?hours=24`
Get historical system metrics.

**Query Parameters:**
- `hours` (optional): Number of hours of data to return (default: 24)

**Response:**
```json
{
  "metrics": [
    {
      "timestamp": "2024-01-15T10:00:00Z",
      "cpu_percent": 12.5,
      "memory_percent": 45.2,
      "disk_read_mb": 234.5,
      "disk_write_mb": 456.7
    }
  ]
}
```

### Backup Management

#### `GET /api/backups`
List all backups.

**Response:**
```json
{
  "backups": [
    {
      "filename": "immich_db_20240115_020000.sql.gz",
      "timestamp": "2024-01-15T02:00:00Z",
      "size_bytes": 1234567890,
      "checksum": "sha256:abc123...",
      "verified": true,
      "offsite_synced": true
    }
  ]
}
```

#### `POST /api/backup/now`
Trigger an immediate backup.

**Response:**
```json
{
  "status": "started",
  "message": "Backup initiated"
}
```

### Alert Management

#### `GET /api/alerts`
Get alert history.

**Response:**
```json
{
  "alerts": [
    {
      "id": 1,
      "timestamp": "2024-01-15T10:30:00Z",
      "severity": "warning",
      "type": "disk_temperature",
      "message": "Disk /dev/sda temperature 55°C exceeds warning threshold",
      "acknowledged": false
    }
  ]
}
```

#### `POST /api/alerts/{alert_id}/acknowledge`
Mark an alert as acknowledged.

#### `POST /api/test-alert`
Send a test alert (useful for testing email/webhook configuration).

**Response:**
```json
{
  "status": "sent",
  "message": "Test alert sent successfully"
}
```

## Architecture

### Components

```
┌─────────────────────────────────────────────────┐
│           FastAPI Application                   │
│  (main.py - HTTP server & API endpoints)        │
└───────┬─────────────────────────────────────────┘
        │
        ├─── DiskMonitor (monitoring.py)
        │    └─── Executes smartctl via subprocess
        │
        ├─── SystemMonitor (monitoring.py)
        │    └─── Uses psutil for metrics
        │
        ├─── DockerMonitor (monitoring.py)
        │    └─── Docker API client
        │
        ├─── BackupManager (backup.py)
        │    ├─── Executes pg_dump via Docker
        │    ├─── Compression (gzip)
        │    └─── Retention policy enforcement
        │
        ├─── BackupVerifier (backup_verifier.py)
        │    └─── Test restore & validation
        │
        ├─── AlertManager (alerts.py)
        │    ├─── SMTP client (aiosmtplib)
        │    └─── Webhook client (requests)
        │
        ├─── Database (database.py)
        │    └─── SQLite with aiosqlite
        │
        └─── APScheduler
             ├─── Disk health checks (every 5 min)
             ├─── Metrics collection (every 1 min)
             └─── Backups (cron schedule)
```

### Database Schema

**SQLite Database:** `server-manager.db`

**Tables:**

1. **disk_health**
   - id (INTEGER PRIMARY KEY)
   - timestamp (TEXT)
   - device (TEXT)
   - smart_status (INTEGER)
   - temperature (INTEGER)
   - power_on_hours (INTEGER)
   - reallocated_sectors (INTEGER)
   - pending_sectors (INTEGER)
   - uncorrectable_sectors (INTEGER)
   - health_ok (INTEGER)
   - warnings (TEXT - JSON)

2. **system_metrics**
   - id (INTEGER PRIMARY KEY)
   - timestamp (TEXT)
   - cpu_percent (REAL)
   - memory_percent (REAL)
   - memory_used_gb (REAL)
   - memory_total_gb (REAL)
   - disk_read_mb (REAL)
   - disk_write_mb (REAL)

3. **backup_records**
   - id (INTEGER PRIMARY KEY)
   - timestamp (TEXT)
   - filename (TEXT)
   - size_bytes (INTEGER)
   - checksum (TEXT)
   - success (INTEGER)
   - duration_seconds (REAL)
   - error_message (TEXT)
   - verified (INTEGER)
   - offsite_synced (INTEGER)

4. **alerts**
   - id (INTEGER PRIMARY KEY)
   - timestamp (TEXT)
   - severity (TEXT)
   - type (TEXT)
   - message (TEXT)
   - details (TEXT - JSON)
   - acknowledged (INTEGER)
   - acknowledged_at (TEXT)

## Usage

### Service Management

```bash
# Start service
sudo systemctl start immich-server-manager

# Stop service
sudo systemctl stop immich-server-manager

# Restart service
sudo systemctl restart immich-server-manager

# View status
sudo systemctl status immich-server-manager

# Enable on boot
sudo systemctl enable immich-server-manager

# Disable on boot
sudo systemctl disable immich-server-manager
```

### Viewing Logs

```bash
# Follow logs in real-time
sudo journalctl -u immich-server-manager -f

# View last 100 lines
sudo journalctl -u immich-server-manager -n 100

# View logs from today
sudo journalctl -u immich-server-manager --since today

# View logs with priority (errors only)
sudo journalctl -u immich-server-manager -p err
```

### Manual Operations

#### Run Backup Manually
```bash
curl -X POST http://localhost:8080/api/backup/now
```

#### Test Email Alerts
```bash
curl -X POST http://localhost:8080/api/test-alert
```

#### Check System Status
```bash
curl http://localhost:8080/api/status | jq
```

### Running in Development

```bash
cd /opt/immich-server-manager
source venv/bin/activate
python -m src.main
```

Access at: http://localhost:8080

## Troubleshooting

### Service Won't Start

```bash
# Check logs for errors
sudo journalctl -u immich-server-manager -n 50

# Verify configuration
cat /opt/immich-server-manager/config/config.yaml

# Test configuration validity
cd /opt/immich-server-manager
source venv/bin/activate
python -c "from src.config import load_config; load_config()"

# Check permissions
ls -la /opt/immich-server-manager/
```

### Disk Monitoring Not Working

```bash
# Verify smartmontools is installed
which smartctl

# Install if missing
sudo apt install smartmontools

# Test manually
sudo smartctl -a /dev/sda

# Check if user has sudo access to smartctl
sudo visudo  # Add: username ALL=(ALL) NOPASSWD: /usr/sbin/smartctl
```

### Backups Failing

```bash
# Check Docker container is running
docker ps | grep postgres

# Test database connection
docker exec immich_postgres psql -U postgres -c "SELECT version();"

# Check backup directory permissions
ls -la /mnt/backups/immich/

# Test manual backup
docker exec immich_postgres pg_dump -U postgres immich > test_backup.sql
```

### Email Alerts Not Sending

```bash
# Test SMTP connection
curl -X POST http://localhost:8080/api/test-alert

# Check logs for SMTP errors
sudo journalctl -u immich-server-manager | grep -i smtp

# For Gmail: Verify App Password is used (not regular password)
# Enable "Less secure app access" or use App Password
```

### Database Errors

```bash
# Check database file
ls -la /opt/immich-server-manager/server-manager.db

# Backup database
cp /opt/immich-server-manager/server-manager.db /tmp/backup.db

# Recreate database (service will recreate on next start)
rm /opt/immich-server-manager/server-manager.db
sudo systemctl restart immich-server-manager
```

## Security Considerations

### API Key Storage
- Never commit `config.yaml` with real API keys to version control
- Use environment variables for sensitive data in production
- Restrict file permissions: `chmod 600 config/config.yaml`

### SMTP Passwords
- Use app-specific passwords for email services
- For Gmail: Create App Password in Google Account settings
- Never use your main account password

### File Permissions
```bash
# Secure configuration file
sudo chown root:root /opt/immich-server-manager/config/config.yaml
sudo chmod 600 /opt/immich-server-manager/config/config.yaml

# Secure backup directory
sudo chown root:root /mnt/backups/immich
sudo chmod 700 /mnt/backups/immich
```

### Network Security
- The service binds to `0.0.0.0:8080` by default
- Consider using `127.0.0.1:8080` if only local access needed
- Use reverse proxy (nginx/Cloudflare Tunnel) for remote access
- Never expose port 8080 directly to the internet

## Development

### Project Structure

```
server-manager/
├── src/
│   ├── __init__.py
│   ├── main.py              # FastAPI app & endpoints
│   ├── config.py            # Configuration loading & validation
│   ├── database.py          # SQLite database operations
│   ├── monitoring.py        # Disk/system/Docker monitoring
│   ├── backup.py            # Backup manager
│   ├── backup_verifier.py   # Backup verification
│   └── alerts.py            # Alert manager (email/webhook)
├── config/
│   └── config.yaml.example  # Configuration template
├── static/
│   └── dashboard.html       # Web dashboard UI
├── requirements.txt          # Python dependencies
├── verify-backup.py         # Standalone backup verification tool
└── README.md                # This file
```

### Adding New Monitoring Features

1. Create new monitor class in `monitoring.py`
2. Initialize in `main.py` startup event
3. Add scheduled job to APScheduler
4. Store data in database (add table if needed)
5. Create API endpoint to expose data
6. Update dashboard UI

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Run tests
pytest

# With coverage
pytest --cov=src --cov-report=html
```

## Performance

### Resource Usage
- **Memory**: ~50-100 MB
- **CPU**: <1% idle, ~5-10% during backup
- **Disk I/O**: Minimal except during backups

### Database Size
- ~1 MB per day with default collection intervals
- Recommend periodic cleanup of old metrics:
  ```sql
  DELETE FROM system_metrics WHERE timestamp < datetime('now', '-90 days');
  DELETE FROM disk_health WHERE timestamp < datetime('now', '-90 days');
  ```

### Scaling Considerations
- SQLite suitable for single-server deployments
- For multi-server: consider PostgreSQL backend
- SMART checks can be slow on many disks (adjust interval)

## License

MIT License - See LICENSE file in repository root.

## Support

- **Issues**: https://github.com/yourusername/immich-manager/issues
- **Immich Discord**: https://discord.immich.app
- **Main Documentation**: See root README.md
