# Immich Updater Fix — Design Spec
**Date:** 2026-03-23

## Problem

The Immich server is deployed with `IMMICH_VERSION=release` in `docker/.env`. The `release` tag is a floating Docker tag with no semver in it (`ghcr.io/immich-app/immich-server:release`). `UpdateChecker.get_running_version()` uses a regex that only matches version numbers (`:v?(\d+\.\d+\.\d+)`), so it returns `None` for the `release` tag.

When `current_version` is `None`, the `/api/updates/status` endpoint skips the version comparison and returns `update_available: false`. The frontend sees "up to date" and never shows the "Apply Update" button — even when a newer version is available on GitHub.

The same `None` return also silences the daily scheduled update alert job (`check_immich_update_job`) — `check_for_update()` returns `None` at line 82 when `get_running_version()` returns `None`.

The "Apply Update" button, update flow, SSE progress stream, snapshot/rollback logic, and update history all exist and work correctly. Only version detection is broken.

## Root Cause

`monitoring.py` `get_immich_containers()` returns the Docker image tag via `c.image.tags[0]`. When `IMMICH_VERSION=release`, this yields `:release`, which the version regex in `update_checker.py` cannot parse.

## Solution — Approach A

### Backend: `update_checker.py`

**New private method: `_get_version_from_immich_api() -> Optional[str]`**

Calls `GET {self.immich_api_url}/server/version` with `timeout=5`. The Immich API returns:
```json
{"major": 1, "minor": 126, "patch": 1}
```
Construct and return the version string `"1.126.1"`. Catch `requests.exceptions.RequestException` (the base class — covers `ConnectionError`, `Timeout`, `InvalidSchema`, and all other requests errors) plus `Exception` as a broad fallback. Return `None` on any failure.

**New public method: `get_running_version_with_reachability() -> Tuple[Optional[str], bool]`**

1. Call `_get_version_from_immich_api()`.
2. If it returns a version → return `(version, True)`.
3. If it returns `None` → call `get_running_version()` (Docker tag fallback) and return `(result, False)` — `False` regardless of whether the fallback found a version. `immich_reachable=False` is the authoritative fact; the fallback version is unreliable.

Note: `Tuple` is already imported in `update_checker.py` (line 11). No new imports needed beyond using `requests.exceptions.RequestException`.

**Updated `check_for_update()`**

The scheduler only needs the best available version — reachability is irrelevant here. Change:
```python
running = self.get_running_version()
if not running:
    logger.debug("Could not determine running Immich version")
    return None
```
To:
```python
running, _ = self.get_running_version_with_reachability()
if not running:
    logger.debug("Could not determine running Immich version")
    return None
```
This gives `check_for_update()` the Immich API version when reachable (fixing the bug), and falls back to the Docker image tag otherwise. The `_` discards reachability — the scheduler only needs a version to compare.

**Constructor**

Add `immich_api_url: str` as a required parameter (no default). Store as `self.immich_api_url`. The caller always passes `config.immich.api_url`.

`get_running_version()` is unchanged — it remains the Docker-tag fallback.

### Backend: `main.py` — `UpdateChecker` instantiation (line 203)

Change:
```python
update_checker = UpdateChecker(docker_monitor)
```
To:
```python
update_checker = UpdateChecker(docker_monitor, immich_api_url=config.immich.api_url)
```
`config` is the local variable set at line 183 in `startup_event`. `config.immich.api_url` defaults to `"http://localhost:2283/api"` and is already passed to `AutoUpdater` at line 213.

### Backend: `main.py` — `/api/updates/status`

Replace the `asyncio.gather` block:

```python
# Before:
current, latest = await asyncio.gather(
    loop.run_in_executor(None, update_checker.get_running_version),
    loop.run_in_executor(None, update_checker.get_latest_github_version),
)

# After:
(current, immich_reachable), latest = await asyncio.gather(
    loop.run_in_executor(None, update_checker.get_running_version_with_reachability),
    loop.run_in_executor(None, update_checker.get_latest_github_version),
)
```

The `update_available` comparison only runs when `immich_reachable=True`. When `immich_reachable=False`, set `update_available=False` unconditionally, regardless of whether the Docker fallback returned a version.

```python
update_available = False
changelog_url = None
if immich_reachable and current and latest:
    try:
        update_available = (
            update_checker._parse_version(latest) > update_checker._parse_version(current)
        )
        if update_available:
            changelog_url = f"https://github.com/immich-app/immich/releases/tag/v{latest}"
    except (ValueError, TypeError):
        pass
```

Add `immich_reachable` to the response dict.

**`/api/updates/apply` — no changes needed**

This endpoint calls `get_running_version()` (Docker-tag fallback only). With `IMMICH_VERSION=release`, `running` will be `None`. The early-exit guard `if running == latest` evaluates `None == "1.126.1"` → `False`, so the guard never fires and the update always proceeds. Accepted trade-off: if already up to date, `docker compose pull && up -d` runs unnecessarily but harmlessly. This endpoint is not updated to use `get_running_version_with_reachability()` because the "Update anyway" button is explicitly designed to work without a reliable version baseline.

