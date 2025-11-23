# Health Monitor

**Self-healing monitoring system for Immich Manager ecosystem**

## Overview

The Health Monitor is a lightweight Python script that runs periodically (every 15 minutes via systemd timer) to check the health of all Immich Manager services and automatically fix common issues. It's designed to keep your Immich ecosystem running smoothly with minimal intervention.

## Features

### 🏥 Service Health Monitoring
- **HTTP Health Checks**: Validates services are responding
  - Immich server (port 2283)
  - Server Manager (port 8080)
  - Photo Curator (port 8081)

- **Systemd Status Checks**: Verifies services are running
  - `immich-server-manager.service`
  - `photo-curator.service`
  - `cloudflared.service` (if installed)

### 🔧 Automatic Healing
- **Service Restart**: Automatically restarts failed services
- **Database Optimization**: Runs SQLite VACUUM on corrupted databases
- **Disk Space Alerts**: Warns when disk space is low
- **Cache Cleanup**: Removes stale cache files

### 📧 Weekly Summaries
- Email reports of all health events
- Summary of auto-fixes performed
- Service uptime statistics
- Early warning indicators

## Installation

### Quick Install

The health monitor is installed as part of the main installation:

```bash
cd /home/user/immich-manager
./install.sh
```

### Manual Installation

```bash
# Create installation directory
sudo mkdir -p /opt/health-monitor
sudo cp -r health-monitor/* /opt/health-monitor/

# Create virtual environment
cd /opt/health-monitor
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp config/config.yaml.example config/config.yaml
nano config/config.yaml

# Install systemd timer and service
sudo cp health-monitor.service /etc/systemd/system/
sudo cp health-monitor.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable health-monitor.timer
sudo systemctl start health-monitor.timer
```

## Configuration

Configuration file location: `/opt/health-monitor/config/config.yaml`

### Minimal Configuration

```yaml
immich:
  base_url: "http://localhost:2283"
  api_key: "your-api-key"

curator:
  url: "http://localhost:8081"

manager:
  url: "http://localhost:8080"

health:
  auto_restart: true
  disk_threshold_percent: 90
```

### Full Configuration Options

```yaml
# Immich server configuration
immich:
  base_url: "http://localhost:2283"
  api_url: "http://localhost:2283/api"
  api_key: ""

# Photo Curator configuration
curator:
  url: "http://localhost:8081"
  service_name: "photo-curator"

# Server Manager configuration
manager:
  url: "http://localhost:8080"
  service_name: "immich-server-manager"

# Cloudflare Tunnel (optional)
cloudflare:
  enabled: false
  service_name: "cloudflared"

# Health monitor settings
health:
  auto_restart: true                    # Automatically restart failed services
  max_restart_attempts: 3               # Max restart attempts before alerting
  restart_cooldown_minutes: 5           # Wait time between restarts

  # Disk space monitoring
  disk_threshold_percent: 90            # Alert when disk > 90% full
  disk_paths:
    - "/"
    - "/mnt/photos"

  # Database maintenance
  database_optimization: true           # Auto-optimize SQLite databases
  optimization_schedule: "weekly"       # weekly or daily

  # Cache cleanup
  cache_cleanup: true
  cache_max_age_hours: 48
  cache_paths:
    - "/tmp/photo-curator-cache"

# Email notifications
notifications:
  email:
    enabled: true
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    smtp_user: "your-email@gmail.com"
    smtp_password: "your-app-password"
    from: "health-monitor@yourdomain.com"
    to:
      - "admin@yourdomain.com"

    # Weekly summary
    weekly_summary: true
    summary_day: 0                      # 0=Monday, 6=Sunday
    summary_hour: 9                     # 9 AM

# Logging
logging:
  level: "INFO"
  file: "/var/log/health-monitor.log"
  retention_days: 30
```

## Architecture

### System Design

