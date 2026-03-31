# Caddy Reverse Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route all three homelab services through Caddy so `manager.houseoffeuer.com` and `curator.houseoffeuer.com` are reachable via the existing Cloudflare Tunnel with shared Immich auth and role-based access control.

**Architecture:** A custom-built Caddy container (with `caddy-ratelimit` plugin via xcaddy) joins the homelab Docker network and routes by subdomain. It validates every request to protected services against Immich's `/api/users/me` using `forward_auth`, and rewrites Immich's login cookie domain to `.houseoffeuer.com` so all three subdomains share the session.

**Tech Stack:** Caddy v2 (xcaddy custom build), `caddy-ratelimit` plugin, Docker Compose multi-file pattern, Cloudflare Tunnel (cloudflared), FastAPI (Server Manager), Python pytest.

---

## Deployment Notes (actual implementation, 2026-03-30)

Deviations from this plan discovered during deployment:

- **`monitor` renamed to `manager`** — more consistent with existing naming (`immich-server-manager`).
- **Existing Immich container uses underscores** — the real Immich instance is `immich_server` (underscore), not `immich-server`. Caddyfile and all references use `immich_server:2283`. Running `docker compose up` on `docker/immich.yml` created a second empty Immich instance; the orphaned containers (`immich-server`, `immich-postgres`, `immich-redis`) were cleaned up after the real data was restored.
- **`header_down` invalid at site block level** — `header_down` only works inside a `reverse_proxy` sub-block. The correct Caddy v2 syntax for response header modification at the site block level is `header >Set-Cookie "pattern" "replacement"` (the `>` prefix).
- **TLS: `auto_https off` instead of `local_certs`** — Cloudflare Tunnel connects to Caddy via plain HTTP on port 80. Caddy does not need to manage certificates. All site addresses use the `http://` scheme.
- **UFW blocks Docker bridge → host on port 8080** — packets from inside the Caddy container to `host.docker.internal:8080` are subject to UFW's INPUT chain. Required: `sudo ufw allow from 172.20.0.0/16 to any port 8080`.
- **Server Manager systemd unit hardcodes `--host 127.0.0.1`** — this flag in `ExecStart` overrides `config.yaml`. Must be changed to `--host 0.0.0.0` for Caddy to reach it via `host.docker.internal`. `config.yaml` alone is not sufficient.
- **Photo Curator missing `libgl1`** — OpenCV (`cv2`) requires `libgl1` which was absent from the Docker image. Added to the `apt-get install` list in `photo-curator/Dockerfile`.
- **Photo Curator `shared/` module not in build context** — `photo-curator/src/auth.py` imports from `shared/` which lives at the project root. The build context was widened from `../photo-curator` to `..` (project root) and `COPY` directives updated accordingly.
- **`docker/immich.yml` not used** — the existing Immich stack runs from `/home/feuer/Documents/Projects/Immich/immich-app` with its own compose file. `docker/immich.yml` is unused.

---

## Important: Scope Adjustment from Spec

The spec called for removing Immich's `127.0.0.1:2283` host port binding. **Do not do this.** Server Manager is a systemd service on the host and calls `http://localhost:2283/api` for token validation. Removing the host binding would break its auth. The binding is already localhost-only, so there is no security downgrade. Caddy accesses Immich via `immich-server:2283` on the homelab Docker network — it does not use the host port.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `server-manager/src/config.py` | Modify | Add `public_url` field to `ServerConfig` |
| `server-manager/src/main.py` | Modify | Include `public_url` in `_get_allowed_origins()` |
| `server-manager/tests/test_csrf.py` | Create | Tests for the allowed-origins logic |
| `/opt/immich-server-manager/config/config.yaml` | Modify | Set `public_url: https://monitor.houseoffeuer.com` |
| `docker/caddy/Dockerfile` | Create | xcaddy build with caddy-ratelimit plugin |
| `docker/proxy.yml` | Create | Caddy Docker Compose service |
| `docker/caddy/Caddyfile` | Create | Routing, auth, security headers, rate limiting |
| `docker/.env.example` | Modify | Uncomment `CADDY_ACME_EMAIL` and `BASE_DOMAIN` |
| `docker/photo-curator.yml` | Modify | Change `ports` to `expose` (after routing verified) |
| `/etc/cloudflared/config.yml` | Modify | Single wildcard entry pointing to Caddy |

