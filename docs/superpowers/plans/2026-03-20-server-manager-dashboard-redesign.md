# Server Manager Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `server-manager/static/dashboard.html` with a React 18 + Vite app that eliminates full-page re-renders, preserves log viewer state across data polls, and applies Immich-style visual design with Heroicons.

**Architecture:** React Query polls four API endpoints independently every 30s — each card component subscribes only to its slice of data, so log viewer state is never touched by data refreshes. `LogViewer` manages its own local state entirely via `useState`/`useRef`. FastAPI's existing `@app.get("/")` route is updated to serve the built `index.html`; a new `/assets` static mount serves JS/CSS bundles.

**Tech Stack:** React 18, Vite 5, TailwindCSS v3, TanStack React Query v5, `@heroicons/react`, Vitest + React Testing Library, FastAPI (existing, unchanged API surface).

**Spec:** `docs/superpowers/specs/2026-03-20-server-manager-dashboard-redesign.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `server-manager/frontend/package.json` | Create | NPM dependencies and scripts |
| `server-manager/frontend/vite.config.js` | Create | Vite build config, dev proxy, test config |
| `server-manager/frontend/tailwind.config.js` | Create | Tailwind theme with Immich color tokens |
| `server-manager/frontend/postcss.config.js` | Create | PostCSS (required by Tailwind) |
| `server-manager/frontend/index.html` | Create | Vite entry HTML |
| `server-manager/frontend/src/main.jsx` | Create | React root, QueryClient instantiation |
| `server-manager/frontend/src/index.css` | Create | Tailwind directives, base font |
| `server-manager/frontend/src/App.jsx` | Create | QueryClientProvider, error boundary, layout |
| `server-manager/frontend/src/hooks/useDashboard.js` | Create | All React Query hooks |
| `server-manager/frontend/src/components/Header.jsx` | Create | Logo, title, "last refreshed" timestamp |
| `server-manager/frontend/src/components/SystemStatusCard.jsx` | Create | CPU/memory/disk progress bars |
| `server-manager/frontend/src/components/ImmichStatusCard.jsx` | Create | Health badge, container count |
| `server-manager/frontend/src/components/DiskHealthCard.jsx` | Create | Per-disk SMART badge + temperature |
| `server-manager/frontend/src/components/BackupsCard.jsx` | Create | Backup history + trigger button |
| `server-manager/frontend/src/components/AlertsPanel.jsx` | Create | Severity-colored alert rows |
| `server-manager/frontend/src/components/LogViewer.jsx` | Create | Tab bar, snapshot/live log output |
| `server-manager/frontend/src/components/ServiceControls.jsx` | Create | Per-service restart + restart-all |
| `server-manager/frontend/src/components/UpdateManagement.jsx` | Create | Version display, apply update, SSE progress |
| `server-manager/frontend/src/utils/thresholds.js` | Create | Color threshold logic (shared by multiple cards) |
| `server-manager/frontend/src/test/thresholds.test.js` | Create | Unit tests for threshold utility |
| `server-manager/frontend/src/test/useDashboard.test.js` | Create | Unit test for useLastRefreshed subscription |
| `server-manager/frontend/src/test/SystemStatusCard.test.jsx` | Create | Component tests for progress bar colors |
| `server-manager/frontend/src/test/DiskHealthCard.test.jsx` | Create | SMART badge rendering tests |
| `server-manager/frontend/src/test/BackupsCard.test.jsx` | Create | Backup history rendering tests |
| `server-manager/frontend/src/test/LogViewer.test.jsx` | Create | State isolation test |
| `server-manager/frontend/src/test/UpdateManagement.test.jsx` | Create | Version display and badge tests |
| `server-manager/src/main.py` | Modify | Update `/` route path, add `/assets` static mount |

---

## Task 1: Project Scaffold

**Files:**
- Create: `server-manager/frontend/package.json`
- Create: `server-manager/frontend/vite.config.js`
- Create: `server-manager/frontend/tailwind.config.js`
- Create: `server-manager/frontend/postcss.config.js`
- Create: `server-manager/frontend/index.html`

- [ ] **Step 1: Create `package.json`**

```json
{
  "name": "immich-server-manager",
  "private": true,
  "version": "0.0.1",
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
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@types/react": "^18.3.5",
    "@types/react-dom": "^18.3.0",
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

```js
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
      '/api': 'http://localhost:8080',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
  },
})
```

- [ ] **Step 3: Create `tailwind.config.js`**

```js
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

```js
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
    <title>Immich Server Manager</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Install dependencies**

```bash
cd server-manager/frontend && npm install
```

Expected: `node_modules/` created, no errors.

- [ ] **Step 7: Commit scaffold**

```bash
git add server-manager/frontend/
git commit -m "feat(dashboard): scaffold React/Vite project with Tailwind and React Query"
```

---

## Task 2: App Entry Point

**Files:**
- Create: `server-manager/frontend/src/main.jsx`
- Create: `server-manager/frontend/src/index.css`
- Create: `server-manager/frontend/src/App.jsx`
- Create: `server-manager/frontend/src/test/setup.js`

- [ ] **Step 1: Create `src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

* {
  box-sizing: border-box;
}
```

- [ ] **Step 2: Create test setup file `src/test/setup.js`**

```js
import '@testing-library/jest-dom'
```

- [ ] **Step 3: Create `src/main.jsx`**

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App.jsx'
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

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
)
```

- [ ] **Step 4: Create `src/App.jsx` with error boundary and layout shell**

```jsx
import React from 'react'

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-immich-bg flex items-center justify-center p-8">
          <div className="bg-immich-surface border border-red-800 rounded-2xl p-6 max-w-lg w-full">
            <h2 className="text-red-400 font-semibold mb-2">Something went wrong</h2>
            <pre className="text-immich-muted text-xs font-mono whitespace-pre-wrap">
              {this.state.error?.message}
            </pre>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

export default function App() {
  return (
    <ErrorBoundary>
      <div className="min-h-screen bg-immich-bg text-immich-text">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <p className="text-immich-muted">Loading components…</p>
        </div>
      </div>
    </ErrorBoundary>
  )
}
```

- [ ] **Step 5: Run dev server to verify it starts**

```bash
cd server-manager/frontend && npm run dev
```

Expected: Vite starts on `http://localhost:5173`, browser shows "Loading components…" on dark background.

- [ ] **Step 6: Commit entry point**

