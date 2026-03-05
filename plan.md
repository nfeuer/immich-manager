# User Management Implementation Plan

## Overview

Add role-based access control (RBAC) with three hierarchical roles — **Admin > User > Guest** — to both server-manager and photo-curator. Roles are stored in local SQLite databases. The first authenticated user is automatically promoted to Admin.

---

## Role Definitions (Hierarchical)

| Capability | Guest | User | Admin |
|---|---|---|---|
| **Server Manager** | | | |
| View dashboard / system status | Yes | Yes | Yes |
| View disk health, metrics, alerts | Yes | Yes | Yes |
| View backup history | Yes | Yes | Yes |
| Acknowledge alerts | No | Yes | Yes |
| Trigger backup | No | No | Yes |
| Trigger restore | No | No | Yes |
| Send test alert | No | No | Yes |
| View audit log | No | No | Yes |
| Manage users (view/assign roles) | No | No | Yes |
| **Photo Curator** | | | |
| View photos, scores, stats, map | Yes | Yes | Yes |
| View preferences | Yes | Yes | Yes |
| Run analysis | No | Yes | Yes |
| Update curation selections | No | Yes | Yes |
| Complete curation (create album) | No | Yes | Yes |
| Update preferences | No | Yes | Yes |
| Family mode (share/collaborate) | No | Yes | Yes |
| Manage duplicates (delete) | No | Yes | Yes |
| Manage users (view/assign roles) | No | No | Yes |

---

## Implementation Steps

### Step 1: Shared Auth Library (`shared/auth/`)

Create a small shared module used by both services to avoid code duplication.

**Files to create:**
- `shared/__init__.py`
- `shared/auth/__init__.py`
- `shared/auth/roles.py` — Role enum, permission definitions, role-checking helpers
- `shared/auth/user_db.py` — SQLite user table management (create, get, update role)
- `shared/auth/middleware.py` — FastAPI dependency that enriches the current user dict with their role

**Key design:**
```python
class Role(str, Enum):
    GUEST = "guest"
    USER = "user"
    ADMIN = "admin"

ROLE_HIERARCHY = {Role.ADMIN: 3, Role.USER: 2, Role.GUEST: 1}

def require_role(minimum_role: Role) -> Dependency:
    """FastAPI dependency: raises 403 if user's role < minimum_role"""
```

**User table schema (added to each service's existing SQLite DB):**
```sql
CREATE TABLE IF NOT EXISTS users (
    immich_user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    name TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Bootstrap logic:**
- On authentication, look up `immich_user_id` in the `users` table
- If no users exist at all → insert this user as `admin`
- If this user doesn't exist but others do → insert as `user` (default role)
- Attach `role` to the user dict returned by the auth dependency

---

### Step 2: Integrate into Server Manager

**Modify `server-manager/src/database.py`:**
- Add `users` table to schema migrations
- Add CRUD functions: `get_user()`, `upsert_user()`, `update_user_role()`, `list_users()`

**Modify `server-manager/src/main.py`:**
- Import shared auth module
- Update `require_auth()` to call bootstrap/lookup logic after Immich validation
- Add `require_role()` dependency to protected endpoints:
  - `GET /api/status`, `/api/disks`, `/api/metrics`, `/api/backups`, `/api/alerts`, `/api/immich-update` → `Role.GUEST`
  - `POST /api/alerts/{id}/acknowledge` → `Role.USER`
  - `POST /api/backup/now`, `/api/restore`, `/api/test-alert`, `GET /api/audit` → `Role.ADMIN`
- Add new admin endpoints:
  - `GET /api/admin/users` — list all users with roles
  - `PUT /api/admin/users/{user_id}/role` — change a user's role
- Update dashboard HTML to show/hide actions based on role

---

### Step 3: Integrate into Photo Curator

**Modify `photo-curator/src/database.py`:**
- Add `users` table to schema migrations (same schema)
- Add CRUD functions (same as server-manager)

**Modify `photo-curator/src/auth.py`:**
- Update `get_current_user()` to call bootstrap/lookup logic
- Add `require_role()` dependency

**Modify `photo-curator/src/main.py`:**
- Add role requirements to endpoints:
  - `GET /api/photos/*`, `/api/progress`, `/api/stats`, `/api/preferences`, `/api/analytics`, `/api/photos/map` → `Role.GUEST`
  - `POST /api/analyze/*`, `/api/curation/*/update`, `/api/curation/*/complete`, `PUT /api/preferences`, family mode endpoints, `POST /api/duplicates/delete` → `Role.USER`
  - User management endpoints → `Role.ADMIN`
- Add admin endpoints:
  - `GET /api/admin/users` — list all users with roles
  - `PUT /api/admin/users/{user_id}/role` — change a user's role
- Update UI to show/hide controls based on role

---

### Step 4: Admin UI Components

**Server Manager dashboard (`GET /`):**
- Add "User Management" section (visible to admins only)
- Show table of users with role dropdowns
- Disable destructive buttons (backup, restore) for non-admin users

**Photo Curator UI (`GET /`):**
- Add "User Management" section (visible to admins only)
- Show table of users with role dropdowns
- Hide edit/action controls for guests (show read-only view)

---

### Step 5: Audit Logging Integration

**Modify `server-manager/src/audit.py`:**
- Log role-change events: `"User X changed role of User Y from 'user' to 'admin'"`
- Include acting user's ID in all audit entries

---

### Step 6: API Response Enrichment

- Add `role` field to the `/api/auth/check` response in photo-curator
- Add `role` field to the user info returned by server-manager auth
- Frontend JS can use this to conditionally render UI elements

---

### Step 7: Tests

- Unit tests for role hierarchy checks
- Unit tests for bootstrap logic (first user = admin)
- Integration tests for endpoint access by role (admin allowed, guest blocked, etc.)
- Test role persistence across sessions

---

## File Change Summary

| Action | File | Description |
|--------|------|-------------|
| Create | `shared/__init__.py` | Package init |
| Create | `shared/auth/__init__.py` | Auth module init |
| Create | `shared/auth/roles.py` | Role enum, hierarchy, `require_role()` |
| Create | `shared/auth/user_db.py` | User table CRUD |
| Modify | `server-manager/src/database.py` | Add users table migration |
| Modify | `server-manager/src/main.py` | Add role checks, admin endpoints, UI |
| Modify | `server-manager/src/audit.py` | Log role changes |
| Modify | `photo-curator/src/database.py` | Add users table migration |
| Modify | `photo-curator/src/auth.py` | Add role lookup to auth flow |
| Modify | `photo-curator/src/main.py` | Add role checks, admin endpoints, UI |
| Create | `tests/test_roles.py` | Role logic tests |
| Create | `tests/test_user_management.py` | User management integration tests |

---

## Edge Cases & Considerations

1. **Role sync across services**: Roles are per-service (each SQLite DB has its own users table). A user could theoretically have different roles in each service. This is acceptable — an admin may want to grant server-manager admin only to ops staff while giving photo-curator admin to a family member.

2. **Last admin protection**: Prevent the last admin from demoting themselves. The `update_role()` function must check that at least one admin remains.

3. **Immich admin vs. manager admin**: These are independent. An Immich admin is not automatically a manager admin (except via first-user bootstrap).

4. **Token expiry**: Roles are checked on every request (looked up from DB after Immich token validation). No stale role caching issues.

5. **Guest default option**: Currently defaulting new users to `user` role. Could be configurable in `config.yaml` (e.g., `default_role: guest` for public-facing instances). Will add this as a config option.
