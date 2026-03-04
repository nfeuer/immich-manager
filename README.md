# Immich Manager

**Production-ready monitoring, backups, curation, and remote access for Immich**

https://houseoffeuer.com | Discord: House of Feuer

---

## What This Provides

### Server Manager (port 8080)
- Disk health monitoring (SMART), automated daily backups with optional **age encryption**
- Prometheus-compatible `/metrics` endpoint, system metrics (CPU/RAM/disk/network)
- Immich version update notifications, Docker container monitoring
- Email, webhook, and **Discord** alerts (House of Feuer branding)
- API rate limiting, audit log, structured JSON logging
- Guided backup restore workflow (stop Immich, restore, restart)
- Systemd watchdog heartbeats

### Photo Curator (port 8081)
- AI photo quality scoring (local models, no API costs)
- Monthly curation reminders with per-user targets
- Duplicate detection, Year in Review summary
- Photo Map View (OpenStreetMap + Leaflet)
- Family Mode: shared curation sessions with collaborator invites
- Immich SSO authentication (no separate login)

### Remote Access
- Cloudflare Tunnel (no port forwarding, automatic HTTPS, DDoS protection)
- Multi-service routing: domain -> Immich, /monitor/ -> Server Manager, /curator/ -> Photo Curator

### Security Hardening
- fail2ban, UFW firewall, SSH hardening (key-only auth, root login disabled)
- Automatic security updates (unattended-upgrades, security-only)
- Services run as dedicated `immich-mgr` user with systemd sandboxing
- CSRF protection, CSP headers, secrets in environment file (not config)
- Backup encryption with [age](https://age-encryption.org/)

### Deployment
- Automated deploy script with backup, selective service restart, and rollback
- Schema migration system (no manual DB changes needed on update)

---

## Quick Start (Clean Ubuntu Install)

### Prerequisites
- Ubuntu 22.04+ or Debian 12+ (fresh install is fine)
- Immich already installed and running ([install guide](https://immich.app/docs/install/docker-compose))
- sudo access
- A domain name pointed at Cloudflare (~$12/year) if you want remote access

### Step 1: Clone and auto-install dependencies

```bash
git clone https://github.com/nfeuer/immich-manager.git
cd immich-manager

# Auto-install everything: Docker, Python, fail2ban, etc.
./scripts/01-install-prerequisites.sh
```

This installs: Python 3 + pip + venv, Docker CE + Compose, build-essential, curl, jq, git, smartmontools, UFW, fail2ban, unattended-upgrades, OpenCV system libs, and creates the `immich-mgr` service user.

**If it tells you to log out** (for Docker group changes), do so, then continue.

### Step 2: Edit secrets

```bash
sudo nano /etc/immich-ecosystem/secrets.env
```

Fill in at minimum:
- `IMMICH_API_KEY` — generate in Immich: Admin -> API Keys
- `SMTP_PASSWORD` — if you want email alerts
- `DISCORD_WEBHOOK_URL` — if you want Discord notifications

### Step 3: Run the installer

```bash
./install.sh
```

The installer walks you through 5 phases interactively (~30 minutes).

---

## Manual Steps After Installation

These cannot be automated and **you must do them yourself**:

### 1. Set up your SSH key (CRITICAL before exposing to the web)

From your **local machine** (not the server):

```bash
# Generate a key if you don't have one
ssh-keygen -t ed25519

# Copy it to the server
ssh-copy-id youruser@server-ip
```

Then re-run the security hardening to fully disable password auth:

```bash
./scripts/40-security-hardening.sh --force
```

Verify you can still SSH in with your key before closing your current session.

### 2. Enable 2FA for all Immich users (CRITICAL)

1. Login to Immich as admin
2. Go to **Admin -> Users**
3. For each user: click user -> Settings -> Enable 2FA
4. Each user sets up an authenticator app (Google Authenticator, Authy, etc.)
5. **Save recovery codes** in a safe place

### 3. Set up Cloudflare Access (recommended)

This adds a zero-trust auth layer in front of the management dashboards:

1. Go to https://one.dash.cloudflare.com/
2. Navigate to **Access -> Applications -> Add an Application**
3. Create a self-hosted app:
   - Application domain: `yourdomain.com`, Path: `/monitor/*`
   - Add another rule for: `yourdomain.com`, Path: `/curator/*`
4. Set policy: "Allow" with email one-time pin (your email only)

This means even if someone finds `/monitor/`, they hit a Cloudflare login wall before reaching the app.

### 4. Enable backup encryption (recommended)

```bash
# Install age encryption tool
sudo apt install age

# Generate a key pair
sudo age-keygen -o /etc/immich-ecosystem/backup-key.txt

# Note the public key from the output (starts with "age1...")
```

Edit `/opt/immich-server-manager/config/config.yaml`:

```yaml
backup:
  encryption:
    enabled: true
    public_key: "age1your-public-key-here"
```

**Keep `/etc/immich-ecosystem/backup-key.txt` safe** — without it, you cannot restore encrypted backups. Copy it to a secure location off-server.

### 5. Configure alerts

Edit `/opt/immich-server-manager/config/config.yaml` to set:
- Email recipients (`alerts.email.to`)
- Discord webhook URL (`alerts.discord.webhook_url`)
- Alert thresholds (disk temp, disk space)

Test:

```bash
curl -X POST http://localhost:8080/api/test-alert
```

### 6. Review the security checklist

```bash
cat /opt/immich-ecosystem/security-checklist.txt
```

---

## Updating / Deploying Changes

After pulling new code from the repo:

```bash
# Update everything with automatic backup
sudo ./scripts/deploy.sh

# Update only one service
sudo ./scripts/deploy.sh photo-curator

# Roll back if something breaks
sudo ./scripts/deploy.sh --rollback
```

The deploy script:
1. Backs up databases before changing anything
2. Pulls latest code from git
3. Syncs files and installs new Python dependencies
4. Restarts only the specified services (with health checks)
5. Verifies database migrations applied
6. Keeps 10 deploy backups for rollback

---

## Configuration Reference

### Secrets (credentials)

All secrets live in one file, readable only by root and the service user:

```
/etc/immich-ecosystem/secrets.env    (mode 640, root:immich-mgr)
```

Config files reference them with `${ENV_VAR}` or `${ENV_VAR:-default}` syntax.

### Service configs

| Service | Config file | Example |
|---------|------------|---------|
| Server Manager | `/opt/immich-server-manager/config/config.yaml` | `server-manager/config/config.yaml.example` |
| Photo Curator | `/opt/photo-curator/config/config.yaml` | `photo-curator/config/config.yaml.example` |

### Key directories

| Path | Purpose |
|------|---------|
| `/etc/immich-ecosystem/secrets.env` | API keys, passwords |
| `/etc/immich-ecosystem/backup-key.txt` | Backup encryption key |
| `/opt/immich-server-manager/` | Server Manager install |
| `/opt/photo-curator/` | Photo Curator install |
| `/var/log/immich-ecosystem/` | Application logs (rotated daily, 30 days) |
| `/var/lib/immich-ecosystem/` | Install state (persistent) |
| `/mnt/backups/immich/` | Database backups |
| `/etc/ssh/sshd_config.d/99-immich-hardening.conf` | SSH hardening config |

---

## Service Management

```bash
# View logs
sudo journalctl -u immich-server-manager -f
sudo journalctl -u photo-curator -f
sudo journalctl -u cloudflared -f

# Restart
sudo systemctl restart immich-server-manager
sudo systemctl restart photo-curator

# Health check
./scripts/health-check.sh

# Security audit
/opt/immich-ecosystem/scripts/security-monitor.sh
```

---

## API Endpoints

### Server Manager (http://localhost:8080)

All endpoints except `/health` require Immich authentication (cookie or Bearer token).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (no auth) |
| GET | `/api/status` | System status |
| GET | `/api/disks` | Disk health (SMART) |
| GET | `/api/metrics?hours=24` | Historical system metrics |
| GET | `/api/backups` | Backup history |
| POST | `/api/backup/now` | Trigger backup |
| GET | `/api/alerts` | Alert history |
| POST | `/api/test-alert` | Send test alert |
| GET | `/metrics` | Prometheus metrics |
| GET | `/api/audit` | Audit log |
| GET | `/api/backups/available` | List restorable backups |
| POST | `/api/restore` | Start guided restore |
| GET | `/api/immich-update` | Check for Immich updates |

### Photo Curator (http://localhost:8081)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (no auth) |
| GET | `/` | Main curation UI |
| GET | `/year-in-review` | Year in Review page |
| GET | `/map` | Photo Map View |
| GET | `/api/year-in-review/{year}` | Year in Review data |
| GET | `/api/photos/map` | Photo locations |
| POST | `/api/curation/{year}/{month}/share` | Invite collaborator |
| GET | `/api/curation/{year}/{month}/collaborators` | List collaborators |
| GET | `/api/shared-sessions` | Your shared sessions |
| POST | `/api/curation/{year}/{month}/shared-pick` | Add shared pick |

Full interactive API docs: http://localhost:8080/docs and http://localhost:8081/docs

---

## Security Architecture

```
Internet
    |
    v
[Cloudflare Edge] -- DDoS protection, HTTPS termination
    |
    v
[Cloudflare Tunnel] -- outbound-only connection, no open ports
    |
    v
[UFW Firewall] -- deny all incoming except SSH + local subnet
    |
    v
[fail2ban] -- auto-ban after 5 failed SSH attempts
    |
    v
[SSH] -- key-only auth, root login disabled, 3 max tries
    |
    v
[systemd sandbox] -- immich-mgr user, ProtectSystem=strict,
                      PrivateDevices, ProtectHome, RestrictNamespaces
    |
    v
[FastAPI app] -- Immich SSO auth, CSRF protection, rate limiting,
                  CSP headers, audit logging
    |
    v
[Secrets] -- /etc/immich-ecosystem/secrets.env (640 root:immich-mgr)
```

### What's automated
- Security patches via unattended-upgrades (daily, security-only)
- Log rotation (daily, 30 days, compressed)
- fail2ban monitoring
- Service watchdog (auto-restart on crash)

### What requires manual action
- SSH key setup (before disabling password auth)
- Immich 2FA enrollment (per user)
- Cloudflare Access policy (optional but recommended)
- Backup encryption key generation
- Periodic security checklist review

---

## Troubleshooting

### Service won't start

```bash
sudo journalctl -u immich-server-manager -n 50 --no-pager
# or
sudo journalctl -u photo-curator -n 50 --no-pager
```

### Permission errors after deploy

```bash
sudo chown -R immich-mgr:immich-mgr /opt/immich-server-manager
sudo chown -R immich-mgr:immich-mgr /opt/photo-curator
```

### Can't SSH after security hardening

If you're locked out (password auth was disabled before adding a key):
1. Access the server via physical console or hosting provider's console
2. Edit `/etc/ssh/sshd_config.d/99-immich-hardening.conf`
3. Uncomment `PasswordAuthentication no` line
4. Run `sudo systemctl restart ssh`
5. Add your SSH key, then re-run `./scripts/40-security-hardening.sh --force`

### Remote access not working

```bash
sudo systemctl status cloudflared
sudo journalctl -u cloudflared -n 100
dig yourdomain.com
```

### Backup restore

```bash
# List available backups
curl http://localhost:8080/api/backups/available

# Trigger guided restore via API
curl -X POST http://localhost:8080/api/restore -d '{"backup_file": "/mnt/backups/immich/immich_db_20240101_020000.sql.gz"}'
```

For encrypted backups, ensure `/etc/immich-ecosystem/backup-key.txt` is present on the server.

---

## Project Structure

```
immich-manager/
├── install.sh                          # Master installer (interactive)
├── README.md
├── scripts/
│   ├── 00-check-prerequisites.sh       # Validate requirements
│   ├── 01-install-prerequisites.sh     # Auto-install all dependencies
│   ├── 10-install-server-manager.sh    # Install server manager
│   ├── 20-install-photo-curator.sh     # Install photo curator
│   ├── 30-install-remote-access.sh     # Cloudflare Tunnel setup
│   ├── 40-security-hardening.sh        # SSH, fail2ban, UFW, checklist
│   ├── 50-test-installation.sh         # Post-install verification
│   ├── deploy.sh                       # Automated update/rollback
│   ├── health-check.sh                 # Quick health check
│   ├── lib/state-manager.sh            # Install state tracking
│   └── systemd/                        # Service unit files
├── server-manager/
│   ├── src/
│   │   ├── main.py                     # FastAPI app, all endpoints
│   │   ├── config.py                   # Pydantic config with env var support
│   │   ├── database.py                 # SQLite + migration system
│   │   ├── monitoring.py               # Disk, system, Docker monitoring
│   │   ├── backup.py                   # Backup + age encryption
│   │   ├── backup_verifier.py          # Backup integrity verification
│   │   ├── alerts.py                   # Email, webhook, Discord alerts
│   │   ├── update_checker.py           # Immich version checker
│   │   ├── prometheus.py               # Prometheus metrics exposition
│   │   ├── audit.py                    # Audit log
│   │   └── logging_config.py           # Structured JSON logging
│   ├── config/config.yaml.example
│   └── requirements.txt
├── photo-curator/
│   ├── src/
│   │   ├── main.py                     # FastAPI app, curation + map + family mode
│   │   ├── database.py                 # SQLite + migrations + shared curation
│   │   ├── auth.py                     # Immich SSO integration
│   │   ├── immich_client.py            # Immich API client
│   │   ├── analyzer.py                 # AI photo scoring
│   │   ├── notifications.py            # Email notifications
│   │   └── logging_config.py           # Structured JSON logging
│   ├── config/config.yaml.example
│   └── requirements.txt
├── migration-tools/                    # Database migration utilities
└── health-monitor/                     # Standalone health monitor
```

---

## Cost

**Total: ~$12/year** (domain name only). Everything else is free and self-hosted.

---

## Support

- **Website:** https://houseoffeuer.com
- **Discord:** House of Feuer
- **Immich Docs:** https://immich.app/docs

---

## License

MIT License - See LICENSE file for details.