---

## Task 1: Add `public_url` to Server Manager config and fix CSRF

**Why first:** The CSRF middleware must allow `https://monitor.houseoffeuer.com` before Caddy routes traffic there. Fix this, restart the service, then deploy Caddy.

**Files:**
- Modify: `server-manager/src/config.py`
- Modify: `server-manager/src/main.py`
- Create: `server-manager/tests/test_csrf.py`
- Modify: `/opt/immich-server-manager/config/config.yaml`

- [ ] **Step 1: Write the failing tests**

Create `server-manager/tests/test_csrf.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from src.config import Config, ServerConfig, ImmichConfig


def _make_cfg(public_url="", port=8080, api_url="http://localhost:2283/api"):
    data = {"server": {"port": port, "public_url": public_url}, "immich": {"api_url": api_url}}
    return Config(**data)


# --- _get_allowed_origins ---

def test_allowed_origins_includes_localhost(monkeypatch):
    from src.main import _get_allowed_origins
    monkeypatch.setattr("src.main.load_config", lambda: _make_cfg())
    origins = _get_allowed_origins()
    assert "http://localhost:8080" in origins
    assert "http://127.0.0.1:8080" in origins


def test_allowed_origins_includes_immich_base_url(monkeypatch):
    from src.main import _get_allowed_origins
    monkeypatch.setattr("src.main.load_config", lambda: _make_cfg())
    origins = _get_allowed_origins()
    assert "http://localhost:2283" in origins


def test_allowed_origins_includes_public_url_when_set(monkeypatch):
    from src.main import _get_allowed_origins
    monkeypatch.setattr("src.main.load_config",
                        lambda: _make_cfg(public_url="https://monitor.houseoffeuer.com"))
    origins = _get_allowed_origins()
    assert "https://monitor.houseoffeuer.com" in origins


def test_allowed_origins_omits_empty_public_url(monkeypatch):
    from src.main import _get_allowed_origins
    monkeypatch.setattr("src.main.load_config", lambda: _make_cfg(public_url=""))
    origins = _get_allowed_origins()
    assert "" not in origins
```

- [ ] **Step 2: Run tests — expect failure on `public_url` field**

```bash
cd server-manager
python -m pytest tests/test_csrf.py -v
```

Expected: `test_allowed_origins_includes_public_url_when_set` FAILS with `ValidationError` (field doesn't exist yet).

- [ ] **Step 3: Add `public_url` to `ServerConfig` in `config.py`**

In `server-manager/src/config.py`, add one field to `ServerConfig`:

```python
class ServerConfig(BaseModel):
    """Server configuration"""
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 2
    log_level: str = "INFO"
    public_url: str = ""   # Add this line
```

- [ ] **Step 4: Update `_get_allowed_origins()` in `main.py`**

Replace the existing `_get_allowed_origins` function (lines 64–76) in `server-manager/src/main.py`:

```python
def _get_allowed_origins() -> List[str]:
    """Build allowed origins from config at startup."""
    try:
        cfg = load_config()
        immich_url = cfg.immich.api_url.rsplit("/api", 1)[0]
        origins = [
            f"http://localhost:{cfg.server.port}",
            f"http://127.0.0.1:{cfg.server.port}",
            immich_url,
        ]
        if cfg.server.public_url:
            origins.append(cfg.server.public_url)
        return origins
    except Exception:
        return ["http://localhost:8080", "http://127.0.0.1:8080"]
```

- [ ] **Step 5: Run tests — expect all pass**

```bash
cd server-manager
python -m pytest tests/test_csrf.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 6: Add `public_url` to the installed config**

Edit `/opt/immich-server-manager/config/config.yaml` — add `public_url` under the `server:` block:

```yaml
server:
  host: "127.0.0.1"
  port: 8080
  workers: 2
  log_level: "INFO"
  public_url: "https://monitor.houseoffeuer.com"
```

- [ ] **Step 7: Restart Server Manager to pick up the config change**

```bash
sudo systemctl restart immich-server-manager
sudo systemctl status immich-server-manager
```

Expected: `active (running)`.

- [ ] **Step 8: Commit**

```bash
cd /home/feuer/Documents/Projects/immich-manager
git add server-manager/src/config.py server-manager/src/main.py server-manager/tests/test_csrf.py
git commit -m "feat(server-manager): add public_url config field and include in CSRF allowed origins"
```

---

## Task 2: Create the Caddy Docker build files

**Files:**
- Create: `docker/caddy/Dockerfile`
- Create: `docker/proxy.yml`

- [ ] **Step 1: Create `docker/caddy/Dockerfile`**

```dockerfile
FROM caddy:2-builder AS builder
RUN xcaddy build \
    --with github.com/mholt/caddy-ratelimit

FROM caddy:2-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
```

- [ ] **Step 2: Create `docker/proxy.yml`**

```yaml
# =============================================================================
# proxy.yml — Caddy reverse proxy
# =============================================================================
# Start with:
#   docker compose --env-file docker/.env \
#     -f docker/core.yml -f docker/proxy.yml up -d
# =============================================================================

services:
  caddy:
    build:
      context: ./caddy
      dockerfile: Dockerfile
    container_name: caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"   # HTTP/3
    volumes:
      - ./caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    extra_hosts:
      - "host.docker.internal:host-gateway"
    networks:
      - homelab

volumes:
  caddy_data:
    name: caddy_data
  caddy_config:
    name: caddy_config

networks:
  homelab:
    external: true
    name: homelab
```

- [ ] **Step 3: Commit**

```bash
git add docker/caddy/Dockerfile docker/proxy.yml
git commit -m "feat(caddy): add proxy.yml and xcaddy Dockerfile with caddy-ratelimit"
```

---

## Task 3: Write the Caddyfile

**Files:**
- Create: `docker/caddy/Caddyfile`

- [ ] **Step 1: Create `docker/caddy/Caddyfile`**

```caddyfile
{
    email {$CADDY_ACME_EMAIL}
}

# ---------------------------------------------------------------------------
# Shared snippet: security response headers applied to all three domains
# ---------------------------------------------------------------------------
(security_headers) {
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server
    }
}