```
┌──────────────────────────────────────────────┐
│   systemd Timer (Every 15 Minutes)          │
│   health-monitor.timer                       │
└───────────────┬──────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────┐
│   Health Monitor Script (main.py)            │
│   - Runs health checks                       │
│   - Performs auto-healing                    │
│   - Logs results                             │
└───────┬──────────────────────────────────────┘
        │
        ├─── HTTP Health Checks
        │    ├─── Immich (GET /api/server-info)
        │    ├─── Curator (GET /health)
        │    └─── Manager (GET /health)
        │
        ├─── Systemd Status Checks
        │    ├─── systemctl status photo-curator
        │    ├─── systemctl status immich-server-manager
        │    └─── systemctl status cloudflared (optional)
        │
        ├─── Auto-Healing Actions
        │    ├─── systemctl restart <service>
        │    ├─── sqlite3 VACUUM
        │    ├─── rm stale cache files
        │    └─── df -h (disk space check)
        │
        └─── Notifications
             ├─── Email alerts (immediate failures)
             └─── Weekly summary email
```

### Health Check Flow

```
1. Timer triggers script every 15 minutes
2. For each service:
   a. HTTP health check (5 second timeout)
   b. If fails → Check systemd status
   c. If service stopped → Restart service
   d. If service running but not responding → Restart service
   e. Log health check result
3. Database health:
   a. Check SQLite integrity
   b. If corrupted → Run VACUUM
   c. If optimization scheduled → Run VACUUM
4. Disk space check:
   a. Check all monitored paths
   b. If > threshold → Send alert
5. Cache cleanup:
   a. Find files older than max age
   b. Delete stale cache files
6. Weekly summary:
   a. If configured day/hour → Send summary email
   b. Include all health events from past week
   c. Include service uptime statistics
```

## Usage

### Systemd Timer Management

```bash
# Check timer status
sudo systemctl status health-monitor.timer

# View timer schedule
systemctl list-timers health-monitor.timer

# Start timer (if not running)
sudo systemctl start health-monitor.timer

# Stop timer
sudo systemctl stop health-monitor.timer

# Enable on boot
sudo systemctl enable health-monitor.timer

# Disable on boot
sudo systemctl disable health-monitor.timer
```

### Manual Execution

Run health check immediately (without waiting for timer):

```bash
cd /opt/health-monitor
source venv/bin/activate
python -m src.main
```

Or use systemd:

```bash
# Run once immediately
sudo systemctl start health-monitor.service

# View logs from last run
sudo journalctl -u health-monitor.service -n 50
```

### Viewing Logs

```bash
# Follow logs in real-time
sudo journalctl -u health-monitor.service -f

# View logs from today
sudo journalctl -u health-monitor.service --since today

# View timer logs
sudo journalctl -u health-monitor.timer -f

# View last 100 lines
sudo journalctl -u health-monitor.service -n 100

# View only errors
sudo journalctl -u health-monitor.service -p err
```

### Health Check Output

Example output from a successful health check:

```
2024-01-15 10:15:00 - INFO - Starting health check
2024-01-15 10:15:00 - INFO - Checking Immich server...
2024-01-15 10:15:00 - INFO - ✓ Immich is healthy
2024-01-15 10:15:01 - INFO - Checking Photo Curator...
2024-01-15 10:15:01 - INFO - ✓ Photo Curator is healthy
2024-01-15 10:15:02 - INFO - Checking Server Manager...
2024-01-15 10:15:02 - INFO - ✓ Server Manager is healthy
2024-01-15 10:15:03 - INFO - Checking disk space...
2024-01-15 10:15:03 - INFO - ✓ Disk space OK (75% used)
2024-01-15 10:15:04 - INFO - Cleaning cache...
2024-01-15 10:15:04 - INFO - ✓ Removed 12 stale cache files (234 MB freed)
2024-01-15 10:15:04 - INFO - Health check completed successfully
```

Example output when a service fails:

```
2024-01-15 10:15:00 - INFO - Starting health check
2024-01-15 10:15:00 - INFO - Checking Photo Curator...
2024-01-15 10:15:05 - WARNING - Photo Curator health check failed (timeout)
2024-01-15 10:15:05 - INFO - Checking systemd status...
2024-01-15 10:15:05 - ERROR - photo-curator.service is inactive (dead)
2024-01-15 10:15:05 - INFO - Attempting to restart service...
2024-01-15 10:15:05 - INFO - Executing: systemctl restart photo-curator
2024-01-15 10:15:10 - INFO - Service restarted successfully
2024-01-15 10:15:10 - INFO - Verifying service is now healthy...
2024-01-15 10:15:15 - INFO - ✓ Photo Curator is now responding
2024-01-15 10:15:15 - INFO - Sending email alert...
2024-01-15 10:15:16 - INFO - Alert sent to admin@yourdomain.com
```

## Health Checks Performed

### 1. Service HTTP Checks

| Service | Endpoint | Expected Response | Timeout |
|---------|----------|-------------------|---------|
| Immich | `GET /api/server-info` | 200 OK | 5s |
| Curator | `GET /health` | 200 OK | 5s |
| Manager | `GET /health` | 200 OK | 5s |

### 2. Systemd Service Checks

```bash
systemctl is-active photo-curator
systemctl is-active immich-server-manager
systemctl is-active cloudflared  # if enabled
```

### 3. Database Health

```bash
# Check SQLite integrity
sqlite3 /opt/photo-curator/curator.db "PRAGMA integrity_check;"
sqlite3 /opt/immich-server-manager/server-manager.db "PRAGMA integrity_check;"

# Optimize if needed
sqlite3 curator.db "VACUUM;"
```

### 4. Disk Space

```bash
df -h / | awk 'NR==2 {print $5}'  # Check root partition
df -h /mnt/photos | awk 'NR==2 {print $5}'  # Check photo storage
```

### 5. Cache Cleanup

```bash
# Find files older than 48 hours
find /tmp/photo-curator-cache -type f -mtime +2

# Delete old files
find /tmp/photo-curator-cache -type f -mtime +2 -delete
```

## Auto-Healing Actions

### Automatic Service Restart

When a service fails the health check:

1. Check if service is running via systemd
2. If stopped → Restart immediately
3. If running but not responding → Restart
4. Wait 10 seconds
5. Re-check health
6. If still failing → Send alert email
7. Log all actions

**Cooldown Period:** 5 minutes between restart attempts to prevent restart loops.

**Max Attempts:** After 3 failed restart attempts, stop trying and send critical alert.

### Database Optimization

Weekly (or daily) SQLite VACUUM:

```python
# Optimize database
subprocess.run(['sqlite3', db_path, 'VACUUM;'])

# Verify integrity
result = subprocess.run(
    ['sqlite3', db_path, 'PRAGMA integrity_check;'],
    capture_output=True, text=True
)
if result.stdout != "ok\n":
    send_alert("Database corruption detected!")
```

### Cache Cleanup

Remove files older than configured age:

```python
import time
from pathlib import Path

cache_path = Path("/tmp/photo-curator-cache")
max_age_seconds = 48 * 3600  # 48 hours

for file in cache_path.glob("*"):
    if time.time() - file.stat().st_mtime > max_age_seconds:
        file.unlink()
        logger.info(f"Deleted stale cache file: {file.name}")
```

## Email Notifications

### Immediate Alerts

Sent when:
- Service fails and cannot be auto-restarted
- Disk space exceeds threshold
- Database corruption detected
- Multiple restart attempts failed

**Example Alert Email:**

```
Subject: [CRITICAL] Immich Health Monitor Alert

Service Failure Detected

Service: photo-curator
Status: Failed
Timestamp: 2024-01-15 10:15:00 UTC

Details:
- HTTP health check failed (connection refused)
- Systemd status: inactive (dead)
- Auto-restart attempted: Yes
- Restart successful: No
- Attempts: 3

Action Required:
Please investigate the photo-curator service logs:
  sudo journalctl -u photo-curator -n 100

Manual restart:
  sudo systemctl restart photo-curator
```

