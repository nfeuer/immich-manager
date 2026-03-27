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
                    ├── immich.houseoffeuer.com  → immich-server:2283  (Docker, homelab network)
                    ├── monitor.houseoffeuer.com → host.docker.internal:8080  (Server Manager, systemd)
                    └── curator.houseoffeuer.com → host.docker.internal:8081  (Photo Curator, systemd)
```

### Network access model

- **No open inbound firewall ports required.** The Cloudflare Tunnel makes an
  outbound connection; UFW never needs to open 443.
- **Immich decoupled from host.** Port 2283 moves from `127.0.0.1:2283`
  (host-bound) to Docker-network-internal only (`expose: ["2283"]`). The host
  can no longer reach Immich directly.
- **Server Manager and Photo Curator remain localhost-only.** They are
  reachable only via `host.docker.internal` from within the Caddy container.
  LAN peers cannot reach them directly.

---

## Auth Flow

### Login

1. User navigates to `immich.houseoffeuer.com` and authenticates.
2. Immich sets `immich_access_token` cookie (scoped to `immich.houseoffeuer.com`
   by default).
3. Caddy intercepts the `Set-Cookie` response header and rewrites it to add
   `Domain=.houseoffeuer.com`. The cookie is now visible to all
   `*.houseoffeuer.com` subdomains.
4. Cookie attributes enforced: `HttpOnly`, `Secure`, `SameSite=Lax`,
   `Domain=.houseoffeuer.com`.

### Accessing a protected service

```
Browser → monitor.houseoffeuer.com (sends immich_access_token cookie)
  └── Caddy forward_auth → immich-server:2283/api/auth/validateToken
        ├── Valid token + isAdmin=true  → forward to Server Manager ✓
        ├── Valid token + isAdmin=false → 403 Forbidden
        └── Invalid / expired token    → 401 → redirect to Immich login

Browser → curator.houseoffeuer.com (sends immich_access_token cookie)
  └── Caddy forward_auth → immich-server:2283/api/auth/validateToken
        ├── Valid token (any authenticated user) → forward to Photo Curator ✓
        └── Invalid / expired token             → 401 → redirect to Immich login
```

### Logout

- User logs out of Immich → token invalidated server-side.
- Next request to any protected service → `validateToken` returns 401.
- All services are effectively logged out simultaneously without any client-side
  coordination.

### Multi-user session isolation

- When a second user logs in on the same browser, Immich overwrites the
  `immich_access_token` cookie with the new user's token.
- The new token does not carry admin privileges → Server Manager returns 403.
- No privilege bleed between sessions.

### Defense in depth for Server Manager

Admin enforcement happens at two layers:

1. **Caddy `forward_auth`** — validates the token is present and not revoked.
2. **Server Manager application** — checks the `isAdmin` flag from the Immich
   API response on every request. A bypassed Caddy layer alone is not
   sufficient to gain access.

---

## Security Headers

Applied globally to all three domains via a shared Caddy snippet:

| Header | Value |
|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains; preload` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Server` | removed (do not advertise Caddy version) |

Rate limiting applied to `immich.houseoffeuer.com/api/auth/login`: 5 requests
per minute per IP to slow brute-force attempts.

---

## Files Changed

| File | Action | Notes |
|---|---|---|
| `docker/proxy.yml` | Create | Caddy service; joins homelab network; `extra_hosts: host.docker.internal:host-gateway` |
| `docker/caddy/Caddyfile` | Create | Routing, forward_auth, cookie rewrite, security headers, rate limiting |
| `docker/immich.yml` | Modify | Replace `ports: - "127.0.0.1:2283:2283"` with `expose: ["2283"]` |
| `/etc/cloudflared/config.yml` | Modify | Single ingress entry: `houseoffeuer.com → http://localhost:80`; remove per-service entries |
| `docker/.env.example` | Update | Uncomment `CADDY_ACME_EMAIL` and `BASE_DOMAIN` |

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
  ├── (security_headers) — HSTS, X-Frame-Options, etc.
  └── (immich_auth)      — forward_auth to /api/auth/validateToken

immich.houseoffeuer.com
  ├── import security_headers
  ├── reverse_proxy immich-server:2283
  ├── header_down Set-Cookie: add Domain=.houseoffeuer.com
  └── rate_limit /api/auth/login: 5r/m per IP

monitor.houseoffeuer.com
  ├── import security_headers
  ├── import immich_auth
  └── reverse_proxy host.docker.internal:8080

curator.houseoffeuer.com
  ├── import security_headers
  ├── import immich_auth
  └── reverse_proxy host.docker.internal:8081
```

---

## Out of Scope

- TLS certificate provisioning details (Caddy handles this automatically via
  Let's Encrypt ACME).
- Photo Curator bug fixes (photos not loading) — separate initiative.
- Server Manager frontend changes — no path rewriting needed with subdomains.
- Jellyfin, Nextcloud, or other future services — they follow the same pattern
  but are not part of this change.
