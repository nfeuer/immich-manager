# Immich Updater Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the Immich update checker so it correctly detects the running version by querying the Immich API, and surfaces an "Immich unreachable" error state with an "Update anyway" button when Immich is down.

**Architecture:** Add `_get_version_from_immich_api()` and `get_running_version_with_reachability()` to `UpdateChecker`, wire the new method into the `/api/updates/status` endpoint with a new `immich_reachable` field, and update the `UpdateManagement` React component to branch on reachability before showing any update badge.

**Tech Stack:** Python 3, FastAPI, `requests`, React 18, Vitest, `@testing-library/react`

---

## File Map

| File | What changes |
|------|-------------|
| `server-manager/src/update_checker.py` | Add `immich_api_url` param, `_get_version_from_immich_api()`, `get_running_version_with_reachability()`, update `check_for_update()` |
| `server-manager/src/main.py` | Pass `config.immich.api_url` to `UpdateChecker` at line 203; restructure gather + logic in `/api/updates/status`; comment legacy `/api/immich-update` endpoint |
| `server-manager/frontend/src/components/UpdateManagement.jsx` | Null-guard version displays; add `immich_reachable` branch before `upToDate` ternary |
| `server-manager/frontend/src/test/UpdateManagement.test.jsx` | Add `immich_reachable: true` to all three existing mocks; add fourth test for unreachable state |

---

### Task 1: Add `_get_version_from_immich_api()` and `get_running_version_with_reachability()` to `UpdateChecker`

**Files:**
- Modify: `server-manager/src/update_checker.py:24-28` (constructor), lines 80-83 (`check_for_update`)

- [ ] **Step 1: Write failing tests for the two new methods**

  Add a new test file `server-manager/tests/test_update_checker.py` (or append to existing if present — check with `ls server-manager/tests/` first):

  ```python
  # server-manager/tests/test_update_checker.py
  from unittest.mock import MagicMock, patch
  import pytest
  from src.update_checker import UpdateChecker


  def _make_checker(api_url="http://localhost:2283/api"):
      docker_monitor = MagicMock()
      docker_monitor.get_immich_containers.return_value = []
      return UpdateChecker(docker_monitor, immich_api_url=api_url)


  def test_get_version_from_immich_api_success():
      checker = _make_checker()
      mock_resp = MagicMock()
      mock_resp.status_code = 200
      mock_resp.json.return_value = {"major": 1, "minor": 126, "patch": 1}
      with patch("src.update_checker.requests.get", return_value=mock_resp):
          result = checker._get_version_from_immich_api()
      assert result == "1.126.1"


  def test_get_version_from_immich_api_connection_error():
      import requests
      checker = _make_checker()
      with patch("src.update_checker.requests.get", side_effect=requests.exceptions.ConnectionError()):
          result = checker._get_version_from_immich_api()
      assert result is None


  def test_get_version_from_immich_api_non_200():
      checker = _make_checker()
      mock_resp = MagicMock()
      mock_resp.status_code = 503
      mock_resp.raise_for_status.side_effect = Exception("503")
      with patch("src.update_checker.requests.get", return_value=mock_resp):
          result = checker._get_version_from_immich_api()
      assert result is None


  def test_get_running_version_with_reachability_api_success():
      checker = _make_checker()
      with patch.object(checker, "_get_version_from_immich_api", return_value="1.126.1"):
          version, reachable = checker.get_running_version_with_reachability()
      assert version == "1.126.1"
      assert reachable is True


  def test_get_running_version_with_reachability_api_fails_docker_fallback():
      checker = _make_checker()
      with patch.object(checker, "_get_version_from_immich_api", return_value=None):
          with patch.object(checker, "get_running_version", return_value="1.120.0"):
              version, reachable = checker.get_running_version_with_reachability()
      assert version == "1.120.0"
      assert reachable is False


  def test_get_running_version_with_reachability_both_fail():
      checker = _make_checker()
      with patch.object(checker, "_get_version_from_immich_api", return_value=None):
          with patch.object(checker, "get_running_version", return_value=None):
              version, reachable = checker.get_running_version_with_reachability()
      assert version is None
      assert reachable is False


  def test_check_for_update_uses_api_version():
      """check_for_update must use get_running_version_with_reachability so it works with release tag."""
      checker = _make_checker()
      with patch.object(checker, "get_running_version_with_reachability", return_value=("1.120.0", True)):
          with patch.object(checker, "get_latest_github_version", return_value="1.126.1"):
              result = checker.check_for_update()
      assert result is not None
      assert result["running_version"] == "1.120.0"
      assert result["latest_version"] == "1.126.1"
  ```

