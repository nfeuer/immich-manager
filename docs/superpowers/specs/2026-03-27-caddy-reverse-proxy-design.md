# Caddy Reverse Proxy — Design Spec

**Date:** 2026-03-27
**Status:** Approved

---

## Goal

Route all three homelab services through a single Caddy reverse proxy so that
`monitor.houseoffeuer.com` and `curator.houseoffeuer.com` are reachable
externally via the existing Cloudflare Tunnel. Auth is shared via Immich's
JWT cookie, with role enforcement ensuring only Immich admins can access
Server Manager.

---

## Architecture

```
Browser
  └── Cloudflare (DDoS protection, hides real IP)
        └── Cloudflare Tunnel (outbound-only, no open inbound ports)
              └── Caddy [Docker container, homelab network, port 80]
                    ├── immich.houseoffeuer.com  → immich-server:2283   (Docker, homelab network)
                    ├── monitor.houseoffeuer.com → host.docker.internal:8080  (Server Manager, systemd)
                    └── curator.houseoffeuer.com → photo-curator:8081   (Docker, homelab network)
```

### Service deployment types

| Service | Deployment | Caddy reaches it via |
|---|---|---|
| Immich | Docker container (`immich-server`) | Container name on homelab network |
| Server Manager | systemd on host (port 8080) | `host.docker.internal:8080` |
| Photo Curator | Docker container (`photo-curator`) | Container name on homelab network |

### Network access model

- **No open inbound firewall ports required.** The Cloudflare Tunnel makes an
  outbound connection; UFW never needs to open 443. Note: Docker manages its
  own iptables rules independently of UFW, so Docker-to-host communication on
  port 8080 (Server Manager) works without UFW changes.
- **Immich decoupled from host.** Port 2283 moves from `127.0.0.1:2283`
  (host-bound) to Docker-network-internal only (`expose: ["2283"]`). The host
  can no longer reach Immich directly.
- **Server Manager remains localhost-only.** Only reachable via
  `host.docker.internal` from Caddy. LAN peers cannot reach it directly.

---

## Auth Flow

### Login

1. User navigates to `immich.houseoffeuer.com` and authenticates.
2. Immich sets `immich_access_token` cookie (scoped to `immich.houseoffeuer.com`
   by default, no `Domain` attribute).
3. Caddy intercepts the `Set-Cookie` response header for `immich_access_token`
   and rewrites it using a regex replacement to append
   `Domain=.houseoffeuer.com`. The cookie is now visible to all
   `*.houseoffeuer.com` subdomains.
   - Caddy v2 directive: `header_down Set-Cookie "(immich_access_token=[^;]+)(.*)" "$1$2; Domain=.houseoffeuer.com"`
   - This is a string replacement, not an `add` sub-directive.
4. Cookie attributes preserved plus added: `HttpOnly`, `Secure`, `SameSite=Lax`,
   `Domain=.houseoffeuer.com`.

### Accessing a protected service

**Authentication (Caddy layer):** Caddy's `forward_auth` makes a subrequest to
`GET immich-server:2283/api/users/me` to validate the token. The `Cookie`
header from the original request must be explicitly forwarded to this subrequest
via `header_up Cookie {http.request.header.Cookie}`. Immich's `/api/users/me`
returns 200 for a valid token, 401 for invalid/expired.

Note: `/api/auth/validateToken` was removed in Immich v2.x. The correct
validation endpoint is `/api/users/me`.

**Authorization (application layer):** Caddy only gates on
authentication presence (valid vs. invalid token). Admin role enforcement for
Server Manager happens inside the Server Manager application itself — Caddy
cannot parse the JSON response body from `/api/users/me` to check `isAdmin`.

```
Browser → monitor.houseoffeuer.com (sends immich_access_token cookie)
  └── Caddy forward_auth → GET immich-server:2283/api/users/me
        ├── 200 (valid token) → forward to Server Manager
        │     └── Server Manager checks isAdmin → 403 if not admin
        └── 401 (invalid/expired) → redirect to Immich login

Browser → curator.houseoffeuer.com (sends immich_access_token cookie)
  └── Caddy forward_auth → GET immich-server:2283/api/users/me
        ├── 200 (valid token, any authenticated user) → forward to Photo Curator ✓
        └── 401 (invalid/expired) → redirect to Immich login
```

### Logout

- User logs out of Immich → token invalidated server-side.
- Next request to any protected service → `/api/users/me` returns 401.
- All services are effectively logged out simultaneously without any client-side
  coordination.

### Multi-user session isolation

- When a second user logs in on the same browser, Immich overwrites the
  `immich_access_token` cookie with the new user's token.
