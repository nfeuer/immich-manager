# IP Gate Security Monitoring Design

**Date:** 2026-04-03
**Status:** Approved
**Scope:** Server Manager, Photo Curator, SSH monitoring, Cloudflare integration

## Overview

A centralized IP verification and monitoring system that challenges unknown IP addresses before granting access. Users verify their own IPs via email. Admins get full access (Server Manager + Photo Curator + Cloudflare), regular users get Photo Curator only. SSH monitoring is alert-only with manual admin action.

## Goals

- Block access from unrecognized IPs across web apps and Cloudflare
- Allow multi-user self-service IP verification via email
- Provide admin dashboard for IP trust management, blacklisting, and connection analytics
- Alert on SSH connections from unknown IPs without automated blocking
- Optionally sync trusted IPs to Cloudflare Access policies (paid tier)

## Non-Goals

- Automated SSH firewall management (too risky — could lock admin out)
- Replacing Immich SSO or existing auth (IP gate is an additional layer, not a replacement)
- Geolocation-based blocking (out of scope for now)

---

## Data Model

All tables live in the Server Manager SQLite database.

### `trusted_ips`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `ip_address` | TEXT UNIQUE | The IP address |
| `status` | TEXT | `pending`, `trusted`, `revoked` |
| `access_level` | TEXT | `admin` (all services) or `user` (Photo Curator only) |
| `trust_duration` | TEXT | `permanent`, `24h`, `7d`, `30d`, `90d`, `session` |
| `trusted_at` | DATETIME | When the IP was approved |
| `expires_at` | DATETIME | NULL for permanent, calculated from trust_duration |
| `verified_by` | TEXT | Email of the user who verified |
| `label` | TEXT | Optional user-assigned name (e.g., "Home", "Office") |
| `last_seen` | DATETIME | Last connection timestamp |
| `connection_count_7d` | INTEGER | Rolling 7-day connection count (computed from `ip_connections` table on dashboard load, not stored) |
| `created_at` | DATETIME | First seen timestamp |
| `source` | TEXT | `web`, `cloudflare`, `ssh` — which layer first saw this IP |
| `revoked_at` | DATETIME | When the IP was blacklisted (NULL if not revoked) |
| `revoked_by` | TEXT | Admin email who revoked (NULL if not revoked) |
| `revoke_reason` | TEXT | Optional reason for blacklisting |

### `ip_connections`

Historical connection log for analytics and auditing.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `ip_address` | TEXT | The IP |
| `timestamp` | DATETIME | Connection time |
| `service` | TEXT | `server-manager`, `photo-curator`, `ssh`, `cloudflare` |
| `action` | TEXT | `allowed`, `challenged`, `blocked`, `alert_sent` |
| `user_id` | TEXT | Associated user if known (post-auth) |

### `verification_tokens`

Single-use tokens for email verification links.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `token` | TEXT UNIQUE | `secrets.token_urlsafe(32)` |
| `ip_address` | TEXT | IP being verified |
| `email` | TEXT | Email that requested verification |
| `created_at` | DATETIME | When the token was generated |
| `expires_at` | DATETIME | Token expiry (15 minutes) |
| `used` | BOOLEAN | Whether the link has been clicked |
| `trust_duration` | TEXT | Duration applied on approval |

---

## IP Gate Middleware

A shared FastAPI middleware in `shared/auth/ip_gate.py` that runs before the existing auth middleware on every request.

### Request Flow

```
Request arrives
    -> Extract IP (request.client.host, or X-Forwarded-For behind Caddy)
    -> Check trusted_ips table
        -> trusted + not expired -> update last_seen, increment counter, pass through
        -> trusted + expired -> set status to pending, treat as unknown
        -> revoked -> return 403 Forbidden (hard block, no challenge)
        -> pending -> redirect to challenge page
        -> not found -> insert as pending, send Discord + email alert, redirect to challenge page
```

### Access Level Enforcement

- If IP has `access_level=admin` -> access to Server Manager + Photo Curator
- If IP has `access_level=user` -> access to Photo Curator only, Server Manager returns 403

### Exempted Paths

These bypass the IP gate (required for the verification flow to work):

- `/api/ip-gate/verify/{token}` — email approval endpoint
- `/api/ip-gate/status` — polling endpoint for challenge page
- `/api/ip-gate/challenge` — challenge page and email submission
- `/health` — health checks

### Caddy Integration

