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
    "permanent": None,
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


def trust_ip(db, ip_address: str, access_level: str, trust_duration: str, verified_by: str) -> None:
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


def revoke_ip(db, ip_address: str, revoked_by: str, reason: Optional[str] = None) -> None:
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


def list_ips_by_status(db, status: str, limit: int = 200) -> List[Dict[str, Any]]:
    """List IPs filtered by status."""
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM trusted_ips WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        )
        return [dict(row) for row in cursor.fetchall()]


def record_ip_connection(db, ip_address: str, service: str, action: str, user_id: Optional[str] = None) -> None:
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


def get_connection_log(db, limit: int = 200, ip_filter: Optional[str] = None,
                       service_filter: Optional[str] = None, action_filter: Optional[str] = None) -> List[Dict[str, Any]]:
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


def create_verification_token(db, ip_address: str, email: str, expiry_minutes: int = 15) -> str:
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
        if row["expires_at"]:
            expires = datetime.fromisoformat(row["expires_at"])
            if datetime.utcnow() > expires:
                expire_stale_ips(db)
                return {"action": "challenge", "reason": "expired", "ip_record": row}

        if service == "server-manager" and row["access_level"] != "admin":
            return {"action": "block", "reason": "insufficient_access_level", "ip_record": row}

        update_last_seen(db, ip_address)
        return {"action": "allow", "reason": "trusted", "ip_record": row}

    return {"action": "challenge", "reason": "unknown_status", "ip_record": row}
