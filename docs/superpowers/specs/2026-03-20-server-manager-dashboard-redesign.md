# Server Manager Dashboard Redesign

**Date:** 2026-03-20
**Scope:** `server-manager/` dashboard only (Photo Curator is a separate effort)
**Status:** Approved for implementation

---

## Problem

The current `dashboard.html` is a single HTML file with a full `innerHTML` re-render every 30 seconds. This causes:

1. All user selections (log service, live toggle) reset on every poll cycle
2. The log viewer loses scroll position and state on refresh
3. Switching between log services requires opening a dropdown and re-selecting
4. The UI uses emoji icons and plain colored text instead of proper visual indicators
5. Pure black background (`#000000`) is visually harsh

---

## Goals

- Eliminate full-page re-renders during data polling
- Log viewer state (selected service, live toggle, scroll position) persists indefinitely
- Fast log service switching via tab bar (one click, no dropdown)
- Immich-style visual design with Heroicons, progress bars, and status badges
- Single-page layout (no navigation/sidebar)

---

## Architecture

### Stack

- **Framework:** React 18 + Vite
- **Styling:** Tailwind CSS v3 (config file, not CDN)
- **Icons:** `@heroicons/react`
- **Data fetching:** TanStack React Query v5
- **Build output:** `server-manager/frontend/dist/` — served as static files by existing FastAPI

### Serving

FastAPI serves the React app on the existing port 8080. No new server processes or ports. All existing API endpoints are unchanged.

**FastAPI changes required (`server-manager/src/main.py`):**

1. The existing `@app.get("/")` route (which has `require_admin` auth dependency) is updated to read and return `frontend/dist/index.html` as an `HTMLResponse`. The new path expression: `Path(__file__).parent.parent / "frontend" / "dist" / "index.html"`. Auth is fully preserved.

2. A new `StaticFiles` mount is added **after** all `@app.get(...)` routes to avoid shadowing them:
   ```python
   app.mount("/assets", StaticFiles(directory=Path(__file__).parent.parent / "frontend" / "dist" / "assets"), name="assets")
   ```
   This serves the Vite-built JS/CSS bundles under `/assets/...`, matching the paths Vite emits in `index.html` when `base: "/"` is set.

### File Structure

```
server-manager/
  frontend/
    src/
      App.jsx
      main.jsx
      index.css
      components/
        Header.jsx
        SystemStatusCard.jsx
        ImmichStatusCard.jsx
        DiskHealthCard.jsx
        BackupsCard.jsx
        AlertsPanel.jsx
        LogViewer.jsx
        ServiceControls.jsx
        UpdateManagement.jsx
      hooks/
        useDashboard.js
    index.html
    vite.config.js
    tailwind.config.js
    package.json
```

### Data Flow

- React Query polls `/api/status`, `/api/disks`, `/api/backups`, `/api/alerts` independently every 30 seconds via `useQuery` with `staleTime: 25_000`
- Each card component subscribes only to its relevant query — a status refresh never re-renders `LogViewer` or `ServiceControls`
- `LogViewer` manages its own local state with `useState`/`useRef` — completely isolated from the polling cycle
- Update progress uses `EventSource` (SSE) scoped inside `UpdateManagement` component, same as current implementation

### API Endpoints

All existing endpoints are unchanged. Full inventory:

| Endpoint | Method | Used by |
|---|---|---|
| `/api/status` | GET | `SystemStatusCard`, `ImmichStatusCard` |
| `/api/disks` | GET | `DiskHealthCard` |
| `/api/backups` | GET | `BackupsCard` |
| `/api/alerts` | GET | `AlertsPanel` |
| `/api/backup/now` | POST | `BackupsCard` |
| `/api/logs/{service}` | GET | `LogViewer` (snapshot) |
| `/api/logs/{service}/stream` | GET (SSE) | `LogViewer` (live) |
| `/api/services/{service}/restart` | POST | `ServiceControls` |
| `/api/services/restart-all` | POST | `ServiceControls` |
| `/api/updates/status` | GET | `UpdateManagement` (includes `history` array in response) |
| `/api/updates/apply` | POST | `UpdateManagement` |
| `/api/updates/apply/stream` | GET (SSE) | `UpdateManagement` |

