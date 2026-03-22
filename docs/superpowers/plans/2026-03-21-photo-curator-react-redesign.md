# Photo Curator React Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Photo Curator's 7 static HTML pages into a React SPA matching server-manager's design system, fix the photo-loading workflow, add sidebar navigation, and expose a year-progress tracker.

**Architecture:** Two new FastAPI endpoints (`/api/photos/{year}/{month}/raw` and `/api/progress/year/{year}`) are added alongside the existing ones. FastAPI serves the built React dist at `/` (same pattern as server-manager). The React SPA uses React Router v6 for page routing, TanStack Query for data fetching, and a shared auth hook that detects 401s and shows a "Sign in via Immich" screen.

**Tech Stack:** Python 3.11 / FastAPI (backend), React 18 + Vite 5 + Tailwind CSS 3 + React Router v6 + TanStack Query v5 + @heroicons/react (frontend), Vitest + @testing-library/react (frontend tests), pytest + httpx (backend tests)

---

## File Map

### New backend files
| Path | Purpose |
|---|---|
| `photo-curator/tests/__init__.py` | Test package marker |
| `photo-curator/tests/test_raw_photos.py` | Tests for `/api/photos/{year}/{month}/raw` |
| `photo-curator/tests/test_year_progress.py` | Tests for `/api/progress/year/{year}` |

### Modified backend files
| Path | Change |
|---|---|
| `photo-curator/src/main.py` | Add 2 new endpoints, mount React dist, tighten CSP |

### New frontend files (all under `photo-curator/frontend/`)
| Path | Purpose |
|---|---|
| `package.json` | Dependencies (mirrors server-manager + react-router-dom) |
| `vite.config.js` | Build config with proxy to :8081 |
| `tailwind.config.js` | Exact copy of server-manager tokens |
| `postcss.config.js` | Autoprefixer |
| `index.html` | HTML shell |
| `src/main.jsx` | React root + QueryClient |
| `src/App.jsx` | Router + AuthGuard |
| `src/index.css` | Tailwind directives |
| `src/utils/api.js` | Fetch wrapper; throws on 401 |
| `src/hooks/useAuth.js` | Auth state: detects 401, stores login URL |
| `src/hooks/useCurator.js` | Photos, analysis progress, curation selections |
| `src/hooks/useYearProgress.js` | 12-month curation status |
| `src/components/Layout.jsx` | Sidebar (desktop) + outlet |
| `src/components/Sidebar.jsx` | Fixed left nav with badge |
| `src/components/BottomTabBar.jsx` | Mobile bottom tabs |
| `src/components/YearTracker.jsx` | 12 month pill row |
| `src/components/PhotoGrid.jsx` | Thumbnail grid with selection state |
| `src/components/CurationFooter.jsx` | Sticky footer: count + Save/Reset |
| `src/pages/Login.jsx` | "Sign in via Immich" screen |
| `src/pages/AlbumCurator.jsx` | Main curation page |
| `src/pages/Import.jsx` | Import wizard |
| `src/pages/Duplicates.jsx` | Side-by-side duplicate cards |
| `src/pages/Events.jsx` | Event cluster album cards |
| `src/pages/Analytics.jsx` | Stats cards + charts |
| `src/pages/Preferences.jsx` | Settings form |
| `src/test/setup.js` | Vitest setup (jest-dom matchers) |
| `src/test/Layout.test.jsx` | Sidebar + BottomTabBar render tests |
| `src/test/YearTracker.test.jsx` | Pill states + click tests |
| `src/test/AlbumCurator.test.jsx` | Photo load, analysis progress, curation flow |

---

## Task 1: Add `/api/photos/{year}/{month}/raw` endpoint

**Files:**
- Modify: `photo-curator/src/main.py`
- Create: `photo-curator/tests/__init__.py`
- Create: `photo-curator/tests/test_raw_photos.py`

**Context:** `get_user_photos(user_id, year, month)` is on `ImmichClient` (which takes `use_bearer=True` for user tokens). The user dict from `get_current_user` has `id` (Immich user ID) and `access_token`. The existing `/api/photos/{year}/{month}` returns scored photos; this new endpoint returns unscored photos directly from Immich.

- [ ] **Step 1: Create test package**

```bash
touch photo-curator/tests/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `photo-curator/tests/test_raw_photos.py`:
```python
"""Tests for GET /api/photos/{year}/{month}/raw"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from main import app

FAKE_USER = {
    "id": "user-123",
    "email": "test@example.com",
    "name": "Test User",
    "access_token": "tok-abc",
    "_local_user": {"id": 1, "role": "user"},
}

FAKE_PHOTOS = [
    {
        "id": "asset-1",
        "fileCreatedAt": "2024-03-15T10:00:00Z",
        "exifInfo": {"exifImageWidth": 1920, "exifImageHeight": 1080},
    },
    {
        "id": "asset-2",
        "fileCreatedAt": "2024-03-20T12:00:00Z",
        "exifInfo": {"exifImageWidth": 800, "exifImageHeight": 600},
    },
]


def _auth_override():
    return FAKE_USER


def test_raw_photos_returns_list():
    app.dependency_overrides = {}
    from auth import get_current_user
    app.dependency_overrides[get_current_user] = _auth_override

    with patch("main.ImmichClient") as MockClient:
        instance = MockClient.return_value
        instance.get_user_photos.return_value = FAKE_PHOTOS

        client = TestClient(app)
        resp = client.get("/api/photos/2024/3/raw")

    app.dependency_overrides = {}
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["photos"][0]["asset_id"] == "asset-1"
    assert data["photos"][0]["thumbnail_url"] == "/api/thumbnail/asset-1"
    assert data["photos"][0]["width"] == 1920
    assert data["photos"][0]["height"] == 1080


def test_raw_photos_requires_auth():
    app.dependency_overrides = {}
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/photos/2024/3/raw")
    assert resp.status_code == 401


def test_raw_photos_empty_month():
    from auth import get_current_user
    app.dependency_overrides[get_current_user] = _auth_override

    with patch("main.ImmichClient") as MockClient:
        instance = MockClient.return_value
        instance.get_user_photos.return_value = []

        client = TestClient(app)
        resp = client.get("/api/photos/2024/2/raw")

    app.dependency_overrides = {}
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["photos"] == []
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd photo-curator && python -m pytest tests/test_raw_photos.py -v 2>&1 | head -30
```
Expected: `FAILED` — endpoint does not exist yet.

- [ ] **Step 4: Add the endpoint to `main.py`**

Find the section of `main.py` where the existing `GET /api/photos/{year}/{month}` endpoint is defined (search for `@app.get("/api/photos/{year}/{month}")`). Add the new endpoint directly after it:

```python
@app.get("/api/photos/{year}/{month}/raw")
async def get_raw_photos(
    year: int,
    month: int,
    current_user: Dict = Depends(get_current_user),
):
    """Fetch photos for a month directly from Immich, no analysis required."""
    immich_api_url = app.state.immich_api_url
    user_client = ImmichClient(immich_api_url, current_user["access_token"], use_bearer=True)
    photos = user_client.get_user_photos(current_user["id"], year, month)
    return {
        "photos": [
            {
                "asset_id": p["id"],
                "thumbnail_url": f"/api/thumbnail/{p['id']}",
                "width": p.get("exifInfo", {}).get("exifImageWidth"),
                "height": p.get("exifInfo", {}).get("exifImageHeight"),
                "taken_at": p.get("fileCreatedAt"),
            }
            for p in photos
        ],
        "total": len(photos),
    }
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd photo-curator && python -m pytest tests/test_raw_photos.py -v
```
Expected: 3 tests `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add photo-curator/tests/__init__.py photo-curator/tests/test_raw_photos.py photo-curator/src/main.py
git commit -m "feat(curator): add GET /api/photos/{year}/{month}/raw endpoint"
```

---

## Task 2: Add `/api/progress/year/{year}` endpoint

**Files:**
- Modify: `photo-curator/src/main.py`
- Modify: `photo-curator/src/database.py`
- Create: `photo-curator/tests/test_year_progress.py`

**Context:** "Curated" = a `curation_sessions` row exists for `(user_id, year, month)` with `status = 'completed'` and a non-null `album_id`. The database object is on `request.app.state.database`.

- [ ] **Step 1: Add `get_year_progress` to Database**

Find the curation session methods in `photo-curator/src/database.py` (search for `complete_curation_session`) and add after them:

```python
def get_year_progress(self, user_id: str, year: int) -> dict:
    """
    Return curation status for all 12 months of a year.

    Returns:
        Dict mapping month (1-12) to bool (True = completed album exists)
    """
    with self._get_connection() as conn:
        rows = conn.execute(
            """
            SELECT month FROM curation_sessions
            WHERE user_id = ? AND year = ? AND status = 'completed' AND album_id IS NOT NULL
            """,
            (user_id, year),
        ).fetchall()
    curated = {row[0] for row in rows}
    return {month: month in curated for month in range(1, 13)}
```

- [ ] **Step 2: Write the failing tests**

Create `photo-curator/tests/test_year_progress.py`:
```python
"""Tests for GET /api/progress/year/{year}"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from main import app

