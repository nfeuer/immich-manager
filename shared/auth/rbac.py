"""
Role-based access control for Immich Manager services.

Provides a Role enum, user management backed by each service's SQLite DB,
and FastAPI dependencies for gating endpoints by role.
"""

import enum
import logging
from typing import Dict, Any, Optional, List, Tuple

import requests as http_requests
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)

VALID_ROLES = ("admin", "user", "guest")


class Role(enum.IntEnum):
    """Hierarchical roles — higher value means more privilege."""
    GUEST = 0
    USER = 1
    ADMIN = 2


# ---------------------------------------------------------------------------
# Users table management
# ---------------------------------------------------------------------------

def ensure_users_table(db) -> None:
    """Create the ``users`` table if it doesn't exist."""
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                immich_user_id TEXT NOT NULL UNIQUE,
                email TEXT,
                name TEXT,
                role TEXT NOT NULL DEFAULT 'user',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_immich_id ON users(immich_user_id)"
        )


def get_or_create_user(
    db,
    immich_user: Dict[str, Any],
    default_role: str = "user",
) -> Tuple[Dict[str, Any], bool]:
    """Look up or create a local user from an Immich user dict.

    Returns ``(user_dict, created)`` where *created* is True when the
    user was freshly inserted.  The very first user in the database is
    always promoted to admin (bootstrap).
    """
    immich_id = immich_user["id"]
    with db._get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE immich_user_id = ?", (immich_id,))
        row = cursor.fetchone()
        if row:
            user = dict(row)
            # Update name/email if changed upstream
            if (user.get("email") != immich_user.get("email")
                    or user.get("name") != immich_user.get("name")):
                cursor.execute(
                    "UPDATE users SET email = ?, name = ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE immich_user_id = ?",
                    (immich_user.get("email"), immich_user.get("name"), immich_id),
                )
                user["email"] = immich_user.get("email")
                user["name"] = immich_user.get("name")
            return user, False

        # New user — bootstrap first user as admin
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        role = "admin" if count == 0 else default_role

        cursor.execute(
            "INSERT INTO users (immich_user_id, email, name, role) VALUES (?, ?, ?, ?)",
            (immich_id, immich_user.get("email"), immich_user.get("name"), role),
        )
        user_id = cursor.lastrowid
        logger.info(
            "Created local user id=%s immich_id=%s role=%s (bootstrap=%s)",
            user_id, immich_id, role, count == 0,
        )
        return {
            "id": user_id,
            "immich_user_id": immich_id,
            "email": immich_user.get("email"),
            "name": immich_user.get("name"),
            "role": role,
        }, True


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def require_role(minimum_role: Role):
    """Return a FastAPI dependency that enforces a minimum role.

    The dependency expects ``request.state._local_user`` to have been
    set by an earlier auth dependency.
    """
    async def _check(request: Request) -> Dict[str, Any]:
        local_user = getattr(request.state, "_local_user", None)
        if local_user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        user_role = Role[local_user["role"].upper()]
        if user_role < minimum_role:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return local_user
    return _check


# ---------------------------------------------------------------------------
# Admin helpers
# ---------------------------------------------------------------------------

def get_all_users(db) -> List[Dict[str, Any]]:
    """Return every row in the ``users`` table."""
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY created_at")
        return [dict(row) for row in cursor.fetchall()]


def update_user_role(db, user_id: int, new_role: str) -> bool:
    """Change a user's role.

    Returns False (without modifying) if the change would remove the
    last admin.  Raises ``ValueError`` for invalid role strings.
    """
    if new_role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {new_role!r}. Must be one of {VALID_ROLES}")

    with db._get_connection() as conn:
        cursor = conn.cursor()

        # Prevent removing the last admin
        if new_role != "admin":
            cursor.execute(
                "SELECT role FROM users WHERE id = ?", (user_id,)
            )
            row = cursor.fetchone()
            if row and row["role"] == "admin":
                cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
                if cursor.fetchone()[0] <= 1:
                    return False

        cursor.execute(
            "UPDATE users SET role = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_role, user_id),
        )
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Token helpers (deduplicate from both services)
# ---------------------------------------------------------------------------

def extract_token(request: Request) -> Optional[str]:
    """Extract Immich access token from cookie or Authorization header."""
    token = request.cookies.get("immich_access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
    return token


def validate_immich_token(api_url: str, token: str) -> Optional[Dict[str, Any]]:
    """Validate a token against the Immich API and return user info.

    Returns the user dict from ``/users/me`` on success, or ``None``.
    """
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = http_requests.get(
            f"{api_url}/auth/validateToken", headers=headers, timeout=5,
        )
        if resp.status_code != 200:
            return None

        user_resp = http_requests.get(
            f"{api_url}/users/me", headers=headers, timeout=5,
        )
        if user_resp.status_code != 200:
            return None

        user_data = user_resp.json()
        user_data["access_token"] = token
        return user_data

    except http_requests.RequestException as exc:
        logger.error("Immich token validation failed: %s", exc)
        return None
