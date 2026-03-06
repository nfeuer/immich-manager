#!/bin/bash
set -euo pipefail

# Only run in remote Claude Code on the web environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || pwd)}"

echo "[$(date +%H:%M:%S)] Installing dependencies for immich-manager..."

# Install linting and testing tools
pip install --no-input --no-color ruff pytest

# Install dependencies for all three services.
# Skip packages that conflict with system-managed installs:
#   - sdnotify: requires systemd headers not available in dev containers
#   - pyyaml: installed by apt (6.0.1), cannot be upgraded by pip
# Note: photo-curator/requirements-ml.txt (dlib, torch) is intentionally skipped here —
#       those packages require compilation or 2+ GB downloads, making them too slow for
#       cloud sessions. They are installed by scripts/20-install-photo-curator.sh instead.
install_requirements() {
  local req_file="$1"
  echo "[$(date +%H:%M:%S)] Installing $(basename $(dirname $req_file)) deps..."
  grep -vE '^\s*(sdnotify|pyyaml|PyYAML)' "$req_file" | pip install --no-input --no-color -r /dev/stdin
}

install_requirements "$PROJECT_DIR/server-manager/requirements.txt"
install_requirements "$PROJECT_DIR/photo-curator/requirements.txt"
install_requirements "$PROJECT_DIR/migration-tools/requirements.txt"

echo "[$(date +%H:%M:%S)] All dependencies installed successfully."
