"""Shared authentication and RBAC for Immich Manager services."""

from .rbac import (
    Role,
    ensure_users_table,
    get_or_create_user,
    require_role,
    get_all_users,
    update_user_role,
    extract_token,
    validate_immich_token,
)

__all__ = [
    "Role",
    "ensure_users_table",
    "get_or_create_user",
    "require_role",
    "get_all_users",
    "update_user_role",
    "extract_token",
    "validate_immich_token",
]
