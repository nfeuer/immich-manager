#!/bin/bash
#
# Automated deployment script for Immich Manager
# https://houseoffeuer.com  |  Discord: House of Feuer
#
# Usage:
#   sudo ./scripts/deploy.sh                     # Update everything
#   sudo ./scripts/deploy.sh server-manager      # Only server-manager
#   sudo ./scripts/deploy.sh photo-curator       # Only photo-curator
#   sudo ./scripts/deploy.sh server-manager photo-curator  # Both (explicit)
#   sudo ./scripts/deploy.sh --no-backup         # Skip pre-deploy backup
#   sudo ./scripts/deploy.sh --rollback          # Roll back to previous version
#

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# ── Paths ────────────────────────────────────────────────────────────
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SM_INSTALL="/opt/immich-server-manager"
PC_INSTALL="/opt/photo-curator"
SM_SERVICE="immich-server-manager"
PC_SERVICE="photo-curator"
BACKUP_DIR="/var/backups/immich-manager-deploy"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# ── Parse arguments ──────────────────────────────────────────────────
SERVICES=()
SKIP_BACKUP=false
ROLLBACK=false
BRANCH=""

for arg in "$@"; do
    case "$arg" in
        server-manager)  SERVICES+=("server-manager") ;;
        photo-curator)   SERVICES+=("photo-curator") ;;
        --no-backup)     SKIP_BACKUP=true ;;
        --rollback)      ROLLBACK=true ;;
        --branch=*)      BRANCH="${arg#--branch=}" ;;
        --help|-h)
            echo "Usage: sudo $0 [services...] [options]"
            echo ""
            echo "Services (default: all):"
            echo "  server-manager    Only update server-manager"
            echo "  photo-curator     Only update photo-curator"
            echo ""
            echo "Options:"
            echo "  --no-backup       Skip pre-deployment database backup"
            echo "  --rollback        Roll back to previous deployment"
            echo "  --branch=NAME     Pull from a specific git branch"
            echo "  -h, --help        Show this help"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown argument: $arg${NC}"
            echo "Run $0 --help for usage"
            exit 1
            ;;
    esac
done

# Default: update everything
if [ ${#SERVICES[@]} -eq 0 ]; then
    SERVICES=("server-manager" "photo-curator")
fi

# ── Helpers ──────────────────────────────────────────────────────────
log()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $*"; }
err()  { echo -e "${RED}[deploy]${NC} $*"; }
sep()  { echo "────────────────────────────────────────────────"; }

check_health() {
    local port="$1"
    local name="$2"
    local attempts=0
    local max_attempts=15

    while [ $attempts -lt $max_attempts ]; do
        if curl -sf "http://localhost:${port}/health" > /dev/null 2>&1; then
            log "${name} is healthy"
            return 0
        fi
        attempts=$((attempts + 1))
        sleep 2
    done

    err "${name} failed health check after ${max_attempts} attempts"
    return 1
}

service_active() {
    systemctl is-active --quiet "$1" 2>/dev/null
}

# ── Preflight ────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   House of Feuer — Deploy              ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════╝${NC}"
echo ""
log "Timestamp:  ${TIMESTAMP}"
log "Services:   ${SERVICES[*]}"
log "Repo:       ${REPO_DIR}"
echo ""

# Must be root (for systemctl and file copies)
if [ "$EUID" -ne 0 ]; then
    err "This script must be run as root (sudo)"
    exit 1
fi

# ── Rollback mode ────────────────────────────────────────────────────
if [ "$ROLLBACK" = true ]; then
    sep
    log "Rolling back to previous deployment..."

    for svc in "${SERVICES[@]}"; do
        case "$svc" in
            server-manager) install_dir="$SM_INSTALL"; service="$SM_SERVICE"; port=8080 ;;
            photo-curator)  install_dir="$PC_INSTALL"; service="$PC_SERVICE"; port=8081 ;;
        esac

        # Find the most recent backup
        latest_backup="$(ls -td "${BACKUP_DIR}/${svc}_"* 2>/dev/null | head -1)"
        if [ -z "$latest_backup" ]; then
            err "No backup found for ${svc} in ${BACKUP_DIR}"
            continue
        fi

        log "Restoring ${svc} from ${latest_backup}..."

        # Restore database snapshot
        if [ -f "${latest_backup}/data.tar.gz" ]; then
            systemctl stop "$service" || true
            tar -xzf "${latest_backup}/data.tar.gz" -C "$install_dir"
            log "Database restored for ${svc}"
        fi

        # Restore code
        if [ -f "${latest_backup}/git-sha" ]; then
            sha="$(cat "${latest_backup}/git-sha")"
            cd "$REPO_DIR"
            git checkout "$sha" -- "${svc}/"
            cp -r "${REPO_DIR}/${svc}/"* "$install_dir/"
            log "Code rolled back to ${sha:0:8}"
        fi

        # Reinstall deps and restart
        if [ -f "${install_dir}/venv/bin/pip" ]; then
            "${install_dir}/venv/bin/pip" install -q -r "${install_dir}/requirements.txt"
        fi
        systemctl start "$service"
        check_health "$port" "$svc"
    done

    log "Rollback complete"
    exit 0
