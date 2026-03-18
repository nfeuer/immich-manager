#!/bin/bash
#
# Phase 5: Test Installation
# Comprehensive testing of all components
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PASSED=0
FAILED=0
WARNINGS=0

function test_passed() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASSED++)) || true
}

function test_failed() {
    echo -e "${RED}✗${NC} $1"
    ((FAILED++)) || true
}

function test_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++)) || true
}

echo "╔════════════════════════════════════════╗"
echo "║   Installation Test Suite              ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Test 1: Immich running
echo "Testing Immich..."
if curl -s http://localhost:2283/api/server-info &>/dev/null; then
    test_passed "Immich is running"
else
    test_failed "Immich is not responding"
fi

# Test 2: Server Manager
echo ""
echo "Testing Server Manager..."
if curl -s http://localhost:8080/health | grep -q "ok"; then
    test_passed "Server Manager is running"

    if systemctl is-active --quiet immich-server-manager; then
        test_passed "Server Manager service is active"
    else
        test_warning "Server Manager service not active"
    fi
else
    test_failed "Server Manager is not responding"
fi

# Test 3: Photo Curator
echo ""
echo "Testing Photo Curator..."
if curl -s http://localhost:8081/health | grep -q "ok"; then
    test_passed "Photo Curator is running"

    if systemctl is-active --quiet photo-curator; then
        test_passed "Photo Curator service is active"
    else
        test_warning "Photo Curator service not active"
    fi
else
    test_failed "Photo Curator is not responding"
fi

# Test 4: Cloudflare Tunnel
echo ""
echo "Testing Remote Access..."
if systemctl is-active --quiet cloudflared; then
    test_passed "Cloudflare Tunnel is running"

    # Test domain if configured
    if [ -f /opt/immich-ecosystem/config/domain.yaml ]; then
        DOMAIN=$(grep "domain:" /opt/immich-ecosystem/config/domain.yaml | cut -d: -f2 | tr -d ' ')
        if [ -n "$DOMAIN" ]; then
            if curl -s -k -I "https://$DOMAIN" -m 5 &>/dev/null; then
                test_passed "Remote access to $DOMAIN is working"
            else
                test_warning "Cannot reach $DOMAIN (DNS may still be propagating)"
            fi
        fi
    fi
else
    test_warning "Cloudflare Tunnel not running (may not be installed)"
fi

# Test 5: Security
echo ""
echo "Testing Security..."
if systemctl is-active --quiet fail2ban; then
    test_passed "fail2ban is running"
else
    test_warning "fail2ban not running"
fi

if sudo ufw status | grep -q "Status: active"; then
    test_passed "UFW firewall is active"
else
    test_warning "UFW firewall not active"
fi

# Test 6: Storage
echo ""
echo "Testing Storage..."
if mountpoint -q /mnt/storage 2>/dev/null; then
    USAGE=$(df -h /mnt/storage | tail -1 | awk '{print $5}')
    test_passed "Storage mounted at /mnt/storage ($USAGE used)"
elif mountpoint -q /mnt/user 2>/dev/null; then
    USAGE=$(df -h /mnt/user | tail -1 | awk '{print $5}')
    test_passed "Storage mounted at /mnt/user ($USAGE used)"
else
    test_warning "No storage mount found (using system disk)"
fi

# Test 7: Backups
echo ""
echo "Testing Backups..."
if [ -d "/mnt/backups/immich" ]; then
    test_passed "Backup directory exists"

    LATEST=$(ls -t /mnt/backups/immich/immich_db_*.* 2>/dev/null | head -1)
    if [ -n "$LATEST" ]; then
        AGE=$(($(date +%s) - $(stat -c %Y "$LATEST")))
        HOURS=$((AGE / 3600))
        if [ $HOURS -lt 48 ]; then
            test_passed "Recent backup found (${HOURS}h old)"
        else
            test_warning "Last backup is ${HOURS}h old"
        fi
    else
        test_warning "No backups found yet"
    fi
else
    test_warning "Backup directory not configured"
fi

# Test 8: Docker containers
echo ""
echo "Testing Docker..."
IMMICH_CONTAINERS=$(docker ps --format '{{.Names}}' | grep -c "immich" || true)
if [ "$IMMICH_CONTAINERS" -gt 0 ]; then
    test_passed "Immich containers running ($IMMICH_CONTAINERS containers)"

    # Check specific containers
    for container in immich_server immich_machine_learning postgres redis; do
        if docker ps --format '{{.Names}}' | grep -q "$container"; then
            test_passed "$container is running"
        else
            test_warning "$container not found"
        fi
    done
else
    test_failed "No Immich containers running"
fi

# Summary
echo ""
echo "════════════════════════════════════════"
echo "Test Summary"
echo "════════════════════════════════════════"
echo ""
echo "Passed:   $PASSED"
echo "Failed:   $FAILED"
echo "Warnings: $WARNINGS"
echo ""

if [ $FAILED -eq 0 ]; then
    if [ $WARNINGS -eq 0 ]; then
        echo -e "${GREEN}🎉 All tests passed!${NC}"
        echo ""
        echo "Your Immich ecosystem is fully operational!"
        echo ""
        echo "Next steps:"
        echo "  1. Review security checklist: /opt/immich-ecosystem/security-checklist.txt"
        echo "  2. Enable 2FA for all users"
        echo "  3. Test from mobile app"
        echo "  4. Share user guide with family"
    else
        echo -e "${YELLOW}⚠ Tests passed with warnings${NC}"
        echo ""
        echo "Review warnings above and address if needed."
    fi

    echo ""
    echo "Quick Access:"
    echo "  • Dashboard:     http://localhost:8080"
    echo "  • Photo Curator: http://localhost:8081"
    echo "  • Immich:        http://localhost:2283"

    if [ -f /opt/immich-ecosystem/config/domain.yaml ]; then
        DOMAIN=$(grep "domain:" /opt/immich-ecosystem/config/domain.yaml | cut -d: -f2 | tr -d ' ')
        if [ -n "$DOMAIN" ]; then
            echo ""
            echo "Remote Access:"
            echo "  • https://$DOMAIN"
            echo "  • https://immich.$DOMAIN"
        fi
    fi

    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    echo ""
    echo "Please fix the issues above and rerun this script."
    echo ""
    echo "Troubleshooting:"
    echo "  • Check logs: sudo journalctl -u [service-name]"
    echo "  • Review config files"
    echo "  • Rerun installation scripts if needed"
    exit 1
fi
