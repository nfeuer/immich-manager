#!/bin/bash
#
# Phase 4: Security Hardening
# Setup fail2ban, UFW firewall, and security monitoring
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/state-manager.sh"

echo "╔════════════════════════════════════════╗"
echo "║   Phase 4: Security Hardening          ║"
echo "╚════════════════════════════════════════╝"
echo ""

if check_phase_complete "phase4_security"; then
    echo -e "${YELLOW}Security already configured.${NC}"
    [ "$1" == "--force" ] || exit 0
fi

# Install fail2ban
echo "Installing fail2ban..."
mark_step_start "phase4_security" "install_fail2ban"

if ! command -v fail2ban-client &> /dev/null; then
    sudo apt-get update > /dev/null
    sudo apt-get install -y fail2ban
    echo -e "${GREEN}✓${NC} fail2ban installed"
else
    echo -e "${GREEN}✓${NC} fail2ban already installed"
fi

mark_step_complete "phase4_security" "install_fail2ban"

# Configure fail2ban
echo ""
echo "Configuring fail2ban..."
mark_step_start "phase4_security" "configure_fail2ban"

sudo tee /etc/fail2ban/jail.d/immich.conf > /dev/null <<'EOF'
[DEFAULT]
bantime = 3600
findtime = 600

[sshd]
enabled = true
port = 2222
maxretry = 5
logpath = %(sshd_log)s
backend = %(sshd_backend)s
EOF

sudo systemctl restart fail2ban
sudo systemctl enable fail2ban

mark_step_complete "phase4_security" "configure_fail2ban"
echo -e "${GREEN}✓${NC} fail2ban configured"

# Setup UFW firewall
echo ""
echo "Configuring UFW firewall..."
mark_step_start "phase4_security" "configure_ufw"

if ! sudo ufw status | grep -q "Status: active"; then
    # Reset to defaults
    sudo ufw --force reset > /dev/null

    # Default policies
    sudo ufw default deny incoming
    sudo ufw default allow outgoing

    # Allow SSH on non-standard port (important!)
    sudo ufw allow 2222/tcp

    # Allow local network
    LOCAL_SUBNET=$(ip route | grep default | awk '{print $3}' | cut -d. -f1-3).0/24
    sudo ufw allow from $LOCAL_SUBNET

    # Enable firewall
    sudo ufw --force enable

    echo -e "${GREEN}✓${NC} UFW firewall configured"
else
    echo -e "${GREEN}✓${NC} UFW already active"
fi

mark_step_complete "phase4_security" "configure_ufw"

# 2FA reminder
echo ""
echo "╔════════════════════════════════════════╗"
echo "║   IMPORTANT: Enable 2FA                ║"
echo "╚════════════════════════════════════════╝"
echo ""
mark_step_start "phase4_security" "2fa_reminder"

echo "You MUST enable Two-Factor Authentication (2FA) for all Immich users:"
echo ""
echo "1. Login to Immich as admin"
echo "2. Go to Admin → Users"
echo "3. For each user:"
echo "   • Click user → Settings"
echo "   • Enable 2FA"
echo "   • User will be prompted to set up on next login"
echo ""
echo "Each user should:"
echo "  • Install an authenticator app (Google Authenticator, Authy, etc.)"
echo "  • Scan the QR code"
echo "  • Save recovery codes in a safe place"
echo ""

read -p "Have you enabled 2FA for all users? (yes/no): " twofa_done

if [ "$twofa_done" != "yes" ]; then
    echo ""
    echo -e "${YELLOW}⚠${NC} Remember to enable 2FA as soon as possible!"
    echo "This is critical for security when accessing remotely."
fi

mark_step_complete "phase4_security" "2fa_reminder"

# Create security monitoring script
echo ""
echo "Setting up security monitoring..."
mark_step_start "phase4_security" "setup_monitoring"

sudo mkdir -p /opt/immich-ecosystem/scripts

