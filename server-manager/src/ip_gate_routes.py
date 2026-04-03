"""
IP Gate API routes — challenge, verification, and admin management.

Public endpoints (no auth):
  GET  /api/ip-gate/status          — Check if requesting IP is trusted/pending/unknown
  POST /api/ip-gate/challenge       — Submit email for verification (rate limited)
  GET  /api/ip-gate/verify/{token}  — Verify IP via email link click (rate limited)

Admin management endpoints (auth + admin required):
  GET    /api/ip-gate/management/trusted      — List trusted IPs with 7d connection counts
  GET    /api/ip-gate/management/pending       — List pending IPs
  GET    /api/ip-gate/management/revoked       — List blacklisted IPs
  GET    /api/ip-gate/management/connections   — Filterable connection log
  POST   /api/ip-gate/management/approve       — Manual approve
  POST   /api/ip-gate/management/revoke        — Revoke/blacklist
  POST   /api/ip-gate/management/unblock       — Unblock revoked IP
  DELETE  /api/ip-gate/management/{ip_address} — Delete IP record
  PUT    /api/ip-gate/management/{ip_address}  — Update label/duration
"""

import hmac
import logging
import os
from datetime import datetime
from typing import Optional

import requests as http_requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from shared.auth.ip_gate import (
    create_verification_token,
    delete_ip,
    get_connection_log,
    get_ip_connections_count_7d,
    get_trusted_ip,
    insert_pending_ip,
    is_valid_email,
    list_ips_by_status,
    mark_token_used,
    record_ip_connection,
    revoke_ip,
    trust_ip,
    unblock_ip,
    update_ip_label,
    update_ip_trust_duration,
    validate_verification_token,
)
from shared.auth import extract_token, validate_immich_token, get_or_create_user, Role

logger = logging.getLogger(__name__)

ip_gate_router = APIRouter(prefix="/api/ip-gate")

limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ChallengeRequest(BaseModel):
    email: str


class ManualApproveRequest(BaseModel):
    ip_address: str
    access_level: str = "user"
    trust_duration: str = "24h"
    label: Optional[str] = None


class RevokeRequest(BaseModel):
    ip_address: str
    reason: Optional[str] = None


class UpdateIPRequest(BaseModel):
    label: Optional[str] = None
    trust_duration: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_db(request: Request):
    """Return the IP gate database from app state."""
    db = getattr(request.app.state, "ip_gate_db", None)
    if not db:
        raise HTTPException(status_code=503, detail="IP gate database not available")
    return db


def _get_client_ip(request: Request) -> str:
    """Extract client IP using same logic as the middleware."""
    from ip_gate_middleware import get_client_ip

    config = getattr(request.app.state, "ip_gate_config", None)
    trusted_proxies = config.trusted_proxy_ips if config else []
    return get_client_ip(request, trusted_proxies)