FAKE_USER = {
    "id": "user-123",
    "email": "test@example.com",
    "name": "Test User",
    "access_token": "tok-abc",
    "_local_user": {"id": 1, "role": "user"},
}


def _auth_override():
    return FAKE_USER


def test_year_progress_returns_12_months():
    from auth import get_current_user
    app.dependency_overrides[get_current_user] = _auth_override

    mock_db = MagicMock()
    mock_db.get_year_progress.return_value = {m: m in (1, 3) for m in range(1, 13)}
    app.state.database = mock_db

    client = TestClient(app)
    resp = client.get("/api/progress/year/2024")

    app.dependency_overrides = {}
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 12
    assert data["1"] is True
    assert data["3"] is True
    assert data["2"] is False
    assert data["12"] is False


def test_year_progress_requires_auth():
    app.dependency_overrides = {}
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/progress/year/2024")
    assert resp.status_code == 401
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd photo-curator && python -m pytest tests/test_year_progress.py -v 2>&1 | head -20
```
Expected: `FAILED`.

- [ ] **Step 4: Add the endpoint to `main.py`**

Find `GET /api/photos/{year}/{month}/raw` you just added and place the new endpoint after it:

```python
@app.get("/api/progress/year/{year}")
async def get_year_progress(
    year: int,
    current_user: Dict = Depends(get_current_user),
):
    """Return curation status for all 12 months of a year."""
    db = app.state.database
    progress = db.get_year_progress(current_user["id"], year)
    return progress
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd photo-curator && python -m pytest tests/test_year_progress.py -v
```
Expected: 2 tests `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add photo-curator/src/main.py photo-curator/src/database.py photo-curator/tests/test_year_progress.py
git commit -m "feat(curator): add GET /api/progress/year/{year} endpoint"
```

---

## Task 3: Serve React SPA from FastAPI + tighten CSP

**Files:**
- Modify: `photo-curator/src/main.py`

**Context:** The existing `GET /` serves inline HTML. The React build will land at `photo-curator/frontend/dist/`. We mount `/assets` as a static dir and return `index.html` for the root. The CSP currently allows Tailwind CDN and Chart.js CDN — these are no longer needed once Tailwind is bundled.

The `not_authenticated_handler` (which returns an HTML login page) will become unreachable once the React app handles 401s, but we leave it in place — it's harmless and protects direct-browser access to API endpoints that aren't consumed by the SPA.

- [ ] **Step 1: Find the current `GET /` handler**

```bash
grep -n '@app.get("/")' photo-curator/src/main.py
```
Note the line number.

- [ ] **Step 2: Add StaticFiles import and mount**

At the top of `main.py`, in the `from fastapi` imports line, add `StaticFiles`:
```python
from fastapi.staticfiles import StaticFiles
```

After the `app = FastAPI(...)` block (around line 57), add the static mount:
```python
# Serve React frontend assets — must be declared before route handlers
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")
```

- [ ] **Step 3: Replace the `GET /` handler**

Find the existing `GET /` handler (it returns an `HTMLResponse` or `RedirectResponse` for the curator HTML). Replace its body so it serves `index.html`:

```python
@app.get("/")
async def serve_spa(request: Request):
    """Serve React SPA entry point."""
    index_path = Path(__file__).resolve().parent.parent / "frontend" / "dist" / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text())
    return HTMLResponse(content="<p>Frontend not built. Run: cd photo-curator/frontend && npm run build</p>", status_code=503)
```

- [ ] **Step 4: Tighten the CSP**

Find the `add_security_headers` middleware and update the CSP string — remove CDN allowances now that everything is bundled:

```python
response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "frame-ancestors 'none'"
)
```

- [ ] **Step 5: Smoke test (no frontend yet)**

```bash
cd photo-curator && python -m pytest tests/ -v
```
Expected: all existing tests pass. The `/` route will return 503 until the frontend is built — that's intentional.

- [ ] **Step 6: Commit**

```bash
git add photo-curator/src/main.py
git commit -m "feat(curator): serve React SPA from FastAPI, tighten CSP"
```

---

## Task 4: Scaffold frontend project

**Files:**
- Create: `photo-curator/frontend/package.json`
- Create: `photo-curator/frontend/vite.config.js`
- Create: `photo-curator/frontend/tailwind.config.js`
- Create: `photo-curator/frontend/postcss.config.js`
- Create: `photo-curator/frontend/index.html`

- [ ] **Step 1: Create `package.json`**

```json
{
  "name": "photo-curator",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@heroicons/react": "^2.1.5",
    "@tanstack/react-query": "^5.56.2",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.2"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.20",
    "jsdom": "^25.0.0",
    "postcss": "^8.4.47",
    "tailwindcss": "^3.4.12",
    "vite": "^5.4.8",
    "vitest": "^2.1.1"
  }
}
```

- [ ] **Step 2: Create `vite.config.js`**

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: 'dist',
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8081',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
  },
})
```

- [ ] **Step 3: Create `tailwind.config.js`** (exact copy of server-manager tokens)

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        'immich-primary': '#4250af',
        'immich-bg': '#0f0f11',
        'immich-surface': '#1a1a27',
        'immich-border': '#2a2a3d',
        'immich-text': '#f1f0ff',
        'immich-muted': '#7c7c9a',
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 4: Create `postcss.config.js`**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

- [ ] **Step 5: Create `index.html`**

```html
<!DOCTYPE html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Photo Curator</title>
  </head>
  <body class="bg-immich-bg text-immich-text">
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Install dependencies**

```bash
cd photo-curator/frontend && npm install
```
Expected: `node_modules/` created, no errors.

- [ ] **Step 7: Commit**

```bash
git add photo-curator/frontend/package.json photo-curator/frontend/package-lock.json \
  photo-curator/frontend/vite.config.js photo-curator/frontend/tailwind.config.js \
  photo-curator/frontend/postcss.config.js photo-curator/frontend/index.html