### Weekly Summary

Sent on configured day/time (default: Monday 9 AM).

**Example Summary Email:**

```
Subject: [INFO] Weekly Immich Health Summary

Health Monitor Weekly Report
Period: Jan 8 - Jan 15, 2024

Service Uptime:
  ✓ Immich: 100% (672/672 checks passed)
  ✓ Photo Curator: 99.7% (670/672 checks passed)
  ✓ Server Manager: 100% (672/672 checks passed)

Events This Week:
  - 2024-01-12 03:15: Photo Curator auto-restarted (1 attempt)
  - 2024-01-14 22:00: Cache cleanup (567 MB freed)

Auto-Healing Actions:
  - Service restarts: 1
  - Database optimizations: 1
  - Cache cleanups: 7

Disk Space:
  / : 75% used (250 GB free)
  /mnt/photos: 82% used (180 GB free)

Database Sizes:
  curator.db: 12.3 MB
  server-manager.db: 8.7 MB

All systems operating normally.
```

## Troubleshooting

### Timer Not Running

```bash
# Check timer status
systemctl status health-monitor.timer

# Check if timer is enabled
systemctl is-enabled health-monitor.timer

# Enable and start timer
sudo systemctl enable health-monitor.timer
sudo systemctl start health-monitor.timer

# Verify timer is scheduled
systemctl list-timers | grep health-monitor
```

### Script Errors

```bash
# Check recent logs
sudo journalctl -u health-monitor.service -n 50

# Test script manually
cd /opt/health-monitor
source venv/bin/activate
python -m src.main

# Check Python dependencies
pip list

# Reinstall dependencies
pip install -r requirements.txt
```

### Email Not Sending

```bash
# Test email configuration
cd /opt/health-monitor
source venv/bin/activate
python -c "
import yaml
import asyncio
from src.main import HealthMonitor

with open('config/config.yaml') as f:
    config = yaml.safe_load(f)

monitor = HealthMonitor(config)
asyncio.run(monitor.send_test_email())
"

# Check SMTP settings in config.yaml
cat config/config.yaml | grep -A 10 "email:"
```

### Auto-Restart Not Working

```bash
# Verify auto_restart is enabled in config
grep "auto_restart" /opt/health-monitor/config/config.yaml

# Check if script has sudo permissions for systemctl
# Add to /etc/sudoers.d/health-monitor:
# health-monitor ALL=(ALL) NOPASSWD: /bin/systemctl restart photo-curator
# health-monitor ALL=(ALL) NOPASSWD: /bin/systemctl restart immich-server-manager

# Test manual restart
sudo systemctl restart photo-curator
```

### Database Optimization Failing

```bash
# Check SQLite is installed
which sqlite3

# Install if missing
sudo apt install sqlite3

# Test database access
sqlite3 /opt/photo-curator/curator.db "PRAGMA integrity_check;"

# Check file permissions
ls -la /opt/photo-curator/curator.db
```

## Performance

### Resource Usage
- **Memory**: ~20-30 MB during execution
- **CPU**: <5% for ~5-10 seconds every 15 minutes
- **Disk I/O**: Minimal (only during cache cleanup)

### Execution Time
- Typical health check: 5-10 seconds
- With service restart: 15-30 seconds
- Database optimization: 1-5 seconds
- Cache cleanup: 1-10 seconds (depends on cache size)

### Impact on System
- Very low overhead
- Does not interfere with other services
- Safe to run in production

## Best Practices

### Restart Cooldown
- Default 5-minute cooldown prevents restart loops
- Adjust if services take longer to initialize
- Monitor logs for frequent restarts (indicates deeper issue)

### Email Alerts
- Configure quiet hours for non-critical alerts
- Use separate email for alerts (easier to filter)
- Set up email rules to prioritize CRITICAL alerts

