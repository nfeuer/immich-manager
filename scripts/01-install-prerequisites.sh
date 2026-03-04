#!/bin/bash
#
# Phase 0b: Auto-install Prerequisites for Immich Ecosystem
# Installs all required system packages on a clean Ubuntu/Debian system
#
# https://houseoffeuer.com  |  Discord: House of Feuer
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "╔════════════════════════════════════════╗"
echo "║   Auto-install Prerequisites           ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Must not be root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}✗ Do not run as root.${NC}"
    echo "Run as a normal user with sudo access."
    exit 1
fi

# Must be Ubuntu/Debian
if [ -f /etc/os-release ]; then
    source /etc/os-release
    if [[ "$ID" != "ubuntu" ]] && [[ "$ID" != "debian" ]]; then
        echo -e "${YELLOW}⚠ This script is designed for Ubuntu/Debian.${NC}"
        echo "   Detected: $PRETTY_NAME"
        read -p "Continue anyway? (yes/no): " cont
        [ "$cont" == "yes" ] || exit 0
    else
        echo -e "${GREEN}✓${NC} Detected: $PRETTY_NAME"
    fi
else
    echo -e "${RED}✗ Cannot detect operating system.${NC}"
    exit 1
fi

echo ""
echo "This will install the following if missing:"
echo "  - Python 3 + pip + venv + dev headers"
echo "  - Docker CE + Docker Compose plugin"
echo "  - build-essential (for compiling Python packages)"
echo "  - curl, jq, git, smartmontools"
echo "  - UFW firewall, fail2ban"
echo ""
read -p "Continue? (yes/no): " confirm
[ "$confirm" == "yes" ] || exit 0

echo ""

# ──────────────────────────────────────────────
# 1. Update package lists
# ──────────────────────────────────────────────
echo "Updating package lists..."
sudo apt-get update -qq
echo -e "${GREEN}✓${NC} Package lists updated"

# ──────────────────────────────────────────────
# 2. Core system packages
# ──────────────────────────────────────────────
echo ""
echo "Installing core system packages..."
sudo apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common \
    git \
    jq \
    > /dev/null 2>&1
echo -e "${GREEN}✓${NC} Core packages installed"

# ──────────────────────────────────────────────
# 3. Python 3 + build dependencies
# ──────────────────────────────────────────────
echo ""
echo "Installing Python 3 and build tools..."
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    libssl-dev \
    libffi-dev \
    > /dev/null 2>&1

PYTHON_VERSION=$(python3 --version 2>/dev/null | cut -d' ' -f2)
echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION installed"

# ──────────────────────────────────────────────
# 4. Docker CE
# ──────────────────────────────────────────────
echo ""
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version | cut -d' ' -f3 | tr -d ',')
    echo -e "${GREEN}✓${NC} Docker already installed ($DOCKER_VERSION)"
else
    echo "Installing Docker CE..."

    # Remove any old/conflicting packages
    for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do
        sudo apt-get remove -y $pkg > /dev/null 2>&1 || true
    done

    # Add Docker official GPG key
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/$ID/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    # Add Docker repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$ID \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -qq
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin > /dev/null 2>&1

    # Enable and start Docker
    sudo systemctl enable docker
    sudo systemctl start docker

    DOCKER_VERSION=$(docker --version | cut -d' ' -f3 | tr -d ',')
    echo -e "${GREEN}✓${NC} Docker $DOCKER_VERSION installed"
fi

# Add current user to docker group
if ! groups "$USER" | grep -q docker; then
    echo "Adding $USER to docker group..."
    sudo usermod -aG docker "$USER"
    echo -e "${GREEN}✓${NC} Added $USER to docker group"
    echo -e "${YELLOW}⚠${NC} You may need to log out and back in for group changes to take effect"
    NEEDS_RELOGIN=true
fi

# ──────────────────────────────────────────────
# 5. Monitoring and security tools
# ──────────────────────────────────────────────
echo ""
echo "Installing monitoring and security tools..."
sudo apt-get install -y \
    smartmontools \
    ufw \
    fail2ban \
    > /dev/null 2>&1
echo -e "${GREEN}✓${NC} smartmontools, UFW, fail2ban installed"

# ──────────────────────────────────────────────
# 6. OpenCV system dependencies (for Photo Curator)
# ──────────────────────────────────────────────
echo ""
echo "Installing OpenCV dependencies..."
sudo apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    > /dev/null 2>&1
echo -e "${GREEN}✓${NC} OpenCV dependencies installed"

# ──────────────────────────────────────────────
# 7. Create dedicated service user
# ──────────────────────────────────────────────
echo ""
if id "immich-mgr" &>/dev/null; then
    echo -e "${GREEN}✓${NC} Service user 'immich-mgr' already exists"