# ---------------------------------------------------------------------------
# Shared snippet: validate immich_access_token before forwarding request.
# Caddy calls GET /api/users/me; any 2xx means the token is valid.
# /api/auth/validateToken was removed in Immich v2 — /api/users/me is correct.
# ---------------------------------------------------------------------------
(immich_auth) {
    forward_auth immich-server:2283 {
        uri /api/users/me
        header_up Cookie {http.request.header.Cookie}
    }
}

# ---------------------------------------------------------------------------
# Immich — main photo management app
# ---------------------------------------------------------------------------
immich.houseoffeuer.com {
    import security_headers

    # Rewrite Set-Cookie domain so immich_access_token is visible to all
    # *.houseoffeuer.com subdomains. Without this, monitor and curator
    # subdomains would never receive the cookie from the browser.
    #
    # NOTE: `header_down` with a regex applies only when the pattern matches,
    # so no named matcher is needed — and using one (with header_regexp) would
    # be wrong because header_regexp matches REQUEST headers, not response headers.
    header_down Set-Cookie "(immich_access_token=[^;]+)(.*)" "$1$2; Domain=.houseoffeuer.com"

    # Rate-limit login attempts: 5 per minute per IP
    @loginPath path /api/auth/login
    rate_limit @loginPath {
        zone login_zone {
            key {remote_host}
            events 5
            window 1m
        }
    }

    # reverse_proxy handles WebSocket upgrade automatically (Immich uses WS
    # for real-time notifications)
    reverse_proxy immich-server:2283
}

# ---------------------------------------------------------------------------
# Server Manager — admin-only. Auth gated by Caddy; role gated by the app.
# ---------------------------------------------------------------------------
monitor.houseoffeuer.com {
    import security_headers
    import immich_auth
    reverse_proxy host.docker.internal:8080
}

# ---------------------------------------------------------------------------
# Photo Curator — any authenticated Immich user
# ---------------------------------------------------------------------------
curator.houseoffeuer.com {
    import security_headers
    import immich_auth
    reverse_proxy photo-curator:8081
}
```

- [ ] **Step 2: Validate Caddyfile syntax before committing**

Run the stock Caddy image (not the custom xcaddy build) for syntax checking — the config directives used here are all built-in:

```bash
docker run --rm \
  -v "$(pwd)/docker/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" \
  caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile
```

Expected: `Valid configuration` with no errors. If you see `unknown directive: rate_limit`, that's expected — the stock image doesn't have the plugin. The important thing is no parse errors on the structural directives.

- [ ] **Step 3: Commit**

```bash
git add docker/caddy/Caddyfile
git commit -m "feat(caddy): add Caddyfile with routing, auth, cookie rewrite, and security headers"
```

---

## Task 4: Update `.env.example`

**Files:**
- Modify: `docker/.env.example`

- [ ] **Step 1: Uncomment the Caddy env vars**

In `docker/.env.example`, find the `--- Reverse proxy (Caddy) ---` section and replace the commented lines:

```bash
# --- Reverse proxy (Caddy) ---
# CADDY_ACME_EMAIL=you@example.com
# BASE_DOMAIN=yourdomain.com
```

with:

```bash
# --- Reverse proxy (Caddy) ---
CADDY_ACME_EMAIL=you@example.com
BASE_DOMAIN=yourdomain.com   # documentation only — not interpolated in Caddyfile
```

- [ ] **Step 2: Add the values to the live `.env` file**

Edit `docker/.env` and add at the bottom:

```bash
CADDY_ACME_EMAIL=<your-email>
BASE_DOMAIN=houseoffeuer.com
```

(Use the email registered with your Cloudflare/Let's Encrypt account.)

- [ ] **Step 3: Commit the `.env.example` change only** (`.env` is gitignored)

```bash
git add docker/.env.example
git commit -m "chore: uncomment Caddy env vars in .env.example"
```

---

## Task 5: Build and start Caddy — verify internal routing

- [ ] **Step 1: Build the Caddy image**

```bash
cd /home/feuer/Documents/Projects/immich-manager
docker compose --env-file docker/.env \
  -f docker/core.yml -f docker/proxy.yml build caddy
```

Expected: build completes, no errors. The xcaddy build step downloads and compiles the ratelimit plugin — this takes ~2 minutes on first run.

- [ ] **Step 2: Start Caddy**

```bash
docker compose --env-file docker/.env \
  -f docker/core.yml -f docker/proxy.yml up -d caddy
```

Expected: `caddy` container starts. Check logs:

```bash
docker logs caddy --tail 30
```

Expected: Caddy logs show it parsed the Caddyfile and is listening. No `ERROR` lines.

- [ ] **Step 3: Verify Caddy can reach Immich internally**

Note: Docker publishes port 80 to all interfaces, bypassing UFW rules — `localhost:80` is always reachable from the host regardless of UFW settings.

```bash
curl -si -H "Host: immich.houseoffeuer.com" http://localhost/api/server/version
```

Expected: `200 OK` with Immich version JSON. If you get a 502, Caddy started but can't reach `immich-server:2283` — check that Immich containers are running (`docker ps`).

- [ ] **Step 4: Verify `forward_auth` snippet works — unauthenticated request should 401**

```bash
curl -si -H "Host: monitor.houseoffeuer.com" http://localhost/
```

Expected: `401 Unauthorized` (Caddy blocked the request because no valid token was provided). This confirms `forward_auth` is active.

- [ ] **Step 5: Verify cookie domain rewrite**

Log into Immich in a browser at `http://immich.houseoffeuer.com` (still going directly for now, or via the local test with Host header). In DevTools → Application → Cookies, confirm `immich_access_token` shows `Domain: .houseoffeuer.com`.

Alternatively via curl — look for the `Domain=` attribute in the Set-Cookie response:

```bash
curl -si -H "Host: immich.houseoffeuer.com" \
  -X POST http://localhost/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"your@email.com","password":"yourpassword"}' \
  | grep -i set-cookie
```

Expected: `Set-Cookie: immich_access_token=...; Domain=.houseoffeuer.com; ...`

---

## Task 6: Update Cloudflare Tunnel config

**Files:**
- Modify: `/etc/cloudflared/config.yml`

Do this step only after Task 5 verifies Caddy is routing correctly.

- [ ] **Step 1: Back up the current tunnel config**

```bash
sudo cp /etc/cloudflared/config.yml /etc/cloudflared/config.yml.bak
```

- [ ] **Step 2: Replace the ingress rules**

Edit `/etc/cloudflared/config.yml`. Replace everything under `ingress:` with:

```yaml
ingress:
  - hostname: "*.houseoffeuer.com"
    service: http://localhost:80
  - hostname: houseoffeuer.com
    service: http://localhost:80
  - service: http_status:404
```