git commit -m "chore(curator-frontend): scaffold Vite + React + Tailwind project"
```

---

## Task 5: API utility + auth hook + Login page

**Files:**
- Create: `photo-curator/frontend/src/utils/api.js`
- Create: `photo-curator/frontend/src/hooks/useAuth.js`
- Create: `photo-curator/frontend/src/pages/Login.jsx`
- Create: `photo-curator/frontend/src/index.css`
- Create: `photo-curator/frontend/src/test/setup.js`

**Context:** `get_current_user` in `auth.py` returns a 401 with JSON `{ "detail": { "error": "Not authenticated", "login_url": "<immich-login-url>" } }`. The React frontend reads `login_url` from the 401 body to show the "Sign in via Immich" button.

- [ ] **Step 1: Create `src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 2: Create `src/test/setup.js`**

```javascript
import '@testing-library/jest-dom'
```

- [ ] **Step 3: Create `src/utils/api.js`**

```javascript
/**
 * Fetch wrapper that throws a structured AuthError on 401,
 * or a plain Error on other non-OK responses.
 */
export class AuthError extends Error {
  constructor(loginUrl) {
    super('Not authenticated')
    this.name = 'AuthError'
    this.loginUrl = loginUrl
  }
}

export async function apiFetch(path, options = {}) {
  const resp = await fetch(path, {
    credentials: 'include',
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  })

  if (resp.status === 401) {
    let loginUrl = null
    try {
      const body = await resp.json()
      loginUrl = body?.detail?.login_url ?? null
    } catch (_) {}
    throw new AuthError(loginUrl)
  }

  if (!resp.ok) {
    throw new Error(`API error ${resp.status}: ${resp.statusText}`)
  }

  return resp.json()
}
```

- [ ] **Step 4: Create `src/hooks/useAuth.js`**

```javascript
import { useState, useCallback } from 'react'
import { AuthError } from '../utils/api'

/**
 * Tracks auth state. When any query throws an AuthError,
 * call onAuthError(error) to capture the login URL and show the Login page.
 */
export function useAuth() {
  const [loginUrl, setLoginUrl] = useState(null)

  const onAuthError = useCallback((error) => {
    if (error instanceof AuthError) {
      setLoginUrl(error.loginUrl)
    }
  }, [])

  const clearAuthError = useCallback(() => setLoginUrl(null), [])

  return { loginUrl, onAuthError, clearAuthError }
}
```

- [ ] **Step 5: Create `src/pages/Login.jsx`**

```jsx
export default function Login({ loginUrl }) {
  return (
    <div className="min-h-screen bg-immich-bg flex items-center justify-center">
      <div className="bg-immich-surface border border-immich-border rounded-xl p-8 max-w-sm w-full text-center">
        {/* Immich logo placeholder */}
        <div className="w-16 h-16 rounded-full bg-immich-primary mx-auto mb-4 flex items-center justify-center">
          <span className="text-white text-2xl font-bold">I</span>
        </div>
        <h1 className="text-immich-text text-xl font-semibold mb-2">Photo Curator</h1>
        <p className="text-immich-muted text-sm mb-6">Sign in with your Immich account to continue.</p>
        {loginUrl ? (
          <a
            href={loginUrl}
            className="inline-block w-full px-4 py-2 bg-immich-primary text-white font-medium rounded-lg hover:opacity-90 transition-opacity"
          >
            Sign in via Immich
          </a>
        ) : (
          <p className="text-immich-muted text-sm">
            Unable to reach the server. Is Photo Curator running?
          </p>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Commit**

```bash
git add photo-curator/frontend/src/
git commit -m "feat(curator-frontend): add API utility, auth hook, and Login page"
```

---

## Task 6: Layout — Sidebar + BottomTabBar + tests

**Files:**
- Create: `photo-curator/frontend/src/components/Sidebar.jsx`
- Create: `photo-curator/frontend/src/components/BottomTabBar.jsx`
- Create: `photo-curator/frontend/src/components/Layout.jsx`
- Create: `photo-curator/frontend/src/test/Layout.test.jsx`

**Context:** Nav items: AI Album Curator (`/`), Import (`/import`), Duplicates (`/duplicates`), Events & Trips (`/events`), Analytics (`/analytics`), Preferences (`/preferences`). The "AI Album Curator" item shows a badge with the count of un-curated months in the current year. The badge is hidden when 0.

- [ ] **Step 1: Write the failing tests**

Create `photo-curator/frontend/src/test/Layout.test.jsx`:
```jsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import BottomTabBar from '../components/BottomTabBar'

const NAV_LABELS = ['AI Album Curator', 'Import', 'Duplicates', 'Events & Trips', 'Analytics', 'Preferences']

