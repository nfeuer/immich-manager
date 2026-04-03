"""
HTTP client that delegates IP gate checks to Server Manager.
Photo Curator does not access the trusted_ips DB directly.
"""

import logging
from typing import Dict, Any

import requests as http_requests

logger = logging.getLogger(__name__)


class IPGateClient:
    """Client for Server Manager's IP gate API."""

    def __init__(self, server_manager_url: str):
        self.base_url = server_manager_url.rstrip("/")

    def check_ip(self, ip_address: str) -> Dict[str, Any]:
        """
        Check if an IP is trusted by querying Server Manager.
        Returns {"status": "trusted|pending|revoked|unknown", "ip": "..."}
        """
        try:
            resp = http_requests.get(
                f"{self.base_url}/api/ip-gate/status",
                headers={"x-forwarded-for": ip_address},
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json()
            return {"status": "unknown", "ip": ip_address}
        except Exception as e:
            logger.error("Failed to check IP with Server Manager: %s", e)
            # Fail open — if Server Manager is down, don't block Photo Curator
            return {"status": "trusted", "ip": ip_address}
