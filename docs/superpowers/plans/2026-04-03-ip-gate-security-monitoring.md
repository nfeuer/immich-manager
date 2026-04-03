# IP Gate Security Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a centralized IP verification system that challenges unknown IPs before granting access, with multi-user email verification, SSH alerting, optional Cloudflare sync, and an admin IP management dashboard.

**Architecture:** A shared `ip_gate.py` module handles DB operations and IP checking logic. Server Manager hosts the API endpoints, middleware, challenge page, and management dashboard. Photo Curator delegates IP checks to Server Manager via HTTP. An SSH monitor runs as a separate systemd service watching journalctl.

**Tech Stack:** Python 3.9+, FastAPI, SQLite (sqlite3 with Row factory), aiosmtplib, requests, React 18, TanStack Query, Tailwind CSS, Heroicons

---

## File Structure

```
shared/auth/
    ip_gate.py              # DB operations, IP checking, token management, email validation

server-manager/src/
    ip_gate_routes.py       # FastAPI routes: challenge, verify, status, management CRUD
    ip_gate_middleware.py    # FastAPI middleware that intercepts requests
    ip_gate_ssh_monitor.py  # Standalone SSH watcher script (systemd service)
    ip_gate_cloudflare.py   # Cloudflare Lists API integration

server-manager/frontend/src/
    components/IPManagement.jsx   # Dashboard UI with four tabs
    pages/ChallengePage.jsx       # Standalone email verification page
    hooks/useIPManagement.js      # TanStack Query hooks for IP gate API

server-manager/tests/
    test_ip_gate.py         # Tests for shared/auth/ip_gate.py
    test_ip_gate_routes.py  # Tests for API endpoints
    test_ip_gate_middleware.py  # Tests for middleware logic

photo-curator/src/
    ip_gate_client.py       # HTTP client that calls Server Manager IP gate API
```

---

### Task 1: Database Schema & Core IP Gate Module

**Files:**
- Create: `shared/auth/ip_gate.py`
- Modify: `shared/auth/__init__.py` (add exports)
- Test: `server-manager/tests/test_ip_gate.py`

- [ ] **Step 1: Write failing tests for table creation and IP lookup**

```python
# server-manager/tests/test_ip_gate.py
import sqlite3
import pytest
from datetime import datetime, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.auth.ip_gate import (
    ensure_ip_gate_tables,
    get_trusted_ip,
    insert_pending_ip,
    trust_ip,
    revoke_ip,
    record_ip_connection,
    get_ip_connections_count_7d,
)


class FakeDB:
    """Minimal DB wrapper matching Database._get_connection pattern."""
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def _get_connection(self):
        from contextlib import contextmanager

        @contextmanager
        def ctx():
            yield self.conn
        return ctx()


@pytest.fixture
def db():
    d = FakeDB()
    ensure_ip_gate_tables(d)
    return d


def test_ensure_tables_creates_all_three(db):
    cursor = db.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert "trusted_ips" in tables
    assert "ip_connections" in tables
    assert "verification_tokens" in tables


def test_insert_pending_ip(db):
    insert_pending_ip(db, "1.2.3.4", source="web")
    row = get_trusted_ip(db, "1.2.3.4")
    assert row is not None
    assert row["status"] == "pending"
    assert row["source"] == "web"


def test_insert_pending_ip_duplicate_ignored(db):
    insert_pending_ip(db, "1.2.3.4", source="web")
    insert_pending_ip(db, "1.2.3.4", source="ssh")  # should not raise
    row = get_trusted_ip(db, "1.2.3.4")
    assert row["source"] == "web"  # first insert wins


def test_trust_ip(db):
    insert_pending_ip(db, "10.0.0.1", source="web")
    trust_ip(db, "10.0.0.1", access_level="admin", trust_duration="30d",
             verified_by="admin@test.com")
    row = get_trusted_ip(db, "10.0.0.1")
    assert row["status"] == "trusted"
    assert row["access_level"] == "admin"
    assert row["verified_by"] == "admin@test.com"
    assert row["expires_at"] is not None


def test_trust_ip_permanent_no_expiry(db):
    insert_pending_ip(db, "10.0.0.2", source="web")
    trust_ip(db, "10.0.0.2", access_level="user", trust_duration="permanent",
             verified_by="user@test.com")
    row = get_trusted_ip(db, "10.0.0.2")
    assert row["expires_at"] is None


def test_revoke_ip(db):
    insert_pending_ip(db, "5.5.5.5", source="web")
    trust_ip(db, "5.5.5.5", access_level="user", trust_duration="permanent",
             verified_by="u@test.com")
    revoke_ip(db, "5.5.5.5", revoked_by="admin@test.com", reason="suspicious")
    row = get_trusted_ip(db, "5.5.5.5")
    assert row["status"] == "revoked"
    assert row["revoked_by"] == "admin@test.com"
    assert row["revoke_reason"] == "suspicious"


def test_record_and_count_connections(db):
    record_ip_connection(db, "1.1.1.1", service="server-manager", action="allowed")
    record_ip_connection(db, "1.1.1.1", service="server-manager", action="allowed")
    record_ip_connection(db, "1.1.1.1", service="photo-curator", action="allowed")
    count = get_ip_connections_count_7d(db, "1.1.1.1")
    assert count == 3


def test_get_trusted_ip_returns_none_for_unknown(db):
    assert get_trusted_ip(db, "9.9.9.9") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/feuer/Documents/Projects/immich-manager && python -m pytest server-manager/tests/test_ip_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shared.auth.ip_gate'`

- [ ] **Step 3: Implement the core ip_gate module**

