#!/bin/bash
#
# Quick health check of Immich ecosystem
#

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "Immich Ecosystem Health Check"
echo "=============================="
echo "$(date)"
echo ""

# Immich
echo -n "Immich:          "
if curl -s http://localhost:2283/api/server-info &>/dev/null; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not responding${NC}"
fi

# Server Manager
echo -n "Server Manager:  "
if curl -s http://localhost:8080/health | grep -q "ok"; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not responding${NC}"
fi

# Photo Curator
echo -n "Photo Curator:   "
if curl -s http://localhost:8081/health | grep -q "ok"; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not responding${NC}"
fi

# Cloudflare Tunnel
echo -n "Remote Access:   "
if systemctl is-active --quiet cloudflared 2>/dev/null; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${YELLOW}⚠ Not configured${NC}"
fi

# Storage
echo -n "Storage:         "
if mountpoint -q /mnt/storage 2>/dev/null; then
    USAGE=$(df -h /mnt/storage | tail -1 | awk '{print $5}')
    echo -e "${GREEN}✓ Mounted${NC} ($USAGE used)"
elif mountpoint -q /mnt/user 2>/dev/null; then
    USAGE=$(df -h /mnt/user | tail -1 | awk '{print $5}')
    echo -e "${GREEN}✓ Mounted${NC} ($USAGE used)"
else
    echo -e "${YELLOW}⚠ Not mounted${NC}"
fi

# Recent backup
echo -n "Last Backup:     "
if [ -d "/mnt/backups/immich" ]; then
    LATEST=$(ls -t /mnt/backups/immich/immich_db_*.* 2>/dev/null | head -1)
    if [ -n "$LATEST" ]; then
        AGE=$(($(date +%s) - $(stat -c %Y "$LATEST")))
        HOURS=$((AGE / 3600))
        if [ $HOURS -lt 48 ]; then
            echo -e "${GREEN}${HOURS}h ago${NC}"
        else
            echo -e "${YELLOW}${HOURS}h ago (old)${NC}"
        fi
    else
        echo -e "${YELLOW}None found${NC}"
    fi
else
    echo -e "${YELLOW}Not configured${NC}"
fi

echo ""
echo "Quick commands:"
echo "  Full test:       /home/user/immich-manager/scripts/50-test-installation.sh"
echo "  Server Manager:  http://localhost:8080"
echo "  Photo Curator:   http://localhost:8081"
echo "  View logs:       sudo journalctl -u immich-server-manager -f"