else
    echo "Creating dedicated service user..."
    sudo useradd --system --shell /usr/sbin/nologin --home-dir /opt/immich-server-manager --user-group immich-mgr
    # Add to docker group so services can manage containers
    sudo usermod -aG docker immich-mgr
    echo -e "${GREEN}✓${NC} Service user 'immich-mgr' created"
fi

# ──────────────────────────────────────────────
# 8. Create directory structure
# ──────────────────────────────────────────────
echo ""
echo "Creating directory structure..."

sudo mkdir -p /opt/immich-server-manager/data
sudo mkdir -p /opt/photo-curator/data
sudo mkdir -p /opt/immich-ecosystem/config
sudo mkdir -p /opt/immich-ecosystem/scripts
sudo mkdir -p /etc/immich-ecosystem
sudo mkdir -p /var/log/immich-ecosystem

# Set ownership
sudo chown -R immich-mgr:immich-mgr /opt/immich-server-manager
sudo chown -R immich-mgr:immich-mgr /opt/photo-curator
sudo chown -R immich-mgr:immich-mgr /var/log/immich-ecosystem

# Secrets directory: only root and service user can read
sudo chown root:immich-mgr /etc/immich-ecosystem
sudo chmod 750 /etc/immich-ecosystem

echo -e "${GREEN}✓${NC} Directories created"

# ──────────────────────────────────────────────
# 9. Create secrets environment file template
# ──────────────────────────────────────────────
echo ""
if [ ! -f /etc/immich-ecosystem/secrets.env ]; then
    echo "Creating secrets file template..."
    sudo tee /etc/immich-ecosystem/secrets.env > /dev/null <<'EOF'
# Immich Ecosystem Secrets
# This file is read by systemd services via EnvironmentFile=
# Permissions: 640 root:immich-mgr
#
# IMPORTANT: Fill in your actual values below.

# Immich API key (generate in Immich: Admin → API Keys)
IMMICH_API_KEY=

# SMTP email settings (for alerts and notifications)
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=

# Discord webhook URL (optional)
DISCORD_WEBHOOK_URL=

# AWS S3 (optional, for offsite backup)
# AWS_ACCESS_KEY_ID=
# AWS_SECRET_ACCESS_KEY=
EOF
    sudo chown root:immich-mgr /etc/immich-ecosystem/secrets.env
    sudo chmod 640 /etc/immich-ecosystem/secrets.env
    echo -e "${GREEN}✓${NC} Secrets file created at /etc/immich-ecosystem/secrets.env"
    echo -e "${YELLOW}⚠${NC} Edit this file to add your credentials before starting services"
else
    echo -e "${GREEN}✓${NC} Secrets file already exists"
fi

# ──────────────────────────────────────────────
# 10. Install logrotate configuration
# ──────────────────────────────────────────────
echo ""
echo "Configuring log rotation..."
sudo tee /etc/logrotate.d/immich-ecosystem > /dev/null <<'EOF'
/var/log/immich-ecosystem/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 immich-mgr immich-mgr
    sharedscripts
    postrotate
        systemctl kill -s HUP immich-server-manager 2>/dev/null || true
        systemctl kill -s HUP photo-curator 2>/dev/null || true
    endscript
}
EOF
echo -e "${GREEN}✓${NC} Log rotation configured"

# ──────────────────────────────────────────────
# 11. Persistent install state directory
# ──────────────────────────────────────────────
echo ""
echo "Setting up persistent state tracking..."
sudo mkdir -p /var/lib/immich-ecosystem
sudo chown "$USER:$USER" /var/lib/immich-ecosystem
echo -e "${GREEN}✓${NC} State directory created"

# ──────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────
echo ""
echo "╔════════════════════════════════════════╗"
echo "║   Prerequisites Installed!             ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "Installed:"
echo "  ✓ Python $PYTHON_VERSION + pip + venv + dev headers"
echo "  ✓ Docker CE + Compose plugin"
echo "  ✓ build-essential, curl, jq, git"
echo "  ✓ smartmontools, UFW, fail2ban"
echo "  ✓ OpenCV system libraries"
echo "  ✓ Service user 'immich-mgr'"
echo "  ✓ Secrets file: /etc/immich-ecosystem/secrets.env"
echo "  ✓ Log rotation configured"
echo ""

if [ "${NEEDS_RELOGIN:-false}" = true ]; then
    echo -e "${YELLOW}IMPORTANT: Log out and log back in for Docker group changes.${NC}"
    echo "Then re-run: ./install.sh"
    echo ""
fi

echo "Next step:"
echo "  1. Edit secrets:  sudo nano /etc/immich-ecosystem/secrets.env"
echo "  2. Run installer: ./install.sh"
echo ""