- [ ] **Step 2: Run to verify tests fail**

  ```bash
  cd server-manager && python -m pytest tests/test_update_checker.py -v 2>&1 | head -40
  ```
  Expected: multiple failures — `UpdateChecker.__init__` doesn't accept `immich_api_url`, methods don't exist yet.

- [ ] **Step 3: Update `UpdateChecker.__init__` to accept `immich_api_url`**

  In `server-manager/src/update_checker.py`, replace lines 24-28:
  ```python
  def __init__(self, docker_monitor):
      self.docker_monitor = docker_monitor
      self._last_notified_version: Optional[str] = None
      self._cached_latest: Optional[str] = None
      self._cache_ts: float = 0
  ```
  With:
  ```python
  def __init__(self, docker_monitor, immich_api_url: str):
      self.docker_monitor = docker_monitor
      self.immich_api_url = immich_api_url
      self._last_notified_version: Optional[str] = None
      self._cached_latest: Optional[str] = None
      self._cache_ts: float = 0
  ```

- [ ] **Step 4: Add `_get_version_from_immich_api()`**

  Insert after the `__init__` block (before `get_running_version`), at line 30:
  ```python
  def _get_version_from_immich_api(self) -> Optional[str]:
      """Query the running Immich server for its version via the API."""
      try:
          resp = requests.get(
              f"{self.immich_api_url}/server/version",
              timeout=5,
          )
          resp.raise_for_status()
          data = resp.json()
          return f"{data['major']}.{data['minor']}.{data['patch']}"
      except requests.exceptions.RequestException as e:
          logger.debug(f"Immich API unreachable: {e}")
          return None
      except Exception as e:
          logger.debug(f"Unexpected error querying Immich API version: {e}")
          return None
  ```

- [ ] **Step 5: Add `get_running_version_with_reachability()`**

  Insert after `get_running_version()` (after line 45):
  ```python
  def get_running_version_with_reachability(self) -> Tuple[Optional[str], bool]:
      """
      Return (version, immich_reachable).

      Tries the Immich API first (authoritative). Falls back to Docker image
      tag parsing if the API is unreachable. immich_reachable=False means the
      API call failed regardless of whether the fallback found a version.
      """
      api_version = self._get_version_from_immich_api()
      if api_version:
          return api_version, True
      return self.get_running_version(), False
  ```

- [ ] **Step 6: Update `check_for_update()` to use the new method**

  In `check_for_update()`, replace lines 80-83:
  ```python
  running = self.get_running_version()
  if not running:
      logger.debug("Could not determine running Immich version")
      return None
  ```
  With:
  ```python
  running, _ = self.get_running_version_with_reachability()
  if not running:
      logger.debug("Could not determine running Immich version")
      return None
  ```

- [ ] **Step 7: Run tests to verify they pass**

  ```bash
  cd server-manager && python -m pytest tests/test_update_checker.py -v
  ```
  Expected: all 7 tests PASS.

- [ ] **Step 8: Commit**

  ```bash
  git add server-manager/src/update_checker.py server-manager/tests/test_update_checker.py
  git commit -m "feat(update-checker): query Immich API for running version, add reachability detection"
  ```

---

### Task 2: Wire `immich_api_url` and `immich_reachable` into `main.py`

**Files:**
- Modify: `server-manager/src/main.py:203` (UpdateChecker instantiation)
- Modify: `server-manager/src/main.py:1210-1245` (`/api/updates/status` endpoint)
- Modify: `server-manager/src/main.py:652-657` (legacy endpoint comment)

- [ ] **Step 1: Pass `immich_api_url` to `UpdateChecker`**

  In `server-manager/src/main.py`, find line 203:
  ```python
  update_checker = UpdateChecker(docker_monitor)
  ```
  Change to:
  ```python
  update_checker = UpdateChecker(docker_monitor, immich_api_url=config.immich.api_url)
  ```

