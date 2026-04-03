# server-manager/src/ip_gate_cloudflare.py
"""
Optional Cloudflare Zero Trust integration for IP gate.

When enabled, syncs admin-trusted IPs to a Cloudflare Access IP list.
Requires a paid Teams Standard plan for the Lists API.
"""

import logging
from typing import List, Optional

import requests as http_requests

logger = logging.getLogger(__name__)

_CF_API_BASE = "https://api.cloudflare.com/client/v4"


class CloudflareIPSync:
    """Manages a Cloudflare Zero Trust IP list."""

    def __init__(self, api_token: str, account_id: str, list_name: str):
        self.api_token = api_token
        self.account_id = account_id
        self.list_name = list_name
        self._list_id: Optional[str] = None
        self.session = http_requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        })

    def _get_or_create_list(self) -> Optional[str]:
        """Find or create the IP list. Returns list ID or None."""
        if self._list_id:
            return self._list_id

        try:
            resp = self.session.get(
                f"{_CF_API_BASE}/accounts/{self.account_id}/rules/lists",
                timeout=10,
            )
            resp.raise_for_status()
            for lst in resp.json().get("result", []):
                if lst["name"] == self.list_name:
                    self._list_id = lst["id"]
                    return self._list_id

            resp = self.session.post(
                f"{_CF_API_BASE}/accounts/{self.account_id}/rules/lists",
                json={
                    "name": self.list_name,
                    "kind": "ip",
                    "description": "Immich Manager trusted IPs",
                },
                timeout=10,
            )
            resp.raise_for_status()
            self._list_id = resp.json()["result"]["id"]
            return self._list_id

        except Exception as e:
            logger.error("Failed to get/create Cloudflare list: %s", e)
            return None

    def add_ip(self, ip_address: str) -> bool:
        """Add an IP to the Cloudflare list."""
        list_id = self._get_or_create_list()
        if not list_id:
            return False

        try:
            resp = self.session.post(
                f"{_CF_API_BASE}/accounts/{self.account_id}/rules/lists/{list_id}/items",
                json=[{"ip": ip_address}],
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("Added IP %s to Cloudflare list %s", ip_address, self.list_name)
            return True
        except Exception as e:
            logger.error("Failed to add IP to Cloudflare: %s", e)
            return False

    def remove_ip(self, ip_address: str) -> bool:
        """Remove an IP from the Cloudflare list."""
        list_id = self._get_or_create_list()
        if not list_id:
            return False

        try:
            resp = self.session.get(
                f"{_CF_API_BASE}/accounts/{self.account_id}/rules/lists/{list_id}/items",
                timeout=10,
            )
            resp.raise_for_status()

            item_id = None
            for item in resp.json().get("result", []):
                if item.get("ip") == ip_address:
                    item_id = item["id"]
                    break

            if not item_id:
                logger.info("IP %s not found in Cloudflare list", ip_address)
                return True

            resp = self.session.delete(
                f"{_CF_API_BASE}/accounts/{self.account_id}/rules/lists/{list_id}/items",
                json={"items": [{"id": item_id}]},
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("Removed IP %s from Cloudflare list", ip_address)
            return True

        except Exception as e:
            logger.error("Failed to remove IP from Cloudflare: %s", e)
            return False

    def sync(self, trusted_admin_ips: List[str]) -> bool:
        """
        Reconcile: ensure the Cloudflare list matches the given set of IPs.
        Adds missing IPs, removes IPs not in the trusted set.
        """
        list_id = self._get_or_create_list()
        if not list_id:
            return False

        try:
            resp = self.session.get(
                f"{_CF_API_BASE}/accounts/{self.account_id}/rules/lists/{list_id}/items",
                timeout=10,
            )
            resp.raise_for_status()

            cf_items = {item["ip"]: item["id"] for item in resp.json().get("result", [])}
            cf_ips = set(cf_items.keys())
            local_ips = set(trusted_admin_ips)

            to_add = local_ips - cf_ips
            for ip in to_add:
                self.add_ip(ip)

            to_remove = cf_ips - local_ips
            for ip in to_remove:
                self.remove_ip(ip)

            if to_add or to_remove:
                logger.info("Cloudflare sync: added %d, removed %d", len(to_add), len(to_remove))
            return True

        except Exception as e:
            logger.error("Cloudflare sync failed: %s", e)
            return False