```python
# shared/auth/ip_gate.py
"""
Centralized IP gate — database operations, IP checking, token management.

All functions accept a `db` object that exposes `_get_connection()` returning
a context manager yielding a sqlite3.Connection with row_factory = sqlite3.Row.
"""

import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

_DURATION_DELTAS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}


def ensure_ip_gate_tables(db) -> None:
    """Create IP gate tables if they don't exist."""
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trusted_ips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending',
                access_level TEXT DEFAULT NULL,
                trust_duration TEXT DEFAULT NULL,
                trusted_at DATETIME DEFAULT NULL,
                expires_at DATETIME DEFAULT NULL,
                verified_by TEXT DEFAULT NULL,
                label TEXT DEFAULT NULL,
                last_seen DATETIME DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                source TEXT DEFAULT 'web',
                revoked_at DATETIME DEFAULT NULL,
                revoked_by TEXT DEFAULT NULL,
                revoke_reason TEXT DEFAULT NULL
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_trusted_ips_status ON trusted_ips(status)"
        )
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ip_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                service TEXT,
                action TEXT,
                user_id TEXT
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_ip_connections_ip ON ip_connections(ip_address)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_ip_connections_timestamp ON ip_connections(timestamp)"
        )
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verification_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                ip_address TEXT NOT NULL,
                email TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                trust_duration TEXT DEFAULT '24h'
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_verification_tokens_token ON verification_tokens(token)"
        )


# ---------------------------------------------------------------------------
# IP CRUD
# ---------------------------------------------------------------------------

def get_trusted_ip(db, ip_address: str) -> Optional[Dict[str, Any]]:
    """Look up a single IP. Returns dict or None."""
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM trusted_ips WHERE ip_address = ?", (ip_address,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def insert_pending_ip(db, ip_address: str, source: str = "web") -> None:
    """Insert an IP as pending. Silently ignores duplicates."""
    with db._get_connection() as conn:
        conn.cursor().execute(
            "INSERT OR IGNORE INTO trusted_ips (ip_address, status, source) VALUES (?, 'pending', ?)",
            (ip_address, source),
        )


def trust_ip(
    db,
    ip_address: str,
    access_level: str,
    trust_duration: str,
    verified_by: str,
) -> None:
    """Mark an IP as trusted with the given duration and access level."""
    now = datetime.utcnow()
    delta = _DURATION_DELTAS.get(trust_duration)
    expires_at = (now + delta).isoformat() if delta else None

    with db._get_connection() as conn:
        conn.cursor().execute(
            """UPDATE trusted_ips
               SET status = 'trusted',
                   access_level = ?,
                   trust_duration = ?,
                   trusted_at = ?,
                   expires_at = ?,
                   verified_by = ?,
                   last_seen = ?
               WHERE ip_address = ?""",
            (access_level, trust_duration, now.isoformat(), expires_at,
             verified_by, now.isoformat(), ip_address),
        )


def revoke_ip(
    db,
    ip_address: str,
    revoked_by: str,
    reason: Optional[str] = None,
) -> None:
    """Revoke (blacklist) an IP."""
    now = datetime.utcnow().isoformat()
    with db._get_connection() as conn:
        conn.cursor().execute(
            """UPDATE trusted_ips
               SET status = 'revoked', revoked_at = ?, revoked_by = ?, revoke_reason = ?
               WHERE ip_address = ?""",
            (now, revoked_by, reason, ip_address),
        )


def unblock_ip(db, ip_address: str) -> None:
    """Move a revoked IP back to pending."""
    with db._get_connection() as conn:
        conn.cursor().execute(
            """UPDATE trusted_ips
               SET status = 'pending', revoked_at = NULL, revoked_by = NULL,
                   revoke_reason = NULL, access_level = NULL, trusted_at = NULL,
                   expires_at = NULL, verified_by = NULL
               WHERE ip_address = ?""",
            (ip_address,),
        )


def delete_ip(db, ip_address: str) -> None:
    """Permanently remove an IP from the database."""
    with db._get_connection() as conn:
        conn.cursor().execute(
            "DELETE FROM trusted_ips WHERE ip_address = ?", (ip_address,)
        )


def update_last_seen(db, ip_address: str) -> None:
    """Bump last_seen timestamp."""
    with db._get_connection() as conn:
        conn.cursor().execute(
            "UPDATE trusted_ips SET last_seen = ? WHERE ip_address = ?",
            (datetime.utcnow().isoformat(), ip_address),
        )


def update_ip_label(db, ip_address: str, label: str) -> None:
    """Set the user-friendly label for an IP."""
    with db._get_connection() as conn:
        conn.cursor().execute(
            "UPDATE trusted_ips SET label = ? WHERE ip_address = ?",
            (label, ip_address),
        )


def update_ip_trust_duration(db, ip_address: str, trust_duration: str) -> None:
    """Update trust duration (and recalculate expiry)."""
    delta = _DURATION_DELTAS.get(trust_duration)
    trusted_at = datetime.utcnow()
    expires_at = (trusted_at + delta).isoformat() if delta else None
    with db._get_connection() as conn:
        conn.cursor().execute(
            """UPDATE trusted_ips
               SET trust_duration = ?, expires_at = ?
               WHERE ip_address = ?""",
            (trust_duration, expires_at, ip_address),
        )


def expire_stale_ips(db) -> int:
    """Move trusted IPs past their expires_at back to pending. Returns count."""
    now = datetime.utcnow().isoformat()
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE trusted_ips
               SET status = 'pending', access_level = NULL
               WHERE status = 'trusted' AND expires_at IS NOT NULL AND expires_at < ?""",
            (now,),
        )
        return cursor.rowcount


# ---------------------------------------------------------------------------
# Listing helpers (for dashboard)
# ---------------------------------------------------------------------------

def list_ips_by_status(db, status: str, limit: int = 200) -> List[Dict[str, Any]]:
    """List IPs filtered by status."""
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM trusted_ips WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        )
        return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Connection log
# ---------------------------------------------------------------------------

def record_ip_connection(
    db,
    ip_address: str,
    service: str,
    action: str,
    user_id: Optional[str] = None,
) -> None:
    """Log a connection event."""
    with db._get_connection() as conn:
        conn.cursor().execute(
            "INSERT INTO ip_connections (ip_address, service, action, user_id) VALUES (?, ?, ?, ?)",
            (ip_address, service, action, user_id),
        )


def get_ip_connections_count_7d(db, ip_address: str) -> int:
    """Count connections for an IP in the last 7 days."""
    cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM ip_connections WHERE ip_address = ? AND timestamp > ?",
            (ip_address, cutoff),
        )
        return cursor.fetchone()[0]


def get_connection_log(
    db,
    limit: int = 200,
    ip_filter: Optional[str] = None,
    service_filter: Optional[str] = None,
    action_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve connection log with optional filters."""
    query = "SELECT * FROM ip_connections WHERE 1=1"
    params: list = []
    if ip_filter:
        query += " AND ip_address = ?"
        params.append(ip_filter)
    if service_filter:
        query += " AND service = ?"
        params.append(service_filter)
    if action_filter:
        query += " AND action = ?"
        params.append(action_filter)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Verification tokens
# ---------------------------------------------------------------------------

def create_verification_token(
    db,
    ip_address: str,
    email: str,
    expiry_minutes: int = 15,
) -> str:
    """Generate and store a verification token. Returns the token string."""
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(minutes=expiry_minutes)).isoformat()
    with db._get_connection() as conn:
        conn.cursor().execute(
            """INSERT INTO verification_tokens (token, ip_address, email, expires_at)
               VALUES (?, ?, ?, ?)""",
            (token, ip_address, email, expires_at),
        )
    return token


def validate_verification_token(db, token: str) -> Optional[Dict[str, Any]]:
    """Validate a token: exists, not expired, not used. Returns row dict or None."""
    now = datetime.utcnow().isoformat()
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM verification_tokens
               WHERE token = ? AND used = 0 AND expires_at > ?""",
            (token, now),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def mark_token_used(db, token: str) -> None:
    """Mark a verification token as used."""
    with db._get_connection() as conn:
        conn.cursor().execute(
            "UPDATE verification_tokens SET used = 1 WHERE token = ?", (token,)
        )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def is_valid_email(email: str) -> bool:
    """Validate email format against a strict regex."""
    return bool(_EMAIL_RE.match(email))


def check_ip_access(db, ip_address: str, service: str) -> Dict[str, Any]:
    """
    Core IP gate check. Returns a dict with:
      - action: "allow", "challenge", "block"
      - reason: human-readable explanation
      - ip_record: the trusted_ips row (or None)
    """
    row = get_trusted_ip(db, ip_address)

    if row is None:
        return {"action": "challenge", "reason": "unknown_ip", "ip_record": None}

    status = row["status"]

    if status == "revoked":
        return {"action": "block", "reason": "revoked", "ip_record": row}

    if status == "pending":
        return {"action": "challenge", "reason": "pending_verification", "ip_record": row}

    if status == "trusted":
        # Check expiry
        if row["expires_at"]:
            expires = datetime.fromisoformat(row["expires_at"])
            if datetime.utcnow() > expires:
                # Expire it
                expire_stale_ips(db)
                return {"action": "challenge", "reason": "expired", "ip_record": row}

        # Check access level vs service
        if service == "server-manager" and row["access_level"] != "admin":
            return {"action": "block", "reason": "insufficient_access_level", "ip_record": row}

        # All good
        update_last_seen(db, ip_address)
        return {"action": "allow", "reason": "trusted", "ip_record": row}

    return {"action": "challenge", "reason": "unknown_status", "ip_record": row}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/feuer/Documents/Projects/immich-manager && python -m pytest server-manager/tests/test_ip_gate.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Update shared/auth/__init__.py to export IP gate functions**

Add these exports to `shared/auth/__init__.py`:

```python
from .ip_gate import (
    ensure_ip_gate_tables,
    get_trusted_ip,
    insert_pending_ip,
    trust_ip,
    revoke_ip,
    unblock_ip,
    delete_ip,
    update_last_seen,
    update_ip_label,
    update_ip_trust_duration,
    expire_stale_ips,
    list_ips_by_status,
    record_ip_connection,
    get_ip_connections_count_7d,
    get_connection_log,
    create_verification_token,
    validate_verification_token,
    mark_token_used,
    is_valid_email,
    check_ip_access,
)
```

- [ ] **Step 6: Commit**

```bash
git add shared/auth/ip_gate.py shared/auth/__init__.py server-manager/tests/test_ip_gate.py
git commit -m "feat(ip-gate): add core IP gate module with DB operations and tests"
```

---

### Task 2: Configuration

**Files:**
- Modify: `server-manager/src/config.py` (add IPGateConfig and CloudflareConfig)
- Test: `server-manager/tests/test_ip_gate.py` (add config test)

- [ ] **Step 1: Write failing test for config loading**

Append to `server-manager/tests/test_ip_gate.py`:

```python
def test_ip_gate_config_defaults():
    from server_manager_config import IPGateConfig
    cfg = IPGateConfig()
    assert cfg.enabled is True
    assert cfg.token_expiry_minutes == 15
    assert cfg.cloudflare.enabled is False
```

Note: This test imports from a helper — we'll use the actual config module. Adjust import path to match the project's test setup for config:

```python
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from config import IPGateConfig
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/feuer/Documents/Projects/immich-manager && python -m pytest server-manager/tests/test_ip_gate.py::test_ip_gate_config_defaults -v`
Expected: FAIL — `ImportError: cannot import name 'IPGateConfig'`

- [ ] **Step 3: Add config classes to server-manager/src/config.py**

Add before the `Config` class (after `AutoUpdateConfig`):

```python
class CloudflareConfig(BaseModel):
    """Cloudflare Zero Trust integration for IP gate"""
    enabled: bool = False
    api_token: str = ""
    account_id: str = ""
    list_name: str = "immich-trusted-ips"
    reconciliation_interval_hours: int = 6


class IPGateConfig(BaseModel):
    """IP gate security monitoring configuration"""
    enabled: bool = True
    trusted_proxy_ips: List[str] = Field(default_factory=lambda: ["127.0.0.1", "172.17.0.1"])
    token_expiry_minutes: int = 15
    email_rate_limit: str = "3/15minutes"
    verification_rate_limit: str = "5/15minutes"
    admin_email: str = ""
    cloudflare: CloudflareConfig = Field(default_factory=CloudflareConfig)
```

Add to the `Config` class:

```python
    ip_gate: IPGateConfig = Field(default_factory=IPGateConfig)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/feuer/Documents/Projects/immich-manager && python -m pytest server-manager/tests/test_ip_gate.py::test_ip_gate_config_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server-manager/src/config.py server-manager/tests/test_ip_gate.py
git commit -m "feat(ip-gate): add IPGateConfig and CloudflareConfig to config"
```

---

### Task 3: IP Gate Middleware

**Files:**
- Create: `server-manager/src/ip_gate_middleware.py`
- Test: `server-manager/tests/test_ip_gate_middleware.py`

- [ ] **Step 1: Write failing tests for middleware**

```python
# server-manager/tests/test_ip_gate_middleware.py
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ip_gate_middleware import get_client_ip, EXEMPT_PATHS, is_exempt_path


def test_get_client_ip_direct():
    """Without proxy, use request.client.host."""
    request = MagicMock()
    request.client.host = "1.2.3.4"
    request.headers = {}
    assert get_client_ip(request, trusted_proxies=[]) == "1.2.3.4"


def test_get_client_ip_behind_trusted_proxy():
    """Behind Caddy, use X-Forwarded-For when proxy IP is trusted."""
    request = MagicMock()
    request.client.host = "172.17.0.1"
    request.headers = {"x-forwarded-for": "98.45.12.3, 172.17.0.1"}
    assert get_client_ip(request, trusted_proxies=["172.17.0.1"]) == "98.45.12.3"


def test_get_client_ip_untrusted_proxy():
    """If proxy IP is not trusted, ignore X-Forwarded-For."""
    request = MagicMock()
    request.client.host = "10.0.0.5"
    request.headers = {"x-forwarded-for": "1.2.3.4"}
    assert get_client_ip(request, trusted_proxies=["172.17.0.1"]) == "10.0.0.5"


def test_exempt_paths():
    assert is_exempt_path("/api/ip-gate/verify/abc123")
    assert is_exempt_path("/api/ip-gate/status")
    assert is_exempt_path("/api/ip-gate/challenge")
    assert is_exempt_path("/health")
    assert not is_exempt_path("/api/status")
    assert not is_exempt_path("/api/disks")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/feuer/Documents/Projects/immich-manager && python -m pytest server-manager/tests/test_ip_gate_middleware.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ip_gate_middleware'`

- [ ] **Step 3: Implement the middleware**