```bash
git add server-manager/frontend/src/
git commit -m "feat(dashboard): add React app entry point, error boundary, Tailwind base"
```

---

## Task 3: Data Hooks

**Files:**
- Create: `server-manager/frontend/src/hooks/useDashboard.js`

These hooks are the single source of truth for all polled data. Each component imports only the hook it needs.

- [ ] **Step 1: Create `src/hooks/useDashboard.js`**

```js
import { useQuery, useQueryClient } from '@tanstack/react-query'

const fetcher = (url) => fetch(url).then((r) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
})

export function useStatus() {
  return useQuery({ queryKey: ['status'], queryFn: () => fetcher('/api/status') })
}

export function useDisks() {
  return useQuery({ queryKey: ['disks'], queryFn: () => fetcher('/api/disks') })
}

export function useBackups() {
  return useQuery({ queryKey: ['backups'], queryFn: () => fetcher('/api/backups') })
}

export function useAlerts() {
  return useQuery({ queryKey: ['alerts'], queryFn: () => fetcher('/api/alerts') })
}

// Returns the most recent dataUpdatedAt across all four polling queries.
// Uses a cache subscription so consumers re-render when any query updates.
export function useLastRefreshed() {
  const queryClient = useQueryClient()
  const [lastUpdated, setLastUpdated] = useState(0)

  useEffect(() => {
    const cache = queryClient.getQueryCache()
    const unsubscribe = cache.subscribe(() => {
      const keys = ['status', 'disks', 'backups', 'alerts']
      const timestamps = keys.map((k) => queryClient.getQueryState([k])?.dataUpdatedAt ?? 0)
      setLastUpdated(Math.max(...timestamps))
    })
    return unsubscribe
  }, [queryClient])

  return lastUpdated
}
```

Add `useState` and `useEffect` to the import line at the top:
```js
import { useQuery, useQueryClient, useState, useEffect } from '@tanstack/react-query'
```

Wait — `useState` and `useEffect` are React hooks, not React Query hooks. Fix the import:
```js
import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
```

- [ ] **Step 2: Write failing test for `useLastRefreshed`**

Create `src/test/useDashboard.test.js`:

```js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useLastRefreshed } from '../hooks/useDashboard.js'

function makeWrapper(client) {
  return ({ children }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

describe('useLastRefreshed', () => {
  it('returns 0 when no queries have fetched', () => {
    const client = new QueryClient()
    const { result } = renderHook(() => useLastRefreshed(), { wrapper: makeWrapper(client) })
    expect(result.current).toBe(0)
  })

  it('updates when a query cache entry is written', async () => {
    const client = new QueryClient()
    const { result } = renderHook(() => useLastRefreshed(), { wrapper: makeWrapper(client) })
    expect(result.current).toBe(0)

    const before = Date.now()
    act(() => {
      client.setQueryData(['status'], { system: {} })
    })

    expect(result.current).toBeGreaterThanOrEqual(before)
  })
})
```

- [ ] **Step 3: Run test to confirm it fails**

```bash
cd server-manager/frontend && npm test
```

Expected: FAIL — `Cannot find module '../hooks/useDashboard.js'`

- [ ] **Step 4: Create `src/hooks/useDashboard.js`** (as written in Step 1 above)

- [ ] **Step 5: Run tests and confirm they pass**

```bash
cd server-manager/frontend && npm test
```

Expected: Both `useLastRefreshed` tests PASS.

- [ ] **Step 6: Commit hooks and tests**

```bash
git add server-manager/frontend/src/hooks/ server-manager/frontend/src/test/useDashboard.test.js
git commit -m "feat(dashboard): add React Query data hooks with tested useLastRefreshed subscription"
```

---

## Task 4: Threshold Utility + Tests

**Files:**
- Create: `server-manager/frontend/src/utils/thresholds.js`
- Create: `server-manager/frontend/src/test/thresholds.test.js`

This utility is shared by `SystemStatusCard` and `DiskHealthCard`.

- [ ] **Step 1: Write failing tests**

Create `src/test/thresholds.test.js`:

```js
import { describe, it, expect } from 'vitest'
import { metricColor, metricBarColor } from '../utils/thresholds.js'

describe('metricColor', () => {
  it('returns green class below 70', () => {
    expect(metricColor(50)).toBe('text-green-400')
  })
  it('returns yellow class between 70 and 85', () => {
    expect(metricColor(75)).toBe('text-yellow-400')
  })
  it('returns red class above 85', () => {
    expect(metricColor(90)).toBe('text-red-400')
  })
  it('returns yellow at exactly 70', () => {
    expect(metricColor(70)).toBe('text-yellow-400')
  })
  it('returns red at exactly 85', () => {
    expect(metricColor(85)).toBe('text-red-400')
  })
})

describe('metricBarColor', () => {
  it('returns green bar below 70', () => {
    expect(metricBarColor(50)).toBe('bg-green-500')
  })
  it('returns yellow bar between 70 and 85', () => {
    expect(metricBarColor(75)).toBe('bg-yellow-500')
  })
  it('returns red bar above 85', () => {
    expect(metricBarColor(90)).toBe('bg-red-500')
  })
})
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd server-manager/frontend && npm test
```

Expected: FAIL — `Cannot find module '../utils/thresholds.js'`

- [ ] **Step 3: Create `src/utils/thresholds.js`**

```js
export function metricColor(pct) {
  if (pct >= 85) return 'text-red-400'
  if (pct >= 70) return 'text-yellow-400'
  return 'text-green-400'
}

export function metricBarColor(pct) {
  if (pct >= 85) return 'bg-red-500'
  if (pct >= 70) return 'bg-yellow-500'
  return 'bg-green-500'
}
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
cd server-manager/frontend && npm test
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add server-manager/frontend/src/utils/ server-manager/frontend/src/test/thresholds.test.js
git commit -m "feat(dashboard): add metric color threshold utility with tests"
```

---

## Task 5: Header Component

**Files:**
- Create: `server-manager/frontend/src/components/Header.jsx`

- [ ] **Step 1: Create `src/components/Header.jsx`**