- [ ] **Step 2: Restructure the gather block in `/api/updates/status`**

  Find this block (around line 1217):
  ```python
  loop = asyncio.get_running_loop()
  current, latest = await asyncio.gather(
      loop.run_in_executor(None, update_checker.get_running_version),
      loop.run_in_executor(None, update_checker.get_latest_github_version),
  )

  update_available = False
  changelog_url = None
  if current and latest:
      try:
          update_available = (
              update_checker._parse_version(latest) > update_checker._parse_version(current)
          )
          if update_available:
              changelog_url = f"https://github.com/immich-app/immich/releases/tag/v{latest}"
      except (ValueError, TypeError):
          pass
  ```
  Replace with:
  ```python
  loop = asyncio.get_running_loop()
  (current, immich_reachable), latest = await asyncio.gather(
      loop.run_in_executor(None, update_checker.get_running_version_with_reachability),
      loop.run_in_executor(None, update_checker.get_latest_github_version),
  )

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

- [ ] **Step 3: Add `immich_reachable` to the response dict**

  Find the return statement (around line 1239):
  ```python
  return {
      "current_version": current,
      "latest_version": latest,
      "update_available": update_available,
      "changelog_url": changelog_url,
      "history": history,
  }
  ```
  Add `immich_reachable`:
  ```python
  return {
      "current_version": current,
      "latest_version": latest,
      "update_available": update_available,
      "immich_reachable": immich_reachable,
      "changelog_url": changelog_url,
      "history": history,
  }
  ```

- [ ] **Step 4: Add comment to the legacy `/api/immich-update` endpoint**

  Find line 652:
  ```python
  @app.get("/api/immich-update")
  @limiter.limit("5/minute")
  async def check_immich_update(request: Request, user: Dict = Depends(require_admin)):
      """Check if a newer Immich version is available on GitHub"""
  ```
  Change the docstring:
  ```python
  @app.get("/api/immich-update")
  @limiter.limit("5/minute")
  async def check_immich_update(request: Request, user: Dict = Depends(require_admin)):
      """Legacy diagnostic endpoint. Uses Docker image tag fallback only (not Immich API).
      Not used by the frontend update flow — see /api/updates/status instead."""
  ```

- [ ] **Step 5: Start the server and verify it starts without errors**

  ```bash
  cd server-manager && python -m uvicorn src.main:app --host 0.0.0.0 --port 8080 2>&1 | head -20
  ```
  Expected: server starts, no `TypeError: __init__() missing argument` errors.
  Stop with Ctrl+C after confirming startup.

- [ ] **Step 6: Commit**

  ```bash
  git add server-manager/src/main.py
  git commit -m "feat(server-manager): add immich_reachable to update status endpoint"
  ```

---

### Task 3: Update `UpdateManagement.jsx` frontend and fix tests

**Files:**
- Modify: `server-manager/frontend/src/components/UpdateManagement.jsx`
- Modify: `server-manager/frontend/src/test/UpdateManagement.test.jsx`

- [ ] **Step 1: Add `immich_reachable: true` to all existing test mocks and add the fourth test**

  Open `server-manager/frontend/src/test/UpdateManagement.test.jsx`. There are three `json: async () => ({...})` blocks. Add `immich_reachable: true` to all three.

  The file should end up looking like:
  ```js
  import { describe, it, expect, vi, beforeEach } from 'vitest'
  import React from 'react'
  import { render, screen, waitFor } from '@testing-library/react'
  import UpdateManagement from '../components/UpdateManagement.jsx'

  beforeEach(() => {
    global.EventSource = vi.fn().mockImplementation(() => ({
      onmessage: null, onerror: null, close: vi.fn(),
    }))
  })

  describe('UpdateManagement', () => {
    it('shows green "Up to date" badge when current', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          current_version: '1.2.3', latest_version: '1.2.3',
          update_available: false, immich_reachable: true,
          changelog_url: null, history: [],
        }),
      })
      render(React.createElement(UpdateManagement))
      await waitFor(() => expect(screen.getByText(/up to date/i)).toBeInTheDocument())
    })

    it('shows blue "Update Available" badge and Apply button when update exists', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          current_version: '1.2.3', latest_version: '1.3.0',
          update_available: true, immich_reachable: true,
          changelog_url: 'https://github.com/immich-app/immich/releases/tag/v1.3.0',
          history: [],
        }),
      })
      render(React.createElement(UpdateManagement))
      await waitFor(() => expect(screen.getByText(/update available/i)).toBeInTheDocument())
      expect(screen.getByRole('button', { name: /apply update/i })).toBeInTheDocument()
    })

    it('does not render changelog link for non-github URLs', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          current_version: '1.2.3', latest_version: '1.3.0',
          update_available: true, immich_reachable: true,
          changelog_url: 'https://evil.com/steal', history: [],
        }),
      })
      render(React.createElement(UpdateManagement))
      await waitFor(() => screen.getByText(/update available/i))
      expect(screen.queryByText(/changelog/i)).not.toBeInTheDocument()
    })

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
  })
  ```

- [ ] **Step 2: Run tests — they should fail because the component hasn't changed yet**

  ```bash
  cd server-manager/frontend && npm test 2>&1 | tail -30
  ```
  Expected: existing tests fail (rendering amber state instead of green/blue), new test also fails (component doesn't have unreachable state yet).

- [ ] **Step 3: Update `UpdateManagement.jsx`**

  Open `server-manager/frontend/src/components/UpdateManagement.jsx`.

  **Change 1** — null-guard on current version (line 102):
  ```jsx
  // Before:
  Current: <span className="font-mono font-semibold text-immich-text">v{data.current_version}</span>
  // After:
  Current: <span className="font-mono font-semibold text-immich-text">v{data.current_version ?? '?'}</span>
  ```

  **Change 2** — null-guard on latest version (line 105):
  ```jsx
  // Before:
  Latest: <span className="font-mono font-semibold text-immich-text">v{data.latest_version}</span>
  // After:
  Latest: <span className="font-mono font-semibold text-immich-text">v{data.latest_version ?? '?'}</span>
  ```

  **Change 3** — replace the badge/button conditional block. Find:
  ```jsx
  {upToDate ? (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-900/40 text-green-400 border border-green-800">
      Up to date ✓
    </span>
  ) : (
    <>
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-900/40 text-blue-400 border border-blue-800">
        Update Available
      </span>
      <button
        onClick={() => { applyUpdate() }}
        disabled={updating}
        className="px-4 py-1.5 bg-immich-primary hover:bg-blue-600 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors duration-150"
      >
        Apply Update
      </button>
    </>
  )}
  ```
  Replace with:
  ```jsx
  {!data.immich_reachable ? (
    <>
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-900/40 text-red-400 border border-red-800">
        Immich unreachable
      </span>
      <button
        onClick={() => { applyUpdate() }}
        disabled={updating}
        className="px-4 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors duration-150"
      >
        Update anyway
      </button>
    </>
  ) : upToDate ? (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-900/40 text-green-400 border border-green-800">
      Up to date ✓
    </span>
  ) : (
    <>
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-900/40 text-blue-400 border border-blue-800">
        Update Available
      </span>
      <button
        onClick={() => { applyUpdate() }}
        disabled={updating}
        className="px-4 py-1.5 bg-immich-primary hover:bg-blue-600 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors duration-150"
      >
        Apply Update
      </button>
    </>
  )}
  ```

- [ ] **Step 4: Run tests — all 4 should pass**

  ```bash
  cd server-manager/frontend && npm test 2>&1 | tail -20
  ```
  Expected: 4 tests PASS, 0 failures.

- [ ] **Step 5: Commit**

  ```bash
  git add server-manager/frontend/src/components/UpdateManagement.jsx \
          server-manager/frontend/src/test/UpdateManagement.test.jsx
  git commit -m "feat(frontend): add Immich unreachable state with Update anyway button"
  ```

---

### Task 4: Build frontend and verify end-to-end

- [ ] **Step 1: Build the frontend**

  ```bash
  cd server-manager/frontend && npm run build 2>&1 | tail -10
  ```
  Expected: build completes with no errors, `dist/` updated.

- [ ] **Step 2: Commit the built frontend**

  ```bash
  git add server-manager/frontend/dist/
  git commit -m "build: rebuild frontend with Immich updater fix"
  ```

- [ ] **Step 3: Run the full Python test suite**

  ```bash
  cd server-manager && python -m pytest tests/ -v 2>&1 | tail -20
  ```
  Expected: all tests pass (no regressions from the `UpdateChecker` constructor change).

- [ ] **Step 4: Run full JS test suite**

  ```bash
  cd server-manager/frontend && npm test 2>&1 | tail -10
  ```
  Expected: all tests pass.

- [ ] **Final commit if any remaining changes**

  ```bash
  git status
  # If anything unstaged:
  git add -p
  git commit -m "chore: finalize immich updater fix"
  ```