```python
# server-manager/src/ip_gate_middleware.py
"""
IP Gate middleware for FastAPI.

Runs before auth middleware. Checks every request's IP against the trusted_ips
table. Unknown/pending IPs are redirected to the challenge page. Revoked IPs
get a hard 403.
"""

import logging
from typing import List, Optional

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

EXEMPT_PATHS = [
    "/api/ip-gate/verify/",
    "/api/ip-gate/status",
    "/api/ip-gate/challenge",
    "/health",
    "/ip-challenge",       # frontend challenge page route
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
            # Take the first (leftmost) IP — the original client
            return forwarded.split(",")[0].strip()

    return client_host


class IPGateMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces IP verification before allowing access.

    Requires `app.state.ip_gate_db` and `app.state.ip_gate_config` to be set.
    """

    async def dispatch(self, request: Request, call_next):
        # Check if IP gate is enabled
        ip_gate_config = getattr(request.app.state, "ip_gate_config", None)
        if not ip_gate_config or not ip_gate_config.enabled:
            return await call_next(request)

        # Skip exempt paths
        if is_exempt_path(request.url.path):
            return await call_next(request)

        # Skip static files
        if request.url.path.startswith("/assets/") or request.url.path.startswith("/static/"):
            return await call_next(request)

        db = getattr(request.app.state, "ip_gate_db", None)
        if not db:
            logger.warning("IP gate DB not initialized, allowing request")
            return await call_next(request)

        trusted_proxies = ip_gate_config.trusted_proxy_ips
        client_ip = get_client_ip(request, trusted_proxies)

        # Import here to avoid circular imports
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

        # For API requests, return JSON; for browser requests, redirect
        if request.headers.get("accept", "").startswith("application/json"):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "IP verification required",
                    "challenge_url": "/ip-challenge",
                },
            )
        return RedirectResponse(url="/ip-challenge", status_code=303)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/feuer/Documents/Projects/immich-manager && python -m pytest server-manager/tests/test_ip_gate_middleware.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add server-manager/src/ip_gate_middleware.py server-manager/tests/test_ip_gate_middleware.py
git commit -m "feat(ip-gate): add IP gate middleware with proxy-aware IP extraction"
```

---

### Task 4: API Routes — Challenge & Verification

**Files:**
- Create: `server-manager/src/ip_gate_routes.py`
- Test: `server-manager/tests/test_ip_gate_routes.py`

- [ ] **Step 1: Write failing tests for challenge and verification endpoints**

```python
# server-manager/tests/test_ip_gate_routes.py
import pytest
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.auth.ip_gate import ensure_ip_gate_tables, insert_pending_ip, get_trusted_ip


class FakeDB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def _get_connection(self):
        from contextlib import contextmanager

        @contextmanager
        def ctx():
            yield self.conn
        return ctx()


@pytest.fixture
def app_with_db():
    """Create a FastAPI app with IP gate routes and a test DB."""
    from fastapi import FastAPI
    from ip_gate_routes import ip_gate_router

    app = FastAPI()
    db = FakeDB()
    ensure_ip_gate_tables(db)

    app.state.ip_gate_db = db
    app.state.ip_gate_config = MagicMock(
        enabled=True,
        token_expiry_minutes=15,
        trusted_proxy_ips=["127.0.0.1"],
    )
    app.state.alert_manager = None
    app.state.immich_api_url = "http://localhost:2283/api"

    app.include_router(ip_gate_router)
    return app, db


@pytest.fixture
def client(app_with_db):
    app, db = app_with_db
    return TestClient(app), db


def test_status_unknown_ip(client):
    tc, db = client
    resp = tc.get("/api/ip-gate/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unknown"


def test_status_pending_ip(client):
    tc, db = client
    insert_pending_ip(db, "testclient")  # TestClient uses "testclient" as host
    resp = tc.get("/api/ip-gate/status")
    data = resp.json()
    assert data["status"] == "pending"


def test_challenge_submit_invalid_email(client):
    tc, db = client
    resp = tc.post("/api/ip-gate/challenge", json={"email": "not-an-email"})
    assert resp.status_code == 400


def test_challenge_submit_valid_email_no_immich_user(client):
    tc, db = client
    with patch("ip_gate_routes.validate_immich_email") as mock_validate:
        mock_validate.return_value = None
        resp = tc.post("/api/ip-gate/challenge", json={"email": "user@example.com"})
        # Should return 200 regardless (no info leak)
        assert resp.status_code == 200
        assert "verification email" in resp.json()["message"].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/feuer/Documents/Projects/immich-manager && python -m pytest server-manager/tests/test_ip_gate_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ip_gate_routes'`

- [ ] **Step 3: Implement the routes**

```python
# server-manager/src/ip_gate_routes.py
"""
API routes for IP gate: challenge page submission, token verification,
IP status polling, and admin management CRUD.
"""

import logging
import hmac
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from shared.auth.ip_gate import (
    get_trusted_ip,
    insert_pending_ip,
    trust_ip,
    revoke_ip,
    unblock_ip,
    delete_ip,
    update_ip_label,
    update_ip_trust_duration,
    list_ips_by_status,
    record_ip_connection,
    get_ip_connections_count_7d,
    get_connection_log,
    create_verification_token,
    validate_verification_token,
    mark_token_used,
    is_valid_email,
    check_ip_access,
)
from shared.auth import (
    Role, extract_token, validate_immich_token, get_or_create_user,
)

logger = logging.getLogger(__name__)

ip_gate_router = APIRouter(prefix="/api/ip-gate", tags=["ip-gate"])
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
    db = getattr(request.app.state, "ip_gate_db", None)
    if not db:
        raise HTTPException(status_code=503, detail="IP gate not initialized")
    return db


def _get_client_ip(request: Request) -> str:
    from .ip_gate_middleware import get_client_ip
    ip_gate_config = getattr(request.app.state, "ip_gate_config", None)
    proxies = ip_gate_config.trusted_proxy_ips if ip_gate_config else []
    return get_client_ip(request, proxies)


def _require_admin_for_management(request: Request):
    """Validate that the requesting user is an admin. Used for management endpoints."""
    token = extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    immich_api_url = getattr(request.app.state, "immich_api_url", None)
    if not immich_api_url:
        raise HTTPException(status_code=503, detail="Immich API URL not configured")
    immich_user = validate_immich_token(immich_api_url, token)
    if not immich_user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    db = _get_db(request)
    local_user, _ = get_or_create_user(db, immich_user, "user")
    if Role[local_user.get("role", "guest").upper()] < Role.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return immich_user


def validate_immich_email(api_url: str, email: str) -> Optional[Dict[str, Any]]:
    """
    Check if an email corresponds to an Immich user.
    Uses the admin API to search users by email.
    Returns user dict or None.
    """
    import requests as http_requests
    try:
        # Use the server's API key to look up users
        import os
        api_key = os.environ.get("IMMICH_API_KEY", "")
        if not api_key:
            logger.warning("IMMICH_API_KEY not set, cannot validate email")
            return None
        resp = http_requests.get(
            f"{api_url}/users",
            headers={"x-api-key": api_key},
            timeout=5,
        )
        if resp.status_code != 200:
            return None
        users = resp.json()
        for user in users:
            # Constant-time comparison to prevent timing attacks
            if hmac.compare_digest(user.get("email", "").lower(), email.lower()):
                return user
        return None
    except Exception as e:
        logger.error("Failed to validate email against Immich: %s", e)
        return None


# ---------------------------------------------------------------------------
# Public endpoints (no auth required — these are used during the challenge)
# ---------------------------------------------------------------------------

@ip_gate_router.get("/status")
async def ip_gate_status(request: Request):
    """Check if the requesting IP is trusted, pending, or unknown."""
    db = _get_db(request)
    client_ip = _get_client_ip(request)
    row = get_trusted_ip(db, client_ip)
    if row is None:
        return {"status": "unknown", "ip": client_ip}
    return {"status": row["status"], "ip": client_ip}


@ip_gate_router.post("/challenge")
@limiter.limit("3/15minutes")
async def submit_challenge(request: Request, body: ChallengeRequest):
    """
    Submit an email for IP verification.
    Always returns the same response regardless of whether the email exists
    (prevents user enumeration).
    """
    db = _get_db(request)
    client_ip = _get_client_ip(request)

    if not is_valid_email(body.email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    # Ensure IP is in the table
    insert_pending_ip(db, client_ip, source="web")

    # Check if email matches an Immich user
    immich_api_url = getattr(request.app.state, "immich_api_url", None)
    immich_user = None
    if immich_api_url:
        immich_user = validate_immich_email(immich_api_url, body.email)

    if immich_user:
        # Generate verification token
        ip_gate_config = getattr(request.app.state, "ip_gate_config", None)
        expiry = ip_gate_config.token_expiry_minutes if ip_gate_config else 15
        token = create_verification_token(db, client_ip, body.email, expiry)

        # Send verification email
        alert_manager = getattr(request.app.state, "alert_manager", None)
        if alert_manager:
            base_url = getattr(request.app.state, "public_url", "")
            await _send_verification_email(
                alert_manager, body.email, client_ip, token, base_url
            )
            # Send Discord alert
            alert_manager.send_discord(
                "New IP Verification Request",
                f"IP `{client_ip}` requested verification.\nUser: `{body.email}`\nService: web",
                "warning",
            )

    # Always return the same response
    return {
        "message": "A verification email has been sent if the account exists. Please check your email.",
    }


@ip_gate_router.get("/verify/{token}")
@limiter.limit("5/15minutes")
async def verify_token(request: Request, token: str, duration: str = "24h"):
    """
    Verify an IP via email link click.
    Sets the IP as trusted with the chosen duration.
    """
    db = _get_db(request)

    valid_durations = {"24h", "7d", "30d", "90d", "permanent"}
    if duration not in valid_durations:
        raise HTTPException(status_code=400, detail="Invalid duration")

    token_row = validate_verification_token(db, token)
    if not token_row:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    ip_address = token_row["ip_address"]
    email = token_row["email"]

    # Determine access level from user's RBAC role
    immich_api_url = getattr(request.app.state, "immich_api_url", None)
    access_level = "user"
    if immich_api_url:
        immich_user = validate_immich_email(immich_api_url, email)
        if immich_user:
            local_user, _ = get_or_create_user(db, immich_user, "user")
            if Role[local_user.get("role", "guest").upper()] >= Role.ADMIN:
                access_level = "admin"

    # Trust the IP
    trust_ip(db, ip_address, access_level=access_level,
             trust_duration=duration, verified_by=email)
    mark_token_used(db, token)
    record_ip_connection(db, ip_address, "server-manager", "allowed", user_id=email)

    # Notify about admin IP verification for Cloudflare
    if access_level == "admin":
        alert_manager = getattr(request.app.state, "alert_manager", None)
        if alert_manager:
            await _send_cloudflare_notification(alert_manager, ip_address, email, request)

    logger.info("IP %s verified by %s (access=%s, duration=%s)",
                ip_address, email, access_level, duration)

    return {
        "message": f"IP {ip_address} has been verified and trusted for {duration}.",
        "access_level": access_level,
        "redirect": "/",
    }


# ---------------------------------------------------------------------------
# Admin management endpoints (require auth + admin role)
# ---------------------------------------------------------------------------

@ip_gate_router.get("/management/trusted")
async def list_trusted(request: Request):
    """List all trusted IPs with 7-day connection counts."""
    _require_admin_for_management(request)
    db = _get_db(request)
    ips = list_ips_by_status(db, "trusted")
    for ip in ips:
        ip["connection_count_7d"] = get_ip_connections_count_7d(db, ip["ip_address"])
    return {"ips": ips}


@ip_gate_router.get("/management/pending")
async def list_pending(request: Request):
    """List all pending IPs."""
    _require_admin_for_management(request)
    db = _get_db(request)
    return {"ips": list_ips_by_status(db, "pending")}


@ip_gate_router.get("/management/revoked")
async def list_revoked(request: Request):
    """List all blacklisted IPs."""
    _require_admin_for_management(request)
    db = _get_db(request)
    return {"ips": list_ips_by_status(db, "revoked")}


@ip_gate_router.get("/management/connections")
async def list_connections(
    request: Request,
    ip: Optional[str] = None,
    service: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 200,
):
    """List connection log with optional filters."""
    _require_admin_for_management(request)
    db = _get_db(request)
    return {"connections": get_connection_log(db, limit, ip, service, action)}


@ip_gate_router.post("/management/approve")
async def manual_approve(request: Request, body: ManualApproveRequest):
    """Admin manually approves an IP (bypasses email flow)."""
    admin = _require_admin_for_management(request)
    db = _get_db(request)

    # Ensure IP exists in table
    insert_pending_ip(db, body.ip_address, source="web")

    trust_ip(db, body.ip_address, access_level=body.access_level,
             trust_duration=body.trust_duration,
             verified_by=admin.get("email", "admin"))

    if body.label:
        update_ip_label(db, body.ip_address, body.label)

    record_ip_connection(db, body.ip_address, "server-manager", "allowed",
                         user_id=admin.get("email"))
    logger.info("Admin %s manually approved IP %s", admin.get("email"), body.ip_address)
    return {"status": "approved", "ip": body.ip_address}


@ip_gate_router.post("/management/revoke")
async def revoke(request: Request, body: RevokeRequest):
    """Admin revokes (blacklists) an IP."""
    admin = _require_admin_for_management(request)
    db = _get_db(request)
    revoke_ip(db, body.ip_address, revoked_by=admin.get("email", "admin"),
              reason=body.reason)
    logger.info("Admin %s revoked IP %s: %s", admin.get("email"), body.ip_address, body.reason)
    return {"status": "revoked", "ip": body.ip_address}


@ip_gate_router.post("/management/unblock")
async def unblock(request: Request, body: RevokeRequest):
    """Admin moves a revoked IP back to pending."""
    _require_admin_for_management(request)
    db = _get_db(request)
    unblock_ip(db, body.ip_address)
    return {"status": "unblocked", "ip": body.ip_address}


@ip_gate_router.delete("/management/{ip_address}")
async def delete_ip_entry(request: Request, ip_address: str):
    """Admin permanently deletes an IP record."""
    _require_admin_for_management(request)
    db = _get_db(request)
    delete_ip(db, ip_address)
    return {"status": "deleted", "ip": ip_address}


@ip_gate_router.put("/management/{ip_address}")
async def update_ip(request: Request, ip_address: str, body: UpdateIPRequest):
    """Admin updates label or trust duration for an IP."""
    _require_admin_for_management(request)
    db = _get_db(request)
    if body.label is not None:
        update_ip_label(db, ip_address, body.label)
    if body.trust_duration is not None:
        update_ip_trust_duration(db, ip_address, body.trust_duration)
    return {"status": "updated", "ip": ip_address}


# ---------------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------------

async def _send_verification_email(
    alert_manager,
    email: str,
    ip_address: str,
    token: str,
    base_url: str,
):
    """Send verification email with trust duration options."""
    verify_base = f"{base_url}/api/ip-gate/verify/{token}"
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    body = f"""Someone is trying to access Immich from {ip_address} at {now}.

If this is you, choose how long to trust this IP:

  Trust for 24 hours: {verify_base}?duration=24h
  Trust for 7 days:   {verify_base}?duration=7d
  Trust for 30 days:  {verify_base}?duration=30d
  Trust permanently:  {verify_base}?duration=permanent

If this wasn't you, ignore this email. The IP will remain blocked."""

    await alert_manager.send_email(
        "New login attempt from unrecognized IP",
        body,
        "warning",
    )


async def _send_cloudflare_notification(alert_manager, ip_address, email, request):
    """Send notification about admin IP verification for Cloudflare update."""
    ip_gate_config = getattr(request.app.state, "ip_gate_config", None)
    cf_enabled = ip_gate_config and ip_gate_config.cloudflare.enabled

    if cf_enabled:
        # Automated sync will handle it — just notify
        alert_manager.send_discord(
            "Admin IP Verified — Cloudflare Syncing",
            f"IP `{ip_address}` verified by `{email}`.\n"
            "Cloudflare Access list will be updated automatically.",
            "info",
        )
    else:
        # Manual mode — tell admin what to do
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/feuer/Documents/Projects/immich-manager && python -m pytest server-manager/tests/test_ip_gate_routes.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add server-manager/src/ip_gate_routes.py server-manager/tests/test_ip_gate_routes.py
git commit -m "feat(ip-gate): add challenge, verification, and admin management API routes"
```