### Disk Thresholds
- Set warning threshold at 80%, critical at 90%
- Monitor trends to predict when disk will fill
- Set up automated cleanup or expansion before reaching limit

### Database Optimization
- Weekly VACUUM is sufficient for most deployments
- Daily VACUUM if database is heavily used
- Monitor database size over time

### Log Retention
- Keep health monitor logs for at least 30 days
- Archive logs for compliance/audit if needed
- Rotate logs to prevent disk filling

## Security Considerations

### Sudo Access
- Health monitor needs sudo access to restart services
- Use `/etc/sudoers.d/` for granular permissions
- Only allow specific commands (systemctl restart)

Example `/etc/sudoers.d/health-monitor`:
```
health-monitor ALL=(ALL) NOPASSWD: /bin/systemctl restart photo-curator
health-monitor ALL=(ALL) NOPASSWD: /bin/systemctl restart immich-server-manager
health-monitor ALL=(ALL) NOPASSWD: /bin/systemctl restart cloudflared
health-monitor ALL=(ALL) NOPASSWD: /bin/systemctl status photo-curator
health-monitor ALL=(ALL) NOPASSWD: /bin/systemctl status immich-server-manager
health-monitor ALL=(ALL) NOPASSWD: /bin/systemctl status cloudflared
```

### Configuration Security
```bash
# Secure configuration file
sudo chown root:root /opt/health-monitor/config/config.yaml
sudo chmod 600 /opt/health-monitor/config/config.yaml
```

### Email Security
- Use app-specific passwords, not account passwords
- Enable TLS for SMTP connections
- Don't include sensitive data in email alerts

## Development

### Project Structure

```
health-monitor/
├── src/
│   ├── __init__.py
│   └── main.py              # Health monitor script
├── config/
│   └── config.yaml.example  # Configuration template
├── health-monitor.service   # Systemd service unit
├── health-monitor.timer     # Systemd timer unit
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

### Adding New Health Checks

1. Add check method to `HealthMonitor` class:
```python
async def check_custom_service(self) -> HealthCheck:
    """Check custom service health"""
    try:
        response = requests.get("http://localhost:9000/health", timeout=5)
        if response.status_code == 200:
            return HealthCheck(
                service="custom",
                healthy=True,
                message="Service is responding",
                timestamp=datetime.now()
            )
    except Exception as e:
        return HealthCheck(
            service="custom",
            healthy=False,
            message=str(e),
            timestamp=datetime.now()
        )
```

2. Add to main check loop in `main()`:
```python
# Check custom service
custom_check = await monitor.check_custom_service()
health_checks.append(custom_check)
```

3. Update configuration schema to include new service

### Testing

```bash
# Run with debug logging
cd /opt/health-monitor
source venv/bin/activate
export LOG_LEVEL=DEBUG
python -m src.main

# Simulate service failure
sudo systemctl stop photo-curator
python -m src.main  # Should detect and restart

# Test email sending
python -c "
import asyncio
from src.main import HealthMonitor, HealthCheck
from datetime import datetime

async def test():
    monitor = HealthMonitor({'notifications': {...}})
    check = HealthCheck(
        service='test',
        healthy=False,
        message='Test failure',
        timestamp=datetime.now(),
        auto_fixed=False
    )
    await monitor.send_alert(check)

asyncio.run(test())
"
```

## Integration

### Prometheus Metrics (Optional)

Expose health check results as Prometheus metrics:

```python
from prometheus_client import Gauge, start_http_server

health_status = Gauge('service_health', 'Service health status', ['service'])

# In health check:
health_status.labels(service='immich').set(1 if healthy else 0)
```

### Logging to External Systems

Forward logs to external logging systems:

```python
import logging
from logging.handlers import SysLogHandler

# Add syslog handler
handler = SysLogHandler(address=('logserver.local', 514))
logger.addHandler(handler)
```

## License

MIT License - See LICENSE file in repository root.

## Support

- **Issues**: https://github.com/yourusername/immich-manager/issues
- **Main Documentation**: See root README.md
