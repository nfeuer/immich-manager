#!/bin/bash
#
# Phase 1: Install Immich Server Manager
# Monitoring, backups, and system management
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/state-manager.sh"

echo "╔════════════════════════════════════════╗"
echo "║   Phase 1: Server Manager              ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Check if already installed
if check_phase_complete "phase1_server_manager"; then
    echo -e "${YELLOW}Server Manager already installed.${NC}"
    echo "Run with --force to reinstall"
    [ "$1" == "--force" ] || exit 0
fi

# 1. Create installation directory
echo "Creating installation directory..."
mark_step_start "phase1_server_manager" "create_directory"

sudo mkdir -p /opt/immich-server-manager
sudo chown immich-mgr:immich-mgr /opt/immich-server-manager

# Copy source files
sudo cp -r "$SCRIPT_DIR/../server-manager/"* /opt/immich-server-manager/
sudo chown -R immich-mgr:immich-mgr /opt/immich-server-manager

mark_step_complete "phase1_server_manager" "create_directory"
echo -e "${GREEN}✓${NC} Directory created"

# 2. Create Python virtual environment
echo ""
echo "Creating Python virtual environment..."
mark_step_start "phase1_server_manager" "create_venv"

cd /opt/immich-server-manager

if [ ! -d "venv" ]; then
    sudo -u immich-mgr python3 -m venv venv
fi

source venv/bin/activate

mark_step_complete "phase1_server_manager" "create_venv"
echo -e "${GREEN}✓${NC} Virtual environment created"

# 3. Install dependencies
echo ""
echo "Installing Python dependencies..."
mark_step_start "phase1_server_manager" "install_dependencies"

pip install --upgrade pip > /dev/null
pip install -r requirements.txt

# Install system dependencies
sudo apt-get update > /dev/null
sudo apt-get install -y smartmontools > /dev/null

mark_step_complete "phase1_server_manager" "install_dependencies"
echo -e "${GREEN}✓${NC} Dependencies installed"

# 4. Create configuration
echo ""
echo "Creating configuration..."
mark_step_start "phase1_server_manager" "configure"

if [ ! -f "config/config.yaml" ]; then
    cp config/config.yaml.example config/config.yaml

    # Auto-detect Immich path
    IMMICH_PATH="/opt/immich"
    if [ -d "$IMMICH_PATH" ]; then
        sed -i "s|/path/to/immich|$IMMICH_PATH|g" config/config.yaml
    fi

    echo -e "${YELLOW}⚠${NC} Configuration created at config/config.yaml"
    echo ""
    echo "IMPORTANT: Edit config/config.yaml and set:"
    echo "  1. Immich API key (generate in Immich: Admin → API Keys)"
    echo "  2. Email settings (for alerts)"
    echo "  3. Storage device paths"
    echo ""
    read -p "Press Enter when configuration is ready, or Ctrl+C to exit and configure later..."
fi

mark_step_complete "phase1_server_manager" "configure"
echo -e "${GREEN}✓${NC} Configuration ready"

# 5. Initialize database
echo ""
echo "Initializing database..."
mark_step_start "phase1_server_manager" "init_database"

sudo -u immich-mgr mkdir -p data
sudo -u immich-mgr venv/bin/python -c "from src.database import Database; Database('data/server-manager.db')"

mark_step_complete "phase1_server_manager" "init_database"
echo -e "${GREEN}✓${NC} Database initialized"

# 6. Create systemd service
echo ""
echo "Installing systemd service..."
mark_step_start "phase1_server_manager" "install_systemd"

sudo cp "$SCRIPT_DIR/systemd/immich-server-manager.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable immich-server-manager

mark_step_complete "phase1_server_manager" "install_systemd"
echo -e "${GREEN}✓${NC} Service installed"

# 7. Start service
echo ""
echo "Starting Server Manager..."
mark_step_start "phase1_server_manager" "start_service"

sudo systemctl start immich-server-manager
sleep 5

mark_step_complete "phase1_server_manager" "start_service"
echo -e "${GREEN}✓${NC} Service started"

# 8. Verify installation
echo ""
echo "Verifying installation..."
mark_step_start "phase1_server_manager" "verify"

if curl -s http://localhost:8080/health | grep -q "ok"; then
    mark_step_complete "phase1_server_manager" "verify"
    echo -e "${GREEN}✓${NC} Health check passed"
else
    mark_step_failed "phase1_server_manager" "verify" "Health check failed"
    echo -e "${RED}✗${NC} Health check failed"
    echo "Check logs: sudo journalctl -u immich-server-manager -n 50"
    exit 1
fi

# 9. Mark phase complete
mark_phase_complete "phase1_server_manager"

echo ""
echo "╔════════════════════════════════════════╗"
echo "║   Server Manager Installed! 🎉         ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "Dashboard:  http://localhost:8080"
echo "            http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "Logs:       sudo journalctl -u immich-server-manager -f"
echo "Status:     sudo systemctl status immich-server-manager"
echo "Config:     /opt/immich-server-manager/config/config.yaml"
echo ""
echo "Next steps:"
echo "  1. Open dashboard and verify metrics are showing"
echo "  2. Test email alerts: curl -X POST http://localhost:8080/api/test-alert"
echo "  3. Check that backups are scheduled"
echo ""
if [ -f "$SCRIPT_DIR/20-install-photo-curator.sh" ]; then
    echo "  4. Install Photo Curator: $SCRIPT_DIR/20-install-photo-curator.sh"
fi
echo ""