---

### Task 5: Integrate IP Gate into Server Manager Startup

**Files:**
- Modify: `server-manager/src/main.py`

- [ ] **Step 1: Add imports to main.py**

At the top of `main.py`, after the existing imports (around line 41), add:

```python
from .ip_gate_middleware import IPGateMiddleware
from .ip_gate_routes import ip_gate_router
from shared.auth.ip_gate import ensure_ip_gate_tables as ensure_ip_gate_db
```

- [ ] **Step 2: Register the router**

After `app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)` (around line 59), add:

```python
app.include_router(ip_gate_router)
```

- [ ] **Step 3: Add middleware registration**

After the `add_security_headers` middleware (around line 123), add the IP gate middleware. It must be added **after** CORS and security headers (Starlette middleware runs in reverse order of addition, so the last-added middleware runs first — IP gate should run after CORS headers are set):

```python
# IP gate must be added after CORS/security-headers middleware
# (Starlette dispatches in reverse: last-added runs outermost)
app.add_middleware(IPGateMiddleware)
```

- [ ] **Step 4: Initialize IP gate in startup_event**

In the `startup_event` function, after `ensure_users_table(database)` (around line 192), add:

```python
        # Initialize IP gate
        ensure_ip_gate_db(database)
        app.state.ip_gate_db = database
        app.state.ip_gate_config = config.ip_gate
        app.state.public_url = config.server.public_url
```

- [ ] **Step 5: Add expiry job to scheduler**

In the scheduler section of `startup_event`, after the existing scheduled jobs, add:

```python
        # Schedule IP gate expiry checks (every 5 minutes)
        scheduler.add_job(
            _expire_ips_job,
            'interval',
            seconds=300,
            id='ip_gate_expiry'
        )
```

And add this job function near the other job functions:

```python
async def _expire_ips_job():
    """Expire trusted IPs that have passed their expiry time."""
    if not database:
        return
    from shared.auth.ip_gate import expire_stale_ips
    count = expire_stale_ips(database)
    if count > 0:
        logger.info("Expired %d stale trusted IPs", count)
```

- [ ] **Step 6: Verify the app starts without errors**

Run: `cd /home/feuer/Documents/Projects/immich-manager/server-manager && python -c "from src.main import app; print('Import OK')"`
Expected: `Import OK` (or at least no ImportError — config file errors are expected in dev)

- [ ] **Step 7: Commit**

```bash
git add server-manager/src/main.py
git commit -m "feat(ip-gate): integrate IP gate middleware, routes, and expiry job into Server Manager"
```

---

### Task 6: Photo Curator IP Gate Client

**Files:**
- Create: `photo-curator/src/ip_gate_client.py`
- Modify: `photo-curator/src/main.py`

- [ ] **Step 1: Create the IP gate client**

```python
# photo-curator/src/ip_gate_client.py
"""
HTTP client that delegates IP gate checks to Server Manager.
Photo Curator does not access the trusted_ips DB directly.
"""

import logging
from typing import Dict, Any, Optional

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
```

- [ ] **Step 2: Add IP gate middleware to Photo Curator**

In `photo-curator/src/main.py`, after the existing middleware definitions, add a lightweight middleware that checks IPs against Server Manager:

```python
from .ip_gate_client import IPGateClient

# After app initialization and middleware setup:

@app.middleware("http")
async def ip_gate_check(request: Request, call_next):
    """Check IP against Server Manager's IP gate."""
    ip_gate_client = getattr(request.app.state, "ip_gate_client", None)
    if not ip_gate_client:
        return await call_next(request)

    # Exempt paths
    exempt = ["/health", "/api/ip-gate/", "/ip-challenge"]
    if any(request.url.path.startswith(p) for p in exempt):
        return await call_next(request)

    # Skip static files
    if request.url.path.startswith("/assets/") or request.url.path.startswith("/static/"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "0.0.0.0"
    result = ip_gate_client.check_ip(client_ip)

    if result["status"] == "trusted":
        return await call_next(request)

    if result["status"] == "revoked":
        return JSONResponse(
            status_code=403,
            content={"detail": "Access denied. This IP has been blocked."},
        )

    # pending or unknown — redirect to Server Manager challenge page
    server_manager_url = getattr(request.app.state, "server_manager_url", "")
    if request.headers.get("accept", "").startswith("application/json"):
        return JSONResponse(
            status_code=403,
            content={
                "detail": "IP verification required",
                "challenge_url": f"{server_manager_url}/ip-challenge",
            },
        )
    return RedirectResponse(url=f"{server_manager_url}/ip-challenge", status_code=303)
```

