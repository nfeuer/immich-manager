# Immich Updater Fix — Design Spec
**Date:** 2026-03-23

## Problem

The Immich server is deployed with `IMMICH_VERSION=release` in `docker/.env`. The `release` tag is a floating Docker tag with no semver in it (`ghcr.io/immich-app/immich-server:release`). `UpdateChecker.get_running_version()` uses a regex that only matches version numbers (`:v?(\d+\.\d+\.\d+)`), so it returns `None` for the `release` tag.

When `current_version` is `None`, the `/api/updates/status` endpoint skips the version comparison and returns `update_available: false`. The frontend sees "up to date" and never shows the "Apply Update" button — even when a newer version is available on GitHub.

The "Apply Update" button, update flow, SSE progress stream, snapshot/rollback logic, and update history all exist and work correctly. Only version detection is broken.

## Root Cause

`monitoring.py` `get_immich_containers()` returns the Docker image tag via `c.image.tags[0]`. When `IMMICH_VERSION=release`, this yields `:release`, which the version regex in `update_checker.py` cannot parse.

## Solution — Approach A

### Backend: `update_checker.py`

Add a new private method `_get_version_from_immich_api() -> Optional[str]` that calls `GET {immich_api_url}/server/version`. The Immich API returns:
```json
{"major": 1, "minor": 126, "patch": 1}
```
Construct and return the version string `"1.126.1"`. On any failure (connection error, timeout, non-200 response), return `None`.

Change `get_running_version()` to:
1. Try `_get_version_from_immich_api()` first.
2. If that returns a version, return it.
3. Otherwise fall back to the existing Docker image-tag regex logic.

`UpdateChecker.__init__` receives `immich_api_url` as a new parameter (defaulting to `"http://localhost:2283/api"`). The caller in `main.py` already has this URL available.

### Backend: `main.py` — `/api/updates/status`

Add `immich_reachable: bool` to the response. This is `True` when `_get_version_from_immich_api()` succeeds, `False` when it fails (regardless of whether the Docker tag fallback provided a version).

Track reachability by calling `_get_version_from_immich_api()` directly in the status endpoint (or expose it as a method on `UpdateChecker`). The simplest approach: add a `get_running_version_with_reachability() -> Tuple[Optional[str], bool]` method that returns `(version, immich_reachable)`.

### Frontend: `UpdateManagement.jsx`

Add a fourth UI state for `data.immich_reachable === false`:

- Show current version as `v?`
- Show a red "Immich unreachable" badge alongside the latest version
- Show an amber "Update anyway" button that triggers the same `applyUpdate()` function
- The existing "Up to date ✓" green badge and "Update Available" blue badge + "Apply Update" blue button paths are unchanged

## Data Flow

```
/api/updates/status (GET)
  → UpdateChecker.get_running_version_with_reachability()
      → tries GET /api/server/version on Immich
          success → returns (version, reachable=True)
          failure → tries Docker image tag regex
                      success → returns (version, reachable=False)  ← version may be wrong
                      failure → returns (None, reachable=False)
  → compare current vs latest from GitHub
  → return { current_version, latest_version, update_available, immich_reachable, changelog_url, history }

Frontend receives response:
  immich_reachable=true, update_available=false  → "Up to date ✓" (green)
  immich_reachable=true, update_available=true   → "Update Available" (blue) + "Apply Update" button
  immich_reachable=false                         → "Immich unreachable" (red) + "Update anyway" button (amber)
```

## Files Changed

| File | Change |
|------|--------|
| `server-manager/src/update_checker.py` | Add `_get_version_from_immich_api()`, `get_running_version_with_reachability()`, `immich_api_url` param |
| `server-manager/src/main.py` | Pass `immich_api_url` to `UpdateChecker`, use `get_running_version_with_reachability()` in status endpoint, add `immich_reachable` to response |
| `server-manager/frontend/src/components/UpdateManagement.jsx` | Add unreachable state UI with amber "Update anyway" button |

## Out of Scope

- Changing `IMMICH_VERSION` in `.env` (floating `release` tag is intentional)
- Changes to the `apply_update()` workflow, snapshot/rollback, or SSE stream
- Auto-update scheduling changes
