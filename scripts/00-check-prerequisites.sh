#!/bin/bash
#
# Phase 0: Prerequisites Check for Immich Ecosystem
# Validates system requirements before installation
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/state-manager.sh"

FAILED_CHECKS=0
PASSED_CHECKS=0
WARNINGS=0

function check_passed() {
    echo -e "${GREEN}[✓]${NC} $1"
    ((PASSED_CHECKS++))
}

function check_failed() {
    echo -e "${RED}[✗]${NC} $1"
    ((FAILED_CHECKS++))
}

function check_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
    ((WARNINGS++))
}

echo "╔════════════════════════════════════════╗"
echo "║   Prerequisites Check                  ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    check_failed "Running as root"
    echo "   Please run as normal user with sudo access"
    exit 1
else
    check_passed "Running as non-root user"
fi

# Check for sudo access
if sudo -n true 2>/dev/null; then
    check_passed "Sudo access available (passwordless)"
elif sudo -v 2>/dev/null; then
    check_passed "Sudo access available"
else
    check_failed "No sudo access"
    echo "   Run: sudo usermod -aG sudo $USER"
    echo "   Then logout and login again"
fi

# Check operating system
if [ -f /etc/os-release ]; then
    source /etc/os-release
    if [[ "$ID" == "ubuntu" ]] || [[ "$ID" == "debian" ]]; then
        check_passed "Operating System: $PRETTY_NAME"
    else
        check_warning "Operating System: $PRETTY_NAME (Ubuntu/Debian recommended)"
    fi
else
    check_warning "Cannot determine operating system"
fi

# Check Python version
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

    if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 9 ]; then
        check_passed "Python version: $PYTHON_VERSION"
    else
        check_failed "Python version: $PYTHON_VERSION (requires 3.9+)"
        echo "   Run: sudo apt install python3.9 python3.9-venv python3.9-dev"
    fi
else
    check_failed "Python 3 not found"
    echo "   Run: sudo apt install python3 python3-venv python3-pip"
fi

# Check for pip
if python3 -m pip --version &> /dev/null; then
    check_passed "pip installed"
else
    check_failed "pip not found"
    echo "   Run: sudo apt install python3-pip"
fi

# Check for venv module
if python3 -m venv --help &> /dev/null; then
    check_passed "python3-venv available"
else
    check_failed "python3-venv not found"
    echo "   Run: sudo apt install python3-venv"
fi

# Check Docker
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version | cut -d' ' -f3 | tr -d ',')
    check_passed "Docker version: $DOCKER_VERSION"

    # Check if user can run docker without sudo
    if docker ps &> /dev/null; then
        check_passed "Docker access without sudo"
    else
        check_warning "Cannot run docker without sudo"
        echo "   Run: sudo usermod -aG docker $USER"
        echo "   Then logout and login again"
    fi
else
    check_failed "Docker not found"
    echo "   Install Docker: curl -fsSL https://get.docker.com | sh"
fi

# Check Docker Compose
if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
    if docker compose version &> /dev/null; then
        COMPOSE_VERSION=$(docker compose version --short)
        check_passed "Docker Compose version: $COMPOSE_VERSION"
    else
        COMPOSE_VERSION=$(docker-compose --version | cut -d' ' -f3 | tr -d ',')
        check_passed "Docker Compose version: $COMPOSE_VERSION"
    fi
else
    check_failed "Docker Compose not found"
    echo "   Run: sudo apt install docker-compose-plugin"
fi

# Check for Immich installation
echo ""
echo "Checking for Immich..."
if docker ps --format '{{.Names}}' | grep -q "immich"; then
    check_passed "Immich containers running"

    # Count containers
    CONTAINER_COUNT=$(docker ps --format '{{.Names}}' | grep -c "immich" || true)
    echo "   Found $CONTAINER_COUNT Immich containers"

    # Check if API is responding
    if curl -s http://localhost:2283/api/server-info &> /dev/null; then
        check_passed "Immich API responding on port 2283"
    else
        check_warning "Immich containers running but API not responding"
        echo "   Check: docker logs immich_server"
    fi
else
    check_warning "Immich not found"
    echo "   Immich must be installed first"
    echo "   Visit: https://immich.app/docs/install/docker-compose"
fi

