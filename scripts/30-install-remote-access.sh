#!/bin/bash
#
# Phase 3: Install Remote Access (Cloudflare Tunnel)
# Secure remote access without port forwarding
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/state-manager.sh"

echo "╔════════════════════════════════════════╗"
echo "║   Phase 3: Remote Access               ║"
echo "╚════════════════════════════════════════╝"
echo ""

if check_phase_complete "phase3_remote_access"; then
    echo -e "${YELLOW}Remote access already configured.${NC}"
    echo "Run with --force to reconfigure"
    [ "$1" == "--force" ] || exit 0
fi

# Prerequisites check
echo "Prerequisites Checklist:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "You need:"
echo "  1. A domain name (e.g., mydomain.com)"
echo "  2. Cloudflare account (free)"
echo "  3. Domain added to Cloudflare"
echo "  4. Nameservers updated to Cloudflare"
echo ""

mark_step_start "phase3_remote_access" "check_prerequisites"

read -p "Have you completed all prerequisites? (yes/no): " prereqs_done

if [ "$prereqs_done" != "yes" ]; then
    echo ""
    echo -e "${BLUE}Setup Instructions:${NC}"
    echo ""
    echo "1. Buy a domain (~\$12/year):"
    echo "   • Porkbun.com, Namecheap.com, or any registrar"
    echo ""
    echo "2. Create Cloudflare account (free):"
    echo "   • Visit: https://dash.cloudflare.com/sign-up"
    echo ""
    echo "3. Add your domain to Cloudflare:"
    echo "   • Dashboard → Add Site → Enter domain → Follow wizard"
    echo ""
    echo "4. Update nameservers at registrar:"
    echo "   • Cloudflare will show you the nameservers"
    echo "   • Update at your domain registrar"
    echo "   • Wait 15 minutes to 24 hours for propagation"
    echo ""
    echo "Run this script again when ready."
    exit 0
fi

mark_step_complete "phase3_remote_access" "check_prerequisites"

# Get domain
mark_step_start "phase3_remote_access" "get_domain"
echo ""
read -p "Enter your domain name (e.g., mydomain.com): " DOMAIN

if ! [[ "$DOMAIN" =~ ^[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}$ ]]; then
    echo -e "${RED}✗${NC} Invalid domain format"
    exit 1
fi

echo "Domain: $DOMAIN"
read -p "Is this correct? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi

# Save domain
sudo mkdir -p /opt/immich-ecosystem/config
echo "domain: $DOMAIN" | sudo tee /opt/immich-ecosystem/config/domain.yaml > /dev/null

mark_step_complete "phase3_remote_access" "get_domain"
echo -e "${GREEN}✓${NC} Domain configured"

# Install cloudflared
echo ""
echo "Installing cloudflared..."
mark_step_start "phase3_remote_access" "install_cloudflared"

if ! command -v cloudflared &> /dev/null; then
    # Add Cloudflare GPG key
    sudo mkdir -p --mode=0755 /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null

    # Add repository
    echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflared.list

    # Install
    sudo apt-get update > /dev/null
    sudo apt-get install -y cloudflared

    echo -e "${GREEN}✓${NC} cloudflared installed"
else
    echo -e "${GREEN}✓${NC} cloudflared already installed"
fi

mark_step_complete "phase3_remote_access" "install_cloudflared"

# Authenticate
echo ""
echo "Authenticating with Cloudflare..."
echo -e "${YELLOW}⚠${NC} A browser window will open. Please login and authorize."
echo ""
mark_step_start "phase3_remote_access" "authenticate"

read -p "Press Enter to continue..."

cloudflared tunnel login

if [ $? -eq 0 ]; then
    mark_step_complete "phase3_remote_access" "authenticate"
    echo -e "${GREEN}✓${NC} Authentication successful"
else
    mark_step_failed "phase3_remote_access" "authenticate" "Login failed"
    echo -e "${RED}✗${NC} Authentication failed"
    exit 1
fi

# Create tunnel
echo ""
echo "Creating tunnel..."
mark_step_start "phase3_remote_access" "create_tunnel"

TUNNEL_NAME="immich-tunnel"

if cloudflared tunnel list | grep -q "$TUNNEL_NAME"; then
    echo -e "${YELLOW}⚠${NC} Tunnel '$TUNNEL_NAME' already exists"
    TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
else
    cloudflared tunnel create "$TUNNEL_NAME"
    TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
    echo -e "${GREEN}✓${NC} Tunnel created"
fi

# Save tunnel ID
echo "tunnel_id: $TUNNEL_ID" | sudo tee -a /opt/immich-ecosystem/config/domain.yaml > /dev/null

mark_step_complete "phase3_remote_access" "create_tunnel"