**`/api/immich-update` (legacy endpoint, line 652) — no changes**

This endpoint calls `update_checker.get_running_version()` directly. Leave it unchanged and add a comment noting it uses only the Docker-tag fallback. It is a legacy diagnostic endpoint not used by the frontend update flow.

### Frontend: `UpdateManagement.jsx`

**Guard both version displays** against `null` (lines 102 and 105):
```jsx
// Line 102 — current version:
v{data.current_version ?? '?'}
// Line 105 — latest version (guard needed if GitHub is unreachable and cache is cold):
v{data.latest_version ?? '?'}
```

**Add the unreachable state** — this branch must be evaluated BEFORE the `upToDate` conditional. When `immich_reachable=false`, the backend returns `update_available=false`, which means `upToDate=true`. If the unreachable check runs after the `upToDate` ternary, the user would see a false "Up to date ✓" badge. Structure as:

```jsx
{/* Evaluate immich_reachable FIRST — overrides update_available */}
{!data.immich_reachable ? (
  <>
    <span className="...red badge...">Immich unreachable</span>
    <button onClick={applyUpdate} disabled={updating} className="...amber button...">
      Update anyway
    </button>
  </>
) : upToDate ? (
  <span className="...green badge...">Up to date ✓</span>
) : (
  <>
    <span className="...blue badge...">Update Available</span>
    <button onClick={applyUpdate} disabled={updating} className="...blue button...">
      Apply Update
    </button>
  </>
)}
```

The amber button uses the same `applyUpdate()` call as the blue button. No changes to `applyUpdate()` itself.

## Data Flow

```
/api/updates/status (GET)
  → asyncio.gather(
        get_running_version_with_reachability,   ← HTTP to Immich API (timeout=5s)
        get_latest_github_version,               ← HTTP to GitHub (cached 30min)
    )
  → immich_reachable=True:  compare current vs latest → set update_available
    immich_reachable=False: update_available = False  (no reliable baseline)
  → return { current_version, latest_version, update_available, immich_reachable, changelog_url, history }

Frontend (evaluated in order):
  immich_reachable=false                          →  "Immich unreachable" (red) + "Update anyway" (amber)
  immich_reachable=true, update_available=false   →  "Up to date ✓" (green)
  immich_reachable=true, update_available=true    →  "Update Available" (blue) + "Apply Update" (blue)
```

### Frontend: `UpdateManagement.test.jsx`

All three existing mocks lack `immich_reachable`. After the frontend change, `!data.immich_reachable` evaluates to `true` for all of them (undefined is falsy), rendering the amber unreachable state instead of the expected UI. Fix all three mocks by adding `immich_reachable: true`.

Add a fourth test:
```js
it('shows red "Immich unreachable" badge and amber "Update anyway" button', async () => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      current_version: null, latest_version: '1.3.0',
      update_available: false, immich_reachable: false,
      changelog_url: null, history: [],
    }),
  })
  render(React.createElement(UpdateManagement))
  await waitFor(() => expect(screen.getByText(/immich unreachable/i)).toBeInTheDocument())
  expect(screen.getByRole('button', { name: /update anyway/i })).toBeInTheDocument()
})
```

**Version display in the unreachable branch:** The version spans (`v{data.current_version ?? '?'}` and `v{data.latest_version ?? '?'}`) sit outside the badge/button conditional and render in all states. In the unreachable state, `current_version` is `null` → shows `v?`; `latest_version` shows the GitHub version if available. This is intentional — the user can see what the latest version is even when Immich is unreachable.

## Files Changed

| File | Change |
|------|--------|
| `server-manager/src/update_checker.py` | Add `_get_version_from_immich_api()` (timeout=5s, catch `RequestException`), `get_running_version_with_reachability()`, update `check_for_update()`, add `immich_api_url` constructor param |
| `server-manager/src/main.py` | Pass `config.immich.api_url` to `UpdateChecker` at line 203; restructure `asyncio.gather` in `/api/updates/status`; add `immich_reachable` to response; comment legacy endpoint |
| `server-manager/frontend/src/components/UpdateManagement.jsx` | Guard both version displays with `?? '?'`; add `immich_reachable` branch before `upToDate` ternary; amber "Update anyway" button |
| `server-manager/frontend/src/test/UpdateManagement.test.jsx` | Add `immich_reachable: true` to all three existing mocks; add fourth test for unreachable state |

## Out of Scope

- Changing `IMMICH_VERSION` in `.env` (floating `release` tag is intentional)
- Changes to `apply_update()`, snapshot/rollback, or SSE stream
- Auto-update scheduling interval changes
- `/api/immich-update` legacy endpoint behavior