```jsx
import { useState, useEffect } from 'react'
import { useLastRefreshed } from '../hooks/useDashboard.js'

function ImmichLogoIcon() {
  return (
    <svg viewBox="0 0 32 32" className="w-7 h-7" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="32" height="32" rx="8" fill="#4250af"/>
      <path d="M8 22L16 10L24 22" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
      <circle cx="16" cy="10" r="2" fill="white"/>
    </svg>
  )
}

function formatSecondsAgo(ms) {
  if (!ms) return 'never'
  const seconds = Math.floor((Date.now() - ms) / 1000)
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  return `${Math.floor(seconds / 60)}m ago`
}

export default function Header() {
  const lastRefreshed = useLastRefreshed()
  const [label, setLabel] = useState(formatSecondsAgo(lastRefreshed))

  useEffect(() => {
    const id = setInterval(() => setLabel(formatSecondsAgo(lastRefreshed)), 1000)
    return () => clearInterval(id)
  }, [lastRefreshed])

  return (
    <header className="bg-immich-surface border border-immich-border rounded-2xl px-6 py-4 mb-6 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <ImmichLogoIcon />
        <div>
          <h1 className="text-lg font-semibold text-immich-text leading-none">Server Manager</h1>
          <p className="text-xs text-immich-muted mt-0.5">Monitoring · Backups · Health</p>
        </div>
      </div>
      <span className="text-xs text-immich-muted">Updated {label}</span>
    </header>
  )
}
```

- [ ] **Step 2: Wire `Header` into `App.jsx`** — replace the placeholder paragraph:

```jsx
import Header from './components/Header.jsx'

// inside the inner div, replace <p>Loading components…</p> with:
<Header />
```

- [ ] **Step 3: Verify in browser** — `npm run dev`, confirm header renders with logo, title, and "Updated never" timestamp (no data loaded yet).

- [ ] **Step 4: Commit**

```bash
git add server-manager/frontend/src/components/Header.jsx server-manager/frontend/src/App.jsx
git commit -m "feat(dashboard): add Header with logo and last-refreshed timestamp"
```

---

## Task 6: System Status + Immich Status Cards

**Files:**
- Create: `server-manager/frontend/src/components/SystemStatusCard.jsx`
- Create: `server-manager/frontend/src/components/ImmichStatusCard.jsx`
- Create: `server-manager/frontend/src/test/SystemStatusCard.test.jsx`

- [ ] **Step 1: Write failing test for `SystemStatusCard`**

Create `src/test/SystemStatusCard.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import SystemStatusCard from '../components/SystemStatusCard.jsx'

// Mock the hook
vi.mock('../hooks/useDashboard.js', () => ({
  useStatus: vi.fn(),
}))

import { useStatus } from '../hooks/useDashboard.js'

function wrapper({ children }) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      {children}
    </QueryClientProvider>
  )
}

describe('SystemStatusCard', () => {
  it('shows loading state when data is undefined', () => {
    useStatus.mockReturnValue({ data: undefined, isLoading: true })
    render(<SystemStatusCard />, { wrapper })
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('renders CPU percent without GB value', () => {
    useStatus.mockReturnValue({
      data: { system: { cpu_percent: 45, memory_percent: 60, memory_used_gb: 8.2, disk_usage_percent: 55, disk_used_gb: 220 } },
      isLoading: false,
    })
    render(<SystemStatusCard />, { wrapper })
    expect(screen.getByText('45.0%')).toBeInTheDocument()
    expect(screen.getByText(/60\.0%.*8\.2 GB/)).toBeInTheDocument()
  })

  it('renders red color class when CPU exceeds 85%', () => {
    useStatus.mockReturnValue({
      data: { system: { cpu_percent: 92, memory_percent: 30, memory_used_gb: 4, disk_usage_percent: 30, disk_used_gb: 100 } },
      isLoading: false,
    })
    const { container } = render(<SystemStatusCard />, { wrapper })
    expect(container.querySelector('.bg-red-500')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd server-manager/frontend && npm test
```

Expected: FAIL — `Cannot find module '../components/SystemStatusCard.jsx'`

- [ ] **Step 3: Create `src/components/SystemStatusCard.jsx`**

```jsx
import { CpuChipIcon, CircleStackIcon, ServerIcon } from '@heroicons/react/24/outline'
import { useStatus } from '../hooks/useDashboard.js'
import { metricBarColor, metricColor } from '../utils/thresholds.js'

function MetricRow({ label, icon: Icon, pct, suffix }) {
  return (
    <div className="mb-4 last:mb-0">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5 text-immich-muted text-xs font-medium uppercase tracking-wider">
          <Icon className="w-3.5 h-3.5" />
          {label}
        </div>
        <span className={`text-sm font-semibold font-mono ${metricColor(pct)}`}>
          {pct.toFixed(1)}%{suffix ? ` (${suffix})` : ''}
        </span>
      </div>
      <div className="h-1.5 bg-immich-border rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${metricBarColor(pct)}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  )
}

export default function SystemStatusCard() {
  const { data, isLoading } = useStatus()

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4">System</h2>
      {isLoading || !data ? (
        <p className="text-immich-muted text-sm">Loading…</p>
      ) : (
        <>
          <MetricRow label="CPU" icon={CpuChipIcon} pct={Number(data.system.cpu_percent)} />
          <MetricRow label="Memory" icon={ServerIcon} pct={Number(data.system.memory_percent)} suffix={`${Number(data.system.memory_used_gb).toFixed(1)} GB`} />
          <MetricRow label="Disk" icon={CircleStackIcon} pct={Number(data.system.disk_usage_percent)} suffix={`${Number(data.system.disk_used_gb).toFixed(1)} GB`} />
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Create `src/components/ImmichStatusCard.jsx`**

```jsx
import { CheckCircleIcon, ExclamationCircleIcon, CubeIcon } from '@heroicons/react/24/outline'
import { useStatus } from '../hooks/useDashboard.js'

function HealthBadge({ healthy }) {
  return healthy ? (
    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-900/40 text-green-400 border border-green-800">
      <CheckCircleIcon className="w-3.5 h-3.5" /> Healthy
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-900/40 text-red-400 border border-red-800">
      <ExclamationCircleIcon className="w-3.5 h-3.5" /> Issues Detected
    </span>
  )
}

