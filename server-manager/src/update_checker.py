"""
Immich version update checker.

Compares the currently running Immich container image tag against the latest
GitHub release and fires an alert when an update is available.
"""

import logging
import re
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)

GITHUB_LATEST_RELEASE_URL = "https://api.github.com/repos/immich-app/immich/releases/latest"


class UpdateChecker:
    """Checks for new Immich releases on GitHub."""

    def __init__(self, docker_monitor):
        self.docker_monitor = docker_monitor
        self._last_notified_version: Optional[str] = None

    def get_running_version(self) -> Optional[str]:
        """Extract the version tag from the running immich-server container."""
        containers = self.docker_monitor.get_immich_containers()
        for c in containers:
            image = c.get("image", "")
            # Match tags like ghcr.io/immich-app/immich-server:v1.99.0
            if "immich-server" in image or "immich_server" in image:
                match = re.search(r":v?(\d+\.\d+\.\d+)", image)
                if match:
                    return match.group(1)
            # Also check plain version tags
            if "immich" in image:
                match = re.search(r":v?(\d+\.\d+\.\d+)", image)
                if match:
                    return match.group(1)
        return None

    @staticmethod
    def get_latest_github_version() -> Optional[str]:
        """Fetch the latest release version from GitHub."""
        try:
            resp = requests.get(
                GITHUB_LATEST_RELEASE_URL,
                headers={"Accept": "application/vnd.github+json"},
                timeout=15,
            )
            resp.raise_for_status()
            tag = resp.json().get("tag_name", "")
            # Strip leading 'v' if present
            return tag.lstrip("v") if tag else None
        except Exception as e:
            logger.warning(f"Failed to check Immich latest release: {e}")
            return None

    @staticmethod
    def _parse_version(version_str: str) -> Tuple[int, ...]:
        return tuple(int(x) for x in version_str.split("."))

    def check_for_update(self) -> Optional[dict]:
        """
        Compare running vs latest version.

        Returns a dict with update info if a newer version exists,
        or None if up-to-date or unable to determine.
        """
        running = self.get_running_version()
        if not running:
            logger.debug("Could not determine running Immich version")
            return None

        latest = self.get_latest_github_version()
        if not latest:
            return None

        try:
            if self._parse_version(latest) > self._parse_version(running):
                # Only notify once per new version
                if self._last_notified_version == latest:
                    return None
                self._last_notified_version = latest
                return {
                    "running_version": running,
                    "latest_version": latest,
                    "release_url": f"https://github.com/immich-app/immich/releases/tag/v{latest}",
                }
        except (ValueError, TypeError):
            logger.warning(f"Could not parse versions: running={running}, latest={latest}")

        return None