- The new token does not carry admin privileges → Server Manager returns 403
  (enforced at the application layer).
- No privilege bleed between sessions.

### Defense in depth for Server Manager

Admin enforcement happens at two layers:

1. **Caddy `forward_auth`** — validates the token is present and not revoked
   by making a subrequest to `/api/users/me` with the forwarded cookie. A
   request with no cookie or an expired token is rejected before reaching
   Server Manager.
2. **Server Manager application** — independently calls `/api/users/me` using
   the token as a `Bearer` header to get the full user object, then checks the
   `isAdmin` flag. A bypassed or misconfigured Caddy layer alone is not
   sufficient to gain admin access.

This double-validation is intentional: Caddy handles authentication presence
(is the token valid?), while Server Manager handles authorization (is this user
an admin?).

---

## Security Headers

Applied globally to all three domains via a shared Caddy snippet:

| Header | Value |
|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Server` | removed (do not advertise Caddy version) |

Note: Server Manager sets its own `Content-Security-Policy` at the application
layer. Caddy does not add a CSP header to avoid conflicting values.

Rate limiting applied to `immich.houseoffeuer.com/api/auth/login`: 5 requests
per minute per IP to slow brute-force attempts. This requires a custom Caddy
build using `xcaddy` with the `caddy-ratelimit` plugin (not included in the
stock `caddy:2-alpine` image). See `docker/proxy.yml` build configuration.

---

## Files Changed

| File | Action | Notes |
|---|---|---|
| `docker/proxy.yml` | Create | Caddy service; joins homelab network; `extra_hosts: host.docker.internal:host-gateway`; custom xcaddy build for rate limiting. Start with: `docker compose --env-file docker/.env -f docker/core.yml -f docker/proxy.yml up -d` |
| `docker/caddy/Dockerfile` | Create | `xcaddy` build with `caddy-ratelimit` plugin |
| `docker/caddy/Caddyfile` | Create | Routing, forward_auth, cookie rewrite, security headers, rate limiting |
| `docker/immich.yml` | Modify | Replace `ports: - "127.0.0.1:2283:2283"` with `expose: ["2283"]` |
| `docker/photo-curator.yml` | Modify | Replace `ports: - "8081:8081"` with `expose: ["8081"]` — removes direct LAN access, all traffic goes through Caddy |
| `/etc/cloudflared/config.yml` | Modify | Single wildcard ingress entry pointing to `http://localhost:80`; remove per-service entries |
| `docker/.env.example` | Update | Uncomment `CADDY_ACME_EMAIL` and `BASE_DOMAIN` |
| Server Manager config | Update | Add `https://monitor.houseoffeuer.com` to the allowed origins list used by the CSRF middleware (`_get_allowed_origins()`), otherwise all POST/PUT/DELETE requests from the browser will be rejected with 403 |

---

## Cloudflare Tunnel Change

Current config has separate entries for each service path. After this change it
becomes a single catch-all:

```yaml
ingress:
  - hostname: "*.houseoffeuer.com"
    service: http://localhost:80
  - hostname: houseoffeuer.com
    service: http://localhost:80
  - service: http_status:404
```

Caddy takes over all subdomain routing. The tunnel no longer needs to know
about individual services.

---

## Caddyfile Structure

```
Global options block
  └── ACME email

Snippets
  ├── (security_headers) — HSTS, X-Frame-Options, nosniff, Referrer-Policy, remove Server header
  └── (immich_auth)      — forward_auth to GET /api/users/me
                           with header_up Cookie {http.request.header.Cookie}

immich.houseoffeuer.com
  ├── import security_headers
  ├── reverse_proxy immich-server:2283  (WebSocket upgrade handled automatically)
  ├── header_down Set-Cookie: regex rewrite to add Domain=.houseoffeuer.com
  └── rate_limit /api/auth/login: 5 req/min per IP (requires caddy-ratelimit plugin)

monitor.houseoffeuer.com
  ├── import security_headers
  ├── import immich_auth
  └── reverse_proxy host.docker.internal:8080

curator.houseoffeuer.com
  ├── import security_headers
  ├── import immich_auth
  └── reverse_proxy photo-curator:8081
```

Caddy's `reverse_proxy` handles WebSocket upgrade headers automatically — no
additional configuration needed for Immich's real-time notification connections.

---

## Out of Scope

- TLS certificate provisioning details (Caddy handles this automatically via
  Let's Encrypt ACME).
- Photo Curator bug fixes (photos not loading) — separate initiative.
- Server Manager frontend changes — no path rewriting needed with subdomains.
- Jellyfin, Nextcloud, or other future services — they follow the same pattern
  but are not part of this change.