sudo tee /opt/immich-ecosystem/scripts/security-monitor.sh > /dev/null <<'EOF'
#!/bin/bash
#
# Security monitoring script
#

echo "Security Status Report"
echo "======================"
echo "Generated: $(date)"
echo ""

# fail2ban status
echo "fail2ban Bans:"
echo "━━━━━━━━━━━━━━"
sudo fail2ban-client status | grep "Jail list" || echo "No jails configured"
echo ""

# Recent SSH attempts
echo "Recent SSH Attempts (last 24h):"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sudo journalctl -u ssh --since "24 hours ago" | grep -i "failed\|invalid" | tail -10 || echo "No failed attempts"
echo ""

# UFW status
echo "Firewall Status:"
echo "━━━━━━━━━━━━━━━━"
sudo ufw status
echo ""

# Cloudflare tunnel status
if systemctl is-active --quiet cloudflared; then
    echo "✓ Cloudflare Tunnel: Running"
else
    echo "✗ Cloudflare Tunnel: Not running"
fi
echo ""

# Docker status
echo "Docker Containers:"
echo "━━━━━━━━━━━━━━━━━━"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep immich || echo "No Immich containers running"
EOF

sudo chmod +x /opt/immich-ecosystem/scripts/security-monitor.sh

mark_step_complete "phase4_security" "setup_monitoring"
echo -e "${GREEN}✓${NC} Security monitoring configured"

# Create security checklist
echo ""
echo "Creating security checklist..."
mark_step_start "phase4_security" "create_checklist"

sudo tee /opt/immich-ecosystem/security-checklist.txt > /dev/null <<'EOF'
Security Checklist
==================

Initial Setup:
[✓] fail2ban installed and configured
[✓] UFW firewall enabled
[ ] 2FA enabled for all Immich users
[ ] Strong passwords set (use password manager)
[ ] Recovery codes saved securely

Weekly Tasks:
[ ] Review security logs: /opt/immich-ecosystem/scripts/security-monitor.sh
[ ] Check fail2ban bans: sudo fail2ban-client status
[ ] Verify backups are running

Monthly Tasks:
[ ] Update system: sudo apt update && sudo apt upgrade
[ ] Review user list (remove inactive users)
[ ] Test backup restore procedure
[ ] Review Cloudflare security dashboard

Quarterly Tasks:
[ ] Review and rotate admin passwords
[ ] Audit user permissions
[ ] Test disaster recovery
[ ] Review access logs

If Compromised:
1. Stop remote access: sudo systemctl stop cloudflared
2. Check logs: sudo journalctl -u cloudflared | grep -i "error\|fail"
3. Change all passwords
4. Revoke and re-enable 2FA
5. Review and remove suspicious content
6. Restore from backup if needed

Support:
- Security monitor: /opt/immich-ecosystem/scripts/security-monitor.sh
- Logs: /var/log/immich-ecosystem/
- Cloudflare: https://dash.cloudflare.com/
EOF

mark_step_complete "phase4_security" "create_checklist"
echo -e "${GREEN}✓${NC} Checklist created"

# Mark complete
mark_phase_complete "phase4_security"

echo ""
echo "╔════════════════════════════════════════╗"
echo "║   Security Hardening Complete! 🎉      ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "Security features enabled:"
echo "  ✓ fail2ban - Blocks brute force attacks"
echo "  ✓ UFW firewall - Restricts network access"
echo "  ✓ Security monitoring - Track suspicious activity"
echo "  ⚠ 2FA - MUST be enabled for all users!"
echo ""
echo "Security checklist: /opt/immich-ecosystem/security-checklist.txt"
echo "Monitor security:   /opt/immich-ecosystem/scripts/security-monitor.sh"
echo ""
echo "Next steps:"
echo "  1. Enable 2FA for ALL users (critical!)"
echo "  2. Test remote access from your phone"
echo "  3. Run security monitor: /opt/immich-ecosystem/scripts/security-monitor.sh"
echo ""
