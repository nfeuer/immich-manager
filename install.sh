#!/bin/bash
#
# Master Installation Script for Immich Ecosystem
# Installs all components in sequence
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/scripts/lib/state-manager.sh"

echo "╔════════════════════════════════════════╗"
echo "║   Immich Ecosystem Installer v1.0.0   ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}✗ Do not run this script as root${NC}"
    echo "Run as normal user with sudo access"
    exit 1
fi

# Show what will be installed
echo "This installer will set up:"
echo ""
echo "  📊 Immich Server Manager"
echo "     • Disk health monitoring (SMART)"
echo "     • Automated backups (daily)"
echo "     • Update management"
echo "     • System metrics & alerts"
echo "     • Web dashboard"
echo ""
echo "  📸 Photo Curator Assistant"
echo "     • AI photo quality scoring"
echo "     • Monthly curation reminders"
echo "     • Duplicate detection"
echo "     • Year-end collaboration"
echo ""
echo "  🌐 Remote Access (Cloudflare Tunnel)"
echo "     • Secure access from anywhere"
echo "     • No port forwarding needed"
echo "     • Automatic HTTPS"
echo "     • DDoS protection"
echo ""
echo "  🔒 Security Hardening"
echo "     • fail2ban (brute force protection)"
echo "     • UFW firewall"
echo "     • Security monitoring"
echo "     • 2FA setup guidance"
echo ""
echo "Installation time: ~30-60 minutes"
echo "Cost: \$10-15/year (domain name only)"
echo ""

read -p "Continue with installation? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Installation cancelled"
    exit 0
fi

# Phase 0: Prerequisites
echo ""
echo "═══════════════════════════════════════════"
echo " Phase 0: Checking Prerequisites"
echo "═══════════════════════════════════════════"
echo ""

if check_phase_complete "phase1_server_manager"; then
    echo "Skipping prerequisites check (Phase 1 already complete)"
else
    $SCRIPT_DIR/scripts/00-check-prerequisites.sh

    if [ $? -ne 0 ]; then
        echo ""
        echo -e "${RED}✗ Prerequisites check failed${NC}"
        echo "Please fix the issues above and rerun this script"
        exit 1
    fi
fi

# Phase 1: Server Manager
echo ""
echo "═══════════════════════════════════════════"
echo " Phase 1: Installing Server Manager"
echo "═══════════════════════════════════════════"
echo ""

$SCRIPT_DIR/scripts/10-install-server-manager.sh

if [ $? -ne 0 ]; then
    echo ""
    echo -e "${RED}✗ Server Manager installation failed${NC}"
    exit 1
fi

# Phase 2: Photo Curator
echo ""
echo "═══════════════════════════════════════════"
echo " Phase 2: Installing Photo Curator"
echo "═══════════════════════════════════════════"
echo ""

$SCRIPT_DIR/scripts/20-install-photo-curator.sh

if [ $? -ne 0 ]; then
    echo ""
    echo -e "${RED}✗ Photo Curator installation failed${NC}"
    exit 1
fi

# Phase 3: Remote Access
echo ""
echo "═══════════════════════════════════════════"
echo " Phase 3: Setting up Remote Access"
echo "═══════════════════════════════════════════"
echo ""
echo "Remote access requires a domain name and Cloudflare account."
echo ""
read -p "Install remote access now? (yes/skip): " install_remote

if [ "$install_remote" == "yes" ]; then
    $SCRIPT_DIR/scripts/30-install-remote-access.sh

    if [ $? -ne 0 ]; then
        echo ""
        echo -e "${YELLOW}⚠ Remote access setup incomplete${NC}"
        echo "You can complete it later by running:"
        echo "  $SCRIPT_DIR/scripts/30-install-remote-access.sh"
    fi
else
    echo "Skipping remote access (can install later)"
fi

# Phase 4: Security Hardening
echo ""
echo "═══════════════════════════════════════════"
echo " Phase 4: Security Hardening"
echo "═══════════════════════════════════════════"
echo ""

$SCRIPT_DIR/scripts/40-security-hardening.sh

if [ $? -ne 0 ]; then
    echo ""
    echo -e "${YELLOW}⚠ Security hardening incomplete${NC}"
fi

# Phase 5: Testing
echo ""
echo "═══════════════════════════════════════════"
echo " Phase 5: Testing Installation"
echo "═══════════════════════════════════════════"
echo ""

$SCRIPT_DIR/scripts/50-test-installation.sh

TEST_RESULT=$?

echo ""
echo "╔════════════════════════════════════════╗"
echo "║   Installation Complete!               ║"
echo "╚════════════════════════════════════════╝"
echo ""

if [ $TEST_RESULT -eq 0 ]; then
    echo -e "${GREEN}🎉 All components installed and tested successfully!${NC}"
else
    echo -e "${YELLOW}⚠ Installation completed with some warnings${NC}"
    echo "Review the test output above"
fi

echo ""
echo "Access your services:"
echo "  • Server Manager:  http://localhost:8080"
echo "  • Photo Curator:   http://localhost:8081"
echo "  • Immich:          http://localhost:2283"

if [ -f /opt/immich-ecosystem/config/domain.yaml ]; then
    DOMAIN=$(grep "domain:" /opt/immich-ecosystem/config/domain.yaml 2>/dev/null | cut -d: -f2 | tr -d ' ')
    if [ -n "$DOMAIN" ]; then
        echo ""
        echo "Remote access:"
        echo "  • https://$DOMAIN"
        echo "  • https://immich.$DOMAIN"
    fi
fi

echo ""
echo "Important next steps:"
echo ""
echo "  1. 🔒 Enable 2FA for all Immich users (CRITICAL!)"
echo "     Login to Immich → Admin → Users → Enable 2FA"
echo ""
echo "  2. 📧 Configure email alerts"
echo "     Edit: /opt/immich-server-manager/config/config.yaml"
echo "     Test: curl -X POST http://localhost:8080/api/test-alert"
echo ""
echo "  3. ✅ Review security checklist"
echo "     View: /opt/immich-ecosystem/security-checklist.txt"
echo ""
echo "  4. 📱 Test mobile app access"
echo "     Install Immich app and connect"
echo ""
echo "Useful commands:"
echo "  • Health check:      $SCRIPT_DIR/scripts/health-check.sh"
echo "  • View logs:         sudo journalctl -u immich-server-manager -f"
echo "  • Security monitor:  /opt/immich-ecosystem/scripts/security-monitor.sh"
echo "  • Run full test:     $SCRIPT_DIR/scripts/50-test-installation.sh"
echo ""
echo "Documentation:"
echo "  • README:            $SCRIPT_DIR/README.md"
echo "  • Security:          /opt/immich-ecosystem/security-checklist.txt"
echo "  • Remote access:     /opt/immich-ecosystem/remote-access-info.txt"
echo ""
echo "Need help? Check the documentation or visit:"
echo "  • Immich Discord: https://discord.immich.app"
echo "  • Immich Docs:    https://immich.app/docs"
echo ""