Note: `/api/updates/history` exists as a standalone endpoint but is not used by `UpdateManagement` — the `history` array is already embedded in the `/api/updates/status` response. The SSE endpoints (`/api/logs/{service}/stream`, `/api/updates/apply/stream`) are same-origin in production, so `connect-src 'self'` in the existing CSP header covers them with no changes needed.

---

## Components

### `Header`
- Immich logo SVG + "Server Manager" wordmark
- "Last refreshed" relative timestamp — displays the **most recent** `dataUpdatedAt` across all four polling queries (`status`, `disks`, `backups`, `alerts`), updated every second via `useEffect`. Formatted as "X seconds ago".
- No navigation links (single page)

### `SystemStatusCard`
- CPU, memory, disk usage as labeled progress bars
- Color thresholds: green (< 70%), yellow (70–85%), red (> 85%)
- **CPU:** shown as `XX.X%` (no GB value — CPU has no meaningful byte representation)
- **Memory and disk:** shown as `XX.X% (X.X GB)` inline with bar
- Data source: `system` field from `/api/status` response (`cpu_percent`, `memory_percent`, `memory_used_gb`, `disk_usage_percent`, `disk_used_gb`)

### `ImmichStatusCard`
- Service health as a pill badge: green "Healthy" or red "Issues Detected" — sourced from `immich_healthy` boolean in `/api/status`
- Container count sourced from `len(containers)` (derived, no dedicated count field) — displayed as plain text, e.g. "4 running"

### `DiskHealthCard`
- One row per disk: device name + temperature + SMART status badge
- SMART pass = green badge, fail = red badge
- Data source: `disks` array from `/api/disks` response

### `BackupsCard`
- Reads from `/api/backups` response field `history` (array of `{ timestamp, status }` objects). The `available` field (list of backup files) is **intentionally ignored in v1**.
- Displays up to 3 entries: formatted date from `timestamp` + status badge (green "success", red otherwise)
- "Backup Now" button triggers `POST /api/backup/now` with a confirmation dialog

### `AlertsPanel`
- Only renders if `alerts` array from `/api/alerts` is non-empty
- Severity-colored rows: critical (red), warning (amber), info (blue)
- Up to 5 most recent alerts shown
- Alert acknowledgement (`POST /api/alerts/{alert_id}/acknowledge`) is **out of scope for v1** — no acknowledge button rendered

### `LogViewer`
- **Tab bar** replacing dropdown: one tab per service (`immich_server`, `immich_machine_learning`, `immich_postgres`, `immich_redis`, `server_manager`, `photo_curator`, `system`)
  - `system` = host journalctl — valid as a log source but not restartable (excluded from `ServiceControls`)
- Active tab has primary-color bottom border indicator
- State preserved: selected tab, live toggle, scroll position all survive parent re-renders
- Live mode shows pulsing green dot next to "Live" label
- Log output: `h-96`, monospace, dark terminal background, auto-scroll when live
- Switching tabs: immediately fetches snapshot for new service; if live mode is on, switches the SSE stream to the new service

### `ServiceControls`
- Services rendered: `immich_server`, `immich_machine_learning`, `immich_postgres`, `immich_redis`, `server_manager`, `photo_curator` — **`system` is excluded** (backend rejects restart requests for it with 422)
- One row per service with service name + restart button
- Restart button shows loading spinner during request, then ✓/✗ for 3s, then resets
- "Restart All Immich Services" button styled as amber warning action, positioned below the list

### `UpdateManagement`
- Calls `GET /api/updates/status` which returns `{ current_version, latest_version, update_available, changelog_url, history: [...] }`
- Version display: `Current: vX.X.X` / `Latest: vX.X.X` + changelog link rendered only when `changelog_url` is non-null and starts with `https://github.com/` (backend only sets this when an update is available)
- Status: green "Up to date" badge or blue "Update Available" badge + "Apply Update" button
- Update progress streams into an inline terminal panel (SSE from `/api/updates/apply/stream`)
- Update history table rendered from the `history` array in the `/api/updates/status` response: date, `vX → vY` version transition, status