# Configure routing
echo ""
echo "Configuring tunnel routing..."
mark_step_start "phase3_remote_access" "configure_routing"

sudo mkdir -p /etc/cloudflared

# Create config
sudo tee /etc/cloudflared/config.yml > /dev/null <<EOF
tunnel: $TUNNEL_ID
credentials-file: /root/.cloudflared/$TUNNEL_ID.json

ingress:
  # Main Immich application
  - hostname: $DOMAIN
    service: http://localhost:2283

  # Immich subdomain
  - hostname: immich.$DOMAIN
    service: http://localhost:2283

  # Server Manager
  - hostname: $DOMAIN
    path: /monitor/*
    service: http://localhost:8080

  # Photo Curator
  - hostname: $DOMAIN
    path: /curator/*
    service: http://localhost:8081

  # Catch-all
  - service: http_status:404
EOF

# Copy credentials for root
if [ -f "$HOME/.cloudflared/$TUNNEL_ID.json" ]; then
    sudo mkdir -p /root/.cloudflared
    sudo cp "$HOME/.cloudflared/$TUNNEL_ID.json" /root/.cloudflared/
fi

mark_step_complete "phase3_remote_access" "configure_routing"
echo -e "${GREEN}✓${NC} Routing configured"

# Create DNS records
echo ""
echo "Creating DNS records..."
mark_step_start "phase3_remote_access" "create_dns"

cloudflared tunnel route dns "$TUNNEL_NAME" "$DOMAIN" 2>/dev/null || true
cloudflared tunnel route dns "$TUNNEL_NAME" "immich.$DOMAIN" 2>/dev/null || true

mark_step_complete "phase3_remote_access" "create_dns"
echo -e "${GREEN}✓${NC} DNS records created"

# Install service
echo ""
echo "Installing systemd service..."
mark_step_start "phase3_remote_access" "install_service"

sudo cloudflared service install
sudo systemctl enable cloudflared

mark_step_complete "phase3_remote_access" "install_service"
echo -e "${GREEN}✓${NC} Service installed"

# Start tunnel
echo ""
echo "Starting tunnel..."
mark_step_start "phase3_remote_access" "start_tunnel"

sudo systemctl start cloudflared
sleep 5

if sudo systemctl is-active --quiet cloudflared; then
    mark_step_complete "phase3_remote_access" "start_tunnel"
    echo -e "${GREEN}✓${NC} Tunnel is running"
else
    mark_step_failed "phase3_remote_access" "start_tunnel" "Service failed to start"
    echo -e "${RED}✗${NC} Tunnel failed to start"
    echo "Check logs: sudo journalctl -u cloudflared -n 50"
    exit 1
fi

# Mark complete
mark_phase_complete "phase3_remote_access"

echo ""
echo "╔════════════════════════════════════════╗"
echo "║   Remote Access Configured! 🎉         ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "Your services are accessible at:"
echo "  • Immich:         https://$DOMAIN"
echo "  • Immich:         https://immich.$DOMAIN"
echo "  • Server Manager: https://$DOMAIN/monitor/"
echo "  • Photo Curator:  https://$DOMAIN/curator/"
echo ""
echo -e "${YELLOW}⚠ Note: DNS propagation may take 5-60 minutes${NC}"
echo ""
echo "Status:  sudo systemctl status cloudflared"
echo "Logs:    sudo journalctl -u cloudflared -f"
echo "Config:  /etc/cloudflared/config.yml"
echo ""
echo "Next steps:"
echo "  1. Wait a few minutes for DNS propagation"
echo "  2. Test access from your phone (outside home wifi)"
echo "  3. Proceed to security hardening"
echo ""
if [ -f "$SCRIPT_DIR/40-security-hardening.sh" ]; then
    echo "  Run: $SCRIPT_DIR/40-security-hardening.sh"
fi
echo ""

# Save summary
sudo tee /opt/immich-ecosystem/remote-access-info.txt > /dev/null <<EOF
Remote Access Configuration
============================
Installed: $(date)

URLs:
- Immich:         https://$DOMAIN
- Immich:         https://immich.$DOMAIN
- Server Manager: https://$DOMAIN/monitor/
- Photo Curator:  https://$DOMAIN/curator/

Tunnel ID: $TUNNEL_ID
Tunnel Name: $TUNNEL_NAME
Config: /etc/cloudflared/config.yml
Credentials: /root/.cloudflared/$TUNNEL_ID.json

Management:
- Status: sudo systemctl status cloudflared
- Restart: sudo systemctl restart cloudflared
- Logs: sudo journalctl -u cloudflared -f
- Dashboard: https://dash.cloudflare.com/

Troubleshooting:
- Test DNS: dig $DOMAIN
- Test connection: curl https://$DOMAIN
- Check tunnel: cloudflared tunnel info $TUNNEL_NAME
EOF
