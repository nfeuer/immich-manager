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

FastAPI's existing static file mount is updated to point at `frontend/dist/`. No new server processes or ports. The existing API endpoints (`/api/status`, `/api/disks`, `/api/backups`, `/api/alerts`, `/api/logs/*`, `/api/services/*`, `/api/updates/*`) are unchanged.

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

---

## Components

### `Header`
- Immich logo SVG + "Server Manager" wordmark
- "Last refreshed" relative timestamp (updates quietly every second via `useEffect`, no flash)
- No navigation links (single page)

### `SystemStatusCard`
- CPU, memory, disk usage as labeled progress bars
- Color thresholds: green (< 70%), yellow (70–85%), red (> 85%)
- Values shown as `XX.X% (X.X GB)` inline with bar

### `ImmichStatusCard`
- Service health as a pill badge: green "Healthy" or red "Issues Detected"
- Container count as plain text

### `DiskHealthCard`
- One row per disk: device name + temperature + SMART status badge
- SMART pass = green badge, fail = red badge

### `BackupsCard`
- Up to 3 recent backups with date + status badge
- "Backup Now" button triggers `POST /api/backup/now` with confirmation dialog

### `AlertsPanel`
- Only renders if there are active alerts
- Severity-colored rows: critical (red), warning (amber), info (blue)
- Up to 5 most recent alerts shown

### `LogViewer`
- **Tab bar** replacing dropdown: one tab per service (`immich_server`, `immich_machine_learning`, `immich_postgres`, `immich_redis`, `server_manager`, `photo_curator`, `system`)
- Active tab has primary-color bottom border indicator
- State preserved: selected tab, live toggle, scroll position all survive parent re-renders
- Live mode shows pulsing green dot next to "Live" label
- Log output: `h-96`, monospace, dark terminal background, auto-scroll when live
- Switching tabs: immediately fetches snapshot for new service; if live mode is on, switches the SSE stream

### `ServiceControls`
- One row per service with service name + restart button
- Restart button shows loading spinner during request, then ✓/✗ for 3s
- "Restart All Immich Services" button styled as amber warning action, positioned below the list

### `UpdateManagement`
- Version display: `Current: vX.X.X` / `Latest: vX.X.X` + changelog link
- Status: green "Up to date" badge or blue "Update Available" badge + "Apply Update" button
- Update progress streams into an inline terminal panel (SSE, same logic as current)
- Update history table: date, version transition, status

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
2. `vite.config.js` proxies `/api/*` to `http://localhost:8080` in dev mode
3. FastAPI static files mount updated: `app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")`
4. `npm run build` output goes to `frontend/dist/`

---

## Out of Scope

- Photo Curator redesign (separate effort)
- Light mode (dark only for now)
- Mobile-specific layout changes beyond what Tailwind responsive classes provide
- Authentication UI changes
- Any new API endpoints

---

## Success Criteria

- [ ] Data polling every 30s does not reset log viewer service selection or scroll position
- [ ] Switching log services takes ≤ 1 click and loads within ~500ms
- [ ] All emoji icons replaced with Heroicons SVGs
- [ ] CPU/memory/disk shown with progress bars and color thresholds
- [ ] Status indicators use pill badges, not plain colored text
- [ ] Background is `#0f0f11`, not pure black
- [ ] FastAPI serves the built React app on the same port 8080