export default function ImmichStatusCard() {
  const { data, isLoading } = useStatus()

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4">Immich</h2>
      {isLoading || !data ? (
        <p className="text-immich-muted text-sm">Loading…</p>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-immich-muted">Service Health</span>
            <HealthBadge healthy={data.immich_healthy} />
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs text-immich-muted">
              <CubeIcon className="w-3.5 h-3.5" /> Containers
            </div>
            <span className="text-sm font-medium text-immich-text">{data.containers.length} running</span>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Run all tests and confirm they pass**

```bash
cd server-manager/frontend && npm test
```

Expected: All tests PASS (thresholds + SystemStatusCard).

- [ ] **Step 6: Wire both cards into `App.jsx`**

Add to `App.jsx` imports:
```jsx
import SystemStatusCard from './components/SystemStatusCard.jsx'
import ImmichStatusCard from './components/ImmichStatusCard.jsx'
```

Add to layout (below `<Header />`):
```jsx
<div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5 mb-6">
  <SystemStatusCard />
  <ImmichStatusCard />
  {/* remaining cards added in later tasks */}
</div>
```

- [ ] **Step 7: Verify in browser** with the dev proxy active (FastAPI must be running on `:8080`). Confirm progress bars and badges render. If FastAPI is not running, cards show "Loading…" — that's fine.

- [ ] **Step 8: Commit**

```bash
git add server-manager/frontend/src/components/SystemStatusCard.jsx server-manager/frontend/src/components/ImmichStatusCard.jsx server-manager/frontend/src/test/SystemStatusCard.test.jsx server-manager/frontend/src/App.jsx
git commit -m "feat(dashboard): add SystemStatusCard with progress bars and ImmichStatusCard with health badge"
```

---

## Task 7: Disk Health + Backups Cards

**Files:**
- Create: `server-manager/frontend/src/components/DiskHealthCard.jsx`
- Create: `server-manager/frontend/src/components/BackupsCard.jsx`
- Create: `server-manager/frontend/src/test/DiskHealthCard.test.jsx`
- Create: `server-manager/frontend/src/test/BackupsCard.test.jsx`

- [ ] **Step 1: Write failing tests**

Create `src/test/DiskHealthCard.test.jsx`:

```jsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import DiskHealthCard from '../components/DiskHealthCard.jsx'

vi.mock('../hooks/useDashboard.js', () => ({ useDisks: vi.fn() }))
import { useDisks } from '../hooks/useDashboard.js'

const wrapper = ({ children }) => (
  <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
)

describe('DiskHealthCard', () => {
  it('shows loading when data is undefined', () => {
    useDisks.mockReturnValue({ data: undefined, isLoading: true })
    render(<DiskHealthCard />, { wrapper })
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('renders a green OK badge for a healthy disk', () => {
    useDisks.mockReturnValue({
      data: { disks: [{ device: '/dev/sda', smart_status: true, temperature: 38 }] },
      isLoading: false,
    })
    render(<DiskHealthCard />, { wrapper })
    expect(screen.getByText('OK')).toBeInTheDocument()
    expect(screen.getByText('/dev/sda')).toBeInTheDocument()
    expect(screen.getByText('38°C')).toBeInTheDocument()
  })

  it('renders a red Fail badge for a failing disk', () => {
    useDisks.mockReturnValue({
      data: { disks: [{ device: '/dev/sdb', smart_status: false, temperature: null }] },
      isLoading: false,
    })
    render(<DiskHealthCard />, { wrapper })
    expect(screen.getByText('Fail')).toBeInTheDocument()
  })
})
```

Create `src/test/BackupsCard.test.jsx`:

```jsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import BackupsCard from '../components/BackupsCard.jsx'

vi.mock('../hooks/useDashboard.js', () => ({ useBackups: vi.fn() }))
import { useBackups } from '../hooks/useDashboard.js'

const wrapper = ({ children }) => (
  <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
)

describe('BackupsCard', () => {
  it('renders green badge for successful backup', () => {
    useBackups.mockReturnValue({
      data: { history: [{ timestamp: '2026-03-01T12:00:00Z', status: 'success' }] },
      isLoading: false,
    })
    render(<BackupsCard />, { wrapper })
    expect(screen.getByText('success')).toBeInTheDocument()
  })

  it('renders red badge for failed backup', () => {
    useBackups.mockReturnValue({
      data: { history: [{ timestamp: '2026-03-01T12:00:00Z', status: 'failed' }] },
      isLoading: false,
    })
    render(<BackupsCard />, { wrapper })
    expect(screen.getByText('failed')).toBeInTheDocument()
  })

  it('shows at most 3 history entries', () => {
    useBackups.mockReturnValue({
      data: {
        history: Array.from({ length: 5 }, (_, i) => ({
          timestamp: `2026-03-0${i + 1}T12:00:00Z`,
          status: 'success',
        })),
      },
      isLoading: false,
    })
    render(<BackupsCard />, { wrapper })
    expect(screen.getAllByText('success')).toHaveLength(3)
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd server-manager/frontend && npm test
```

Expected: FAIL — `Cannot find module '../components/DiskHealthCard.jsx'`

- [ ] **Step 3: Create `src/components/DiskHealthCard.jsx`**

```jsx
import { CircleStackIcon, CheckCircleIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { useDisks } from '../hooks/useDashboard.js'

function SmartBadge({ pass }) {
  return pass ? (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-900/40 text-green-400 border border-green-800">
      <CheckCircleIcon className="w-3 h-3" /> OK
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-900/40 text-red-400 border border-red-800">
      <ExclamationTriangleIcon className="w-3 h-3" /> Fail
    </span>
  )
}

export default function DiskHealthCard() {
  const { data, isLoading } = useDisks()
  const disks = data?.disks ?? []

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4">Disk Health</h2>
      {isLoading ? (
        <p className="text-immich-muted text-sm">Loading…</p>
      ) : disks.length === 0 ? (
        <p className="text-immich-muted text-sm">No disk data</p>
      ) : (
        <div className="space-y-3">
          {disks.map((disk) => (
            <div key={disk.device} className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 min-w-0">
                <CircleStackIcon className="w-3.5 h-3.5 text-immich-muted flex-shrink-0" />
                <span className="text-xs font-mono text-immich-text truncate">{disk.device}</span>
                {disk.temperature != null && (
                  <span className="text-xs text-immich-muted ml-1">{Number(disk.temperature)}°C</span>
                )}
              </div>
              <SmartBadge pass={disk.smart_status} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Create `src/components/BackupsCard.jsx`**

```jsx
import { ArchiveBoxIcon, CheckCircleIcon, XCircleIcon } from '@heroicons/react/24/outline'
import { useBackups } from '../hooks/useDashboard.js'

function StatusBadge({ status }) {
  const ok = status === 'success'
  return ok ? (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-900/40 text-green-400 border border-green-800">
      <CheckCircleIcon className="w-3 h-3" /> {status}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-900/40 text-red-400 border border-red-800">
      <XCircleIcon className="w-3 h-3" /> {status}
    </span>
  )
}

async function triggerBackup() {
  if (!window.confirm('Start a backup now?')) return
  try {
    const r = await fetch('/api/backup/now', { method: 'POST' })
    if (r.ok) {
      window.alert('Backup started!')
    } else {
      window.alert('Failed to start backup.')
    }
  } catch {
    window.alert('Failed to start backup.')
  }
}

export default function BackupsCard() {
  const { data, isLoading } = useBackups()
  const history = (data?.history ?? []).slice(0, 3)

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 flex flex-col">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4">Backups</h2>
      {isLoading ? (
        <p className="text-immich-muted text-sm">Loading…</p>
      ) : history.length === 0 ? (
        <p className="text-immich-muted text-sm mb-4">No backups yet</p>
      ) : (
        <div className="space-y-2 mb-4 flex-1">
          {history.map((b, i) => (
            <div key={i} className="flex items-center justify-between">
              <span className="text-xs text-immich-muted">
                {new Date(b.timestamp).toLocaleDateString()}
              </span>
              <StatusBadge status={b.status} />
            </div>
          ))}
        </div>
      )}
      <button
        onClick={triggerBackup}
        className="mt-auto w-full px-4 py-2 bg-immich-primary hover:bg-blue-600 text-white rounded-lg text-sm font-medium transition-colors duration-150 flex items-center justify-center gap-2"
      >
        <ArchiveBoxIcon className="w-4 h-4" />
        Backup Now
      </button>
    </div>
  )
}
```

- [ ] **Step 4: Run all tests and confirm they pass**

```bash
cd server-manager/frontend && npm test
```

Expected: All DiskHealthCard and BackupsCard tests PASS.

- [ ] **Step 5: Add both cards to `App.jsx` grid** (fill in the two empty grid slots after `ImmichStatusCard`):

```jsx
import DiskHealthCard from './components/DiskHealthCard.jsx'
import BackupsCard from './components/BackupsCard.jsx'

// Add inside the grid div after ImmichStatusCard:
<DiskHealthCard />
<BackupsCard />
```

- [ ] **Step 6: Commit**

```bash
git add server-manager/frontend/src/components/DiskHealthCard.jsx server-manager/frontend/src/components/BackupsCard.jsx server-manager/frontend/src/test/DiskHealthCard.test.jsx server-manager/frontend/src/test/BackupsCard.test.jsx server-manager/frontend/src/App.jsx
git commit -m "feat(dashboard): add DiskHealthCard with SMART badges and BackupsCard with backup history"
```

---

## Task 8: Alerts Panel

**Files:**
- Create: `server-manager/frontend/src/components/AlertsPanel.jsx`

- [ ] **Step 1: Create `src/components/AlertsPanel.jsx`**

```jsx
import { BellAlertIcon } from '@heroicons/react/24/outline'
import { useAlerts } from '../hooks/useDashboard.js'

const SEVERITY_STYLES = {
  critical: 'bg-red-900/20 text-red-300 border-red-800',
  warning: 'bg-yellow-900/20 text-yellow-300 border-yellow-800',
  info: 'bg-blue-900/20 text-blue-300 border-blue-800',
}

export default function AlertsPanel() {
  const { data } = useAlerts()
  const alerts = (data?.alerts ?? []).slice(0, 5)

  if (alerts.length === 0) return null

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4 flex items-center gap-1.5">
        <BellAlertIcon className="w-3.5 h-3.5" /> Alerts
      </h2>
      <div className="space-y-2">
        {alerts.map((alert, i) => (
          <div
            key={i}
            className={`px-3 py-2.5 rounded-lg border text-sm ${SEVERITY_STYLES[alert.severity] ?? SEVERITY_STYLES.info}`}
          >
            <span className="font-semibold">{alert.category}:</span> {alert.message}
            <span className="block text-xs mt-0.5 opacity-60">
              {new Date(alert.timestamp).toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add `AlertsPanel` to `App.jsx`** — insert between the 4-column grid and the log viewer (which hasn't been added yet):

```jsx
import AlertsPanel from './components/AlertsPanel.jsx'

// after the grid div:
<AlertsPanel />
```

- [ ] **Step 3: Commit**

```bash
git add server-manager/frontend/src/components/AlertsPanel.jsx server-manager/frontend/src/App.jsx
git commit -m "feat(dashboard): add AlertsPanel with severity-colored rows"
```

---

## Task 9: Log Viewer

**Files:**
- Create: `server-manager/frontend/src/components/LogViewer.jsx`
- Create: `server-manager/frontend/src/test/LogViewer.test.jsx`

This is the most complex component. Its state must survive parent re-renders entirely.

- [ ] **Step 1: Write failing state isolation test**

Create `src/test/LogViewer.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import LogViewer from '../components/LogViewer.jsx'

// Mock fetch for log snapshots
beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ lines: ['log line 1', 'log line 2'] }),
  })
  // Mock EventSource
  global.EventSource = vi.fn().mockImplementation(() => ({
    onmessage: null,
    onerror: null,
    close: vi.fn(),
  }))
})

describe('LogViewer', () => {
  it('renders all 7 service tabs', () => {
    render(<LogViewer />)
    expect(screen.getByRole('button', { name: /immich_server/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /system/ })).toBeInTheDocument()
  })

  it('preserves selected tab when re-rendered by parent', () => {
    const { rerender } = render(<LogViewer />)
    fireEvent.click(screen.getByRole('button', { name: /server_manager/ }))
    // Re-render with same props (simulates parent state change)
    rerender(<LogViewer />)
    // The server_manager tab should still be active (has the active indicator class)
    const tab = screen.getByRole('button', { name: /server_manager/ })
    expect(tab.className).toMatch(/border-immich-primary/)
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd server-manager/frontend && npm test
```

Expected: FAIL — `Cannot find module '../components/LogViewer.jsx'`

- [ ] **Step 3: Create `src/components/LogViewer.jsx`**

```jsx
import { useState, useEffect, useRef, useCallback } from 'react'
import { DocumentTextIcon } from '@heroicons/react/24/outline'

const SERVICES = [
  'immich_server',
  'immich_machine_learning',
  'immich_postgres',
  'immich_redis',
  'server_manager',
  'photo_curator',
  'system',
]

// Abbreviated display names for the tab bar
const TAB_LABELS = {
  immich_server: 'server',
  immich_machine_learning: 'ml',
  immich_postgres: 'postgres',
  immich_redis: 'redis',
  server_manager: 'server_manager',
  photo_curator: 'photo_curator',
  system: 'system',
}

export default function LogViewer() {
  const [selectedService, setSelectedService] = useState(SERVICES[0])
  const [isLive, setIsLive] = useState(false)
  const [logLines, setLogLines] = useState([])
  const [loading, setLoading] = useState(false)
  const outputRef = useRef(null)
  const eventSourceRef = useRef(null)

  const stopStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [])

  const loadSnapshot = useCallback(async (service) => {
    setLoading(true)
    try {
      const r = await fetch(`/api/logs/${encodeURIComponent(service)}`)
      if (!r.ok) throw new Error(r.status)
      const data = await r.json()
      setLogLines(data.lines ?? [])
    } catch (e) {
      setLogLines([`Error loading logs: ${e.message}`])
    } finally {
      setLoading(false)
    }
  }, [])

  const startStream = useCallback((service) => {
    stopStream()
    setLogLines([])
    const es = new EventSource(`/api/logs/${encodeURIComponent(service)}/stream`)
    es.onmessage = (e) => {
      setLogLines((prev) => [...prev, e.data])
    }
    es.onerror = () => {
      stopStream()
      setIsLive(false)
    }
    eventSourceRef.current = es
  }, [stopStream])

  // When service changes: stop any stream, load snapshot (or restart stream if live)
  useEffect(() => {
    stopStream()
    if (isLive) {
      startStream(selectedService)
    } else {
      loadSnapshot(selectedService)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedService])

  // When live toggled on/off
  useEffect(() => {
    if (isLive) {
      startStream(selectedService)
    } else {
      stopStream()
      loadSnapshot(selectedService)
    }
    return stopStream
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLive])

  // Auto-scroll when live
  useEffect(() => {
    if (isLive && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight
    }
  }, [logLines, isLive])

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4 flex items-center gap-1.5">
        <DocumentTextIcon className="w-3.5 h-3.5" /> Log Viewer
      </h2>

      {/* Tab bar */}
      <div className="flex flex-wrap gap-1 mb-3 border-b border-immich-border pb-3">
        {SERVICES.map((svc) => (
          <button
            key={svc}
            role="button"
            aria-label={svc}
            onClick={() => setSelectedService(svc)}
            className={`px-3 py-1.5 text-xs font-mono rounded-lg transition-colors duration-150 border-b-2 ${
              selectedService === svc
                ? 'text-immich-primary border-immich-primary bg-immich-primary/10'
                : 'text-immich-muted border-transparent hover:text-immich-text hover:bg-immich-border/50'
            }`}
          >
            {TAB_LABELS[svc]}
          </button>
        ))}
      </div>

      {/* Controls */}
      <div className="flex items-center gap-4 mb-3">
        <button
          onClick={() => !isLive && loadSnapshot(selectedService)}
          disabled={isLive}
          className="px-3 py-1.5 bg-immich-primary hover:bg-blue-600 disabled:opacity-40 text-white rounded-lg text-xs font-medium transition-colors duration-150"
        >
          Refresh
        </button>
        <label className="flex items-center gap-2 cursor-pointer select-none text-xs text-immich-muted">
          <input
            type="checkbox"
            checked={isLive}
            onChange={(e) => setIsLive(e.target.checked)}
            className="cursor-pointer"
          />
          <span className="flex items-center gap-1.5">
            {isLive && (
              <span className="inline-block w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            )}
            Live
          </span>
        </label>
      </div>

      {/* Output */}
      <pre
        ref={outputRef}
        className="bg-[#080810] text-gray-300 rounded-xl p-3 text-xs font-mono h-96 overflow-y-auto whitespace-pre-wrap break-all leading-relaxed"
      >
        {loading ? 'Loading…' : logLines.length ? logLines.join('\n') : 'Select a service to load logs.'}
      </pre>
    </div>
  )
}
```

- [ ] **Step 4: Run all tests**

```bash
cd server-manager/frontend && npm test
```

Expected: All tests PASS including the 2 new LogViewer tests.

- [ ] **Step 5: Add `LogViewer` to `App.jsx`**

```jsx
import LogViewer from './components/LogViewer.jsx'

// after <AlertsPanel />:
<LogViewer />
```

- [ ] **Step 6: Commit**

```bash
git add server-manager/frontend/src/components/LogViewer.jsx server-manager/frontend/src/test/LogViewer.test.jsx server-manager/frontend/src/App.jsx
git commit -m "feat(dashboard): add LogViewer with tab bar and isolated state"
```

---

## Task 10: Service Controls

**Files:**
- Create: `server-manager/frontend/src/components/ServiceControls.jsx`

- [ ] **Step 1: Create `src/components/ServiceControls.jsx`**

```jsx
import { useState } from 'react'
import { ArrowPathIcon, WrenchScrewdriverIcon } from '@heroicons/react/24/outline'

const SERVICES = [
  'immich_server',
  'immich_machine_learning',
  'immich_postgres',
  'immich_redis',
  'server_manager',
  'photo_curator',
]

export default function ServiceControls() {
  const [states, setStates] = useState({}) // { [service]: 'idle' | 'loading' | 'ok' | 'error' }

  async function restartService(service) {
    if (!window.confirm(`Restart ${service}?`)) return
    setStates((s) => ({ ...s, [service]: 'loading' }))
    try {
      const r = await fetch(`/api/services/${encodeURIComponent(service)}/restart`, { method: 'POST' })
      setStates((s) => ({ ...s, [service]: r.ok ? 'ok' : 'error' }))
    } catch {
      setStates((s) => ({ ...s, [service]: 'error' }))
    }
    setTimeout(() => setStates((s) => ({ ...s, [service]: 'idle' })), 3000)
  }

  async function restartAll() {
    if (!window.confirm('Restart ALL Immich services? This will briefly interrupt Immich.')) return
    try {
      const r = await fetch('/api/services/restart-all', { method: 'POST' })
      const data = await r.json()
      window.alert(r.ok ? 'All services restarted.' : `Failed: ${data.detail ?? 'unknown error'}`)
    } catch {
      window.alert('Failed to restart all services.')
    }
  }

  function ButtonContent({ service }) {
    const state = states[service] ?? 'idle'
    if (state === 'loading') return <ArrowPathIcon className="w-3.5 h-3.5 animate-spin" />
    if (state === 'ok') return <span>✓</span>
    if (state === 'error') return <span>✗</span>
    return <span>Restart</span>
  }

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4 flex items-center gap-1.5">
        <WrenchScrewdriverIcon className="w-3.5 h-3.5" /> Service Controls
      </h2>
      <div className="space-y-2">
        {SERVICES.map((svc) => (
          <div key={svc} className="flex items-center justify-between py-1.5 border-b border-immich-border last:border-0">
            <span className="text-sm font-mono text-immich-text">{svc}</span>
            <button
              onClick={() => restartService(svc)}
              disabled={(states[svc] ?? 'idle') === 'loading'}
              className="px-3 py-1.5 bg-immich-primary hover:bg-blue-600 disabled:opacity-50 text-white rounded-lg text-xs font-medium transition-colors duration-150 min-w-[64px] flex items-center justify-center"
            >
              <ButtonContent service={svc} />
            </button>
          </div>
        ))}
      </div>
      <div className="mt-4 flex justify-end">
        <button
          onClick={restartAll}
          className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-sm font-medium transition-colors duration-150"
        >
          Restart All Immich Services
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add `ServiceControls` to `App.jsx`**

```jsx
import ServiceControls from './components/ServiceControls.jsx'

// after <LogViewer />:
<ServiceControls />
```

- [ ] **Step 3: Commit**

```bash
git add server-manager/frontend/src/components/ServiceControls.jsx server-manager/frontend/src/App.jsx
git commit -m "feat(dashboard): add ServiceControls with per-service restart and spinner feedback"
```

---

## Task 11: Update Management

**Files:**
- Create: `server-manager/frontend/src/components/UpdateManagement.jsx`
- Create: `server-manager/frontend/src/test/UpdateManagement.test.jsx`

- [ ] **Step 1: Write failing tests**

Create `src/test/UpdateManagement.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
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
        update_available: false, changelog_url: null, history: [],
      }),
    })
    render(<UpdateManagement />)
    await waitFor(() => expect(screen.getByText(/up to date/i)).toBeInTheDocument())
  })

  it('shows blue "Update Available" badge and Apply button when update exists', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        current_version: '1.2.3', latest_version: '1.3.0',
        update_available: true, changelog_url: 'https://github.com/immich-app/immich/releases/tag/v1.3.0', history: [],
      }),
    })
    render(<UpdateManagement />)
    await waitFor(() => expect(screen.getByText(/update available/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /apply update/i })).toBeInTheDocument()
  })

  it('does not render changelog link for non-github URLs', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        current_version: '1.2.3', latest_version: '1.3.0',
        update_available: true, changelog_url: 'https://evil.com/steal', history: [],
      }),
    })
    render(<UpdateManagement />)
    await waitFor(() => screen.getByText(/update available/i))
    expect(screen.queryByText(/changelog/i)).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd server-manager/frontend && npm test