- Caddy handles TLS termination and passes `X-Forwarded-For`
- Middleware trusts `X-Forwarded-For` only from Caddy's known internal IP (configurable in `config.yaml`)
- This is a second layer behind Caddy's `forward_auth`

### Cross-Service Communication

Photo Curator does not access the trusted_ips database directly. It makes async HTTP calls to Server Manager's IP gate endpoints. Server Manager is the single source of truth.

---

## Challenge Page & Verification Flow

### Challenge Page

A minimal standalone HTML page served without auth (since the user can't auth yet).

**Content:**
- Message: "This IP address has not been verified."
- Email input field
- Submit button
- After submission: "A verification email has been sent if the account exists. Please check your email."
- [Refresh Status] button that polls `/api/ip-gate/status` to check if the IP was approved

### Email Submission

1. User enters their email on the challenge page
2. Backend validates email format against strict regex
3. Backend checks if email matches an Immich user (parameterized query only, no string interpolation)
4. If match: generates token, stores in `verification_tokens`, sends verification email
5. If no match: returns identical response (no information leak about valid emails)
6. Constant-time comparison to prevent timing-based enumeration

### Verification Email

**Subject:** New login attempt from unrecognized IP

**Body:**

> Someone is trying to access Immich from **{ip_address}** at **{timestamp}**.
>
> If this is you, choose how long to trust this IP:
> - [Trust for 24 hours]
> - [Trust for 7 days]
> - [Trust for 30 days]
> - [Trust permanently]
>
> If this wasn't you, ignore this email. The IP will remain blocked.

Each duration option is a separate link with the token and duration encoded in the URL.

### Token Verification

1. User clicks link: `GET /api/ip-gate/verify/{token}?duration=30d`
2. Backend validates: token exists, not expired, not used
3. Marks IP as trusted with chosen duration
4. Sets `access_level` based on user's RBAC role (`admin` or `user`)
5. Marks token as used (single-use)
6. Logs to `ip_connections` with `action=allowed`
7. If admin and Cloudflare sync enabled: adds IP to Cloudflare list

### Rate Limiting

- Email submission: 3 attempts per IP per 15 minutes
- Token verification: 5 attempts per IP per 15 minutes

---

## SSH Monitoring

A lightweight systemd service (`ip-gate-ssh-monitor.service`) that monitors SSH connections.

### Implementation

- Python script that follows `journalctl -u ssh -f`
- Watches for `Accepted` entries (successful SSH logins)
- Extracts source IP and username
- Checks IP against `trusted_ips` table
- If unknown: sends Discord + email alert to admin only

### SSH Alert Content

> **SSH login from unrecognized IP**
>
> User `{ssh_user}` logged in via SSH from `{ip_address}` at `{timestamp}`.
>
> This is an alert only -- no automatic action has been taken. If this wasn't you, investigate immediately.

### What SSH Monitoring Does NOT Do

- No firewall rule changes
- No blocking or challenging SSH connections
- No interaction with UFW or fail2ban rules

### Logging

Each SSH connection is recorded in `ip_connections` with `service=ssh` and `action=alert_sent` (for unknown IPs) or `action=allowed` (for trusted IPs). This provides a unified view in the dashboard.

---

## Cloudflare Tunnel Integration

Two modes: alert-only (free tier, default) and automated sync (paid tier, optional).

### Default Mode: Alert-Only (Free Tier)

When an admin IP is verified, a Discord + email alert is sent:

> **New admin IP verified -- update Cloudflare manually**
>
> IP `{ip_address}` was verified by `{admin_email}`.
> Add it to your Cloudflare Access policy: Zero Trust -> Access -> [your app] -> Add IP rule.

Same alert sent on revocation with instructions to remove the IP.

### Optional Mode: Automated Sync (Paid Tier)

Enabled via toggle in the Server Manager IP Management dashboard.

**Configuration** (added to `config.yaml`):

```yaml
ip_gate:
  cloudflare:
    enabled: false  # toggle in dashboard
    api_token: "${CLOUDFLARE_API_TOKEN}"
    account_id: "your-account-id"
    list_name: "immich-trusted-ips"
```

**Behavior:**
- On admin IP verification: IP added to Cloudflare list immediately via Lists API
- On revocation/expiry: IP removed from Cloudflare list
- Periodic reconciliation: scheduled task every 6 hours syncs local trusted IPs with Cloudflare list
- API token scope: `Account.Zero Trust: Edit` only (minimal privilege)

**Non-admin IPs** are NOT synced to Cloudflare. They access Photo Curator through the tunnel like any Immich user — local IP gate handles their verification.

**Failure handling:** If the Cloudflare API call fails, the IP is still trusted/blocked locally. A Discord alert fires about the sync failure.

---

## IP Management Dashboard

A new section in the Server Manager UI with four tabs:

### Tab 1: Trusted IPs

Table showing all IPs with `status=trusted`:

| IP Address | Label | User | Access Level | Trust Duration | Expires | Last Seen | Connections (7d) | Actions |
|------------|-------|------|-------------|---------------|---------|-----------|-------------------|---------|
| 192.168.1.5 | Home | admin@... | Admin | Permanent | Never | 2 min ago | 142 | [Edit] [Revoke] |
| 98.45.12.3 | Mom's Hotel | mom@... | User | 7 days | Apr 10 | 1 hr ago | 8 | [Edit] [Revoke] |

**Actions:**
- Edit: change label, trust duration
- Revoke: blacklist the IP (with optional reason field)

### Tab 2: Pending IPs

IPs awaiting verification:

| IP Address | Requested By | First Seen | Service | Actions |
|------------|-------------|------------|---------|---------|
| 203.0.113.5 | user@... | 10 min ago | web | [Approve] [Blacklist] |

**Actions:**
- Approve: manually approve with duration selection (bypasses email flow)
- Blacklist: revoke immediately

### Tab 3: Blacklisted IPs

Revoked/blocked IPs:

| IP Address | Original User | Date Blacklisted | Blacklisted By | Reason | Actions |
|------------|--------------|-------------------|----------------|--------|---------|
| 45.33.22.11 | unknown | Mar 28, 2026 | admin@... | Suspicious activity | [Unblock] [Delete] |

**Actions:**
- Unblock: move back to pending status
- Delete: remove from database entirely

### Tab 4: Connection Log

Filterable log of all connections:

| Timestamp | IP Address | Service | Action | User |
|-----------|-----------|---------|--------|------|
| 2 min ago | 192.168.1.5 | server-manager | allowed | admin@... |
| 5 min ago | 203.0.113.5 | photo-curator | challenged | -- |
| 1 hr ago | 10.0.0.1 | ssh | alert_sent | root |

Filters: IP address, service, action, user, date range.

### Cloudflare Sync Toggle

At the top of the IP Management section:

> **Cloudflare Auto-Sync:** [OFF/ON toggle]
> When enabled, admin-trusted IPs are automatically synced to your Cloudflare Access IP list.
> Requires: API token, account ID, and list name in configuration.

When toggled on without valid config: shows inline error with link to configuration instructions.

---

## Security Considerations

### SQL Injection Prevention
- All database queries use SQLAlchemy parameterized queries
- Email input validated against strict regex before any DB operation
- No string interpolation in SQL

### Information Leakage Prevention
- Challenge page returns identical response whether email exists or not
- Constant-time email lookup to prevent timing attacks
- No user enumeration possible through the challenge flow

### Token Security
- Verification tokens: `secrets.token_urlsafe(32)` (256-bit entropy)
- 15-minute expiry
- Single-use (marked as used after first click)
- Rate-limited endpoint

### X-Forwarded-For Trust
- Only trusted from Caddy's known internal IP
- Configurable in `config.yaml` to prevent IP spoofing

### Existing Security Layers Preserved
- Immich SSO authentication unchanged
- CSRF middleware unchanged
- Rate limiting on all existing endpoints unchanged
- fail2ban and UFW unchanged
- IP gate is additive, not replacing any existing security

---

## Configuration

Added to Server Manager `config.yaml`:

```yaml
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
    enabled: false
    api_token: "${CLOUDFLARE_API_TOKEN}"
    account_id: ""
    list_name: "immich-trusted-ips"
    reconciliation_interval_hours: 6
```

---

## File Structure

```
shared/auth/
    ip_gate.py              # IP gate middleware, DB operations, token management

server-manager/src/
    ip_gate_routes.py       # API endpoints: challenge, verify, status, management CRUD
    ip_gate_ssh_monitor.py  # SSH journalctl watcher (runs as separate systemd service)

server-manager/frontend/src/components/
    IPManagement.jsx        # Dashboard UI with four tabs

server-manager/frontend/src/pages/
    ChallengePage.jsx       # Standalone challenge page (no auth required)
```