---

## Visual Design

### Color Tokens (Tailwind config extension)

```js
colors: {
  'immich-primary': '#4250af',
  'immich-bg': '#0f0f11',       // replaces pure black
  'immich-surface': '#1a1a27',  // card background
  'immich-border': '#2a2a3d',   // card borders
  'immich-text': '#f1f0ff',     // primary text
  'immich-muted': '#7c7c9a',    // secondary text
}
```

### Typography
- Font: system UI stack (same as Immich web app)
- Headings: `text-sm font-semibold uppercase tracking-wider text-immich-muted` (section labels)
- Values: `text-2xl font-bold text-immich-text` for key metrics
- Mono: log output, version strings, service names

### Cards
- `bg-immich-surface border border-immich-border rounded-2xl p-5`
- No box shadow (border is sufficient on dark background)

### Buttons
- Primary: `bg-immich-primary hover:bg-blue-600 text-white rounded-lg px-4 py-2 text-sm font-medium`
- Danger/warning: `bg-amber-500 hover:bg-amber-600 text-white`
- All buttons include `transition-colors duration-150`

---

## Build & Integration

1. `package.json` with `vite`, `react`, `react-dom`, `@tanstack/react-query`, `@heroicons/react`, `tailwindcss`, `autoprefixer`, `postcss`

2. `vite.config.js`:
   - `base: "/"` — ensures built asset paths are `/assets/...` (matching the FastAPI `StaticFiles` mount)
   - `build.outDir: "dist"` (Vite default; relative to `vite.config.js` location at `server-manager/frontend/`) — outputs to `server-manager/frontend/dist/`
   - Dev server proxy: `/api/*` → `http://localhost:8080`

3. **FastAPI static serving** (see Serving section above for exact code)

4. **Dev mode note:** The Vite dev server (`:5173`) serves `index.html` without the FastAPI auth check. Developers need a valid session cookie from a prior login at `:8080`, or can temporarily disable `require_admin` locally. The CSP middleware on the FastAPI instance does not affect Vite's HMR (different origin in dev).

5. `npm run build` → `frontend/dist/index.html` + `frontend/dist/assets/`

### `App.jsx` / `main.jsx` Setup

`main.jsx` instantiates a single `QueryClient` with global defaults:
```js
new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 25_000,
      refetchInterval: 30_000,
      retry: 1,
    }
  }
})
```

`App.jsx` wraps the component tree in `<QueryClientProvider>` and a React error boundary. The error boundary renders a styled error card (not a white-screen crash) if a component throws.

---

## Out of Scope

- Photo Curator redesign (separate effort)
- Light mode (dark only for now)
- Mobile-specific layout changes beyond what Tailwind responsive classes provide
- Authentication UI changes
- Any new API endpoints
- Alert acknowledgement UI (v1 displays alerts read-only)

---

## Success Criteria

- [ ] Triggering a 30s data poll does not change the selected log service tab, live toggle state, or scroll position in `LogViewer`
- [ ] Switching log service tabs fetches and renders log output without any other page state changing; new log lines appear within 1 second of tab click on a local network
- [ ] No emoji characters appear anywhere in the rendered dashboard (reference: `📊 🖥️ 📷 💾 💿 🔔 📋 ⚙️ 🔄` from the original `dashboard.html`) — all replaced with Heroicon SVGs
- [ ] CPU shown as percent-only; memory and disk shown as `XX.X% (X.X GB)`, each with a colored progress bar using the correct green/yellow/red thresholds
- [ ] Immich service health and disk SMART status are rendered as pill badges (not plain colored text)
- [ ] Page background color is `#0f0f11`, not `#000000`
- [ ] `GET /` on port 8080 returns the React app's `index.html` and auth checking remains intact (unauthenticated requests are rejected with 401)
- [ ] Clicking "Restart" for any service (e.g. `immich_server`) shows a loading spinner, then ✓ or ✗ within 10 seconds, without refreshing any other part of the page