```

Expected: FAIL — `Cannot find module '../components/UpdateManagement.jsx'`

- [ ] **Step 3: Create `src/components/UpdateManagement.jsx`**

```jsx
import { useState, useEffect, useRef } from 'react'
import { ArrowPathIcon } from '@heroicons/react/24/outline'

export default function UpdateManagement() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [progressLines, setProgressLines] = useState([])
  const [updating, setUpdating] = useState(false)
  const progressRef = useRef(null)
  const esRef = useRef(null)

  async function load() {
    setLoading(true)
    try {
      const r = await fetch('/api/updates/status')
      if (!r.ok) throw new Error(r.status)
      setData(await r.json())
    } catch (e) {
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    if (updating && progressRef.current) {
      progressRef.current.scrollTop = progressRef.current.scrollHeight
    }
  }, [progressLines, updating])

  async function applyUpdate() {
    if (!window.confirm('Apply the latest Immich update? A snapshot will be taken first and rollback is automatic on failure.')) return
    try {
      const r = await fetch('/api/updates/apply', { method: 'POST' })
      const d = await r.json()
      if (d.status === 'up_to_date') { window.alert('Already up to date.'); return }
      if (!r.ok) { window.alert(`Failed: ${d.detail ?? 'unknown error'}`); return }
      setUpdating(true)
      setProgressLines([])
      if (esRef.current) esRef.current.close()
      const es = new EventSource('/api/updates/apply/stream')
      esRef.current = es
      es.onmessage = (e) => {
        try {
          const obj = JSON.parse(e.data)
          setProgressLines((prev) => [...prev, { step: obj.step, message: `[${obj.step}] ${obj.message}` }])
          if (['done', 'rolled_back', 'error'].includes(obj.step)) {
            es.close()
            esRef.current = null
            load()
          }
        } catch {}
      }
      es.onerror = () => { es.close(); esRef.current = null }
    } catch (e) {
      window.alert(`Failed to start update: ${e.message}`)
    }
  }

  if (loading) {
    return (
      <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4 flex items-center gap-1.5">
          <ArrowPathIcon className="w-3.5 h-3.5" /> Updates
        </h2>
        <p className="text-immich-muted text-sm">Loading version info…</p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4">Updates</h2>
        <p className="text-red-400 text-sm">Failed to load update status.</p>
      </div>
    )
  }

  const upToDate = !data.update_available

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4 flex items-center gap-1.5">
        <ArrowPathIcon className="w-3.5 h-3.5" /> Updates
      </h2>

      <div className="flex flex-wrap items-center gap-4 mb-4">
        <span className="text-sm text-immich-muted">
          Current: <span className="font-mono font-semibold text-immich-text">v{data.current_version}</span>
        </span>
        <span className="text-sm text-immich-muted">
          Latest: <span className="font-mono font-semibold text-immich-text">v{data.latest_version}</span>
        </span>
        {data.changelog_url?.startsWith('https://github.com/') && (
          <a href={data.changelog_url} target="_blank" rel="noopener noreferrer"
            className="text-xs text-immich-primary hover:underline">
            View Changelog ↗
          </a>
        )}
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
              onClick={applyUpdate}
              className="px-4 py-1.5 bg-immich-primary hover:bg-blue-600 text-white rounded-lg text-sm font-medium transition-colors duration-150"
            >
              Apply Update
            </button>
          </>
        )}
      </div>

      {updating && progressLines.length > 0 && (
        <pre
          ref={progressRef}
          className="bg-[#080810] text-gray-300 rounded-xl p-3 text-xs font-mono max-h-40 overflow-y-auto whitespace-pre-wrap mb-4"
        >
          {progressLines.map((l, i) => (
            <span key={i} className={
              l.step === 'done' ? 'text-green-400' :
              ['rolled_back', 'error'].includes(l.step) ? 'text-red-400' : ''
            }>
              {l.message}{'\n'}
            </span>
          ))}
        </pre>
      )}

      {(data.history ?? []).length > 0 && (
        <div className="border-t border-immich-border pt-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-3">History</h3>
          <table className="w-full text-sm">
            <tbody>
              {data.history.slice(0, 5).map((h, i) => (
                <tr key={i} className="border-b border-immich-border last:border-0">
                  <td className="py-1.5 pr-4 text-xs text-immich-muted">
                    {h.timestamp ? new Date(h.timestamp).toLocaleDateString() : '—'}
                  </td>
                  <td className="py-1.5 pr-4 font-mono text-xs text-immich-text">
                    v{h.from_version ?? '?'} → v{h.to_version ?? '?'}
                  </td>
                  <td className={`py-1.5 text-xs font-medium ${h.status === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                    {h.status === 'success' ? '✓ success' : `✗ ${h.status}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run all tests and confirm they pass**

```bash
cd server-manager/frontend && npm test
```

Expected: All 3 UpdateManagement tests PASS.

- [ ] **Step 5: Add `UpdateManagement` to `App.jsx`**

```jsx
import UpdateManagement from './components/UpdateManagement.jsx'

// after <ServiceControls />:
<UpdateManagement />
```

- [ ] **Step 6: Run full test suite**

```bash
cd server-manager/frontend && npm test
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add server-manager/frontend/src/components/UpdateManagement.jsx server-manager/frontend/src/test/UpdateManagement.test.jsx server-manager/frontend/src/App.jsx
git commit -m "feat(dashboard): add UpdateManagement with version display and SSE update progress"
```

---

## Task 12: FastAPI Integration

**Files:**
- Modify: `server-manager/src/main.py` (two changes)

The goal is to make FastAPI serve the React build. `StaticFiles` is already imported at line 8 — no new import needed.

- [ ] **Step 1: Build the React app first** (need `dist/` to exist before testing the mount):

```bash
cd server-manager/frontend && npm run build
```

Expected: `server-manager/frontend/dist/index.html` and `server-manager/frontend/dist/assets/` are created.

- [ ] **Step 2: Update the `@app.get("/")` route in `main.py`**

Find this single line (around line 532, inside the `root` function body):
```python
    dashboard_path = Path(__file__).parent.parent / "static" / "dashboard.html"
```

Replace **only that one line** with:
```python
    dashboard_path = Path(__file__).parent.parent / "frontend" / "dist" / "index.html"
```

Also update the fallback HTML string (the `else` branch, a few lines below) to say:
```python
        return """
        <html>
            <head><title>Immich Server Manager</title></head>
            <body>
                <h1>Immich Server Manager</h1>
                <p>Frontend not built. Run: <code>cd server-manager/frontend &amp;&amp; npm run build</code></p>
                <p>API Documentation: <a href="/docs">/docs</a></p>
            </body>
        </html>
        """
```

Leave the `async def root(...)` signature and all decorators (`@app.get("/", response_class=HTMLResponse)`, `@limiter.limit(...)` if present) exactly as they are. Only change the path string and the fallback message.

- [ ] **Step 3: Add `/assets` static mount at the end of `main.py`** — just before the `def main():` function:

```python
# Serve React build assets (must be after all @app.get routes to avoid shadowing)
_assets_dir = Path(__file__).parent.parent / "frontend" / "dist" / "assets"
if _assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")
```

- [ ] **Step 4: Restart FastAPI and verify**

```bash
# In the server-manager directory:
python -m uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
```

Open `http://localhost:8080` in a browser. Expected: React dashboard loads with dark background, cards visible.

- [ ] **Step 5: Verify auth is preserved** — open a private browser window and navigate to `http://localhost:8080`. Expected: 401 response or redirect to login (same behavior as before).

- [ ] **Step 6: Commit**

```bash
git add server-manager/src/main.py
git commit -m "feat(dashboard): update FastAPI to serve React build from frontend/dist"
```

---

## Task 13: Final Build Verification

- [ ] **Step 1: Run full test suite**

```bash
cd server-manager/frontend && npm test
```

Expected: All tests PASS.

- [ ] **Step 2: Production build**

```bash
cd server-manager/frontend && npm run build
```

Expected: No build errors. Check that `dist/index.html` references `/assets/index-[hash].js`.

- [ ] **Step 3: Verify success criteria**

Check each item manually against a running server:

- [ ] Trigger a data refresh (wait 30s or temporarily set `refetchInterval: 5_000` in `main.jsx`): confirm log viewer tab selection and scroll position are unchanged
- [ ] Click through log service tabs: confirm each switches in ≤1 click, logs load without page reload
- [ ] Visually confirm: no emoji anywhere in the UI
- [ ] Confirm CPU shows `XX.X%` only; memory/disk show `XX.X% (X.X GB)` with colored progress bars
- [ ] Confirm health/SMART status use pill badges
- [ ] Confirm page background is dark (not pure black)
- [ ] Confirm unauthenticated `GET /` returns 401
- [ ] Click Restart on `immich_server`: confirm spinner → ✓/✗ without other cards updating

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(dashboard): complete React dashboard redesign - all success criteria verified"
```

---

## Notes for Implementer

- **No FastAPI changes are needed for the API endpoints** — they are all unchanged. Only the `@app.get("/")` route body and the `app.mount("/assets", ...)` call change.
- **Dev workflow:** Start FastAPI on `:8080` first, then `npm run dev` in `server-manager/frontend/`. The Vite proxy forwards `/api/*` to FastAPI. You must be authenticated to see real data.
- **The old `dashboard.html`** at `server-manager/static/dashboard.html` can be left in place — it is no longer served but does no harm.
- **Heroicons v2** package is `@heroicons/react`. Import from `@heroicons/react/24/outline` (outline style) or `/24/solid` for filled icons.
- **React Query v5** uses the `useQuery({ queryKey, queryFn })` object syntax — not the positional argument syntax from v4.
