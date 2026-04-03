# server-manager/src/ip_gate_middleware.py
"""
IP Gate middleware for FastAPI.

Runs before auth middleware. Checks every request's IP against the trusted_ips
table. Unknown/pending IPs are redirected to the challenge page. Revoked IPs
get a hard 403.
"""

import logging
from typing import List

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

EXEMPT_PATHS = [
    "/api/ip-gate/verify/",
    "/api/ip-gate/status",
    "/api/ip-gate/challenge",
    "/health",
    "/ip-challenge",
]


def is_exempt_path(path: str) -> bool:
    """Check if the request path is exempt from IP gate checks."""
    for exempt in EXEMPT_PATHS:
        if path == exempt or path.startswith(exempt):
            return True
    return False


def get_client_ip(request: Request, trusted_proxies: List[str]) -> str:
    """
    Extract the real client IP from the request.
    Trusts X-Forwarded-For only when request.client.host is a known proxy.
    """
    client_host = request.client.host if request.client else "0.0.0.0"

    if client_host in trusted_proxies:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()

    return client_host


class IPGateMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces IP verification before allowing access.
    Requires app.state.ip_gate_db and app.state.ip_gate_config to be set.
    """

    async def dispatch(self, request: Request, call_next):
        ip_gate_config = getattr(request.app.state, "ip_gate_config", None)
        if not ip_gate_config or not ip_gate_config.enabled:
            return await call_next(request)

        if is_exempt_path(request.url.path):
            return await call_next(request)

        if request.url.path.startswith("/assets/") or request.url.path.startswith("/static/"):
            return await call_next(request)

        db = getattr(request.app.state, "ip_gate_db", None)
        if not db:
            logger.warning("IP gate DB not initialized, allowing request")
            return await call_next(request)

        trusted_proxies = ip_gate_config.trusted_proxy_ips
        client_ip = get_client_ip(request, trusted_proxies)

        from shared.auth.ip_gate import check_ip_access, insert_pending_ip, record_ip_connection

        service = "server-manager"
        result = check_ip_access(db, client_ip, service)
        action = result["action"]

        if action == "allow":
            record_ip_connection(db, client_ip, service, "allowed")
            return await call_next(request)

        if action == "block":
            record_ip_connection(db, client_ip, service, "blocked")
            logger.warning("Blocked request from revoked IP %s: %s", client_ip, result["reason"])
            return JSONResponse(
                status_code=403,
                content={"detail": "Access denied. This IP has been blocked."},
            )

        # action == "challenge"
        if result["ip_record"] is None:
            insert_pending_ip(db, client_ip, source="web")
        record_ip_connection(db, client_ip, service, "challenged")

        if request.headers.get("accept", "").startswith("application/json"):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "IP verification required",
                    "challenge_url": "/ip-challenge",
                },
            )
        return RedirectResponse(url="/ip-challenge", status_code=303)
