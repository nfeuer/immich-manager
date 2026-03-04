#!/bin/bash
#
# Phase 2: Install Photo Curator Assistant
# AI-powered photo curation
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/state-manager.sh"

echo "╔════════════════════════════════════════╗"
echo "║   Phase 2: Photo Curator               ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Check if already installed
if check_phase_complete "phase2_photo_curator"; then
    echo -e "${YELLOW}Photo Curator already installed.${NC}"
    echo "Run with --force to reinstall"
    [ "$1" == "--force" ] || exit 0
fi

# 1. Create installation directory
echo "Creating installation directory..."
mark_step_start "phase2_photo_curator" "create_directory"

sudo mkdir -p /opt/photo-curator
sudo chown immich-mgr:immich-mgr /opt/photo-curator

sudo cp -r "$SCRIPT_DIR/../photo-curator/"* /opt/photo-curator/
sudo chown -R immich-mgr:immich-mgr /opt/photo-curator

mark_step_complete "phase2_photo_curator" "create_directory"
echo -e "${GREEN}✓${NC} Directory created"

# 2. Create Python virtual environment
echo ""
echo "Creating Python virtual environment..."
mark_step_start "phase2_photo_curator" "create_venv"

cd /opt/photo-curator

if [ ! -d "venv" ]; then
    sudo -u immich-mgr python3 -m venv venv
fi

source venv/bin/activate

mark_step_complete "phase2_photo_curator" "create_venv"
echo -e "${GREEN}✓${NC} Virtual environment created"

# 3. Install dependencies
echo ""
echo "Installing Python dependencies (this may take a while)..."
mark_step_start "phase2_photo_curator" "install_dependencies"

pip install --upgrade pip > /dev/null
pip install -r requirements.txt

# Install system dependencies for OpenCV
sudo apt-get update > /dev/null
sudo apt-get install -y libgl1-mesa-glx libglib2.0-0 > /dev/null

mark_step_complete "phase2_photo_curator" "install_dependencies"
echo -e "${GREEN}✓${NC} Dependencies installed"

# 4. Create configuration
echo ""
echo "Creating configuration..."
mark_step_start "phase2_photo_curator" "configure"

if [ ! -f "config/config.yaml" ]; then
    cp config/config.yaml.example config/config.yaml

    echo -e "${YELLOW}⚠${NC} Configuration created at config/config.yaml"
    echo "You may want to edit it to customize settings"
fi

mark_step_complete "phase2_photo_curator" "configure"
echo -e "${GREEN}✓${NC} Configuration ready"

# 5. Create systemd service
echo ""
echo "Installing systemd service..."
mark_step_start "phase2_photo_curator" "install_systemd"

sudo cp "$SCRIPT_DIR/systemd/photo-curator.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable photo-curator

mark_step_complete "phase2_photo_curator" "install_systemd"
echo -e "${GREEN}✓${NC} Service installed"

# 6. Start service
echo ""
echo "Starting Photo Curator..."
mark_step_start "phase2_photo_curator" "start_service"

sudo systemctl start photo-curator
sleep 5

mark_step_complete "phase2_photo_curator" "start_service"
echo -e "${GREEN}✓${NC} Service started"

# 7. Verify installation
echo ""
echo "Verifying installation..."
mark_step_start "phase2_photo_curator" "verify"

if curl -s http://localhost:8081/health | grep -q "ok"; then
    mark_step_complete "phase2_photo_curator" "verify"
    echo -e "${GREEN}✓${NC} Health check passed"
else
    mark_step_failed "phase2_photo_curator" "verify" "Health check failed"
    echo -e "${RED}✗${NC} Health check failed"
    echo "Check logs: sudo journalctl -u photo-curator -n 50"
    exit 1
fi

# 8. Mark phase complete
mark_phase_complete "phase2_photo_curator"

echo ""
echo "╔════════════════════════════════════════╗"
echo "║   Photo Curator Installed! 🎉          ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "Web UI:     http://localhost:8081"
echo "            http://$(hostname -I | awk '{print $1}'):8081"
echo ""
echo "Logs:       sudo journalctl -u photo-curator -f"
echo "Status:     sudo systemctl status photo-curator"
echo "Config:     /opt/photo-curator/config/config.yaml"
echo ""
echo "Next steps:"
echo "  1. Open web UI to verify it's working"
echo "  2. Connect to Immich by setting API key in config"
echo ""
if [ -f "$SCRIPT_DIR/30-install-remote-access.sh" ]; then
    echo "  3. Install Remote Access: $SCRIPT_DIR/30-install-remote-access.sh"
fi
echo ""
