"""
Audit log — records every significant user and system action.

Stores entries in the ``audit_log`` table and exposes them via
``GET /api/audit``.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def ensure_audit_table(db) -> None:
    """Create the audit_log table if it doesn't already exist."""
    with db._get_connection() as conn:
        conn.cursor().execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                user_id TEXT,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT
            )
        """)
        conn.cursor().execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)"
        )


def record_audit(db, action: str, user_id: Optional[str] = None,
                 details: Optional[str] = None, ip_address: Optional[str] = None) -> None:
    """Write a single audit entry."""
    with db._get_connection() as conn:
        conn.cursor().execute(
            "INSERT INTO audit_log (user_id, action, details, ip_address) VALUES (?, ?, ?, ?)",
            (user_id, action, details, ip_address),
        )


def get_audit_log(db, limit: int = 100, action_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read the most recent audit entries."""
    with db._get_connection() as conn:
        cursor = conn.cursor()
        if action_filter:
            cursor.execute(
                "SELECT * FROM audit_log WHERE action = ? ORDER BY timestamp DESC LIMIT ?",
                (action_filter, limit),
            )
        else:
            cursor.execute(
                "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        return [dict(row) for row in cursor.fetchall()]
