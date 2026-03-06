# Immich Manager

Production-ready monitoring, backups, curation, and remote access for [Immich](https://immich.app) — built for family self-hosting (6–20 users).

## What This Provides

| Component | What it does |
|-----------|-------------|
| **Server Manager** (`:8080`) | Disk health (SMART), automated backups, Discord/email alerts, Immich auto-updates, snapshot rollback |
| **Photo Curator** (`:8081`) | AI photo quality scoring, monthly curation, duplicate detection, analytics dashboard |
| **Health Monitor** | Systemd-timer-based self-healing — restarts failed services, optimizes databases |
| **Remote Access** | Cloudflare Tunnel — HTTPS, no port-forwarding, DDoS protection |
| **Security** | fail2ban, UFW, 2FA guidance |

## Cost

**$10–15/year** (domain name only — everything else is free and self-hosted)

## Quick Start

```bash
git clone https://github.com/yourusername/immich-manager.git
cd immich-manager
./install.sh
```

> Requires Ubuntu/Debian, Python 3.9+, Docker, and Immich already running.
> Installation takes ~30–60 minutes. See [QUICK_START.md](QUICK_START.md) for a guided walkthrough.

## Documentation

| Document | Purpose |
|----------|---------|
| [QUICK_START.md](QUICK_START.md) | Step-by-step installation and first-use guide |
| [SETUP.md](SETUP.md) | Full configuration reference (API keys, SMTP, Cloudflare) |
| [FEATURES.md](FEATURES.md) | Complete feature list with validation checklists |
| [API.md](API.md) | REST API reference for both services |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design, data flows, database schemas |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup and contribution guidelines |
| [docs/DOCKER.md](docs/DOCKER.md) | Multi-file Docker Compose layout and GPU setup |
| [docs/ADDING_FEATURES.md](docs/ADDING_FEATURES.md) | How to add and document new features |

### Component Docs

- [server-manager/README.md](server-manager/README.md)
- [photo-curator/README.md](photo-curator/README.md)
- [health-monitor/README.md](health-monitor/README.md)
- [migration-tools/README.md](migration-tools/README.md)

## Roadmap

See [FEATURES.md](FEATURES.md) for the full feature list with status and validation steps.

**Completed highlights:** Discord alerts · AI photo scoring · Face recognition · Auto-updater with rollback · Guest links · RBAC · Analytics dashboard · Google Photos import · Backup verification

**In progress:** Grafana dashboard config

**Planned:** Per-user storage quotas · Smart album rules · Trip detection · "On this day" emails · Photo book PDF export

## Support

- **Issues:** Open a GitHub issue
- **Immich Discord:** https://discord.immich.app
- **Immich Docs:** https://immich.app/docs