describe('Sidebar', () => {
  it('renders all nav items', () => {
    render(
      <MemoryRouter>
        <Sidebar uncuratedCount={0} />
      </MemoryRouter>
    )
    NAV_LABELS.forEach(label => {
      expect(screen.getByText(label)).toBeInTheDocument()
    })
  })

  it('shows badge when uncuratedCount > 0', () => {
    render(
      <MemoryRouter>
        <Sidebar uncuratedCount={5} />
      </MemoryRouter>
    )
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('hides badge when uncuratedCount is 0', () => {
    render(
      <MemoryRouter>
        <Sidebar uncuratedCount={0} />
      </MemoryRouter>
    )
    expect(screen.queryByTestId('curator-badge')).not.toBeInTheDocument()
  })
})

describe('BottomTabBar', () => {
  it('renders 6 tab icons', () => {
    render(
      <MemoryRouter>
        <BottomTabBar />
      </MemoryRouter>
    )
    // 6 nav links
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(6)
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd photo-curator/frontend && npm test 2>&1 | tail -20
```
Expected: failures — components don't exist.

- [ ] **Step 3: Create `src/components/Sidebar.jsx`**

```jsx
import { NavLink } from 'react-router-dom'
import {
  PhotoIcon,
  ArrowUpTrayIcon,
  DocumentDuplicateIcon,
  MapIcon,
  ChartBarIcon,
  Cog6ToothIcon,
} from '@heroicons/react/24/outline'

const NAV_ITEMS = [
  { to: '/',            label: 'AI Album Curator', Icon: PhotoIcon,             key: 'curator' },
  { to: '/import',      label: 'Import',            Icon: ArrowUpTrayIcon,       key: 'import' },
  { to: '/duplicates',  label: 'Duplicates',        Icon: DocumentDuplicateIcon, key: 'duplicates' },
  { to: '/events',      label: 'Events & Trips',    Icon: MapIcon,               key: 'events' },
  { to: '/analytics',   label: 'Analytics',         Icon: ChartBarIcon,          key: 'analytics' },
  { to: '/preferences', label: 'Preferences',       Icon: Cog6ToothIcon,         key: 'preferences' },
]

export default function Sidebar({ uncuratedCount = 0 }) {
  return (
    <aside className="hidden md:flex flex-col w-[220px] bg-immich-surface border-r border-immich-border h-screen fixed left-0 top-0">
      {/* Logo + Title */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-immich-border">
        <div className="w-8 h-8 rounded-full bg-immich-primary flex items-center justify-center flex-shrink-0">
          <span className="text-white text-sm font-bold">I</span>
        </div>
        <span className="text-immich-text font-semibold text-sm">Photo Curator</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 overflow-y-auto">
        {NAV_ITEMS.map(({ to, label, Icon, key }) => (
          <NavLink
            key={key}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 text-sm font-medium rounded-lg mx-2 mb-0.5 transition-colors ${
                isActive
                  ? 'bg-immich-primary/20 text-immich-primary'
                  : 'text-immich-muted hover:text-immich-text hover:bg-immich-border/40'
              }`
            }
          >
            <Icon className="w-5 h-5 flex-shrink-0" />
            <span className="flex-1">{label}</span>
            {key === 'curator' && uncuratedCount > 0 && (
              <span
                data-testid="curator-badge"
                className="bg-immich-primary text-white text-xs font-bold px-1.5 py-0.5 rounded-full min-w-[1.25rem] text-center"
              >
                {uncuratedCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
```

- [ ] **Step 4: Create `src/components/BottomTabBar.jsx`**

```jsx
import { NavLink } from 'react-router-dom'
import {
  PhotoIcon,
  ArrowUpTrayIcon,
  DocumentDuplicateIcon,
  MapIcon,
  ChartBarIcon,
  Cog6ToothIcon,
} from '@heroicons/react/24/outline'

const TABS = [
  { to: '/',            Icon: PhotoIcon,             label: 'Curator' },
  { to: '/import',      Icon: ArrowUpTrayIcon,       label: 'Import' },
  { to: '/duplicates',  Icon: DocumentDuplicateIcon, label: 'Dupes' },
  { to: '/events',      Icon: MapIcon,               label: 'Events' },
  { to: '/analytics',   Icon: ChartBarIcon,          label: 'Analytics' },
  { to: '/preferences', Icon: Cog6ToothIcon,         label: 'Settings' },
]

export default function BottomTabBar() {
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-immich-surface border-t border-immich-border flex z-10">
      {TABS.map(({ to, Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            `flex-1 flex flex-col items-center py-2 gap-0.5 text-xs transition-colors ${
              isActive ? 'text-immich-primary' : 'text-immich-muted'
            }`
          }
        >
          <Icon className="w-5 h-5" />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  )
}
```

- [ ] **Step 5: Create `src/components/Layout.jsx`**

```jsx
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import BottomTabBar from './BottomTabBar'

export default function Layout({ uncuratedCount = 0 }) {
  return (
    <div className="min-h-screen bg-immich-bg">
      <Sidebar uncuratedCount={uncuratedCount} />
      {/* Main content — offset for sidebar on desktop, padding-bottom for bottom tabs on mobile */}
      <main className="md:ml-[220px] pb-16 md:pb-0">
        <Outlet />
      </main>
      <BottomTabBar />
    </div>
  )
}
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
cd photo-curator/frontend && npm test
```
Expected: all Layout tests `PASS`.

- [ ] **Step 7: Commit**

```bash
git add photo-curator/frontend/src/components/ photo-curator/frontend/src/test/Layout.test.jsx
git commit -m "feat(curator-frontend): add Layout, Sidebar, and BottomTabBar with tests"
```

---

## Task 7: App entry point + routing

**Files:**
- Create: `photo-curator/frontend/src/main.jsx`
- Create: `photo-curator/frontend/src/App.jsx`

**Context:** `App` wraps everything in `BrowserRouter`. It uses `useAuth` to detect 401s (passed as `onError` to TanStack Query's `queryClient`). If `loginUrl` is set, renders `<Login>` instead of `<Layout>`.

- [ ] **Step 1: Create `src/main.jsx`**

```jsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 25_000,
      refetchInterval: 30_000,
      retry: 1,
    },
  },
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>
)
```

- [ ] **Step 2: Create `src/App.jsx`**

```jsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useAuth } from './hooks/useAuth'
import { AuthError } from './utils/api'
import Layout from './components/Layout'
import Login from './pages/Login'
import AlbumCurator from './pages/AlbumCurator'
import Import from './pages/Import'
import Duplicates from './pages/Duplicates'
import Events from './pages/Events'
import Analytics from './pages/Analytics'
import Preferences from './pages/Preferences'
import { useYearProgress } from './hooks/useYearProgress'

function AppInner() {
  const { loginUrl, onAuthError } = useAuth()
  const queryClient = useQueryClient()
  const currentYear = new Date().getFullYear()
  const { data: yearProgress } = useYearProgress(currentYear)

  // Wire auth error handler into react-query global
  useEffect(() => {
    const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
      if (event?.error instanceof AuthError) {
        onAuthError(event.error)
      }
    })
    return unsubscribe
  }, [queryClient, onAuthError])

  if (loginUrl !== null) {
    return <Login loginUrl={loginUrl} />
  }

  const uncuratedCount = yearProgress
    ? Object.values(yearProgress).filter((v) => !v).length
    : 0

  return (
    <Routes>
      <Route element={<Layout uncuratedCount={uncuratedCount} />}>
        <Route index element={<AlbumCurator onAuthError={onAuthError} />} />
        <Route path="import" element={<Import onAuthError={onAuthError} />} />
        <Route path="duplicates" element={<Duplicates onAuthError={onAuthError} />} />
        <Route path="events" element={<Events onAuthError={onAuthError} />} />
        <Route path="analytics" element={<Analytics onAuthError={onAuthError} />} />
        <Route path="preferences" element={<Preferences onAuthError={onAuthError} />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppInner />
    </BrowserRouter>
  )
}
```

- [ ] **Step 3: Create stub pages** (needed so the router compiles; real implementations come in later tasks)

Create each file with a minimal placeholder:

`src/pages/AlbumCurator.jsx`:
```jsx
export default function AlbumCurator() {
  return <div className="p-6 text-immich-text">AI Album Curator — coming soon</div>
}
```

`src/pages/Import.jsx`:
```jsx
export default function Import() {
  return <div className="p-6 text-immich-text">Import — coming soon</div>
}
```

`src/pages/Duplicates.jsx`:
```jsx
export default function Duplicates() {
  return <div className="p-6 text-immich-text">Duplicates — coming soon</div>
}
```

`src/pages/Events.jsx`:
```jsx
export default function Events() {
  return <div className="p-6 text-immich-text">Events & Trips — coming soon</div>
}
```

`src/pages/Analytics.jsx`:
```jsx
export default function Analytics() {
  return <div className="p-6 text-immich-text">Analytics — coming soon</div>
}
```

`src/pages/Preferences.jsx`:
```jsx
export default function Preferences() {
  return <div className="p-6 text-immich-text">Preferences — coming soon</div>
}
```

- [ ] **Step 4: Create `src/hooks/useYearProgress.js`**

```javascript
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'

// NOTE: TanStack Query v5 removed the `onError` option from useQuery.
// Auth errors (AuthError) from all queries are caught by the global
// query cache subscriber wired up in App.jsx — no per-query onError needed.
export function useYearProgress(year) {
  return useQuery({
    queryKey: ['yearProgress', year],
    queryFn: () => apiFetch(`/api/progress/year/${year}`),
  })
}
```

- [ ] **Step 5: Verify the app builds without errors**

```bash
cd photo-curator/frontend && npm run build 2>&1 | tail -10
```
Expected: build succeeds, `dist/` created.

- [ ] **Step 6: Commit**

```bash
git add photo-curator/frontend/src/
git commit -m "feat(curator-frontend): add App router, entry point, and stub pages"
```

---

## Task 8: YearTracker component + tests

**Files:**
- Create: `photo-curator/frontend/src/components/YearTracker.jsx`
- Create: `photo-curator/frontend/src/test/YearTracker.test.jsx`

- [ ] **Step 1: Write the failing tests**

Create `photo-curator/frontend/src/test/YearTracker.test.jsx`:
```jsx
import { render, screen, fireEvent } from '@testing-library/react'
import YearTracker from '../components/YearTracker'

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

describe('YearTracker', () => {
  it('renders 12 month pills', () => {
    const progress = Object.fromEntries(Array.from({length:12},(_,i)=>[i+1, false]))
    render(<YearTracker year={2024} progress={progress} currentMonth={3} onSelect={()=>{}} />)
    MONTHS.forEach(m => expect(screen.getByText(m)).toBeInTheDocument())
  })

  it('marks curated months as green', () => {
    const progress = { ...Object.fromEntries(Array.from({length:12},(_,i)=>[i+1,false])), 1: true, 3: true }
    render(<YearTracker year={2024} progress={progress} currentMonth={3} onSelect={()=>{}} />)
    // Curated pills have data-curated="true"
    const curated = screen.getAllByTestId('month-pill').filter(el => el.dataset.curated === 'true')
    expect(curated).toHaveLength(2)
  })

  it('calls onSelect with month number when a pill is clicked', () => {
    const onSelect = vi.fn()
    const progress = Object.fromEntries(Array.from({length:12},(_,i)=>[i+1, false]))
    render(<YearTracker year={2024} progress={progress} currentMonth={1} onSelect={onSelect} />)
    fireEvent.click(screen.getByText('Mar'))
    expect(onSelect).toHaveBeenCalledWith(3)
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd photo-curator/frontend && npm test -- --reporter=verbose 2>&1 | grep -E "PASS|FAIL|Error"
```

- [ ] **Step 3: Create `src/components/YearTracker.jsx`**

```jsx
const MONTH_LABELS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

export default function YearTracker({ year, progress = {}, currentMonth, onSelect }) {
  return (
    <div className="flex gap-1.5 flex-wrap">
      {MONTH_LABELS.map((label, idx) => {
        const month = idx + 1
        const curated = !!progress[month]
        const isCurrent = month === currentMonth
        return (
          <button
            key={month}
            data-testid="month-pill"
            data-curated={curated}
            onClick={() => onSelect(month)}
            className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ring-1 ${
              curated
                ? 'bg-green-900/40 text-green-400 ring-green-700'
                : 'bg-immich-surface text-immich-muted ring-immich-border'
            } ${isCurrent ? 'ring-2 ring-immich-primary' : ''} hover:opacity-80`}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd photo-curator/frontend && npm test
```
Expected: all tests `PASS`.

- [ ] **Step 5: Commit**

```bash
git add photo-curator/frontend/src/components/YearTracker.jsx photo-curator/frontend/src/test/YearTracker.test.jsx
git commit -m "feat(curator-frontend): add YearTracker component with tests"
```

---

## Task 9: AlbumCurator page — photo grid + curation flow + tests

**Files:**
- Create: `photo-curator/frontend/src/hooks/useCurator.js`
- Create: `photo-curator/frontend/src/components/PhotoGrid.jsx`
- Create: `photo-curator/frontend/src/components/CurationFooter.jsx`
- Modify: `photo-curator/frontend/src/pages/AlbumCurator.jsx`
- Create: `photo-curator/frontend/src/test/AlbumCurator.test.jsx`

**Context:** The flow is:
1. Load raw photos immediately from `/api/photos/{year}/{month}/raw`
2. Queue background analysis via `POST /api/analyze/{year}/{month}`
3. Poll `/api/photos/{year}/{month}` for scores (indicates analysis progress)
4. Show progress bar while analysis runs
5. When all photos scored (or user explicitly triggers), enable **AI Curate** button
6. Clicking AI Curate calls `GET /api/curation/{year}/{month}` to get AI suggestions → apply selections
7. User toggles individual photos on/off freely
8. Save Album calls `POST /api/curation/{year}/{month}/complete`

- [ ] **Step 1: Write the failing tests**

Create `photo-curator/frontend/src/test/AlbumCurator.test.jsx`:
```jsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import AlbumCurator from '../pages/AlbumCurator'
import * as api from '../utils/api'

function wrap(ui) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        {ui}
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('AlbumCurator', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('shows photo thumbnails after load', async () => {
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url.includes('/raw')) return Promise.resolve({ photos: [
        { asset_id: 'a1', thumbnail_url: '/api/thumbnail/a1', width: 100, height: 100, taken_at: null }
      ], total: 1 })
      if (url.includes('/api/analyze')) return Promise.resolve({})
      return Promise.resolve({ photos: [], total: 0 })
    })
    wrap(<AlbumCurator onAuthError={() => {}} />)
    await waitFor(() => expect(screen.getByTestId('photo-a1')).toBeInTheDocument())
  })

  it('shows month/year switcher', async () => {
    vi.spyOn(api, 'apiFetch').mockResolvedValue({ photos: [], total: 0 })
    wrap(<AlbumCurator onAuthError={() => {}} />)
    // Month label visible (any month/year format)
    await waitFor(() => expect(screen.getByTestId('month-label')).toBeInTheDocument())
  })

  it('curation footer appears after AI Curate clicked', async () => {
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url.includes('/raw')) return Promise.resolve({ photos: [
        { asset_id: 'a1', thumbnail_url: '/api/thumbnail/a1', width: 100, height: 100, taken_at: null },
        { asset_id: 'a2', thumbnail_url: '/api/thumbnail/a2', width: 100, height: 100, taken_at: null },
      ], total: 2 })
      if (url.includes('/curation/') && !url.includes('complete')) return Promise.resolve({
        suggested_asset_ids: ['a1'],
        session_id: 's1',
      })
      return Promise.resolve({})
    })
    wrap(<AlbumCurator onAuthError={() => {}} />)
    await waitFor(() => screen.getByTestId('photo-a1'))
    fireEvent.click(screen.getByText('AI Curate'))
    await waitFor(() => expect(screen.getByTestId('curation-footer')).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd photo-curator/frontend && npm test -- AlbumCurator 2>&1 | tail -15
```

- [ ] **Step 3: Create `src/hooks/useCurator.js`**

```javascript
import { useState, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'

export function useCurator(year, month, { onAuthError } = {}) {
  const queryClient = useQueryClient()

  // NOTE: TanStack Query v5 removed onError from useQuery.
  // Auth errors from all queries are caught by the global cache subscriber in App.jsx.

  // Step 1: raw photos — load immediately
  const rawQuery = useQuery({
    queryKey: ['rawPhotos', year, month],
    queryFn: () => apiFetch(`/api/photos/${year}/${month}/raw`),
  })

  // Step 2: trigger background analysis once raw photos are loaded
  const analyzeMutation = useMutation({
    mutationFn: () => apiFetch(`/api/analyze/${year}/${month}`, { method: 'POST' }),
  })

  useEffect(() => {
    if (rawQuery.data && rawQuery.data.total > 0 && !analyzeMutation.isSuccess && !analyzeMutation.isPending) {
      analyzeMutation.mutate()
    }
  }, [rawQuery.data])

  // Step 3: poll scored photos to track analysis progress
  const scoredQuery = useQuery({
    queryKey: ['scoredPhotos', year, month],
    queryFn: () => apiFetch(`/api/photos/${year}/${month}`),
    refetchInterval: 5_000,
  })

  const rawTotal = rawQuery.data?.total ?? 0
  const scoredTotal = scoredQuery.data?.photos?.length ?? 0
  const analysisComplete = rawTotal > 0 && scoredTotal >= rawTotal

  // Curation state
  const [selected, setSelected] = useState(new Set())
  const [curated, setCurated] = useState(false)

  const [recommendedCount, setRecommendedCount] = useState(null)

  const curateMutation = useMutation({
    mutationFn: () => apiFetch(`/api/curation/${year}/${month}`),
    onSuccess: (data) => {
      const suggested = data.suggested_asset_ids ?? []
      setSelected(new Set(suggested))
      setRecommendedCount(suggested.length)
      setCurated(true)
    },
    onError: onAuthError,
  })

  const togglePhoto = useCallback((assetId) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(assetId)) next.delete(assetId)
      else next.add(assetId)
      return next
    })
  }, [])

  const saveAlbumMutation = useMutation({
    mutationFn: () => apiFetch(`/api/curation/${year}/${month}/complete`, {
      method: 'POST',
      body: JSON.stringify({ selected_asset_ids: [...selected] }),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['yearProgress'] })
      setCurated(false)
      setSelected(new Set())
    },
    onError: onAuthError,
  })

  const resetCuration = useCallback(() => {
    setSelected(new Set())
    setCurated(false)
  }, [])

  return {
    photos: rawQuery.data?.photos ?? [],
    isLoading: rawQuery.isPending,
    rawTotal,
    scoredTotal,
    analysisComplete,
    selected,
    curated,
    togglePhoto,
    aiCurate: curateMutation.mutate,
    isCurating: curateMutation.isPending,
    saveAlbum: saveAlbumMutation.mutate,
    isSaving: saveAlbumMutation.isPending,
    resetCuration,
    recommendedCount,
  }
}
```

- [ ] **Step 4: Create `src/components/PhotoGrid.jsx`**

```jsx
export default function PhotoGrid({ photos, selected, onToggle }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2 p-4">
      {photos.map(photo => {
        const isSelected = selected.has(photo.asset_id)
        return (
          <button
            key={photo.asset_id}
            data-testid={`photo-${photo.asset_id}`}
            onClick={() => onToggle(photo.asset_id)}
            className={`relative aspect-square rounded-lg overflow-hidden ring-2 transition-all ${
              isSelected ? 'ring-immich-primary' : 'ring-transparent opacity-70 hover:opacity-100'
            }`}
          >
            <img
              src={photo.thumbnail_url}
              alt=""
              className="w-full h-full object-cover"
              loading="lazy"
            />
            {isSelected && (
              <div className="absolute inset-0 bg-immich-primary/20 flex items-end justify-end p-1">
                <div className="w-5 h-5 rounded-full bg-immich-primary flex items-center justify-center">
                  <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                </div>
              </div>
            )}
          </button>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 5: Create `src/components/CurationFooter.jsx`**

```jsx
export default function CurationFooter({ selectedCount, recommendedCount, onSave, onReset, isSaving }) {
  return (
    <div
      data-testid="curation-footer"
      className="fixed bottom-16 md:bottom-0 left-0 md:left-[220px] right-0 bg-immich-surface border-t border-immich-border px-4 py-3 flex items-center justify-between z-20"
    >
      <span className="text-immich-text text-sm">
        <span className="font-semibold">{selectedCount} selected</span>
        {recommendedCount !== null && (
          <span className="text-immich-muted ml-2">· Recommended: {recommendedCount}</span>
        )}
      </span>
      <div className="flex gap-2">
        <button
          onClick={onReset}
          className="px-4 py-2 bg-immich-surface text-immich-text font-medium rounded-lg border border-immich-border hover:bg-immich-border transition-colors text-sm"
        >
          Reset
        </button>
        <button
          onClick={onSave}
          disabled={isSaving || selectedCount === 0}
          className="px-4 py-2 bg-immich-primary text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 text-sm"
        >
          {isSaving ? 'Saving…' : 'Save Album'}
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Implement `src/pages/AlbumCurator.jsx`**

```jsx
import { useState } from 'react'
import { ChevronLeftIcon, ChevronRightIcon, SparklesIcon } from '@heroicons/react/24/outline'
import { useCurator } from '../hooks/useCurator'
import { useYearProgress } from '../hooks/useYearProgress'
import YearTracker from '../components/YearTracker'
import PhotoGrid from '../components/PhotoGrid'
import CurationFooter from '../components/CurationFooter'

const MONTH_NAMES = ['January','February','March','April','May','June',
                     'July','August','September','October','November','December']

export default function AlbumCurator({ onAuthError }) {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)

  const {
    photos, isLoading, rawTotal, scoredTotal, analysisComplete,
    selected, curated, togglePhoto, aiCurate, isCurating, saveAlbum, isSaving, resetCuration,
    recommendedCount,
  } = useCurator(year, month, { onAuthError })

  const { data: yearProgress } = useYearProgress(year)

  const prevMonth = () => {
    if (month === 1) { setMonth(12); setYear(y => y - 1) }
    else setMonth(m => m - 1)
  }
  const nextMonth = () => {
    if (month === 12) { setMonth(1); setYear(y => y + 1) }
    else setMonth(m => m + 1)
  }

  const analysisProgress = rawTotal > 0 ? Math.round((scoredTotal / rawTotal) * 100) : 0

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="sticky top-0 bg-immich-bg/95 backdrop-blur border-b border-immich-border px-4 py-3 z-10">
        {/* Month switcher */}
        <div className="flex items-center gap-3 mb-3">
          <button onClick={prevMonth} className="p-1.5 rounded-lg hover:bg-immich-surface transition-colors">
            <ChevronLeftIcon className="w-5 h-5 text-immich-muted" />
          </button>
          <span data-testid="month-label" className="text-immich-text font-semibold text-lg min-w-[160px] text-center">
            {MONTH_NAMES[month - 1]} {year}
          </span>
          <button onClick={nextMonth} className="p-1.5 rounded-lg hover:bg-immich-surface transition-colors">
            <ChevronRightIcon className="w-5 h-5 text-immich-muted" />
          </button>
          <div className="ml-auto">
            <button
              onClick={() => aiCurate()}
              disabled={!analysisComplete || isCurating}
              className="flex items-center gap-2 px-4 py-2 bg-immich-primary text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-40 text-sm"
            >
              <SparklesIcon className="w-4 h-4" />
              {isCurating ? 'Curating…' : 'AI Curate'}
            </button>
          </div>
        </div>

        {/* Year tracker */}
        {yearProgress && (
          <YearTracker
            year={year}
            progress={yearProgress}
            currentMonth={month}
            onSelect={(m) => setMonth(m)}
          />
        )}

        {/* Analysis progress bar */}
        {!analysisComplete && rawTotal > 0 && (
          <div className="mt-2">
            <div className="flex justify-between text-xs text-immich-muted mb-1">
              <span>Analyzing photos…</span>
              <span>{scoredTotal} / {rawTotal}</span>
            </div>
            <div className="h-1 bg-immich-border rounded-full overflow-hidden">
              <div
                className="h-full bg-immich-primary transition-all"
                style={{ width: `${analysisProgress}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Photo grid */}
      {isLoading ? (
        <div className="flex items-center justify-center h-64 text-immich-muted">Loading photos…</div>
      ) : photos.length === 0 ? (
        <div className="flex items-center justify-center h-64 text-immich-muted">No photos found for this month.</div>
      ) : (
        <PhotoGrid photos={photos} selected={selected} onToggle={togglePhoto} />
      )}

      {/* Curation footer */}
      {curated && (
        <CurationFooter
          selectedCount={selected.size}
          recommendedCount={recommendedCount}
          onSave={saveAlbum}
          onReset={resetCuration}
          isSaving={isSaving}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 7: Run tests**

```bash
cd photo-curator/frontend && npm test
```
Expected: all tests `PASS` (may need minor adjustments to match actual component behavior).

- [ ] **Step 8: Commit**

```bash
git add photo-curator/frontend/src/
git commit -m "feat(curator-frontend): implement AlbumCurator page with photo grid and curation flow"
```

---

## Task 10: Import page

**Files:**
- Modify: `photo-curator/frontend/src/pages/Import.jsx`

**Context:** Step-by-step wizard. The existing backend has `/api/import/jobs` endpoints. For now, implement the UI shell through step 3 (source, configure, preview) since backend import jobs vary by source. Connect to the existing `POST /api/import/start` if it exists.

- [ ] **Step 1: Implement `src/pages/Import.jsx`**

```jsx
import { useState } from 'react'
import { CheckIcon } from '@heroicons/react/24/solid'

const SOURCES = [
  { id: 'google', label: 'Google Photos', desc: 'Import from a Google Takeout export' },
  { id: 'apple', label: 'Apple Photos', desc: 'Import from an Apple Photos export' },
  { id: 'icloud', label: 'iCloud', desc: 'Import from iCloud Drive' },
]

const STEPS = ['Choose source', 'Configure', 'Preview', 'Import']

export default function Import({ onAuthError }) {
  const [step, setStep] = useState(0)
  const [source, setSource] = useState(null)
  const [path, setPath] = useState('')

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-immich-text text-2xl font-semibold mb-6">Import Photos</h1>

      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-8">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2 flex-1">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
              i < step ? 'bg-green-600 text-white' :
              i === step ? 'bg-immich-primary text-white' :
              'bg-immich-surface text-immich-muted border border-immich-border'
            }`}>
              {i < step ? <CheckIcon className="w-4 h-4" /> : i + 1}
            </div>
            <span className={`text-xs ${i === step ? 'text-immich-text' : 'text-immich-muted'} hidden sm:block`}>{label}</span>
            {i < STEPS.length - 1 && <div className="flex-1 h-px bg-immich-border" />}
          </div>
        ))}
      </div>

      {/* Step 0: Choose source */}
      {step === 0 && (
        <div className="space-y-3">
          {SOURCES.map(s => (
            <button
              key={s.id}
              onClick={() => setSource(s.id)}
              className={`w-full text-left p-4 rounded-xl border transition-colors ${
                source === s.id
                  ? 'border-immich-primary bg-immich-primary/10'
                  : 'border-immich-border bg-immich-surface hover:border-immich-muted'
              }`}
            >
              <p className="text-immich-text font-medium">{s.label}</p>
              <p className="text-immich-muted text-sm mt-0.5">{s.desc}</p>
            </button>
          ))}
          <button
            disabled={!source}
            onClick={() => setStep(1)}
            className="mt-4 px-4 py-2 bg-immich-primary text-white font-medium rounded-lg disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}

      {/* Step 1: Configure */}
      {step === 1 && (
        <div className="space-y-4">
          <label className="block">
            <span className="text-immich-text text-sm font-medium">Export path or file</span>
            <input
              type="text"
              value={path}
              onChange={e => setPath(e.target.value)}
              placeholder="/path/to/export"
              className="mt-1 w-full px-3 py-2 bg-immich-surface border border-immich-border rounded-lg text-immich-text placeholder-immich-muted text-sm focus:outline-none focus:border-immich-primary"
            />
          </label>
          <div className="flex gap-2">
            <button onClick={() => setStep(0)} className="px-4 py-2 bg-immich-surface text-immich-text border border-immich-border rounded-lg text-sm">Back</button>
            <button disabled={!path} onClick={() => setStep(2)} className="px-4 py-2 bg-immich-primary text-white font-medium rounded-lg disabled:opacity-40 text-sm">Preview</button>
          </div>
        </div>
      )}

      {/* Step 2: Preview placeholder */}
      {step === 2 && (
        <div className="space-y-4">
          <div className="p-4 bg-immich-surface rounded-xl border border-immich-border">
            <p className="text-immich-muted text-sm">Preview scan would appear here.</p>
            <p className="text-immich-text text-sm mt-1">Source: <strong>{source}</strong> — Path: <strong>{path}</strong></p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setStep(1)} className="px-4 py-2 bg-immich-surface text-immich-text border border-immich-border rounded-lg text-sm">Back</button>
            <button onClick={() => setStep(3)} className="px-4 py-2 bg-immich-primary text-white font-medium rounded-lg text-sm">Start Import</button>
          </div>
        </div>
      )}

      {/* Step 3: Import progress placeholder */}
      {step === 3 && (
        <div className="p-4 bg-immich-surface rounded-xl border border-immich-border">
          <p className="text-immich-text font-medium">Import in progress…</p>
          <div className="h-2 bg-immich-border rounded-full mt-3 overflow-hidden">
            <div className="h-full bg-immich-primary w-1/3 animate-pulse" />
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

```bash
cd photo-curator/frontend && npm run build 2>&1 | tail -5
```

- [ ] **Step 3: Commit**

```bash
git add photo-curator/frontend/src/pages/Import.jsx
git commit -m "feat(curator-frontend): implement Import wizard page"
```

---

## Task 11: Duplicates page

**Files:**
- Modify: `photo-curator/frontend/src/pages/Duplicates.jsx`

**Context:** Backend has `GET /api/duplicates` returning groups of duplicate photos. Each group has `assets` (list) — show side-by-side and let user pick which to keep.

- [ ] **Step 1: Implement `src/pages/Duplicates.jsx`**

```jsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'
import { TrashIcon } from '@heroicons/react/24/outline'

function DuplicateCard({ group, onDelete }) {
  const [keepId, setKeepId] = useState(group.assets[0]?.id)

  return (
    <div className="bg-immich-surface border border-immich-border rounded-xl p-4">
      <div className="flex gap-3 mb-3">
        {group.assets.map(asset => (
          <button
            key={asset.id}
            onClick={() => setKeepId(asset.id)}
            className={`flex-1 rounded-lg overflow-hidden ring-2 transition-all ${
              keepId === asset.id ? 'ring-immich-primary' : 'ring-transparent opacity-60 hover:opacity-90'
            }`}
          >
            <img src={`/api/thumbnail/${asset.id}`} alt="" className="w-full aspect-square object-cover" />
          </button>
        ))}
      </div>
      <div className="flex items-center justify-between">
        <p className="text-immich-muted text-xs">{group.assets.length} duplicates · click to select keep</p>
        <button
          onClick={() => onDelete(group.id, keepId)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-red-700 text-white text-xs font-medium rounded-lg hover:bg-red-600"
        >
          <TrashIcon className="w-3.5 h-3.5" />
          Delete others
        </button>
      </div>
    </div>
  )
}

export default function Duplicates({ onAuthError }) {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['duplicates'],
    queryFn: () => apiFetch('/api/duplicates'),
  })

  const deleteMutation = useMutation({
    mutationFn: ({ groupId, keepId }) =>
      apiFetch(`/api/duplicates/${groupId}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ keep_asset_id: keepId }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['duplicates'] }),
    onError: onAuthError,
  })

  const groups = data?.groups ?? []

  return (
    <div className="p-6">
      <h1 className="text-immich-text text-2xl font-semibold mb-6">Duplicates</h1>
      {isLoading ? (
        <p className="text-immich-muted">Loading…</p>
      ) : groups.length === 0 ? (
        <div className="text-center py-16 text-immich-muted">No duplicates found.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {groups.map(group => (
            <DuplicateCard
              key={group.id}
              group={group}
              onDelete={(groupId, keepId) => deleteMutation.mutate({ groupId, keepId })}
            />
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add photo-curator/frontend/src/pages/Duplicates.jsx
git commit -m "feat(curator-frontend): implement Duplicates page"
```

---

## Task 12: Events, Analytics, and Preferences pages

**Files:**
- Modify: `photo-curator/frontend/src/pages/Events.jsx`
- Modify: `photo-curator/frontend/src/pages/Analytics.jsx`
- Modify: `photo-curator/frontend/src/pages/Preferences.jsx`

- [ ] **Step 1: Implement `src/pages/Events.jsx`**

```jsx
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'
import { PlusIcon } from '@heroicons/react/24/outline'

export default function Events({ onAuthError }) {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['events'],
    queryFn: () => apiFetch('/api/events'),
  })

  const createMutation = useMutation({
    mutationFn: ({ eventId, albumName }) =>
      apiFetch(`/api/events/${eventId}/album`, {
        method: 'POST',
        body: JSON.stringify({ album_name: albumName }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['events'] }),
    onError: onAuthError,
  })

  const events = data?.events ?? []

  return (
    <div className="p-6">
      <h1 className="text-immich-text text-2xl font-semibold mb-6">Events & Trips</h1>
      {isLoading ? (
        <p className="text-immich-muted">Detecting events…</p>
      ) : events.length === 0 ? (
        <div className="text-center py-16 text-immich-muted">No events detected yet.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {events.map(event => (
            <div key={event.id} className="bg-immich-surface border border-immich-border rounded-xl overflow-hidden">
              {/* Thumbnail strip */}
              <div className="flex h-24 gap-0.5">
                {(event.thumbnails ?? []).slice(0, 3).map((url, i) => (
                  <img key={i} src={url} alt="" className="flex-1 object-cover" />
                ))}
              </div>
              <div className="p-3">
                <p className="text-immich-text font-medium text-sm">{event.title ?? 'Untitled event'}</p>
                <p className="text-immich-muted text-xs mt-0.5">{event.date_range} · {event.photo_count} photos</p>
                <button
                  onClick={() => createMutation.mutate({ eventId: event.id, albumName: event.title })}
                  className="mt-3 flex items-center gap-1.5 px-3 py-1.5 bg-immich-primary text-white text-xs font-medium rounded-lg hover:opacity-90"
                >
                  <PlusIcon className="w-3.5 h-3.5" />
                  Create Album
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Implement `src/pages/Analytics.jsx`**

```jsx
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'

function StatCard({ label, value }) {
  return (
    <div className="bg-immich-surface border border-immich-border rounded-xl p-5">
      <p className="text-immich-muted text-sm">{label}</p>
      <p className="text-immich-text text-3xl font-semibold mt-1">{value ?? '—'}</p>
    </div>
  )
}

export default function Analytics({ onAuthError }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analytics'],
    queryFn: () => apiFetch('/api/analytics'),
  })

  return (
    <div className="p-6">
      <h1 className="text-immich-text text-2xl font-semibold mb-6">Analytics</h1>
      {isLoading ? (
        <p className="text-immich-muted">Loading…</p>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <StatCard label="Total photos" value={data?.total_photos?.toLocaleString()} />
            <StatCard label="Months curated" value={data?.months_curated} />
            <StatCard label="Duplicates found" value={data?.duplicates_found} />
            <StatCard label="Faces identified" value={data?.faces_identified} />
          </div>
          <p className="text-immich-muted text-sm">Charts coming in a future release.</p>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Implement `src/pages/Preferences.jsx`**

```jsx
import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'

export default function Preferences({ onAuthError }) {
  const { data } = useQuery({
    queryKey: ['preferences'],
    queryFn: () => apiFetch('/api/preferences'),
  })

  const [monthlyTarget, setMonthlyTarget] = useState(20)

  useEffect(() => {
    if (data?.monthly_target) setMonthlyTarget(data.monthly_target)
  }, [data])

  const saveMutation = useMutation({
    mutationFn: (prefs) =>
      apiFetch('/api/preferences', { method: 'POST', body: JSON.stringify(prefs) }),
    onError: onAuthError,
  })

  return (
    <div className="p-6 max-w-lg">
      <h1 className="text-immich-text text-2xl font-semibold mb-6">Preferences</h1>

      {/* Album Settings */}
      <section className="bg-immich-surface border border-immich-border rounded-xl p-5 mb-4">
        <h2 className="text-immich-text font-medium mb-4">Album Settings</h2>
        <label className="block">
          <span className="text-immich-muted text-sm">Photos per album (default)</span>
          <input
            type="number"
            min={1}
            max={200}
            value={monthlyTarget}
            onChange={e => setMonthlyTarget(Number(e.target.value))}
            className="mt-1 w-full px-3 py-2 bg-immich-bg border border-immich-border rounded-lg text-immich-text text-sm focus:outline-none focus:border-immich-primary"
          />
        </label>
        <button
          onClick={() => saveMutation.mutate({ monthly_target: monthlyTarget })}
          disabled={saveMutation.isPending}
          className="mt-4 px-4 py-2 bg-immich-primary text-white font-medium rounded-lg disabled:opacity-50 text-sm"
        >
          {saveMutation.isPending ? 'Saving…' : 'Save'}
        </button>
      </section>

      {/* AI Settings placeholder */}
      <section className="bg-immich-surface border border-immich-border rounded-xl p-5 mb-4">
        <h2 className="text-immich-text font-medium mb-2">AI Settings</h2>
        <p className="text-immich-muted text-sm">Advanced AI configuration coming soon.</p>
      </section>
    </div>
  )
}
```

- [ ] **Step 4: Build to confirm no errors**

```bash
cd photo-curator/frontend && npm run build 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
git add photo-curator/frontend/src/pages/
git commit -m "feat(curator-frontend): implement Events, Analytics, and Preferences pages"
```

---

## Task 13: Final build + wire into FastAPI

**Files:**
- Modify: `photo-curator/frontend/vite.config.js` (confirm base path)
- Run build, commit dist

**Context:** Server-manager commits `dist/` to git for simple deployment. We follow the same pattern.

- [ ] **Step 1: Run full test suite**

```bash
cd photo-curator/frontend && npm test
```
Expected: all tests `PASS`.

- [ ] **Step 2: Run backend tests**

```bash
cd photo-curator && python -m pytest tests/ -v
```
Expected: all tests `PASS`.

- [ ] **Step 3: Build frontend**

```bash
cd photo-curator/frontend && npm run build
```
Expected: `dist/` populated with `index.html` + `assets/`.

- [ ] **Step 4: Verify FastAPI serves the SPA**

```bash
cd photo-curator && python -m uvicorn src.main:app --port 8081 &
sleep 2
curl -s http://localhost:8081/ | head -5
kill %1
```
Expected: returns the React `index.html` (starts with `<!DOCTYPE html>`).

- [ ] **Step 5: Check `.gitignore`**

```bash
grep -n "dist" photo-curator/.gitignore 2>/dev/null || echo "no gitignore entry"
```
If `dist` is in `.gitignore`, remove that line (same as server-manager pattern — dist is committed for deployment).

- [ ] **Step 6: Commit dist**

```bash
git add photo-curator/frontend/dist/
git commit -m "chore(curator-frontend): commit built dist for deployment"
```

- [ ] **Step 7: Full commit of any remaining tracked changes**

```bash
git status
# Stage any remaining modified tracked files explicitly, e.g.:
# git add photo-curator/src/main.py photo-curator/src/database.py
git commit -m "feat(curator): complete React SPA redesign"
```

---

## Verification Checklist

After all tasks are complete, verify:

- [ ] `GET /api/photos/2024/3/raw` returns `{ photos: [...], total: N }` with 401 when unauthenticated
- [ ] `GET /api/progress/year/2024` returns 12 boolean values
- [ ] `GET /` returns React `index.html`
- [ ] Frontend loads in browser at `http://localhost:8081`
- [ ] Sidebar visible on desktop (≥768px), bottom tab bar on mobile
- [ ] Navigating between pages works
- [ ] 401 from any API call shows Login page with "Sign in via Immich" button
- [ ] AI Album Curator loads photos without requiring prior analysis
- [ ] Year tracker pills reflect actual curation status
- [ ] All tests pass: `npm test` and `pytest tests/`