def _require_admin_for_management(request: Request):
    """Validate auth token and require admin role. Raises HTTPException on failure."""
    token = extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    immich_api_url = getattr(request.app.state, "immich_api_url", None)
    if not immich_api_url:
        raise HTTPException(status_code=503, detail="Immich API URL not configured")

    immich_user = validate_immich_token(immich_api_url, token)
    if not immich_user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Check admin via Immich's isAdmin flag — no local DB needed for IP gate management
    if not immich_user.get("isAdmin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    return immich_user


def validate_immich_email(api_url: str, email: str) -> Optional[dict]:
    """
    Check whether an email belongs to an Immich user.

    Uses the admin API key from IMMICH_API_KEY env var. Returns the Immich
    user dict if found, None otherwise. Uses constant-time comparison for
    the email to avoid timing side-channels.
    """
    api_key = os.environ.get("IMMICH_API_KEY")
    if not api_key:
        logger.warning("IMMICH_API_KEY not set; cannot validate email against Immich")
        return None

    try:
        resp = http_requests.get(
            f"{api_url}/users",
            headers={"x-api-key": api_key},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("Immich users API returned %d", resp.status_code)
            return None

        for user in resp.json():
            user_email = user.get("email", "")
            if hmac.compare_digest(user_email.lower(), email.lower()):
                return user
    except Exception:
        logger.exception("Failed to validate email against Immich")

    return None


async def _send_verification_email(email: str, token: str, request: Request) -> None:
    """Send verification email to the specific user requesting verification."""
    public_url = getattr(request.app.state, "public_url", "") or str(request.base_url).rstrip("/")
    verify_base = f"{public_url}/api/ip-gate/verify/{token}"
    client_ip = _get_client_ip(request)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    body = (
        f"Someone is trying to access Immich from {client_ip} at {now}.\n\n"
        "If this is you, choose how long to trust this IP:\n\n"
        f"  Trust for 24 hours: {verify_base}?duration=24h\n"
        f"  Trust for 7 days:   {verify_base}?duration=7d\n"
        f"  Trust for 30 days:  {verify_base}?duration=30d\n"
        f"  Trust permanently:  {verify_base}?duration=permanent\n\n"
        "If this wasn't you, ignore this email. The IP will remain blocked."
    )

    alert_manager = getattr(request.app.state, "alert_manager", None)
    if alert_manager:
        await alert_manager.send_email_to(
            email,
            "New login attempt from unrecognized IP",
            body,
            "warning",
        )
    else:
        logger.warning("No alert manager — verification link for %s: %s", email, verify_base)


async def _send_cloudflare_notification(ip_address: str, email: str, request: Request) -> None:
    """Send notification about admin IP verification for Cloudflare update."""
    alert_manager = getattr(request.app.state, "alert_manager", None)
    if not alert_manager:
        return

    ip_gate_config = getattr(request.app.state, "ip_gate_config", None)
    cf_enabled = ip_gate_config and ip_gate_config.cloudflare.enabled

    if cf_enabled:
        alert_manager.send_discord(
            "Admin IP Verified — Cloudflare Syncing",
            f"IP `{ip_address}` verified by `{email}`.\n"
            "Cloudflare Access list will be updated automatically.",
            "info",
        )
    else:
        alert_manager.send_discord(
            "Admin IP Verified — Update Cloudflare Manually",
            f"IP `{ip_address}` was verified by `{email}`.\n"
            "Add it to your Cloudflare Access policy:\n"
            "Zero Trust -> Access -> [your app] -> Add IP rule.",
            "warning",
        )
        await alert_manager.send_email(
            "New admin IP verified — update Cloudflare",
            f"IP {ip_address} was verified by {email}.\n\n"
            "Add it to your Cloudflare Access policy:\n"
            "Zero Trust -> Access -> [your app] -> Add IP rule.",
            "warning",
        )


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------


@ip_gate_router.get("/status")
async def ip_status(request: Request):
    """Check if requesting IP is trusted, pending, or unknown."""
    db = _get_db(request)
    client_ip = _get_client_ip(request)
    record = get_trusted_ip(db, client_ip)

    if record is None:
        return {"status": "unknown", "ip": client_ip}

    return {
        "status": record["status"],
        "ip": client_ip,
        "label": record.get("label"),
        "expires_at": record.get("expires_at"),
    }


@ip_gate_router.post("/challenge")
async def challenge_submit(body: ChallengeRequest, request: Request):
    """
    Submit an email address for IP verification.

    Always returns the same response regardless of whether the email exists
    in Immich — no information leak.
    """
    if not is_valid_email(body.email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    db = _get_db(request)
    client_ip = _get_client_ip(request)

    # Ensure IP is in the pending table
    insert_pending_ip(db, client_ip, source="challenge")

    # Discord alert for new challenge attempt (always, regardless of email validity)
    alert_manager = getattr(request.app.state, "alert_manager", None)
    if alert_manager:
        alert_manager.send_discord(
            "IP Verification Challenge",
            f"New IP `{client_ip}` submitted a verification challenge.",
            "info",
        )

    # Check Immich for user (result intentionally unused in response)
    api_url = getattr(request.app.state, "immich_api_url", "")
    immich_user = validate_immich_email(api_url, body.email)

    if immich_user:
        config = getattr(request.app.state, "ip_gate_config", None)
        expiry = config.token_expiry_minutes if config else 15
        token = create_verification_token(db, client_ip, body.email, expiry)
        await _send_verification_email(body.email, token, request)

    # Identical response whether email exists or not
    return {
        "message": "If this email is registered, a verification email has been sent.",
    }


@ip_gate_router.get("/verify/{token}")
async def verify_token(token: str, request: Request, duration: str = "24h"):
    """Verify an IP via the emailed token link."""
    valid_durations = {"24h", "7d", "30d", "90d", "permanent"}
    if duration not in valid_durations:
        raise HTTPException(status_code=400, detail="Invalid duration")

    db = _get_db(request)

    token_record = validate_verification_token(db, token)
    if not token_record:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    ip_address = token_record["ip_address"]
    email = token_record["email"]

    # Determine access level from user's RBAC role
    access_level = "user"
    api_url = getattr(request.app.state, "immich_api_url", "")
    if api_url:
        immich_user = validate_immich_email(api_url, email)
        if immich_user:
            local_user, _ = get_or_create_user(db, immich_user, "user")
            if Role[local_user.get("role", "guest").upper()] >= Role.ADMIN:
                access_level = "admin"

    # Trust the IP
    trust_ip(db, ip_address, access_level=access_level, trust_duration=duration, verified_by=email)
    mark_token_used(db, token)
    record_ip_connection(db, ip_address, "server-manager", "allowed", user_id=email)

    # Notify about admin IP for Cloudflare
    if access_level == "admin":
        await _send_cloudflare_notification(ip_address, email, request)

    logger.info("IP %s verified by %s (access=%s, duration=%s)",
                ip_address, email, access_level, duration)

    return {
        "message": f"IP {ip_address} has been verified and trusted for {duration}.",
        "ip": ip_address,
        "access_level": access_level,
        "trust_duration": duration,
        "redirect": "/",
    }


# ---------------------------------------------------------------------------
# Admin management endpoints
# ---------------------------------------------------------------------------


@ip_gate_router.get("/management/trusted")
async def list_trusted(request: Request):
    """List trusted IPs with 7-day connection counts."""
    _require_admin_for_management(request)
    db = _get_db(request)
    ips = list_ips_by_status(db, "trusted")
    for ip_rec in ips:
        ip_rec["connections_7d"] = get_ip_connections_count_7d(db, ip_rec["ip_address"])
    return {"trusted": ips}


@ip_gate_router.get("/management/pending")
async def list_pending(request: Request):
    """List pending IPs."""
    _require_admin_for_management(request)
    db = _get_db(request)
    return {"pending": list_ips_by_status(db, "pending")}


@ip_gate_router.get("/management/revoked")
async def list_revoked(request: Request):
    """List revoked/blacklisted IPs."""
    _require_admin_for_management(request)
    db = _get_db(request)
    return {"revoked": list_ips_by_status(db, "revoked")}


@ip_gate_router.get("/management/connections")
async def list_connections(
    request: Request,
    ip: Optional[str] = None,
    service: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 200,
):
    """Filterable connection log."""
    _require_admin_for_management(request)
    db = _get_db(request)
    logs = get_connection_log(db, limit=limit, ip_filter=ip, service_filter=service, action_filter=action)
    return {"connections": logs}


@ip_gate_router.post("/management/approve")
async def manual_approve(body: ManualApproveRequest, request: Request):
    """Manually approve an IP."""
    admin = _require_admin_for_management(request)
    db = _get_db(request)

    # Ensure IP exists in the table
    insert_pending_ip(db, body.ip_address, source="admin")

    verified_by = f"admin:{admin.get('email', admin.get('id', 'unknown'))}"
    trust_ip(db, body.ip_address, body.access_level, body.trust_duration, verified_by)

    if body.label:
        update_ip_label(db, body.ip_address, body.label)

    record_ip_connection(db, body.ip_address, "server-manager", "manual_approve", user_id=verified_by)
    return {"message": f"IP {body.ip_address} approved", "access_level": body.access_level}


@ip_gate_router.post("/management/revoke")
async def revoke(body: RevokeRequest, request: Request):
    """Revoke/blacklist an IP."""
    admin = _require_admin_for_management(request)
    db = _get_db(request)

    revoked_by = f"admin:{admin.get('email', admin.get('id', 'unknown'))}"
    revoke_ip(db, body.ip_address, revoked_by, body.reason)
    record_ip_connection(db, body.ip_address, "server-manager", "revoked", user_id=revoked_by)

    alert_manager = getattr(request.app.state, "alert_manager", None)
    if alert_manager:
        alert_manager.send_discord(
            "IP Revoked",
            f"IP `{body.ip_address}` was revoked by `{revoked_by}`."
            + (f"\nReason: {body.reason}" if body.reason else ""),
            "warning",
        )

    return {"message": f"IP {body.ip_address} revoked"}


@ip_gate_router.post("/management/unblock")
async def unblock(request: Request, ip_address: str = ""):
    """Unblock a revoked IP (moves back to pending)."""
    _require_admin_for_management(request)
    db = _get_db(request)

    if not ip_address:
        body = await request.json()
        ip_address = body.get("ip_address", "")
    if not ip_address:
        raise HTTPException(status_code=400, detail="ip_address required")

    unblock_ip(db, ip_address)
    record_ip_connection(db, ip_address, "server-manager", "unblocked")
    return {"message": f"IP {ip_address} unblocked"}


@ip_gate_router.delete("/management/{ip_address}")
async def delete_ip_record(ip_address: str, request: Request):
    """Permanently delete an IP record."""
    _require_admin_for_management(request)
    db = _get_db(request)
    delete_ip(db, ip_address)
    return {"message": f"IP {ip_address} deleted"}


@ip_gate_router.put("/management/{ip_address}")
async def update_ip(ip_address: str, body: UpdateIPRequest, request: Request):
    """Update label and/or trust duration for an IP."""
    _require_admin_for_management(request)
    db = _get_db(request)

    record = get_trusted_ip(db, ip_address)
    if not record:
        raise HTTPException(status_code=404, detail=f"IP {ip_address} not found")

    if body.label is not None:
        update_ip_label(db, ip_address, body.label)
    if body.trust_duration is not None:
        update_ip_trust_duration(db, ip_address, body.trust_duration)

    return {"message": f"IP {ip_address} updated"}