fi

# ── Step 1: Pre-deploy backup ────────────────────────────────────────
sep
if [ "$SKIP_BACKUP" = true ]; then
    warn "Skipping pre-deploy backup (--no-backup)"
else
    log "Step 1/5: Backing up databases..."

    mkdir -p "$BACKUP_DIR"

    for svc in "${SERVICES[@]}"; do
        case "$svc" in
            server-manager) install_dir="$SM_INSTALL" ;;
            photo-curator)  install_dir="$PC_INSTALL" ;;
        esac

        backup_path="${BACKUP_DIR}/${svc}_${TIMESTAMP}"
        mkdir -p "$backup_path"

        # Save current git SHA for rollback
        cd "$REPO_DIR"
        git rev-parse HEAD > "${backup_path}/git-sha"

        # Snapshot the data directory
        if [ -d "${install_dir}/data" ]; then
            tar -czf "${backup_path}/data.tar.gz" -C "$install_dir" data/
            size=$(du -sh "${backup_path}/data.tar.gz" | cut -f1)
            log "  ${svc}: backed up data/ (${size})"
        else
            warn "  ${svc}: no data/ directory found — skipping"
        fi
    done

    # Clean up old deploy backups (keep last 10)
    for svc in "${SERVICES[@]}"; do
        ls -td "${BACKUP_DIR}/${svc}_"* 2>/dev/null | tail -n +11 | xargs rm -rf 2>/dev/null || true
    done

    log "Backups saved to ${BACKUP_DIR}"
fi

# ── Step 2: Pull latest code ─────────────────────────────────────────
sep
log "Step 2/5: Pulling latest code..."

cd "$REPO_DIR"

# Stash any local changes (e.g. config edits in the repo dir)
if ! git diff --quiet 2>/dev/null; then
    warn "Stashing local changes..."
    git stash
fi

target_branch="${BRANCH:-$(git symbolic-ref --short HEAD)}"
git fetch origin "$target_branch"
git checkout "$target_branch"
git pull origin "$target_branch"

new_sha="$(git rev-parse --short HEAD)"
log "Now at commit ${new_sha}"

# ── Step 3: Update dependencies ──────────────────────────────────────
sep
log "Step 3/5: Updating Python dependencies..."

for svc in "${SERVICES[@]}"; do
    case "$svc" in
        server-manager) install_dir="$SM_INSTALL" ;;
        photo-curator)  install_dir="$PC_INSTALL" ;;
    esac

    # Copy new source files
    cp -r "${REPO_DIR}/${svc}/"* "${install_dir}/"
    log "  ${svc}: files synced"

    # Install/update deps
    if [ -f "${install_dir}/venv/bin/pip" ]; then
        "${install_dir}/venv/bin/pip" install -q -r "${install_dir}/requirements.txt" 2>&1 \
            | tail -1 || true
        log "  ${svc}: dependencies updated"
    else
        warn "  ${svc}: no venv found at ${install_dir}/venv — skipping pip install"
    fi
done

# ── Step 4: Restart services (one at a time, with health checks) ─────
sep
log "Step 4/5: Restarting services..."

FAILED=()

for svc in "${SERVICES[@]}"; do
    case "$svc" in
        server-manager) service="$SM_SERVICE"; port=8080 ;;
        photo-curator)  service="$PC_SERVICE"; port=8081 ;;
    esac

    if ! service_active "$service"; then
        warn "  ${svc}: service was not running — starting it"
    fi

    log "  Restarting ${service}..."
    systemctl restart "$service"

    if check_health "$port" "$svc"; then
        log "  ${svc}: restart successful"
    else
        err "  ${svc}: FAILED health check after restart!"
        FAILED+=("$svc")
    fi

    echo ""
done

# ── Step 5: Verify migrations ────────────────────────────────────────
sep
log "Step 5/5: Checking for applied migrations..."

for svc in "${SERVICES[@]}"; do
    case "$svc" in
        server-manager) service="$SM_SERVICE" ;;
        photo-curator)  service="$PC_SERVICE" ;;
    esac

    migrations="$(journalctl -u "$service" --since "2 minutes ago" --no-pager 2>/dev/null \
        | grep -i "migration" || true)"

    if [ -n "$migrations" ]; then
        log "  ${svc}: migrations applied:"
        echo "$migrations" | sed 's/^/    /'
    else
        log "  ${svc}: no new migrations"
    fi
done

# ── Summary ──────────────────────────────────────────────────────────
sep
echo ""

if [ ${#FAILED[@]} -gt 0 ]; then
    err "Deploy completed with failures: ${FAILED[*]}"
    err "Run: sudo $0 --rollback ${FAILED[*]}"
    exit 1
else
    log "Deploy successful!"
    log "  Commit:   ${new_sha}"
    log "  Services: ${SERVICES[*]}"
    log "  Backup:   ${BACKUP_DIR}/*_${TIMESTAMP}"
    echo ""
    echo -e "  ${BLUE}Rollback if needed:${NC}  sudo $0 --rollback"
    echo ""
fi