- [ ] **Step 3: Initialize IP gate client in Photo Curator startup**

In the Photo Curator startup function, add:

```python
    # Initialize IP gate client (checks IPs against Server Manager)
    server_manager_url = config.get("server_manager_url", "http://localhost:8080")
    app.state.ip_gate_client = IPGateClient(server_manager_url)
    app.state.server_manager_url = server_manager_url
```

- [ ] **Step 4: Add server_manager_url to Photo Curator config**

In the Photo Curator config YAML, add:

```yaml
server_manager_url: "http://localhost:8080"
```

- [ ] **Step 5: Commit**

```bash
git add photo-curator/src/ip_gate_client.py photo-curator/src/main.py
git commit -m "feat(ip-gate): add IP gate client to Photo Curator, delegates checks to Server Manager"
```

---

### Task 7: SSH Monitor Service

**Files:**
- Create: `server-manager/src/ip_gate_ssh_monitor.py`

- [ ] **Step 1: Write the SSH monitor script**

```python
# server-manager/src/ip_gate_ssh_monitor.py
"""
SSH login monitor for IP gate.

Watches journalctl for successful SSH logins and sends alerts for
unrecognized IPs. Does NOT block or modify firewall rules.

Run as a systemd service: ip-gate-ssh-monitor.service
"""

import sys
import re
import subprocess
import logging
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

# Add project root to path for shared library
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.auth.ip_gate import (
    ensure_ip_gate_tables,
    get_trusted_ip,
    insert_pending_ip,
    record_ip_connection,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Matches: "Accepted publickey for username from 1.2.3.4 port 54321 ssh2"
_SSH_ACCEPTED_RE = re.compile(
    r"Accepted\s+\S+\s+for\s+(\S+)\s+from\s+(\d+\.\d+\.\d+\.\d+)\s+port"
)

DB_PATH = "data/server-manager.db"


class SimpleDB:
    """Minimal DB wrapper matching the _get_connection pattern."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def send_ssh_alert(ip_address: str, ssh_user: str):
    """Send Discord + email alert for unknown SSH login."""
    try:
        # Import alert manager — need config
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from config import load_config
        from alerts import AlertManager

        config = load_config()
        alert_mgr = AlertManager(config.alerts)

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        title = "SSH login from unrecognized IP"
        message = (
            f"User `{ssh_user}` logged in via SSH from `{ip_address}` at {now}.\n\n"
            "This is an alert only -- no automatic action has been taken.\n"
            "If this wasn't you, investigate immediately."
        )

        alert_mgr.send_discord(title, message, "critical")

        # Email is async, but we're in a sync context — use asyncio
        import asyncio
        asyncio.run(alert_mgr.send_email(title, message, "critical"))

    except Exception as e:
        logger.error("Failed to send SSH alert: %s", e)


def process_line(line: str, db: SimpleDB):
    """Process a single journalctl line."""
    match = _SSH_ACCEPTED_RE.search(line)
    if not match:
        return

    ssh_user = match.group(1)
    ip_address = match.group(2)

    logger.info("SSH login detected: user=%s ip=%s", ssh_user, ip_address)

    row = get_trusted_ip(db, ip_address)

    if row and row["status"] == "trusted":
        record_ip_connection(db, ip_address, "ssh", "allowed", user_id=ssh_user)
        logger.info("SSH from trusted IP %s (user=%s)", ip_address, ssh_user)
    else:
        insert_pending_ip(db, ip_address, source="ssh")
        record_ip_connection(db, ip_address, "ssh", "alert_sent", user_id=ssh_user)
        logger.warning("SSH from UNKNOWN IP %s (user=%s) — sending alert", ip_address, ssh_user)
        send_ssh_alert(ip_address, ssh_user)


def main():
    """Main loop: follow journalctl for SSH events."""
    logger.info("Starting SSH monitor...")

    db = SimpleDB(DB_PATH)
    ensure_ip_gate_tables(db)

    cmd = ["journalctl", "-u", "ssh", "-f", "--no-pager", "-o", "short"]
    logger.info("Running: %s", " ".join(cmd))

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    try:
        for line in proc.stdout:
            line = line.strip()
            if line:
                process_line(line, db)
    except KeyboardInterrupt:
        logger.info("SSH monitor stopped by user")
    finally:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the SSH log line parser manually**

Run: `cd /home/feuer/Documents/Projects/immich-manager && python -c "
import re
pat = re.compile(r'Accepted\s+\S+\s+for\s+(\S+)\s+from\s+(\d+\.\d+\.\d+\.\d+)\s+port')
line = 'Apr 03 10:23:45 myserver sshd[12345]: Accepted publickey for feuer from 192.168.1.100 port 54321 ssh2'
m = pat.search(line)
assert m.group(1) == 'feuer'
assert m.group(2) == '192.168.1.100'
print('SSH parser OK')
"`
Expected: `SSH parser OK`

- [ ] **Step 3: Commit**

```bash
git add server-manager/src/ip_gate_ssh_monitor.py
git commit -m "feat(ip-gate): add SSH login monitor script with alert-only behavior"
```

---

### Task 8: Cloudflare Integration Module

**Files:**
- Create: `server-manager/src/ip_gate_cloudflare.py`

- [ ] **Step 1: Write the Cloudflare integration**

```python
# server-manager/src/ip_gate_cloudflare.py
"""
Optional Cloudflare Zero Trust integration for IP gate.

When enabled, syncs admin-trusted IPs to a Cloudflare Access IP list.
Requires a paid Teams Standard plan for the Lists API.
"""

import logging
from typing import List, Optional, Dict, Any

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
            # List existing lists
            resp = self.session.get(
                f"{_CF_API_BASE}/accounts/{self.account_id}/rules/lists",
                timeout=10,
            )
            resp.raise_for_status()
            for lst in resp.json().get("result", []):
                if lst["name"] == self.list_name:
                    self._list_id = lst["id"]
                    return self._list_id

            # Create the list
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
            # Get all items to find the one to delete
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
                return True  # Not an error — already removed

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
            # Get current Cloudflare list items
            resp = self.session.get(
                f"{_CF_API_BASE}/accounts/{self.account_id}/rules/lists/{list_id}/items",
                timeout=10,
            )
            resp.raise_for_status()

            cf_items = {item["ip"]: item["id"] for item in resp.json().get("result", [])}
            cf_ips = set(cf_items.keys())
            local_ips = set(trusted_admin_ips)

            # Add missing
            to_add = local_ips - cf_ips
            for ip in to_add:
                self.add_ip(ip)

            # Remove stale
            to_remove = cf_ips - local_ips
            for ip in to_remove:
                self.remove_ip(ip)

            if to_add or to_remove:
                logger.info("Cloudflare sync: added %d, removed %d", len(to_add), len(to_remove))
            return True

        except Exception as e:
            logger.error("Cloudflare sync failed: %s", e)
            return False
```

- [ ] **Step 2: Commit**

```bash
git add server-manager/src/ip_gate_cloudflare.py
git commit -m "feat(ip-gate): add Cloudflare Zero Trust IP list sync module"
```

---

### Task 9: Frontend — Challenge Page

**Files:**
- Create: `server-manager/frontend/src/pages/ChallengePage.jsx`

- [ ] **Step 1: Create the challenge page component**

```jsx
// server-manager/frontend/src/pages/ChallengePage.jsx
import { useState, useEffect, useCallback } from 'react'
import { ShieldExclamationIcon, EnvelopeIcon } from '@heroicons/react/24/outline'

export default function ChallengePage() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [ipStatus, setIpStatus] = useState(null)
  const [clientIp, setClientIp] = useState('')

  const checkStatus = useCallback(async () => {
    try {
      const resp = await fetch('/api/ip-gate/status')
      const data = await resp.json()
      setIpStatus(data.status)
      setClientIp(data.ip || '')
      if (data.status === 'trusted') {
        window.location.href = '/'
      }
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    checkStatus()
    const interval = setInterval(checkStatus, 5000)
    return () => clearInterval(interval)
  }, [checkStatus])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)

    try {
      const resp = await fetch('/api/ip-gate/challenge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      if (resp.ok) {
        setSubmitted(true)
      } else {
        const data = await resp.json()
        setError(data.detail || 'Failed to submit')
      }
    } catch (err) {
      setError('Network error. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-immich-bg flex items-center justify-center p-4">
      <div className="bg-immich-surface border border-immich-border rounded-2xl p-8 max-w-md w-full">
        <div className="flex items-center gap-3 mb-6">
          <ShieldExclamationIcon className="w-8 h-8 text-yellow-400" />
          <h1 className="text-xl font-semibold text-immich-text">
            IP Verification Required
          </h1>
        </div>

        <p className="text-immich-muted text-sm mb-2">
          Your IP address <span className="font-mono text-immich-text">{clientIp}</span> has
          not been verified.
        </p>

        {!submitted ? (
          <form onSubmit={handleSubmit} className="mt-6">
            <label className="block text-sm text-immich-muted mb-2">
              Enter your email to receive a verification link:
            </label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <EnvelopeIcon className="w-5 h-5 text-immich-muted absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  className="w-full pl-10 pr-3 py-2 bg-immich-bg border border-immich-border rounded-lg
                             text-immich-text placeholder-immich-muted/50 text-sm
                             focus:outline-none focus:border-blue-500"
                />
              </div>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50
                           text-white text-sm font-medium rounded-lg transition-colors"
              >
                {submitting ? 'Sending...' : 'Verify'}
              </button>
            </div>
            {error && (
              <p className="mt-2 text-red-400 text-sm">{error}</p>
            )}
          </form>
        ) : (
          <div className="mt-6">
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
              <p className="text-blue-300 text-sm">
                A verification email has been sent if the account exists. Please check
                your email and click the approval link.
              </p>
            </div>
            <button
              onClick={checkStatus}
              className="mt-4 w-full px-4 py-2 bg-immich-bg border border-immich-border
                         hover:border-blue-500 text-immich-text text-sm rounded-lg transition-colors"
            >
              Refresh Status
            </button>
            {ipStatus === 'pending' && (
              <p className="mt-2 text-immich-muted text-xs text-center">
                Status: waiting for verification...
              </p>
            )}
          </div>
        )}

        <p className="mt-6 text-immich-muted text-xs">
          If this wasn't you, ignore this page. Contact your administrator if you
          believe this is an error.
        </p>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add the challenge page route to App.jsx**

This app doesn't use React Router — it's a single-page dashboard. The challenge page needs to be served at `/ip-challenge`. The simplest approach: check `window.location.pathname` and conditionally render:

In `App.jsx`, add the import and a path check:

```jsx
import ChallengePage from './pages/ChallengePage.jsx'