Full file should look like:

```yaml
tunnel: e426e62a-ccaa-4fee-b142-401bbbbb67c4
credentials-file: /root/.cloudflared/e426e62a-ccaa-4fee-b142-401bbbbb67c4.json

ingress:
  - hostname: "*.houseoffeuer.com"
    service: http://localhost:80
  - hostname: houseoffeuer.com
    service: http://localhost:80
  - service: http_status:404
```

- [ ] **Step 3: Restart cloudflared**

```bash
sudo systemctl restart cloudflared
sudo systemctl status cloudflared
```

Expected: `active (running)`.

- [ ] **Step 4: Smoke test all three public URLs**

```bash
# Immich — should load the web UI
curl -si https://immich.houseoffeuer.com/api/server/version

# Server Manager — should 401 (no auth token)
curl -si https://monitor.houseoffeuer.com/api/health

# Photo Curator — should 401 (no auth token)
curl -si https://curator.houseoffeuer.com/api/health
```

Expected:
- Immich: `200 OK`
- Monitor: `401 Unauthorized`
- Curator: `401 Unauthorized`

- [ ] **Step 5: Smoke test authenticated Server Manager access**

Get a token from Immich (use the API key from your config as a Bearer token, or log in via browser):

```bash
TOKEN=$(curl -s -X POST https://immich.houseoffeuer.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"your@email.com","password":"yourpassword"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['accessToken'])")

[ -z "$TOKEN" ] && echo "Login failed — check credentials" && exit 1

curl -si https://monitor.houseoffeuer.com/api/health \
  -H "Cookie: immich_access_token=$TOKEN"
```

Expected: `200 OK` from Server Manager.

- [ ] **Step 6: Smoke test logout propagation**

Log out of Immich, then try to reach Server Manager with the old token:

```bash
# Invalidate the token
curl -s -X POST https://immich.houseoffeuer.com/api/auth/logout \
  -H "Cookie: immich_access_token=$TOKEN"

# This should now 401
curl -si https://monitor.houseoffeuer.com/api/health \
  -H "Cookie: immich_access_token=$TOKEN"
```

Expected: `401 Unauthorized` — logout propagated.

---

## Task 7: Remove Photo Curator direct port binding

Do this last, after all routing is confirmed working via Caddy.

**Files:**
- Modify: `docker/photo-curator.yml`

- [ ] **Step 1: Change `ports` to `expose` in `docker/photo-curator.yml`**

Replace:
```yaml
    ports:
      # Exposed for direct LAN access. Remove if using Caddy reverse proxy only.
      - "8081:8081"
```

With:
```yaml
    expose:
      # Internal only — Caddy routes to photo-curator:8081 on the homelab network.
      - "8081"
```

- [ ] **Step 2: Redeploy Photo Curator to apply the change**

```bash
docker compose --env-file docker/.env \
  -f docker/core.yml -f docker/photo-curator.yml up -d photo-curator
```

- [ ] **Step 3: Confirm direct LAN access is gone**

```bash
curl -si http://localhost:8081/api/health
```

Expected: `Connection refused` — port 8081 is no longer bound to the host.

- [ ] **Step 4: Confirm Caddy routing still works**

```bash
curl -si https://curator.houseoffeuer.com/api/health
```

Expected: `401 Unauthorized` (Caddy auth gate active, not a 502).

- [ ] **Step 5: Commit**

```bash
git add docker/photo-curator.yml
git commit -m "feat(caddy): remove photo-curator direct port binding, all traffic through Caddy"
```

---

## Rollback

If something goes wrong:

```bash
# 1. Restore Cloudflare tunnel to pre-Caddy state
sudo cp /etc/cloudflared/config.yml.bak /etc/cloudflared/config.yml
sudo systemctl restart cloudflared

# 2. Stop Caddy
docker compose --env-file docker/.env \
  -f docker/core.yml -f docker/proxy.yml down

# 3. Git reset to checkpoint (restores photo-curator.yml and all other files)
git reset --hard df5686f

# 4. Restart Photo Curator so the restored ports binding takes effect
#    (the running container still has the old config until restarted)
docker compose --env-file docker/.env \
  -f docker/core.yml -f docker/photo-curator.yml up -d photo-curator
```