# Check disk space on root
ROOT_SPACE=$(df / | tail -1 | awk '{print $4}')
ROOT_SPACE_GB=$((ROOT_SPACE / 1024 / 1024))
if [ "$ROOT_SPACE_GB" -ge 10 ]; then
    check_passed "Disk space on /: ${ROOT_SPACE_GB}GB available"
else
    check_warning "Disk space on /: ${ROOT_SPACE_GB}GB available (10GB+ recommended)"
fi

# Check for storage mount (optional)
if mountpoint -q /mnt/storage 2>/dev/null; then
    STORAGE_SPACE=$(df /mnt/storage | tail -1 | awk '{print $4}')
    STORAGE_SPACE_GB=$((STORAGE_SPACE / 1024 / 1024))
    check_passed "Storage mount: /mnt/storage (${STORAGE_SPACE_GB}GB available)"
elif mountpoint -q /mnt/user 2>/dev/null; then
    STORAGE_SPACE=$(df /mnt/user | tail -1 | awk '{print $4}')
    STORAGE_SPACE_GB=$((STORAGE_SPACE / 1024 / 1024))
    check_passed "Storage mount: /mnt/user (${STORAGE_SPACE_GB}GB available)"
else
    check_warning "No storage mount found at /mnt/storage or /mnt/user"
    echo "   Using system disk for storage (not recommended for large libraries)"
fi

# Check required ports
echo ""
echo "Checking port availability..."
REQUIRED_PORTS=(8080 8081)
for PORT in "${REQUIRED_PORTS[@]}"; do
    if ! sudo lsof -i :$PORT &> /dev/null && ! sudo ss -tuln | grep -q ":$PORT "; then
        check_passed "Port $PORT available"
    else
        check_failed "Port $PORT already in use"
        PROCESS=$(sudo lsof -i :$PORT 2>/dev/null | tail -1 | awk '{print $1}' || echo "unknown")
        echo "   Process using port: $PROCESS"
        echo "   Action: Stop the service or choose a different port"
    fi
done

# Check internet connectivity
echo ""
echo "Checking internet connectivity..."
if ping -c 1 -W 2 8.8.8.8 &> /dev/null; then
    check_passed "Internet connectivity"
else
    check_failed "No internet connection"
    echo "   Internet required for installation"
fi

# Check for curl
if command -v curl &> /dev/null; then
    check_passed "curl installed"
else
    check_failed "curl not found"
    echo "   Run: sudo apt install curl"
fi

# Check for jq (optional but recommended)
if command -v jq &> /dev/null; then
    check_passed "jq installed"
else
    check_warning "jq not installed (optional but recommended)"
    echo "   Run: sudo apt install jq"
fi

# Check for smartctl (for disk monitoring)
if command -v smartctl &> /dev/null; then
    check_passed "smartmontools installed"
else
    check_warning "smartmontools not installed (required for disk monitoring)"
    echo "   Run: sudo apt install smartmontools"
fi

# Summary
echo ""
echo "════════════════════════════════════════"
echo "Summary"
echo "════════════════════════════════════════"
echo ""
echo "Passed:   $PASSED_CHECKS"
echo "Failed:   $FAILED_CHECKS"
echo "Warnings: $WARNINGS"
echo ""

if [ $FAILED_CHECKS -eq 0 ]; then
    if [ $WARNINGS -eq 0 ]; then
        echo -e "${GREEN}✓ All prerequisites met!${NC}"
        echo ""
        echo "Ready to proceed with installation."
        echo ""
        echo "Next step:"
        echo "  ./install.sh"
    else
        echo -e "${YELLOW}⚠ Prerequisites met with warnings${NC}"
        echo ""
        echo "You can proceed, but some features may not work optimally."
        echo ""
        echo "Next step:"
        echo "  ./install.sh"
    fi
    exit 0
else
    echo -e "${RED}✗ Prerequisites not met${NC}"
    echo ""
    echo "Please fix the issues above and rerun this script."
    echo ""
    echo "Quick fix commands:"
    echo "  sudo apt update"
    echo "  sudo apt install -y python3 python3-venv python3-pip docker.io docker-compose-plugin jq curl smartmontools"
    echo "  sudo usermod -aG docker $USER"
    echo "  # Then logout and login again"
    echo ""
    exit 1
fi