export default function App() {
  // Serve challenge page at /ip-challenge
  if (window.location.pathname === '/ip-challenge') {
    return <ChallengePage />
  }

  return (
    <ErrorBoundary>
      {/* ... existing dashboard ... */}
    </ErrorBoundary>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add server-manager/frontend/src/pages/ChallengePage.jsx server-manager/frontend/src/App.jsx
git commit -m "feat(ip-gate): add challenge page for IP verification flow"
```

---

### Task 10: Frontend — IP Management Dashboard

**Files:**
- Create: `server-manager/frontend/src/hooks/useIPManagement.js`
- Create: `server-manager/frontend/src/components/IPManagement.jsx`
- Modify: `server-manager/frontend/src/App.jsx` (add IPManagement to dashboard)

- [ ] **Step 1: Create the TanStack Query hooks**

```javascript
// server-manager/frontend/src/hooks/useIPManagement.js
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

const fetcher = (url) => fetch(url).then((r) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
})

const poster = (url, body) => fetch(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
}).then((r) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
})

const putter = (url, body) => fetch(url, {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
}).then((r) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
})

const deleter = (url) => fetch(url, { method: 'DELETE' }).then((r) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
})

export function useTrustedIPs() {
  return useQuery({
    queryKey: ['ip-gate', 'trusted'],
    queryFn: () => fetcher('/api/ip-gate/management/trusted'),
    refetchInterval: 30000,
  })
}

export function usePendingIPs() {
  return useQuery({
    queryKey: ['ip-gate', 'pending'],
    queryFn: () => fetcher('/api/ip-gate/management/pending'),
    refetchInterval: 15000,
  })
}

export function useRevokedIPs() {
  return useQuery({
    queryKey: ['ip-gate', 'revoked'],
    queryFn: () => fetcher('/api/ip-gate/management/revoked'),
  })
}

export function useConnectionLog(filters = {}) {
  const params = new URLSearchParams()
  if (filters.ip) params.set('ip', filters.ip)
  if (filters.service) params.set('service', filters.service)
  if (filters.action) params.set('action', filters.action)
  const qs = params.toString()
  return useQuery({
    queryKey: ['ip-gate', 'connections', filters],
    queryFn: () => fetcher(`/api/ip-gate/management/connections${qs ? '?' + qs : ''}`),
    refetchInterval: 15000,
  })
}

export function useApproveIP() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => poster('/api/ip-gate/management/approve', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ip-gate'] })
    },
  })
}

export function useRevokeIP() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => poster('/api/ip-gate/management/revoke', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ip-gate'] })
    },
  })
}

export function useUnblockIP() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => poster('/api/ip-gate/management/unblock', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ip-gate'] })
    },
  })
}

export function useDeleteIP() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ip) => deleter(`/api/ip-gate/management/${encodeURIComponent(ip)}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ip-gate'] })
    },
  })
}

export function useUpdateIP() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ ip, ...body }) => putter(`/api/ip-gate/management/${encodeURIComponent(ip)}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ip-gate'] })
    },
  })
}
```

- [ ] **Step 2: Create the IPManagement component**

```jsx
// server-manager/frontend/src/components/IPManagement.jsx
import { useState } from 'react'
import { ShieldCheckIcon } from '@heroicons/react/24/outline'
import {
  useTrustedIPs, usePendingIPs, useRevokedIPs, useConnectionLog,
  useApproveIP, useRevokeIP, useUnblockIP, useDeleteIP, useUpdateIP,
} from '../hooks/useIPManagement.js'

const TABS = ['trusted', 'pending', 'blacklisted', 'connections']
const TAB_LABELS = { trusted: 'Trusted', pending: 'Pending', blacklisted: 'Blacklisted', connections: 'Connections' }

const DURATION_OPTIONS = ['24h', '7d', '30d', '90d', 'permanent']

function timeAgo(ts) {
  if (!ts) return '—'
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

function TrustedTab() {
  const { data, isLoading } = useTrustedIPs()
  const revokeMut = useRevokeIP()
  const updateMut = useUpdateIP()
  const [editingIp, setEditingIp] = useState(null)
  const [editLabel, setEditLabel] = useState('')
  const [editDuration, setEditDuration] = useState('')
  const [revokeIp, setRevokeIp] = useState(null)
  const [revokeReason, setRevokeReason] = useState('')

  if (isLoading) return <p className="text-immich-muted text-sm">Loading...</p>
  const ips = data?.ips || []

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-immich-muted text-left border-b border-immich-border">
            <th className="pb-2 pr-4">IP Address</th>
            <th className="pb-2 pr-4">Label</th>
            <th className="pb-2 pr-4">User</th>
            <th className="pb-2 pr-4">Access</th>
            <th className="pb-2 pr-4">Duration</th>
            <th className="pb-2 pr-4">Expires</th>
            <th className="pb-2 pr-4">Last Seen</th>
            <th className="pb-2 pr-4">7d Conns</th>
            <th className="pb-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {ips.map((ip) => (
            <tr key={ip.ip_address} className="border-b border-immich-border/50">
              <td className="py-2 pr-4 font-mono text-xs">{ip.ip_address}</td>
              <td className="py-2 pr-4">{ip.label || '—'}</td>
              <td className="py-2 pr-4 text-xs">{ip.verified_by || '—'}</td>
              <td className="py-2 pr-4">
                <span className={`text-xs px-2 py-0.5 rounded ${ip.access_level === 'admin' ? 'bg-red-500/20 text-red-300' : 'bg-blue-500/20 text-blue-300'}`}>
                  {ip.access_level}
                </span>
              </td>
              <td className="py-2 pr-4 text-xs">{ip.trust_duration}</td>
              <td className="py-2 pr-4 text-xs">{ip.expires_at ? new Date(ip.expires_at).toLocaleDateString() : 'Never'}</td>
              <td className="py-2 pr-4 text-xs">{timeAgo(ip.last_seen)}</td>
              <td className="py-2 pr-4 text-xs">{ip.connection_count_7d ?? 0}</td>
              <td className="py-2 flex gap-2">
                <button
                  onClick={() => { setEditingIp(ip.ip_address); setEditLabel(ip.label || ''); setEditDuration(ip.trust_duration || '24h') }}
                  className="text-xs text-blue-400 hover:text-blue-300"
                >Edit</button>
                <button
                  onClick={() => setRevokeIp(ip.ip_address)}
                  className="text-xs text-red-400 hover:text-red-300"
                >Revoke</button>
              </td>
            </tr>
          ))}
          {ips.length === 0 && (
            <tr><td colSpan={9} className="py-4 text-center text-immich-muted">No trusted IPs</td></tr>
          )}
        </tbody>
      </table>

      {/* Edit modal */}
      {editingIp && (
        <div className="mt-4 p-4 bg-immich-bg border border-immich-border rounded-lg">
          <h4 className="text-sm font-medium mb-2">Edit {editingIp}</h4>
          <div className="flex gap-3 items-end">
            <div>
              <label className="text-xs text-immich-muted block mb-1">Label</label>
              <input value={editLabel} onChange={(e) => setEditLabel(e.target.value)}
                className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text" />
            </div>
            <div>
              <label className="text-xs text-immich-muted block mb-1">Duration</label>
              <select value={editDuration} onChange={(e) => setEditDuration(e.target.value)}
                className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text">
                {DURATION_OPTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <button onClick={() => { updateMut.mutate({ ip: editingIp, label: editLabel, trust_duration: editDuration }); setEditingIp(null) }}
              className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded">Save</button>
            <button onClick={() => setEditingIp(null)}
              className="px-3 py-1 text-immich-muted hover:text-immich-text text-sm">Cancel</button>
          </div>
        </div>
      )}

      {/* Revoke modal */}
      {revokeIp && (
        <div className="mt-4 p-4 bg-immich-bg border border-red-800/50 rounded-lg">
          <h4 className="text-sm font-medium text-red-400 mb-2">Revoke {revokeIp}</h4>
          <input value={revokeReason} onChange={(e) => setRevokeReason(e.target.value)}
            placeholder="Reason (optional)"
            className="w-full px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text mb-2" />
          <div className="flex gap-2">
            <button onClick={() => { revokeMut.mutate({ ip_address: revokeIp, reason: revokeReason }); setRevokeIp(null); setRevokeReason('') }}
              className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white text-sm rounded">Confirm Revoke</button>
            <button onClick={() => { setRevokeIp(null); setRevokeReason('') }}
              className="px-3 py-1 text-immich-muted hover:text-immich-text text-sm">Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

function PendingTab() {
  const { data, isLoading } = usePendingIPs()
  const approveMut = useApproveIP()
  const revokeMut = useRevokeIP()
  const [approveIp, setApproveIp] = useState(null)
  const [approveDuration, setApproveDuration] = useState('24h')
  const [approveLevel, setApproveLevel] = useState('user')

  if (isLoading) return <p className="text-immich-muted text-sm">Loading...</p>
  const ips = data?.ips || []

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-immich-muted text-left border-b border-immich-border">
            <th className="pb-2 pr-4">IP Address</th>
            <th className="pb-2 pr-4">Source</th>
            <th className="pb-2 pr-4">First Seen</th>
            <th className="pb-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {ips.map((ip) => (
            <tr key={ip.ip_address} className="border-b border-immich-border/50">
              <td className="py-2 pr-4 font-mono text-xs">{ip.ip_address}</td>
              <td className="py-2 pr-4 text-xs">{ip.source}</td>
              <td className="py-2 pr-4 text-xs">{timeAgo(ip.created_at)}</td>
              <td className="py-2 flex gap-2">
                <button onClick={() => setApproveIp(ip.ip_address)}
                  className="text-xs text-green-400 hover:text-green-300">Approve</button>
                <button onClick={() => revokeMut.mutate({ ip_address: ip.ip_address })}
                  className="text-xs text-red-400 hover:text-red-300">Blacklist</button>
              </td>
            </tr>
          ))}
          {ips.length === 0 && (
            <tr><td colSpan={4} className="py-4 text-center text-immich-muted">No pending IPs</td></tr>
          )}
        </tbody>
      </table>

      {approveIp && (
        <div className="mt-4 p-4 bg-immich-bg border border-green-800/50 rounded-lg">
          <h4 className="text-sm font-medium text-green-400 mb-2">Approve {approveIp}</h4>
          <div className="flex gap-3 items-end">
            <div>
              <label className="text-xs text-immich-muted block mb-1">Access Level</label>
              <select value={approveLevel} onChange={(e) => setApproveLevel(e.target.value)}
                className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text">
                <option value="user">User (Photo Curator only)</option>
                <option value="admin">Admin (All services)</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-immich-muted block mb-1">Duration</label>
              <select value={approveDuration} onChange={(e) => setApproveDuration(e.target.value)}
                className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text">
                {DURATION_OPTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <button onClick={() => {
              approveMut.mutate({ ip_address: approveIp, access_level: approveLevel, trust_duration: approveDuration })
              setApproveIp(null)
            }} className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white text-sm rounded">Confirm</button>
            <button onClick={() => setApproveIp(null)}
              className="px-3 py-1 text-immich-muted hover:text-immich-text text-sm">Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

function BlacklistedTab() {
  const { data, isLoading } = useRevokedIPs()
  const unblockMut = useUnblockIP()
  const deleteMut = useDeleteIP()

  if (isLoading) return <p className="text-immich-muted text-sm">Loading...</p>
  const ips = data?.ips || []

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-immich-muted text-left border-b border-immich-border">
            <th className="pb-2 pr-4">IP Address</th>
            <th className="pb-2 pr-4">Original User</th>
            <th className="pb-2 pr-4">Date Blacklisted</th>
            <th className="pb-2 pr-4">Blacklisted By</th>
            <th className="pb-2 pr-4">Reason</th>
            <th className="pb-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {ips.map((ip) => (
            <tr key={ip.ip_address} className="border-b border-immich-border/50">
              <td className="py-2 pr-4 font-mono text-xs">{ip.ip_address}</td>
              <td className="py-2 pr-4 text-xs">{ip.verified_by || 'unknown'}</td>
              <td className="py-2 pr-4 text-xs">{ip.revoked_at ? new Date(ip.revoked_at).toLocaleDateString() : '—'}</td>
              <td className="py-2 pr-4 text-xs">{ip.revoked_by || '—'}</td>
              <td className="py-2 pr-4 text-xs">{ip.revoke_reason || '—'}</td>
              <td className="py-2 flex gap-2">
                <button onClick={() => unblockMut.mutate({ ip_address: ip.ip_address })}
                  className="text-xs text-yellow-400 hover:text-yellow-300">Unblock</button>
                <button onClick={() => deleteMut.mutate(ip.ip_address)}
                  className="text-xs text-red-400 hover:text-red-300">Delete</button>
              </td>
            </tr>
          ))}
          {ips.length === 0 && (
            <tr><td colSpan={6} className="py-4 text-center text-immich-muted">No blacklisted IPs</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

function ConnectionsTab() {
  const [filters, setFilters] = useState({})
  const { data, isLoading } = useConnectionLog(filters)
  const connections = data?.connections || []

  return (
    <div>
      <div className="flex gap-3 mb-4">
        <input placeholder="Filter by IP" onChange={(e) => setFilters(f => ({ ...f, ip: e.target.value || undefined }))}
          className="px-2 py-1 bg-immich-bg border border-immich-border rounded text-sm text-immich-text w-40" />
        <select onChange={(e) => setFilters(f => ({ ...f, service: e.target.value || undefined }))}
          className="px-2 py-1 bg-immich-bg border border-immich-border rounded text-sm text-immich-text">
          <option value="">All services</option>
          <option value="server-manager">server-manager</option>
          <option value="photo-curator">photo-curator</option>
          <option value="ssh">ssh</option>
        </select>
        <select onChange={(e) => setFilters(f => ({ ...f, action: e.target.value || undefined }))}
          className="px-2 py-1 bg-immich-bg border border-immich-border rounded text-sm text-immich-text">
          <option value="">All actions</option>
          <option value="allowed">allowed</option>
          <option value="challenged">challenged</option>
          <option value="blocked">blocked</option>
          <option value="alert_sent">alert_sent</option>
        </select>
      </div>
      {isLoading ? (
        <p className="text-immich-muted text-sm">Loading...</p>
      ) : (
        <div className="overflow-x-auto max-h-96 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-immich-surface">
              <tr className="text-immich-muted text-left border-b border-immich-border">
                <th className="pb-2 pr-4">Timestamp</th>
                <th className="pb-2 pr-4">IP Address</th>
                <th className="pb-2 pr-4">Service</th>
                <th className="pb-2 pr-4">Action</th>
                <th className="pb-2">User</th>
              </tr>
            </thead>
            <tbody>
              {connections.map((c, i) => (
                <tr key={i} className="border-b border-immich-border/50">
                  <td className="py-1.5 pr-4 text-xs">{timeAgo(c.timestamp)}</td>
                  <td className="py-1.5 pr-4 font-mono text-xs">{c.ip_address}</td>
                  <td className="py-1.5 pr-4 text-xs">{c.service}</td>
                  <td className="py-1.5 pr-4">
                    <span className={`text-xs ${
                      c.action === 'allowed' ? 'text-green-400' :
                      c.action === 'blocked' ? 'text-red-400' :
                      c.action === 'challenged' ? 'text-yellow-400' :
                      'text-orange-400'
                    }`}>{c.action}</span>
                  </td>
                  <td className="py-1.5 text-xs">{c.user_id || '—'}</td>
                </tr>
              ))}
              {connections.length === 0 && (
                <tr><td colSpan={5} className="py-4 text-center text-immich-muted">No connections logged</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function IPManagement() {
  const [activeTab, setActiveTab] = useState('trusted')

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <div className="flex items-center gap-2 mb-4">
        <ShieldCheckIcon className="w-5 h-5 text-blue-400" />
        <h2 className="text-lg font-semibold">IP Security</h2>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-immich-border">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm transition-colors border-b-2 -mb-px ${
              activeTab === tab
                ? 'text-blue-400 border-blue-400'
                : 'text-immich-muted border-transparent hover:text-immich-text'
            }`}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'trusted' && <TrustedTab />}
      {activeTab === 'pending' && <PendingTab />}
      {activeTab === 'blacklisted' && <BlacklistedTab />}
      {activeTab === 'connections' && <ConnectionsTab />}
    </div>
  )
}
```

- [ ] **Step 3: Add IPManagement to the dashboard in App.jsx**

In `App.jsx`, add the import and component between `UpdateManagement` and the closing divs:

```jsx
import IPManagement from './components/IPManagement.jsx'

// In the return, add after <UpdateManagement />:
<IPManagement />
```

- [ ] **Step 4: Build the frontend to verify no JSX errors**

Run: `cd /home/feuer/Documents/Projects/immich-manager/server-manager/frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 5: Commit**

```bash
git add server-manager/frontend/src/hooks/useIPManagement.js server-manager/frontend/src/components/IPManagement.jsx server-manager/frontend/src/App.jsx
git commit -m "feat(ip-gate): add IP management dashboard with four tabs and challenge page"
```

---

### Task 11: Systemd Service Files

**Files:**
- Create: `scripts/ip-gate-ssh-monitor.service`

- [ ] **Step 1: Create the systemd unit file**

```ini
# scripts/ip-gate-ssh-monitor.service
[Unit]
Description=IP Gate SSH Login Monitor
After=network.target immich-server-manager.service
Wants=immich-server-manager.service

[Service]
Type=simple
WorkingDirectory=/opt/immich-server-manager
ExecStart=/opt/immich-server-manager/venv/bin/python -m src.ip_gate_ssh_monitor
Restart=on-failure
RestartSec=10
User=root
Group=root

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/immich-server-manager/data
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Commit**

```bash
git add scripts/ip-gate-ssh-monitor.service
git commit -m "feat(ip-gate): add systemd service file for SSH login monitor"
```

---

### Task 12: Deploy Script Updates

**Files:**
- Modify: `scripts/deploy.sh` (if it exists, add IP gate table initialization and SSH monitor service)

- [ ] **Step 1: Check if deploy.sh exists and what it does**

Read `scripts/deploy.sh` to understand the deployment pattern.

- [ ] **Step 2: Add SSH monitor service installation to deploy script**

Add after the existing service installation section:

```bash
# Install IP gate SSH monitor service
if [ ! -f /etc/systemd/system/ip-gate-ssh-monitor.service ]; then
    cp scripts/ip-gate-ssh-monitor.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable ip-gate-ssh-monitor.service
    systemctl start ip-gate-ssh-monitor.service
    echo "IP gate SSH monitor service installed and started"
fi
```

- [ ] **Step 3: Commit**

```bash
git add scripts/deploy.sh
git commit -m "feat(ip-gate): add SSH monitor service to deploy script"
```

---

### Task 13: Send Verification Email to Specific User (Not Admin)

**Files:**
- Modify: `server-manager/src/alerts.py` (add method to send email to a specific recipient)

- [ ] **Step 1: Write failing test**

```python
# Add to server-manager/tests/test_ip_gate_routes.py or a new test file:
def test_send_email_to_recipient():
    """AlertManager.send_email_to sends to a specific address, not the config list."""
    from unittest.mock import AsyncMock, patch, MagicMock
    from alerts import AlertManager

    cfg = MagicMock()
    cfg.email.enabled = True
    cfg.email.smtp_host = "smtp.test"
    cfg.email.smtp_port = 587
    cfg.email.smtp_user = "user"
    cfg.email.smtp_password = "pass"
    cfg.email.from_addr = "from@test.com"
    cfg.quiet_hours.enabled = False

    mgr = AlertManager(cfg)

    with patch("alerts.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        import asyncio
        result = asyncio.run(mgr.send_email_to("user@family.com", "Test Subject", "Test body"))
        assert result is True
        call_args = mock_send.call_args
        message = call_args[0][0]
        assert message["To"] == "user@family.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/feuer/Documents/Projects/immich-manager && python -m pytest server-manager/tests/test_ip_gate_routes.py::test_send_email_to_recipient -v`
Expected: FAIL — `AttributeError: 'AlertManager' object has no attribute 'send_email_to'`

- [ ] **Step 3: Add send_email_to method to AlertManager**

In `server-manager/src/alerts.py`, add after the existing `send_email` method:

```python
    async def send_email_to(self, recipient: str, subject: str, body: str,
                            severity: str = "info") -> bool:
        """Send email to a specific recipient (not the configured list)."""
        if not self.config.email.enabled:
            return False

        try:
            message = MIMEMultipart()
            message["From"] = self.config.email.from_addr
            message["To"] = recipient
            message["Subject"] = f"[Immich {severity.upper()}] {subject}"

            html_body = f"""
            <html>
                <body>
                    <h2>{_SEVERITY_EMOJI.get(severity, '')} {subject}</h2>
                    <p><strong>Severity:</strong> {severity.upper()}</p>
                    <p><strong>Time:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                    <hr>
                    <pre>{body}</pre>
                    <p style="color:#888;font-size:12px">
                        Immich Manager
                    </p>
                </body>
            </html>
            """

            message.attach(MIMEText(html_body, "html"))

            await aiosmtplib.send(
                message,
                hostname=self.config.email.smtp_host,
                port=self.config.email.smtp_port,
                username=self.config.email.smtp_user,
                password=self.config.email.smtp_password,
                start_tls=True,
            )
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {e}")
            return False
```

- [ ] **Step 4: Update ip_gate_routes.py to use send_email_to for verification emails**

In `_send_verification_email` in `ip_gate_routes.py`, change the email sending to use the new method:

```python
async def _send_verification_email(
    alert_manager,
    email: str,
    ip_address: str,
    token: str,
    base_url: str,
):
    """Send verification email to the specific user requesting verification."""
    verify_base = f"{base_url}/api/ip-gate/verify/{token}"
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    body = f"""Someone is trying to access Immich from {ip_address} at {now}.

If this is you, choose how long to trust this IP:

  Trust for 24 hours: {verify_base}?duration=24h
  Trust for 7 days:   {verify_base}?duration=7d
  Trust for 30 days:  {verify_base}?duration=30d
  Trust permanently:  {verify_base}?duration=permanent

If this wasn't you, ignore this email. The IP will remain blocked."""

    # Send to the specific user, not the admin list
    await alert_manager.send_email_to(
        email,
        "New login attempt from unrecognized IP",
        body,
        "warning",
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/feuer/Documents/Projects/immich-manager && python -m pytest server-manager/tests/test_ip_gate_routes.py::test_send_email_to_recipient -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add server-manager/src/alerts.py server-manager/src/ip_gate_routes.py
git commit -m "feat(ip-gate): add send_email_to for per-user verification emails"
```

---

### Task 14: Cloudflare Sync Scheduler & Dashboard Toggle

**Files:**
- Modify: `server-manager/src/main.py` (add Cloudflare sync job)
- Modify: `server-manager/src/ip_gate_routes.py` (add Cloudflare toggle endpoint)

- [ ] **Step 1: Add Cloudflare sync job to startup**

In `main.py` startup, after the IP gate expiry job:

```python
        # Schedule Cloudflare sync if enabled
        if config.ip_gate.cloudflare.enabled:
            from .ip_gate_cloudflare import CloudflareIPSync
            cf_sync = CloudflareIPSync(
                api_token=config.ip_gate.cloudflare.api_token,
                account_id=config.ip_gate.cloudflare.account_id,
                list_name=config.ip_gate.cloudflare.list_name,
            )
            app.state.cloudflare_sync = cf_sync
            scheduler.add_job(
                _cloudflare_sync_job,
                'interval',
                hours=config.ip_gate.cloudflare.reconciliation_interval_hours,
                id='cloudflare_sync'
            )
```

And add the job function:

```python
async def _cloudflare_sync_job():
    """Reconcile Cloudflare IP list with local trusted admin IPs."""
    if not database:
        return
    cf_sync = getattr(app.state, "cloudflare_sync", None)
    if not cf_sync:
        return
    from shared.auth.ip_gate import list_ips_by_status
    admin_ips = [
        ip["ip_address"] for ip in list_ips_by_status(database, "trusted")
        if ip.get("access_level") == "admin"
    ]
    success = cf_sync.sync(admin_ips)
    if not success and alert_manager:
        alert_manager.send_discord(
            "Cloudflare Sync Failed",
            "Failed to reconcile Cloudflare IP list. Check logs for details.",
            "warning",
        )
```

- [ ] **Step 2: Add Cloudflare toggle endpoint**

In `ip_gate_routes.py`, add:

```python
@ip_gate_router.get("/management/cloudflare-status")
async def cloudflare_status(request: Request):
    """Get Cloudflare sync status."""
    _require_admin_for_management(request)
    ip_gate_config = getattr(request.app.state, "ip_gate_config", None)
    cf_sync = getattr(request.app.state, "cloudflare_sync", None)
    return {
        "enabled": ip_gate_config.cloudflare.enabled if ip_gate_config else False,
        "connected": cf_sync is not None,
        "list_name": ip_gate_config.cloudflare.list_name if ip_gate_config else "",
    }
```

- [ ] **Step 3: Commit**

```bash
git add server-manager/src/main.py server-manager/src/ip_gate_routes.py
git commit -m "feat(ip-gate): add Cloudflare sync scheduler and status endpoint"
```

---

### Task 15: Integration Test — Full Flow

**Files:**
- Create: `server-manager/tests/test_ip_gate_integration.py`

- [ ] **Step 1: Write an end-to-end integration test**

```python
# server-manager/tests/test_ip_gate_integration.py
"""
Integration test for the full IP gate flow:
unknown IP -> challenge -> submit email -> verify token -> trusted.
"""
import pytest
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.auth.ip_gate import (
    ensure_ip_gate_tables, get_trusted_ip, create_verification_token,
    validate_verification_token,
)
from ip_gate_routes import ip_gate_router
from ip_gate_middleware import IPGateMiddleware


class FakeDB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def _get_connection(self):
        from contextlib import contextmanager
        @contextmanager
        def ctx():
            yield self.conn
        return ctx()


@pytest.fixture
def full_app():
    app = FastAPI()
    db = FakeDB()
    ensure_ip_gate_tables(db)

    # Also need users table for get_or_create_user
    from shared.auth import ensure_users_table
    ensure_users_table(db)

    ip_gate_config = MagicMock(
        enabled=True,
        token_expiry_minutes=15,
        trusted_proxy_ips=[],
        cloudflare=MagicMock(enabled=False),
    )

    app.state.ip_gate_db = db
    app.state.ip_gate_config = ip_gate_config
    app.state.alert_manager = MagicMock()
    app.state.alert_manager.send_email_to = AsyncMock(return_value=True)
    app.state.alert_manager.send_discord = MagicMock(return_value=True)
    app.state.alert_manager.send_email = AsyncMock(return_value=True)
    app.state.immich_api_url = "http://localhost:2283/api"
    app.state.public_url = "http://localhost:8080"

    app.add_middleware(IPGateMiddleware)
    app.include_router(ip_gate_router)

    # Add a test endpoint that requires IP gate
    @app.get("/api/test")
    async def test_endpoint():
        return {"ok": True}

    return app, db


def test_full_verification_flow(full_app):
    app, db = full_app
    client = TestClient(app)

    # 1. Request to /api/test should be challenged (redirected)
    resp = client.get("/api/test", headers={"accept": "application/json"}, follow_redirects=False)
    assert resp.status_code == 403
    assert "challenge_url" in resp.json()

    # 2. Check status — should be pending now
    resp = client.get("/api/ip-gate/status")
    assert resp.json()["status"] == "pending"

    # 3. Submit challenge email — mock Immich user lookup
    mock_user = {"id": "user-123", "email": "test@example.com", "name": "Test User"}
    with patch("ip_gate_routes.validate_immich_email", return_value=mock_user):
        resp = client.post("/api/ip-gate/challenge", json={"email": "test@example.com"})
        assert resp.status_code == 200

    # 4. Get the token from the DB and verify it
    with db._get_connection() as conn:
        row = conn.cursor().execute("SELECT token FROM verification_tokens LIMIT 1").fetchone()
        token = row["token"]

    # 5. Mock the user lookup for role determination
    with patch("ip_gate_routes.validate_immich_email", return_value=mock_user), \
         patch("ip_gate_routes.get_or_create_user", return_value=({"role": "user"}, False)):
        resp = client.get(f"/api/ip-gate/verify/{token}?duration=7d")
        assert resp.status_code == 200
        assert resp.json()["access_level"] == "user"

    # 6. Now the IP should be trusted
    ip_row = get_trusted_ip(db, "testclient")
    assert ip_row["status"] == "trusted"
    assert ip_row["trust_duration"] == "7d"

    # 7. Request to /api/test should now succeed
    resp = client.get("/api/test")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
```

- [ ] **Step 2: Run integration test**

Run: `cd /home/feuer/Documents/Projects/immich-manager && python -m pytest server-manager/tests/test_ip_gate_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run all IP gate tests together**

Run: `cd /home/feuer/Documents/Projects/immich-manager && python -m pytest server-manager/tests/test_ip_gate*.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add server-manager/tests/test_ip_gate_integration.py
git commit -m "test(ip-gate): add end-to-end integration test for full verification flow"
```

---

### Task 16: Config YAML Example Update

**Files:**
- Modify: `server-manager/config/config.yaml.example`

- [ ] **Step 1: Add ip_gate section to config.yaml.example**

Add at the end of the example config:

```yaml
# IP Gate — centralized IP verification and monitoring
ip_gate:
  enabled: true
  trusted_proxy_ips:
    - "127.0.0.1"
    - "172.17.0.1"  # Docker bridge
  token_expiry_minutes: 15
  email_rate_limit: "3/15minutes"
  verification_rate_limit: "5/15minutes"
  admin_email: "admin@yourdomain.com"  # fallback alert recipient
  cloudflare:
    enabled: false  # requires Teams Standard plan
    api_token: "${CLOUDFLARE_API_TOKEN:-}"
    account_id: ""
    list_name: "immich-trusted-ips"
    reconciliation_interval_hours: 6
```

- [ ] **Step 2: Commit**

```bash
git add server-manager/config/config.yaml.example
git commit -m "docs(ip-gate): add ip_gate config section to config.yaml.example"
```
