# Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 23 issues from the 2026-04-07 `/impeccable:audit` — bring the audit health score from 12/20 to 18+/20.

**Architecture:** Six passes of surgical fixes. Pass 1 establishes shared tailwind tokens. Pass 2 migrates Server Manager to the token system. Pass 3 introduces a hybrid confirmation pattern (inline + dialog). Pass 4 makes IP Management tables mobile-adaptive. Pass 5 addresses performance and accessibility. Pass 6 extracts a shared Button component and polishes remaining items.

**Tech Stack:** React 18, Vite, Tailwind CSS 3.4, Vitest, @testing-library/react, @heroicons/react.

**Reference spec:** `docs/superpowers/specs/2026-04-08-audit-fixes-design.md`

**Branch:** `claude/immich-server-manager-012giFRno49m7TQDqYMw8HNV` (current branch — no new branch/worktree needed)

---

## Context for the engineer

Both frontends live under `server-manager/frontend/` and `photo-curator/frontend/`. They share an identical Tailwind config today, but it's duplicated — this plan consolidates it. Each frontend has a `src/test/` directory using Vitest + @testing-library/react with jsdom. Test command in each is `npm run test`.

**Key conventions already in the codebase:**
- Semantic color tokens: `immich-primary`, `immich-bg`, `immich-surface`, `immich-border`, `immich-text`, `immich-muted`, and 4 status colors (`success`, `error`, `warning`, `info`) each with `DEFAULT`, `muted`, and `border` variants.
- Heroicons from `@heroicons/react/24/outline`.
- TanStack Query v5 for data fetching.
- `focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary` is the standard focus pattern on interactive elements.

**Before starting each task:** read the files listed under "Files" to understand the current state. After each task: run the test suites listed under "Validation" and only commit when they pass.

---

## Task 1: Shared Tailwind Tokens

**Files:**
- Create: `shared/tailwind-tokens.js`
- Modify: `server-manager/frontend/tailwind.config.js`
- Modify: `photo-curator/frontend/tailwind.config.js`

- [ ] **Step 1: Create the shared tokens module**

Create `shared/tailwind-tokens.js` with this content:

```js
// Shared Tailwind theme.extend for both server-manager and photo-curator frontends.
// Single source of truth — edit here, both apps pick it up.

export const themeExtend = {
  colors: {
    'immich-primary': '#4250af',
    'immich-primary-hover': '#5360c0',
    'immich-bg': '#0f0f11',
    'immich-surface': '#1a1a27',
    'immich-border': '#2a2a3d',
    'immich-text': '#f1f0ff',
    'immich-muted': '#7c7c9a',
    'immich-terminal': '#080810',
    'immich-log-info': '#d1d5db',
    'immich-log-debug': '#6b7280',
    'immich-log-untagged': '#fb923c',
    'immich-success': {
      DEFAULT: '#4ade80',
      muted: 'rgba(20, 83, 45, 0.4)',
      border: '#166534',
    },
    'immich-error': {
      DEFAULT: '#f87171',
      muted: 'rgba(127, 29, 29, 0.4)',
      border: '#991b1b',
    },
    'immich-warning': {
      DEFAULT: '#facc15',
      muted: 'rgba(113, 63, 18, 0.4)',
      border: '#a16207',
    },
    'immich-info': {
      DEFAULT: '#60a5fa',
      muted: 'rgba(30, 58, 138, 0.4)',
      border: '#1e40af',
    },
  },
  fontFamily: {
    sans: ['system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
  },
}
```

- [ ] **Step 2: Rewrite server-manager tailwind config to import shared tokens**

Replace the entire contents of `server-manager/frontend/tailwind.config.js` with:

```js
/** @type {import('tailwindcss').Config} */
import { themeExtend } from '../../shared/tailwind-tokens.js'

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: { extend: themeExtend },
  plugins: [],
}
```

- [ ] **Step 3: Rewrite photo-curator tailwind config to import shared tokens**

Replace the entire contents of `photo-curator/frontend/tailwind.config.js` with:

```js
/** @type {import('tailwindcss').Config} */
import { themeExtend } from '../../shared/tailwind-tokens.js'

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: { extend: themeExtend },
  plugins: [],
}
```

- [ ] **Step 4: Build both frontends to verify config resolves**

Run: `cd server-manager/frontend && npm run build`
Expected: Build succeeds with no errors mentioning tailwind config or tokens.

Run: `cd photo-curator/frontend && npm run build`
Expected: Same.

- [ ] **Step 5: Commit**

```bash
git add shared/tailwind-tokens.js server-manager/frontend/tailwind.config.js photo-curator/frontend/tailwind.config.js
git commit -m "refactor(frontend): extract shared tailwind tokens, add new color tokens"
```

---

## Task 2: Fix stale test assertions in AlertsPanel

**Context:** `src/test/AlertsPanel.test.jsx` contains assertions for class names `bg-red-900\\/20` and `bg-yellow-900\\/20` — but the current `AlertsPanel.jsx` uses `bg-immich-error-muted` and `bg-immich-warning-muted`. These tests are broken today independent of our work. Fix them before Pass 2 so the baseline is clean.

**Files:**
- Modify: `server-manager/frontend/src/test/AlertsPanel.test.jsx:60,72`

- [ ] **Step 1: Verify tests currently fail**

Run: `cd server-manager/frontend && npx vitest run src/test/AlertsPanel.test.jsx`
Expected: Two test failures — "applies critical severity styling" and "applies warning severity styling".

- [ ] **Step 2: Update the class name assertions**

In `server-manager/frontend/src/test/AlertsPanel.test.jsx`:

Replace line 60:
```js
expect(container.querySelector('.bg-red-900\\/20')).toBeInTheDocument()
```
with:
```js
expect(container.querySelector('.bg-immich-error-muted')).toBeInTheDocument()
```

Replace line 72:
```js
expect(container.querySelector('.bg-yellow-900\\/20')).toBeInTheDocument()
```
with:
```js
expect(container.querySelector('.bg-immich-warning-muted')).toBeInTheDocument()
```

- [ ] **Step 3: Run tests and verify they pass**

Run: `cd server-manager/frontend && npx vitest run src/test/AlertsPanel.test.jsx`
Expected: All 6 tests pass.

- [ ] **Step 4: Commit**

```bash
git add server-manager/frontend/src/test/AlertsPanel.test.jsx
git commit -m "test(server-manager): fix stale AlertsPanel class name assertions"
```

---

## Task 3: Token migration — LogViewer

**Files:**
- Modify: `server-manager/frontend/src/components/LogViewer.jsx`

- [ ] **Step 1: Replace LEVEL_COLORS and FILTER_ACTIVE_CLASSES**

In `src/components/LogViewer.jsx`, replace lines 34-48:

```js
const LEVEL_COLORS = {
  error: 'text-immich-error',
  warn: 'text-immich-warning',
  info: 'text-gray-300',
  debug: 'text-gray-500',
  untagged: 'text-orange-400',
}

const FILTER_ACTIVE_CLASSES = {
  error: 'text-immich-error border-immich-error bg-immich-error/10',
  warn: 'text-immich-warning border-immich-warning bg-immich-warning/10',
  info: 'text-gray-300 border-gray-300 bg-gray-300/10',
  debug: 'text-gray-500 border-gray-500 bg-gray-500/10',
  untagged: 'text-orange-400 border-orange-400 bg-orange-400/10',
}
```

with:

```js
const LEVEL_COLORS = {
  error: 'text-immich-error',
  warn: 'text-immich-warning',
  info: 'text-immich-log-info',
  debug: 'text-immich-log-debug',
  untagged: 'text-immich-log-untagged',
}

const FILTER_ACTIVE_CLASSES = {
  error: 'text-immich-error border-immich-error bg-immich-error/10',
  warn: 'text-immich-warning border-immich-warning bg-immich-warning/10',
  info: 'text-immich-log-info border-immich-log-info bg-immich-log-info/10',
  debug: 'text-immich-log-debug border-immich-log-debug bg-immich-log-debug/10',
  untagged: 'text-immich-log-untagged border-immich-log-untagged bg-immich-log-untagged/10',
}
```

- [ ] **Step 2: Replace the terminal background and text colors in the output**

In `src/components/LogViewer.jsx` line ~198 (Refresh button) — change `hover:bg-blue-600` to `hover:bg-immich-primary-hover`:

```jsx
className="px-3 py-1.5 bg-immich-primary hover:bg-immich-primary-hover disabled:opacity-40 text-white rounded-lg text-xs font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
```

In `src/components/LogViewer.jsx` line ~257 change:
```jsx
className="bg-[#080810] rounded-xl p-3 text-xs font-mono h-64 sm:h-80 md:h-96 lg:h-[32rem] overflow-y-auto"
```
to:
```jsx
className="bg-immich-terminal rounded-xl p-3 text-xs font-mono h-64 sm:h-80 md:h-96 lg:h-[32rem] overflow-y-auto"
```

In `src/components/LogViewer.jsx` line ~260, 265, 271, 273 change `text-gray-300` → `text-immich-log-info` and `text-gray-500` → `text-immich-log-debug`:

```jsx
{loading ? (
  <span className="text-immich-log-info">Loading…</span>
) : visibleLines.length > 0 ? (
  visibleLines.map(({ line, idx }) => (
    <div
      key={idx}
      className={`whitespace-pre-wrap break-all leading-relaxed ${LEVEL_COLORS[line.level] ?? 'text-immich-log-info'}`}
    >
      {line.text}
    </div>
  ))
) : logLines.length === 0 ? (
  <span className="text-immich-log-info">Select a service to load logs.</span>
) : (
  <span className="text-immich-log-debug">No lines match the active filter.</span>
)}
```

- [ ] **Step 3: Run LogViewer tests**

Run: `cd server-manager/frontend && npx vitest run src/test/LogViewer.test.jsx`
Expected: All tests pass.

- [ ] **Step 4: Run build to confirm no unused class warnings**

Run: `cd server-manager/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 5: Commit**

```bash
git add server-manager/frontend/src/components/LogViewer.jsx
git commit -m "refactor(server-manager): migrate LogViewer to semantic color tokens"
```

---

## Task 4: Token migration — IPManagement

**Files:**
- Modify: `server-manager/frontend/src/components/IPManagement.jsx`

- [ ] **Step 1: Replace the admin/user access level badge**

In `src/components/IPManagement.jsx` around line 60:

Before:
```jsx
<span className={`text-xs px-2 py-0.5 rounded ${ip.access_level === 'admin' ? 'bg-red-500/20 text-red-300' : 'bg-blue-500/20 text-blue-300'}`}>
  {ip.access_level}
</span>
```

After:
```jsx
<span className={`text-xs px-2 py-0.5 rounded ${ip.access_level === 'admin' ? 'bg-immich-error-muted text-immich-error' : 'bg-immich-info-muted text-immich-info'}`}>
  {ip.access_level}
</span>
```

- [ ] **Step 2: Replace TrustedTab action buttons (Edit/Revoke) and inline edit/revoke panels**

In TrustedTab — around lines 69-72 (Edit and Revoke buttons):

```jsx
<td className="py-2 flex gap-2">
  <button type="button" onClick={() => { setEditingIp(ip.ip_address); setEditLabel(ip.label || ''); setEditDuration(ip.trust_duration || '24h') }}
    className="text-xs text-immich-info hover:text-immich-info/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-info rounded">Edit</button>
  <button type="button" onClick={() => setRevokeIp(ip.ip_address)}
    className="text-xs text-immich-error hover:text-immich-error/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error rounded">Revoke</button>
</td>
```

Edit panel (lines ~82-104):

```jsx
{editingIp && (
  <div className="mt-4 p-4 bg-immich-bg border border-immich-border rounded-lg">
    <h4 className="text-sm font-medium mb-2">Edit {editingIp}</h4>
    <div className="flex gap-3 items-end flex-wrap">
      <div>
        <label htmlFor="edit-label" className="text-xs text-immich-muted block mb-1">Label</label>
        <input id="edit-label" value={editLabel} onChange={(e) => setEditLabel(e.target.value)}
          className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary" />
      </div>
      <div>
        <label htmlFor="edit-duration" className="text-xs text-immich-muted block mb-1">Duration</label>
        <select id="edit-duration" value={editDuration} onChange={(e) => setEditDuration(e.target.value)}
          className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary">
          {DURATION_OPTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>
      <button type="button" onClick={() => { updateMut.mutate({ ip: editingIp, label: editLabel, trust_duration: editDuration }); setEditingIp(null) }}
        className="px-3 py-1 bg-immich-primary hover:bg-immich-primary-hover text-white text-sm rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary">Save</button>
      <button type="button" onClick={() => setEditingIp(null)}
        className="px-3 py-1 text-immich-muted hover:text-immich-text text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary rounded">Cancel</button>
    </div>
  </div>
)}
```

Revoke panel (lines ~106-120):

```jsx
{revokeIp && (
  <div className="mt-4 p-4 bg-immich-bg border border-immich-error-border/50 rounded-lg">
    <h4 className="text-sm font-medium text-immich-error mb-2">Revoke {revokeIp}</h4>
    <label htmlFor="revoke-reason" className="sr-only">Reason for revoking</label>
    <input id="revoke-reason" value={revokeReason} onChange={(e) => setRevokeReason(e.target.value)}
      placeholder="Reason (optional)"
      className="w-full px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text mb-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error" />
    <div className="flex gap-2">
      <button type="button" onClick={() => { revokeMut.mutate({ ip_address: revokeIp, reason: revokeReason }); setRevokeIp(null); setRevokeReason('') }}
        className="px-3 py-1 bg-immich-error text-white text-sm rounded hover:bg-immich-error/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error">Confirm Revoke</button>
      <button type="button" onClick={() => { setRevokeIp(null); setRevokeReason('') }}
        className="px-3 py-1 text-immich-muted hover:text-immich-text text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary rounded">Cancel</button>
    </div>
  </div>
)}
```

- [ ] **Step 3: Replace PendingTab action buttons and approve panel**

PendingTab action buttons (lines ~154-157):

```jsx
<td className="py-2 flex gap-2">
  <button type="button" onClick={() => setApproveIp(ip.ip_address)}
    className="text-xs text-immich-success hover:text-immich-success/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-success rounded">Approve</button>
  <button type="button" onClick={() => revokeMut.mutate({ ip_address: ip.ip_address })}
    className="text-xs text-immich-error hover:text-immich-error/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error rounded">Blacklist</button>
</td>
```

Approve panel (lines ~167-194) — replace the whole block:

```jsx
{approveIp && (
  <div className="mt-4 p-4 bg-immich-bg border border-immich-success-border/50 rounded-lg">
    <h4 className="text-sm font-medium text-immich-success mb-2">Approve {approveIp}</h4>
    <div className="flex gap-3 items-end flex-wrap">
      <div>
        <label htmlFor="approve-level" className="text-xs text-immich-muted block mb-1">Access Level</label>
        <select id="approve-level" value={approveLevel} onChange={(e) => setApproveLevel(e.target.value)}
          className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-success">
          <option value="user">User (Photo Curator only)</option>
          <option value="admin">Admin (All services)</option>
        </select>
      </div>
      <div>
        <label htmlFor="approve-duration" className="text-xs text-immich-muted block mb-1">Duration</label>
        <select id="approve-duration" value={approveDuration} onChange={(e) => setApproveDuration(e.target.value)}
          className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-success">
          {DURATION_OPTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>
      <button type="button" onClick={() => {
        approveMut.mutate({ ip_address: approveIp, access_level: approveLevel, trust_duration: approveDuration })
        setApproveIp(null)
      }} className="px-3 py-1 bg-immich-success text-white text-sm rounded hover:bg-immich-success/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-success">Confirm</button>
      <button type="button" onClick={() => setApproveIp(null)}
        className="px-3 py-1 text-immich-muted hover:text-immich-text text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary rounded">Cancel</button>
    </div>
  </div>
)}
```

- [ ] **Step 4: Replace BlacklistedTab Unblock/Delete action buttons**

Around lines 228-233:

```jsx
<td className="py-2 flex gap-2">
  <button type="button" onClick={() => unblockMut.mutate({ ip_address: ip.ip_address })}
    className="text-xs text-immich-warning hover:text-immich-warning/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-warning rounded">Unblock</button>
  <button type="button" onClick={() => deleteMut.mutate(ip.ip_address)}
    className="text-xs text-immich-error hover:text-immich-error/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error rounded">Delete</button>
</td>
```

- [ ] **Step 5: Replace ConnectionsTab action color map and filter focus rings**

Around lines 253-272 (filter inputs), replace `focus-visible:ring-blue-400` with `focus-visible:ring-immich-primary`.

Around lines 294-300 (action color spans):

```jsx
<td className="py-1.5 pr-4">
  <span className={`text-xs ${
    c.action === 'allowed' ? 'text-immich-success' :
    c.action === 'blocked' ? 'text-immich-error' :
    c.action === 'challenged' ? 'text-immich-warning' :
    'text-immich-log-untagged'
  }`}>{c.action}</span>
</td>
```

- [ ] **Step 6: Replace IPManagement header icon and tab bar**

Around lines 322 (ShieldCheckIcon) and 332-338 (tab buttons):

```jsx
<ShieldCheckIcon className="w-5 h-5 text-immich-info" />
```

Tab button styles — replace `text-blue-400 border-blue-400` with `text-immich-info border-immich-info` and `focus-visible:ring-blue-400` with `focus-visible:ring-immich-primary`:

```jsx
<button
  type="button"
  key={tab}
  onClick={() => setActiveTab(tab)}
  className={`px-4 py-2 text-sm transition-colors border-b-2 -mb-px focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary rounded-t ${
    activeTab === tab
      ? 'text-immich-info border-immich-info'
      : 'text-immich-muted border-transparent hover:text-immich-text'
  }`}
>
  {TAB_LABELS[tab]}
</button>
```

- [ ] **Step 7: Run IPManagement tests**

Run: `cd server-manager/frontend && npx vitest run src/test/IPManagement.test.jsx`
Expected: All tests pass.

- [ ] **Step 8: Run full server-manager test suite**

Run: `cd server-manager/frontend && npm run test`
Expected: All tests pass.

- [ ] **Step 9: Commit**

```bash
git add server-manager/frontend/src/components/IPManagement.jsx
git commit -m "refactor(server-manager): migrate IPManagement to semantic color tokens"
```

---

## Task 5: Token migration — remaining Server Manager files

**Files:**
- Modify: `server-manager/frontend/src/components/ServiceControls.jsx`
- Modify: `server-manager/frontend/src/components/BackupsCard.jsx`
- Modify: `server-manager/frontend/src/components/DiscordConfig.jsx`
- Modify: `server-manager/frontend/src/components/UpdateManagement.jsx`
- Modify: `server-manager/frontend/src/pages/ChallengePage.jsx`

- [ ] **Step 1: ServiceControls — replace hover and amber classes**

In `src/components/ServiceControls.jsx`:

Line 68 — restart button:
```jsx
className="px-3 py-1.5 bg-immich-primary hover:bg-immich-primary-hover disabled:opacity-50 text-white rounded-lg text-xs font-medium transition-colors duration-150 min-w-[64px] flex items-center justify-center focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
```

Line 79 — Restart All button:
```jsx
className="px-4 py-2 bg-immich-warning hover:bg-immich-warning/90 text-immich-bg rounded-lg text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-warning"
```

(Note: `text-immich-bg` for dark text on the yellow warning button — yellow + white is low contrast.)

- [ ] **Step 2: BackupsCard — replace hover class**

In `src/components/BackupsCard.jsx` line 55:
```jsx
className="mt-auto w-full px-4 py-2 bg-immich-primary hover:bg-immich-primary-hover text-white rounded-lg text-sm font-medium transition-colors duration-150 flex items-center justify-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
```

- [ ] **Step 3: DiscordConfig — replace hover classes and focus rings**

In `src/components/DiscordConfig.jsx`:

Replace the `inputClass` constant (line 35):
```js
const inputClass = 'w-full px-3 py-2 bg-immich-bg border border-immich-border rounded-lg text-sm text-immich-text placeholder-immich-muted/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary focus:border-immich-primary transition-colors'
```

Lines 168, 201, 263 — replace `hover:bg-blue-600` with `hover:bg-immich-primary-hover` and `focus-visible:ring-blue-400` with `focus-visible:ring-immich-primary`:

```jsx
className="px-4 py-2 bg-immich-primary hover:bg-immich-primary-hover disabled:opacity-40 text-white rounded-lg text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
```

(Apply the same pattern to all three buttons.)

The save button at line 263:
```jsx
className="px-5 py-2 bg-immich-primary hover:bg-immich-primary-hover disabled:opacity-40 text-white rounded-lg text-sm font-semibold transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
```

- [ ] **Step 4: UpdateManagement — replace hover, amber, gray, and hex classes**

In `src/components/UpdateManagement.jsx`:

Line 121 — "Update anyway" button:
```jsx
className="px-4 py-1.5 bg-immich-warning hover:bg-immich-warning/90 disabled:opacity-50 text-immich-bg rounded-lg text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-warning"
```

Line 135 — "Apply Update" button:
```jsx
className="px-4 py-1.5 bg-immich-primary hover:bg-immich-primary-hover disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
```

Line 146 — progress `<pre>`:
```jsx
<pre
  ref={progressRef}
  className="bg-immich-terminal text-immich-log-info rounded-xl p-3 text-xs font-mono max-h-32 sm:max-h-40 md:max-h-52 overflow-y-auto whitespace-pre-wrap mb-4"
>
```

- [ ] **Step 5: ChallengePage — replace blue classes**

In `src/pages/ChallengePage.jsx`:

Line 87-90 — email input:
```jsx
className="w-full pl-10 pr-3 py-2 bg-immich-bg border border-immich-border rounded-lg
           text-immich-text placeholder-immich-muted/50 text-sm
           focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary focus:border-immich-primary"
```

Line 93-96 — verify button:
```jsx
className="px-4 py-2 bg-immich-primary hover:bg-immich-primary-hover disabled:opacity-50
           text-white text-sm font-medium rounded-lg transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
```

Line 107-109 — success banner:
```jsx
<div className="bg-immich-info-muted border border-immich-info-border rounded-lg p-4">
  <p className="text-immich-info text-sm">
    A verification email has been sent if the account exists. Please check
```

Line 115-117 — refresh button:
```jsx
className="mt-4 w-full px-4 py-2 bg-immich-bg border border-immich-border
           hover:border-immich-primary text-immich-text text-sm rounded-lg transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
```

- [ ] **Step 6: Run server-manager test suite**

Run: `cd server-manager/frontend && npm run test`
Expected: All tests pass.

- [ ] **Step 7: Validate zero hard-coded colors remain**

Run: `grep -rnE 'text-(blue|red|green|amber|yellow|orange|gray)-[0-9]|bg-(blue|red|green|amber|yellow|orange|gray)-[0-9]|ring-(blue|red|green|amber|yellow|orange|gray)-[0-9]|border-(blue|red|green|amber|yellow|orange|gray)-[0-9]|bg-\[#' server-manager/frontend/src`
Expected: Zero matches.

- [ ] **Step 8: Build to confirm**

Run: `cd server-manager/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 9: Commit**

```bash
git add server-manager/frontend/src/components/ServiceControls.jsx \
        server-manager/frontend/src/components/BackupsCard.jsx \
        server-manager/frontend/src/components/DiscordConfig.jsx \
        server-manager/frontend/src/components/UpdateManagement.jsx \
        server-manager/frontend/src/pages/ChallengePage.jsx
git commit -m "refactor(server-manager): migrate remaining files to semantic color tokens"
```

---

## Task 6: Create useFocusTrap hook

**Files:**
- Create: `server-manager/frontend/src/hooks/useFocusTrap.js`
- Create: `photo-curator/frontend/src/hooks/useFocusTrap.js`

**Note:** Same file in both apps — copy-paste, not shared (no shared component infra yet).

- [ ] **Step 1: Create the hook in server-manager**

Create `server-manager/frontend/src/hooks/useFocusTrap.js`:

```js
import { useEffect, useRef } from 'react'

/**
 * Traps focus inside a container while `active` is true.
 * Also handles Escape-to-close via `onEscape`.
 *
 * Usage:
 *   const ref = useFocusTrap({ active: isOpen, onEscape: close })
 *   return <div ref={ref}>...</div>
 */
export function useFocusTrap({ active, onEscape }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (!active) return
    const container = containerRef.current
    if (!container) return

    const previouslyFocused = document.activeElement
    const focusable = container.querySelectorAll(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
    const first = focusable[0]
    const last = focusable[focusable.length - 1]

    first?.focus()

    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && onEscape) {
        e.preventDefault()
        onEscape()
        return
      }
      if (e.key !== 'Tab') return
      if (focusable.length === 0) {
        e.preventDefault()
        return
      }
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    container.addEventListener('keydown', handleKeyDown)
    return () => {
      container.removeEventListener('keydown', handleKeyDown)
      if (previouslyFocused instanceof HTMLElement) {
        previouslyFocused.focus()
      }
    }
  }, [active, onEscape])

  return containerRef
}
```

- [ ] **Step 2: Copy the same file to photo-curator**

Create `photo-curator/frontend/src/hooks/useFocusTrap.js` with identical content.

- [ ] **Step 3: Commit**

```bash
git add server-manager/frontend/src/hooks/useFocusTrap.js photo-curator/frontend/src/hooks/useFocusTrap.js
git commit -m "feat(frontend): add useFocusTrap hook for modal focus management"
```

---

## Task 7: Create useInlineConfirm hook

**Files:**
- Create: `server-manager/frontend/src/hooks/useInlineConfirm.js`
- Create: `server-manager/frontend/src/test/useInlineConfirm.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `server-manager/frontend/src/test/useInlineConfirm.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useInlineConfirm } from '../hooks/useInlineConfirm.js'

describe('useInlineConfirm', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('arms a key on first trigger and does not call the handler', () => {
    const { result } = renderHook(() => useInlineConfirm())
    const handler = vi.fn()

    act(() => {
      result.current.trigger('alpha', handler)
    })

    expect(handler).not.toHaveBeenCalled()
    expect(result.current.isArmed('alpha')).toBe(true)
  })

  it('calls the handler and disarms on second trigger while armed', () => {
    const { result } = renderHook(() => useInlineConfirm())
    const handler = vi.fn()

    act(() => {
      result.current.trigger('alpha', handler)
    })
    act(() => {
      result.current.trigger('alpha', handler)
    })

    expect(handler).toHaveBeenCalledTimes(1)
    expect(result.current.isArmed('alpha')).toBe(false)
  })

  it('auto-disarms after 3 seconds', () => {
    const { result } = renderHook(() => useInlineConfirm())
    const handler = vi.fn()

    act(() => {
      result.current.trigger('alpha', handler)
    })
    expect(result.current.isArmed('alpha')).toBe(true)

    act(() => {
      vi.advanceTimersByTime(3000)
    })

    expect(result.current.isArmed('alpha')).toBe(false)
  })

  it('supports multiple independent keys', () => {
    const { result } = renderHook(() => useInlineConfirm())
    const handlerA = vi.fn()
    const handlerB = vi.fn()

    act(() => {
      result.current.trigger('alpha', handlerA)
    })
    act(() => {
      result.current.trigger('beta', handlerB)
    })

    expect(result.current.isArmed('alpha')).toBe(true)
    expect(result.current.isArmed('beta')).toBe(true)

    act(() => {
      result.current.trigger('alpha', handlerA)
    })

    expect(handlerA).toHaveBeenCalledTimes(1)
    expect(handlerB).not.toHaveBeenCalled()
    expect(result.current.isArmed('alpha')).toBe(false)
    expect(result.current.isArmed('beta')).toBe(true)
  })
})
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `cd server-manager/frontend && npx vitest run src/test/useInlineConfirm.test.jsx`
Expected: All tests fail with "Failed to resolve import" or "useInlineConfirm is not a function".

- [ ] **Step 3: Implement the hook**

Create `server-manager/frontend/src/hooks/useInlineConfirm.js`:

```js
import { useState, useRef, useCallback, useEffect } from 'react'

const ARM_TIMEOUT_MS = 3000

/**
 * Two-click confirmation for low-stakes actions.
 *
 * Usage:
 *   const { isArmed, trigger } = useInlineConfirm()
 *   <button onClick={() => trigger('backup', doBackup)}>
 *     {isArmed('backup') ? 'Click again to confirm' : 'Backup Now'}
 *   </button>
 */
export function useInlineConfirm() {
  const [armedKeys, setArmedKeys] = useState(() => new Set())
  const timersRef = useRef(new Map())

  const disarm = useCallback((key) => {
    setArmedKeys((prev) => {
      if (!prev.has(key)) return prev
      const next = new Set(prev)
      next.delete(key)
      return next
    })
    const timer = timersRef.current.get(key)
    if (timer != null) {
      clearTimeout(timer)
      timersRef.current.delete(key)
    }
  }, [])

  const arm = useCallback((key) => {
    setArmedKeys((prev) => {
      const next = new Set(prev)
      next.add(key)
      return next
    })
    const existing = timersRef.current.get(key)
    if (existing != null) clearTimeout(existing)
    const timer = setTimeout(() => disarm(key), ARM_TIMEOUT_MS)
    timersRef.current.set(key, timer)
  }, [disarm])

  const trigger = useCallback((key, handler) => {
    if (armedKeys.has(key)) {
      disarm(key)
      handler()
    } else {
      arm(key)
    }
  }, [armedKeys, arm, disarm])

  const isArmed = useCallback((key) => armedKeys.has(key), [armedKeys])

  useEffect(() => {
    const timers = timersRef.current
    return () => {
      for (const timer of timers.values()) clearTimeout(timer)
      timers.clear()
    }
  }, [])

  return { isArmed, trigger }
}
```

- [ ] **Step 4: Run the test and verify it passes**

Run: `cd server-manager/frontend && npx vitest run src/test/useInlineConfirm.test.jsx`
Expected: All 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add server-manager/frontend/src/hooks/useInlineConfirm.js server-manager/frontend/src/test/useInlineConfirm.test.jsx
git commit -m "feat(server-manager): add useInlineConfirm hook for two-click confirmation"
```

---

## Task 8: Create ConfirmDialog component

**Files:**
- Create: `server-manager/frontend/src/components/ConfirmDialog.jsx`
- Create: `server-manager/frontend/src/test/ConfirmDialog.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `server-manager/frontend/src/test/ConfirmDialog.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import ConfirmDialog from '../components/ConfirmDialog.jsx'

// jsdom does not implement HTMLDialogElement — polyfill the methods we use
beforeEach(() => {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function () { this.open = true }
    HTMLDialogElement.prototype.close = function () { this.open = false }
  }
})

describe('ConfirmDialog', () => {
  it('renders nothing visible when closed', () => {
    render(
      <ConfirmDialog
        open={false}
        title="Delete item"
        description="This cannot be undone."
        confirmLabel="Delete"
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    )
    const dialog = screen.queryByRole('dialog', { hidden: true })
    expect(dialog?.open).toBeFalsy()
  })

  it('shows title, description, and buttons when open', () => {
    render(
      <ConfirmDialog
        open={true}
        title="Delete item"
        description="This cannot be undone."
        confirmLabel="Delete"
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByText('Delete item')).toBeInTheDocument()
    expect(screen.getByText('This cannot be undone.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
  })

  it('calls onConfirm when confirm button is clicked', () => {
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        open={true}
        title="Delete item"
        description="This cannot be undone."
        confirmLabel="Delete"
        onConfirm={onConfirm}
        onCancel={() => {}}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /delete/i }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('calls onCancel when cancel button is clicked', () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        open={true}
        title="Delete item"
        description="This cannot be undone."
        confirmLabel="Delete"
        onConfirm={() => {}}
        onCancel={onCancel}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `cd server-manager/frontend && npx vitest run src/test/ConfirmDialog.test.jsx`
Expected: Fails — "Failed to resolve import './components/ConfirmDialog.jsx'".

- [ ] **Step 3: Implement ConfirmDialog**

Create `server-manager/frontend/src/components/ConfirmDialog.jsx`:

```jsx
import { useEffect, useRef } from 'react'

const VARIANT_CLASSES = {
  danger: 'bg-immich-error hover:bg-immich-error/90 focus-visible:ring-immich-error',
  warning: 'bg-immich-warning hover:bg-immich-warning/90 text-immich-bg focus-visible:ring-immich-warning',
  primary: 'bg-immich-primary hover:bg-immich-primary-hover focus-visible:ring-immich-primary',
}

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  confirmVariant = 'primary',
  onConfirm,
  onCancel,
}) {
  const dialogRef = useRef(null)

  useEffect(() => {
    const dlg = dialogRef.current
    if (!dlg) return
    if (open && !dlg.open) {
      dlg.showModal()
    } else if (!open && dlg.open) {
      dlg.close()
    }
  }, [open])

  // When the native dialog closes via Escape or backdrop, propagate cancel
  useEffect(() => {
    const dlg = dialogRef.current
    if (!dlg) return
    const handleClose = () => {
      if (onCancel) onCancel()
    }
    dlg.addEventListener('close', handleClose)
    return () => dlg.removeEventListener('close', handleClose)
  }, [onCancel])

  const confirmClass =
    (confirmVariant === 'warning' ? '' : 'text-white ') +
    (VARIANT_CLASSES[confirmVariant] ?? VARIANT_CLASSES.primary)

  return (
    <dialog
      ref={dialogRef}
      className="bg-immich-surface border border-immich-border rounded-2xl p-6 max-w-md w-[calc(100%-2rem)] backdrop:bg-immich-bg/80 text-immich-text"
      aria-labelledby="confirm-dialog-title"
      aria-describedby="confirm-dialog-description"
    >
      <h2 id="confirm-dialog-title" className="text-lg font-semibold mb-2">{title}</h2>
      <p id="confirm-dialog-description" className="text-sm text-immich-muted mb-6">{description}</p>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm font-medium text-immich-text border border-immich-border rounded-lg hover:bg-immich-border/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary transition-colors min-h-[44px]"
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          className={`px-4 py-2 text-sm font-medium rounded-lg focus:outline-none focus-visible:ring-2 transition-colors min-h-[44px] ${confirmClass}`}
        >
          {confirmLabel}
        </button>
      </div>
    </dialog>
  )
}
```

- [ ] **Step 4: Run the test and verify it passes**

Run: `cd server-manager/frontend && npx vitest run src/test/ConfirmDialog.test.jsx`
Expected: All 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add server-manager/frontend/src/components/ConfirmDialog.jsx server-manager/frontend/src/test/ConfirmDialog.test.jsx
git commit -m "feat(server-manager): add ConfirmDialog component for destructive confirmations"
```

---

## Task 9: Migrate ServiceControls to hybrid confirm

**Files:**
- Modify: `server-manager/frontend/src/components/ServiceControls.jsx`
- Modify: `server-manager/frontend/src/test/ServiceControls.test.jsx` (update assertions that rely on window.confirm mock)

- [ ] **Step 1: Check existing tests for window.confirm/alert mocking**

Run: `grep -n 'window\\.\\(confirm\\|alert\\)' server-manager/frontend/src/test/ServiceControls.test.jsx`

If tests mock `window.confirm`, note which tests expect the prompt and plan to update them. The goal is to replace assertions that rely on the prompt being called.

- [ ] **Step 2: Rewrite ServiceControls component**

Replace the entire `src/components/ServiceControls.jsx` with:

```jsx
import { useState, useRef, useEffect } from 'react'
import { ArrowPathIcon, WrenchScrewdriverIcon } from '@heroicons/react/24/outline'
import ConfirmDialog from './ConfirmDialog.jsx'
import { useInlineConfirm } from '../hooks/useInlineConfirm.js'

const SERVICES = [
  'immich_server',
  'immich_machine_learning',
  'immich_postgres',
  'immich_redis',
  'server_manager',
  'photo_curator',
]

function ButtonContent({ state, armed }) {
  if (state === 'loading') return <ArrowPathIcon className="w-3.5 h-3.5 animate-spin" />
  if (state === 'ok') return <span>✓</span>
  if (state === 'error') return <span>✗</span>
  if (armed) return <span className="text-[10px] leading-tight">Confirm?</span>
  return <span>Restart</span>
}

export default function ServiceControls() {
  const [states, setStates] = useState({}) // { [service]: 'idle' | 'loading' | 'ok' | 'error' }
  const [restartAllOpen, setRestartAllOpen] = useState(false)
  const [bannerMessage, setBannerMessage] = useState(null) // { type: 'ok' | 'error', text: string }
  const { isArmed, trigger } = useInlineConfirm()
  const timeoutRef = useRef(null)
  const bannerTimeoutRef = useRef(null)

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      if (bannerTimeoutRef.current) clearTimeout(bannerTimeoutRef.current)
    }
  }, [])

  function showBanner(type, text) {
    setBannerMessage({ type, text })
    if (bannerTimeoutRef.current) clearTimeout(bannerTimeoutRef.current)
    bannerTimeoutRef.current = setTimeout(() => setBannerMessage(null), 4000)
  }

  async function performRestart(service) {
    setStates((s) => ({ ...s, [service]: 'loading' }))
    try {
      const r = await fetch(`/api/services/${encodeURIComponent(service)}/restart`, { method: 'POST' })
      setStates((s) => ({ ...s, [service]: r.ok ? 'ok' : 'error' }))
    } catch {
      setStates((s) => ({ ...s, [service]: 'error' }))
    }
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    timeoutRef.current = setTimeout(() => setStates((s) => ({ ...s, [service]: 'idle' })), 3000)
  }

  function handleRestartClick(service) {
    trigger(service, () => { performRestart(service) })
  }

  async function restartAll() {
    setRestartAllOpen(false)
    try {
      const r = await fetch('/api/services/restart-all', { method: 'POST' })
      const data = await r.json()
      if (r.ok) {
        showBanner('ok', 'All services restarted.')
      } else {
        showBanner('error', `Failed: ${data.detail ?? 'unknown error'}`)
      }
    } catch {
      showBanner('error', 'Failed to restart all services.')
    }
  }

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <h2 className="text-sm font-semibold text-immich-text mb-4 flex items-center gap-1.5">
        <WrenchScrewdriverIcon className="w-3.5 h-3.5" /> Service Controls
      </h2>
      <div className="space-y-2">
        {SERVICES.map((svc) => {
          const armed = isArmed(svc)
          const state = states[svc] ?? 'idle'
          return (
            <div key={svc} className="flex items-center justify-between py-1.5 border-b border-immich-border last:border-0">
              <span className="text-sm font-mono text-immich-text">{svc}</span>
              <button
                type="button"
                onClick={() => { handleRestartClick(svc) }}
                disabled={state === 'loading'}
                aria-label={armed ? `Confirm restart ${svc}` : `Restart ${svc}`}
                className={`px-3 py-1.5 disabled:opacity-50 text-white rounded-lg text-xs font-medium transition-colors duration-150 min-w-[80px] flex items-center justify-center focus:outline-none focus-visible:ring-2 ${
                  armed
                    ? 'bg-immich-warning text-immich-bg focus-visible:ring-immich-warning'
                    : 'bg-immich-primary hover:bg-immich-primary-hover focus-visible:ring-immich-primary'
                }`}
              >
                <ButtonContent state={state} armed={armed} />
              </button>
            </div>
          )
        })}
      </div>
      {bannerMessage && (
        <div
          role="status"
          className={`mt-3 px-3 py-2 rounded-lg text-sm border ${
            bannerMessage.type === 'ok'
              ? 'bg-immich-success-muted border-immich-success-border text-immich-success'
              : 'bg-immich-error-muted border-immich-error-border text-immich-error'
          }`}
        >
          {bannerMessage.text}
        </div>
      )}
      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={() => { setRestartAllOpen(true) }}
          className="px-4 py-2 bg-immich-warning hover:bg-immich-warning/90 text-immich-bg rounded-lg text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-warning"
        >
          Restart All Immich Services
        </button>
      </div>
      <ConfirmDialog
        open={restartAllOpen}
        title="Restart all Immich services?"
        description="This will briefly interrupt Immich for all users. Proceed?"
        confirmLabel="Restart All"
        confirmVariant="warning"
        onConfirm={restartAll}
        onCancel={() => setRestartAllOpen(false)}
      />
    </div>
  )
}
```

- [ ] **Step 3: Update ServiceControls tests to drop window.confirm assertions**

Read `src/test/ServiceControls.test.jsx` — for any test that sets `window.confirm = vi.fn(() => true)` or similar, replace the flow:
- For single-service restart: the test needs to click the restart button *twice* (arm, then fire) instead of relying on the confirm dialog.
- For "restart all": the test should click the button to open the dialog, then click "Restart All" inside the dialog (role button, name /restart all/i).

Remove any `window.confirm` / `window.alert` spies. Add the `HTMLDialogElement` polyfill in `beforeEach` (see Task 8's test file for the exact polyfill).

- [ ] **Step 4: Run ServiceControls tests**

Run: `cd server-manager/frontend && npx vitest run src/test/ServiceControls.test.jsx`
Expected: All tests pass. If they don't, iterate on the test file until they do.

- [ ] **Step 5: Commit**

```bash
git add server-manager/frontend/src/components/ServiceControls.jsx server-manager/frontend/src/test/ServiceControls.test.jsx
git commit -m "refactor(server-manager): replace window.confirm in ServiceControls with hybrid pattern"
```

---

## Task 10: Migrate BackupsCard to inline confirm

**Files:**
- Modify: `server-manager/frontend/src/components/BackupsCard.jsx`
- Modify: `server-manager/frontend/src/test/BackupsCard.test.jsx`

- [ ] **Step 1: Rewrite BackupsCard**

Replace `src/components/BackupsCard.jsx`:

```jsx
import { useState, useRef, useEffect } from 'react'
import { ArchiveBoxIcon, CheckCircleIcon, XCircleIcon } from '@heroicons/react/24/outline'
import { useBackups } from '../hooks/useDashboard.js'
import { useInlineConfirm } from '../hooks/useInlineConfirm.js'
import StatusBadge from './StatusBadge.jsx'

function BackupStatusBadge({ status }) {
  const ok = status === 'success'
  return (
    <StatusBadge variant={ok ? 'success' : 'error'}>
      {ok ? <CheckCircleIcon className="w-3 h-3" /> : <XCircleIcon className="w-3 h-3" />}
      {status}
    </StatusBadge>
  )
}

export default function BackupsCard() {
  const { data, isLoading } = useBackups()
  const history = (data?.history ?? []).slice(0, 3)
  const { isArmed, trigger } = useInlineConfirm()
  const [message, setMessage] = useState(null) // { type, text }
  const messageTimeoutRef = useRef(null)

  useEffect(() => {
    return () => { if (messageTimeoutRef.current) clearTimeout(messageTimeoutRef.current) }
  }, [])

  function showMessage(type, text) {
    setMessage({ type, text })
    if (messageTimeoutRef.current) clearTimeout(messageTimeoutRef.current)
    messageTimeoutRef.current = setTimeout(() => setMessage(null), 4000)
  }

  async function doBackup() {
    try {
      const r = await fetch('/api/backup/now', { method: 'POST' })
      if (r.ok) {
        showMessage('ok', 'Backup started!')
      } else {
        showMessage('error', 'Failed to start backup.')
      }
    } catch {
      showMessage('error', 'Failed to start backup.')
    }
  }

  const armed = isArmed('backup')

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 flex flex-col">
      <h2 className="text-sm font-semibold text-immich-text mb-4">Backups</h2>
      {isLoading ? (
        <p className="text-immich-muted text-sm">Loading…</p>
      ) : history.length === 0 ? (
        <p className="text-immich-muted text-sm mb-4">No backups yet</p>
      ) : (
        <div className="space-y-2 mb-4 flex-1">
          {history.map((b) => (
            <div key={b.timestamp} className="flex items-center justify-between">
              <span className="text-xs text-immich-muted">
                {new Date(b.timestamp).toLocaleDateString()}
              </span>
              <BackupStatusBadge status={b.status} />
            </div>
          ))}
        </div>
      )}
      <button
        type="button"
        onClick={() => { trigger('backup', doBackup) }}
        aria-label={armed ? 'Confirm start backup' : 'Start backup now'}
        className={`mt-auto w-full px-4 py-2 text-white rounded-lg text-sm font-medium transition-colors duration-150 flex items-center justify-center gap-2 focus:outline-none focus-visible:ring-2 ${
          armed
            ? 'bg-immich-warning text-immich-bg focus-visible:ring-immich-warning'
            : 'bg-immich-primary hover:bg-immich-primary-hover focus-visible:ring-immich-primary'
        }`}
      >
        <ArchiveBoxIcon className="w-4 h-4" />
        {armed ? 'Click again to confirm' : 'Backup Now'}
      </button>
      {message && (
        <p
          role="status"
          className={`mt-2 text-xs text-center ${
            message.type === 'ok' ? 'text-immich-success' : 'text-immich-error'
          }`}
        >
          {message.text}
        </p>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Update BackupsCard tests**

Read `src/test/BackupsCard.test.jsx` and update any test that mocks `window.confirm` or `window.alert`. The button click now requires two clicks (arm + fire). After the second click, assert the backup is triggered and the status message renders (role="status").

- [ ] **Step 3: Run BackupsCard tests**

Run: `cd server-manager/frontend && npx vitest run src/test/BackupsCard.test.jsx`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add server-manager/frontend/src/components/BackupsCard.jsx server-manager/frontend/src/test/BackupsCard.test.jsx
git commit -m "refactor(server-manager): replace window.confirm in BackupsCard with inline confirm"
```

---

## Task 11: Migrate UpdateManagement to ConfirmDialog + inline errors

**Files:**
- Modify: `server-manager/frontend/src/components/UpdateManagement.jsx`
- Modify: `server-manager/frontend/src/test/UpdateManagement.test.jsx`

- [ ] **Step 1: Rewrite UpdateManagement**

Replace `src/components/UpdateManagement.jsx`:

```jsx
import { useState, useEffect, useRef } from 'react'
import { ArrowPathIcon } from '@heroicons/react/24/outline'
import StatusBadge from './StatusBadge.jsx'
import ConfirmDialog from './ConfirmDialog.jsx'

export default function UpdateManagement() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [progressLines, setProgressLines] = useState([])
  const [updating, setUpdating] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [inlineMessage, setInlineMessage] = useState(null) // { type, text }
  const progressRef = useRef(null)
  const esRef = useRef(null)

  async function load() {
    setLoading(true)
    try {
      const r = await fetch('/api/updates/status')
      if (!r.ok) throw new Error(r.status)
      setData(await r.json())
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    return () => {
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (updating && progressRef.current) {
      progressRef.current.scrollTop = progressRef.current.scrollHeight
    }
  }, [progressLines, updating])

  async function applyUpdate() {
    setDialogOpen(false)
    setInlineMessage(null)
    try {
      const r = await fetch('/api/updates/apply', { method: 'POST' })
      const d = await r.json()
      if (d.status === 'up_to_date') {
        setInlineMessage({ type: 'info', text: 'Already up to date.' })
        return
      }
      if (!r.ok) {
        setInlineMessage({ type: 'error', text: `Failed: ${d.detail ?? 'unknown error'}` })
        return
      }
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
            setUpdating(false)
            load()
          }
        } catch {}
      }
      es.onerror = () => { es.close(); esRef.current = null }
    } catch (e) {
      setInlineMessage({ type: 'error', text: `Failed to start update: ${e.message}` })
    }
  }

  if (loading) {
    return (
      <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
        <h2 className="text-sm font-semibold text-immich-text mb-4 flex items-center gap-1.5">
          <ArrowPathIcon className="w-3.5 h-3.5" /> Updates
        </h2>
        <p className="text-immich-muted text-sm">Loading version info…</p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
        <h2 className="text-sm font-semibold text-immich-text mb-4">Updates</h2>
        <p className="text-immich-error text-sm">Failed to load update status.</p>
      </div>
    )
  }

  const upToDate = !data.update_available
  const dialogTitle = data.immich_reachable ? 'Apply Immich update?' : 'Update Immich while unreachable?'
  const dialogDescription = data.immich_reachable
    ? `This will update Immich to v${data.latest_version ?? '?'}. A snapshot will be taken first and rollback is automatic on failure. Continue?`
    : `Immich is currently unreachable. Apply the update to v${data.latest_version ?? '?'} anyway? A snapshot will be taken first.`

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <h2 className="text-sm font-semibold text-immich-text mb-4 flex items-center gap-1.5">
        <ArrowPathIcon className="w-3.5 h-3.5" /> Updates
      </h2>

      <div className="flex flex-wrap items-center gap-4 mb-4">
        <span className="text-sm text-immich-muted">
          Current: <span className="font-mono font-semibold text-immich-text">v{data.current_version ?? '?'}</span>
        </span>
        <span className="text-sm text-immich-muted">
          Latest: <span className="font-mono font-semibold text-immich-text">v{data.latest_version ?? '?'}</span>
        </span>
        {data.changelog_url?.startsWith('https://github.com/') && (
          <a href={data.changelog_url} target="_blank" rel="noopener noreferrer"
            className="text-xs text-immich-primary hover:underline">
            View Changelog ↗
          </a>
        )}
        {!data.immich_reachable ? (
          <>
            <StatusBadge variant="error">Immich unreachable</StatusBadge>
            <button
              type="button"
              onClick={() => setDialogOpen(true)}
              disabled={updating}
              className="px-4 py-1.5 bg-immich-warning hover:bg-immich-warning/90 disabled:opacity-50 text-immich-bg rounded-lg text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-warning"
            >
              Update anyway
            </button>
          </>
        ) : upToDate ? (
          <StatusBadge variant="success">Up to date ✓</StatusBadge>
        ) : (
          <>
            <StatusBadge variant="info">Update Available</StatusBadge>
            <button
              type="button"
              onClick={() => setDialogOpen(true)}
              disabled={updating}
              className="px-4 py-1.5 bg-immich-primary hover:bg-immich-primary-hover disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
            >
              Apply Update
            </button>
          </>
        )}
      </div>

      {inlineMessage && (
        <p
          role="status"
          className={`text-sm mb-4 ${
            inlineMessage.type === 'error'
              ? 'text-immich-error'
              : inlineMessage.type === 'info'
                ? 'text-immich-info'
                : 'text-immich-success'
          }`}
        >
          {inlineMessage.text}
        </p>
      )}

      {updating && progressLines.length > 0 && (
        <pre
          ref={progressRef}
          aria-live="polite"
          aria-atomic="false"
          className="bg-immich-terminal text-immich-log-info rounded-xl p-3 text-xs font-mono max-h-32 sm:max-h-40 md:max-h-52 overflow-y-auto whitespace-pre-wrap mb-4"
        >
          {progressLines.map((l, i) => (
            <span key={`${l.step}-${i}`} className={
              l.step === 'done' ? 'text-immich-success' :
              ['rolled_back', 'error'].includes(l.step) ? 'text-immich-error' : ''
            }>
              {l.message}{'\n'}
            </span>
          ))}
        </pre>
      )}

      {(data.history ?? []).length > 0 && (
        <div className="border-t border-immich-border pt-4">
          <h3 className="text-sm font-semibold text-immich-text mb-3">History</h3>
          <table className="w-full text-sm">
            <thead className="sr-only">
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Version</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.history.slice(0, 5).map((h, i) => (
                <tr key={h.timestamp ?? `row-${i}`} className="border-b border-immich-border last:border-0">
                  <td className="py-1.5 pr-4 text-xs text-immich-muted">
                    {h.timestamp ? new Date(h.timestamp).toLocaleDateString() : '—'}
                  </td>
                  <td className="py-1.5 pr-4 font-mono text-xs text-immich-text">
                    v{h.from_version ?? '?'} → v{h.to_version ?? '?'}
                  </td>
                  <td className={`py-1.5 text-xs font-medium ${h.status === 'success' ? 'text-immich-success' : 'text-immich-error'}`}>
                    {h.status === 'success' ? '✓ success' : `✗ ${h.status}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={dialogOpen}
        title={dialogTitle}
        description={dialogDescription}
        confirmLabel={data.immich_reachable ? 'Apply Update' : 'Update anyway'}
        confirmVariant={data.immich_reachable ? 'primary' : 'warning'}
        onConfirm={applyUpdate}
        onCancel={() => setDialogOpen(false)}
      />
    </div>
  )
}
```

- [ ] **Step 2: Update UpdateManagement tests**

Read `src/test/UpdateManagement.test.jsx`. Update tests to:
- Add the `HTMLDialogElement` polyfill in `beforeEach` (same pattern as Task 8 test)
- Remove any `window.confirm`/`window.alert` mocks
- For tests that expected the confirm prompt: click the primary button → click the "Apply Update" / "Update anyway" button inside the dialog
- For "already up to date" path: assert the inline message (role="status") appears instead of an alert

- [ ] **Step 3: Run UpdateManagement tests**

Run: `cd server-manager/frontend && npx vitest run src/test/UpdateManagement.test.jsx`
Expected: All tests pass.

- [ ] **Step 4: Validate zero window.alert/confirm in server-manager src**

Run: `grep -rnE 'window\.(alert|confirm)' server-manager/frontend/src`
Expected: Zero matches.

- [ ] **Step 5: Commit**

```bash
git add server-manager/frontend/src/components/UpdateManagement.jsx server-manager/frontend/src/test/UpdateManagement.test.jsx
git commit -m "refactor(server-manager): replace window.confirm in UpdateManagement with ConfirmDialog"
```

---

## Task 12: Add focus trap + Escape to Duplicates DetailPanel

**Files:**
- Modify: `photo-curator/frontend/src/pages/Duplicates.jsx` (DetailPanel function)

- [ ] **Step 1: Import and apply useFocusTrap in DetailPanel**

In `photo-curator/frontend/src/pages/Duplicates.jsx`, at the top of the file add:

```js
import { useFocusTrap } from '../hooks/useFocusTrap.js'
```

In the `DetailPanel` function (around line 256), add the hook and attach the ref to the container div:

```jsx
function DetailPanel({ group, onClose }) {
  const [keepId, setKeepId] = useState(group.recommended_keep_id)
  const queryClient = useQueryClient()
  const containerRef = useFocusTrap({ active: true, onEscape: onClose })

  // ... existing mutation hooks ...

  const assets = group.assets || []

  return (
    <div
      ref={containerRef}
      data-testid="detail-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="detail-panel-title"
      className="fixed inset-y-0 right-0 w-full max-w-2xl bg-immich-surface border-l border-immich-border shadow-xl z-50 overflow-y-auto"
    >
      <div className="flex items-center justify-between p-4 border-b border-immich-border">
        <h2 id="detail-panel-title" className="text-immich-text font-semibold">{assets.length} Similar Photos</h2>
        <button onClick={onClose} aria-label="Close" className="text-immich-muted hover:text-immich-text">
          <XMarkIcon className="w-5 h-5" />
        </button>
      </div>
      {/* ... rest unchanged ... */}
    </div>
  )
}
```

(Keep the rest of the function body unchanged — just add the ref, role, aria-modal, aria-labelledby, and id on the h2.)

- [ ] **Step 2: Run Duplicates tests**

Run: `cd photo-curator/frontend && npx vitest run src/test/Duplicates.test.jsx`
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add photo-curator/frontend/src/pages/Duplicates.jsx
git commit -m "fix(photo-curator): add focus trap and Escape-to-close to Duplicates detail panel"
```

---

## Task 13: IPManagement mobile card layout — TrustedTab

**Files:**
- Modify: `server-manager/frontend/src/components/IPManagement.jsx` (TrustedTab function)

- [ ] **Step 1: Wrap the existing table in `md:table hidden` and add a `md:hidden` card list**

In `TrustedTab`, wrap the existing `<table>` in a `<div className="hidden md:block overflow-x-auto">` instead of the current bare `overflow-x-auto` div. Then add a separate `<div className="md:hidden space-y-3">` that renders the same data as cards.

Replace the return block of `TrustedTab` (after the loading check, around line 37) with:

```jsx
return (
  <div>
    {/* Desktop table */}
    <div className="hidden md:block overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-immich-muted text-left border-b border-immich-border">
            <th scope="col" className="pb-2 pr-4">IP Address</th>
            <th scope="col" className="pb-2 pr-4">Label</th>
            <th scope="col" className="pb-2 pr-4">User</th>
            <th scope="col" className="pb-2 pr-4">Access</th>
            <th scope="col" className="pb-2 pr-4">Duration</th>
            <th scope="col" className="pb-2 pr-4">Expires</th>
            <th scope="col" className="pb-2 pr-4">Last Seen</th>
            <th scope="col" className="pb-2 pr-4">7d Conns</th>
            <th scope="col" className="pb-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {ips.map((ip) => (
            <tr key={ip.ip_address} className="border-b border-immich-border/50">
              <td className="py-2 pr-4 font-mono text-xs">{ip.ip_address}</td>
              <td className="py-2 pr-4">{ip.label || '\u2014'}</td>
              <td className="py-2 pr-4 text-xs">{ip.verified_by || '\u2014'}</td>
              <td className="py-2 pr-4">
                <span className={`text-xs px-2 py-0.5 rounded ${ip.access_level === 'admin' ? 'bg-immich-error-muted text-immich-error' : 'bg-immich-info-muted text-immich-info'}`}>
                  {ip.access_level}
                </span>
              </td>
              <td className="py-2 pr-4 text-xs">{ip.trust_duration}</td>
              <td className="py-2 pr-4 text-xs">{ip.expires_at ? new Date(ip.expires_at).toLocaleDateString() : 'Never'}</td>
              <td className="py-2 pr-4 text-xs">{timeAgo(ip.last_seen)}</td>
              <td className="py-2 pr-4 text-xs">{ip.connections_7d ?? 0}</td>
              <td className="py-2">
                <div className="flex gap-1">
                  <button type="button" onClick={() => { setEditingIp(ip.ip_address); setEditLabel(ip.label || ''); setEditDuration(ip.trust_duration || '24h') }}
                    className="min-h-[44px] px-3 text-xs text-immich-info hover:bg-immich-info-muted rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-info">Edit</button>
                  <button type="button" onClick={() => setRevokeIp(ip.ip_address)}
                    className="min-h-[44px] px-3 text-xs text-immich-error hover:bg-immich-error-muted rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error">Revoke</button>
                </div>
              </td>
            </tr>
          ))}
          {ips.length === 0 && (
            <tr><td colSpan={9} className="py-4 text-center text-immich-muted">No trusted IPs</td></tr>
          )}
        </tbody>
      </table>
    </div>

    {/* Mobile cards */}
    <div className="md:hidden space-y-3">
      {ips.length === 0 ? (
        <p className="py-4 text-center text-immich-muted text-sm">No trusted IPs</p>
      ) : (
        ips.map((ip) => (
          <div key={ip.ip_address} className="bg-immich-bg border border-immich-border rounded-xl p-4">
            <div className="flex items-center justify-between mb-2 gap-2">
              <span className="font-mono text-sm break-all">{ip.ip_address}</span>
              <span className={`text-xs px-2 py-0.5 rounded flex-shrink-0 ${ip.access_level === 'admin' ? 'bg-immich-error-muted text-immich-error' : 'bg-immich-info-muted text-immich-info'}`}>
                {ip.access_level}
              </span>
            </div>
            <dl className="space-y-1 text-xs mb-3">
              <div className="flex justify-between gap-2"><dt className="text-immich-muted">Label</dt><dd className="text-right">{ip.label || '—'}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-immich-muted">User</dt><dd className="text-right">{ip.verified_by || '—'}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-immich-muted">Duration</dt><dd className="text-right">{ip.trust_duration}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-immich-muted">Expires</dt><dd className="text-right">{ip.expires_at ? new Date(ip.expires_at).toLocaleDateString() : 'Never'}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-immich-muted">Last seen</dt><dd className="text-right">{timeAgo(ip.last_seen)}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-immich-muted">7d connections</dt><dd className="text-right">{ip.connections_7d ?? 0}</dd></div>
            </dl>
            <div className="flex gap-2">
              <button type="button" onClick={() => { setEditingIp(ip.ip_address); setEditLabel(ip.label || ''); setEditDuration(ip.trust_duration || '24h') }}
                className="flex-1 min-h-[44px] text-sm text-immich-info border border-immich-info/40 hover:bg-immich-info-muted rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-info">Edit</button>
              <button type="button" onClick={() => setRevokeIp(ip.ip_address)}
                className="flex-1 min-h-[44px] text-sm text-immich-error border border-immich-error/40 hover:bg-immich-error-muted rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error">Revoke</button>
            </div>
          </div>
        ))
      )}
    </div>

    {/* Edit panel (unchanged from Task 4) */}
    {editingIp && (
      <div className="mt-4 p-4 bg-immich-bg border border-immich-border rounded-lg">
        <h4 className="text-sm font-medium mb-2">Edit {editingIp}</h4>
        <div className="flex gap-3 items-end flex-wrap">
          <div>
            <label htmlFor="edit-label" className="text-xs text-immich-muted block mb-1">Label</label>
            <input id="edit-label" value={editLabel} onChange={(e) => setEditLabel(e.target.value)}
              className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary" />
          </div>
          <div>
            <label htmlFor="edit-duration" className="text-xs text-immich-muted block mb-1">Duration</label>
            <select id="edit-duration" value={editDuration} onChange={(e) => setEditDuration(e.target.value)}
              className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary">
              {DURATION_OPTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <button type="button" onClick={() => { updateMut.mutate({ ip: editingIp, label: editLabel, trust_duration: editDuration }); setEditingIp(null) }}
            className="px-3 py-2 bg-immich-primary hover:bg-immich-primary-hover text-white text-sm rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary min-h-[44px]">Save</button>
          <button type="button" onClick={() => setEditingIp(null)}
            className="px-3 py-2 text-immich-muted hover:text-immich-text text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary rounded min-h-[44px]">Cancel</button>
        </div>
      </div>
    )}

    {/* Revoke panel (unchanged from Task 4) */}
    {revokeIp && (
      <div className="mt-4 p-4 bg-immich-bg border border-immich-error-border/50 rounded-lg">
        <h4 className="text-sm font-medium text-immich-error mb-2">Revoke {revokeIp}</h4>
        <label htmlFor="revoke-reason" className="sr-only">Reason for revoking</label>
        <input id="revoke-reason" value={revokeReason} onChange={(e) => setRevokeReason(e.target.value)}
          placeholder="Reason (optional)"
          className="w-full px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text mb-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error" />
        <div className="flex gap-2">
          <button type="button" onClick={() => { revokeMut.mutate({ ip_address: revokeIp, reason: revokeReason }); setRevokeIp(null); setRevokeReason('') }}
            className="px-3 py-2 bg-immich-error text-white text-sm rounded hover:bg-immich-error/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error min-h-[44px]">Confirm Revoke</button>
          <button type="button" onClick={() => { setRevokeIp(null); setRevokeReason('') }}
            className="px-3 py-2 text-immich-muted hover:text-immich-text text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary rounded min-h-[44px]">Cancel</button>
        </div>
      </div>
    )}
  </div>
)
```

- [ ] **Step 2: Run IPManagement tests**

Run: `cd server-manager/frontend && npx vitest run src/test/IPManagement.test.jsx`
Expected: All tests pass. Tests may need updates if they query for specific element counts that now double (desktop + mobile). If so, update queries to scope to the visible variant using `within()` or use more specific selectors.

- [ ] **Step 3: Commit**

```bash
git add server-manager/frontend/src/components/IPManagement.jsx
git commit -m "feat(server-manager): add mobile card layout to IPManagement TrustedTab"
```

---

## Task 14: IPManagement mobile card layout — PendingTab + BlacklistedTab

**Files:**
- Modify: `server-manager/frontend/src/components/IPManagement.jsx` (PendingTab and BlacklistedTab functions)

- [ ] **Step 1: Apply the same dual-layout pattern to PendingTab**

Same structure as TrustedTab: wrap the existing table in `<div className="hidden md:block overflow-x-auto">` and add a `<div className="md:hidden space-y-3">` sibling.

Mobile card structure for PendingTab:

```jsx
<div className="md:hidden space-y-3">
  {ips.length === 0 ? (
    <p className="py-4 text-center text-immich-muted text-sm">No pending IPs</p>
  ) : (
    ips.map((ip) => (
      <div key={ip.ip_address} className="bg-immich-bg border border-immich-border rounded-xl p-4">
        <div className="mb-2">
          <span className="font-mono text-sm break-all">{ip.ip_address}</span>
        </div>
        <dl className="space-y-1 text-xs mb-3">
          <div className="flex justify-between gap-2"><dt className="text-immich-muted">Source</dt><dd className="text-right">{ip.source}</dd></div>
          <div className="flex justify-between gap-2"><dt className="text-immich-muted">First seen</dt><dd className="text-right">{timeAgo(ip.created_at)}</dd></div>
        </dl>
        <div className="flex gap-2">
          <button type="button" onClick={() => setApproveIp(ip.ip_address)}
            className="flex-1 min-h-[44px] text-sm text-immich-success border border-immich-success/40 hover:bg-immich-success-muted rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-success">Approve</button>
          <button type="button" onClick={() => revokeMut.mutate({ ip_address: ip.ip_address })}
            className="flex-1 min-h-[44px] text-sm text-immich-error border border-immich-error/40 hover:bg-immich-error-muted rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error">Blacklist</button>
        </div>
      </div>
    ))
  )}
</div>
```

Also update the existing table wrapper and the desktop action buttons to use `min-h-[44px] px-3` for consistency.

- [ ] **Step 2: Apply the same pattern to BlacklistedTab**

Same structure. Mobile cards:

```jsx
<div className="md:hidden space-y-3">
  {ips.length === 0 ? (
    <p className="py-4 text-center text-immich-muted text-sm">No blacklisted IPs</p>
  ) : (
    ips.map((ip) => (
      <div key={ip.ip_address} className="bg-immich-bg border border-immich-border rounded-xl p-4">
        <div className="mb-2">
          <span className="font-mono text-sm break-all">{ip.ip_address}</span>
        </div>
        <dl className="space-y-1 text-xs mb-3">
          <div className="flex justify-between gap-2"><dt className="text-immich-muted">Original user</dt><dd className="text-right">{ip.verified_by || 'unknown'}</dd></div>
          <div className="flex justify-between gap-2"><dt className="text-immich-muted">Blacklisted</dt><dd className="text-right">{ip.revoked_at ? new Date(ip.revoked_at).toLocaleDateString() : '—'}</dd></div>
          <div className="flex justify-between gap-2"><dt className="text-immich-muted">By</dt><dd className="text-right">{ip.revoked_by || '—'}</dd></div>
          {ip.revoke_reason && <div className="flex justify-between gap-2"><dt className="text-immich-muted">Reason</dt><dd className="text-right">{ip.revoke_reason}</dd></div>}
        </dl>
        <div className="flex gap-2">
          <button type="button" onClick={() => unblockMut.mutate({ ip_address: ip.ip_address })}
            className="flex-1 min-h-[44px] text-sm text-immich-warning border border-immich-warning/40 hover:bg-immich-warning-muted rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-warning">Unblock</button>
          <button type="button" onClick={() => deleteMut.mutate(ip.ip_address)}
            className="flex-1 min-h-[44px] text-sm text-immich-error border border-immich-error/40 hover:bg-immich-error-muted rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error">Delete</button>
        </div>
      </div>
    ))
  )}
</div>
```

- [ ] **Step 3: Run tests**

Run: `cd server-manager/frontend && npx vitest run src/test/IPManagement.test.jsx`
Expected: All tests pass (update tests if they assert specific element counts — scope queries using `within` on the visible table or card list).

- [ ] **Step 4: Commit**

```bash
git add server-manager/frontend/src/components/IPManagement.jsx
git commit -m "feat(server-manager): add mobile card layout to Pending and Blacklisted tabs"
```

---

## Task 15: IPManagement mobile card layout — ConnectionsTab + filter grid

**Files:**
- Modify: `server-manager/frontend/src/components/IPManagement.jsx` (ConnectionsTab function)

- [ ] **Step 1: Convert filter bar to grid layout**

In `ConnectionsTab`, replace the filter row (around line 252-273):

```jsx
<div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-4">
  <div>
    <label htmlFor="conn-filter-ip" className="sr-only">Filter by IP</label>
    <input id="conn-filter-ip" placeholder="Filter by IP" onChange={(e) => setFilters(f => ({ ...f, ip: e.target.value || undefined }))}
      className="w-full px-2 py-2 bg-immich-bg border border-immich-border rounded text-sm text-immich-text focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary" />
  </div>
  <div>
    <label htmlFor="conn-filter-service" className="sr-only">Filter by service</label>
    <select id="conn-filter-service" onChange={(e) => setFilters(f => ({ ...f, service: e.target.value || undefined }))}
      className="w-full px-2 py-2 bg-immich-bg border border-immich-border rounded text-sm text-immich-text focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary">
      <option value="">All services</option>
      <option value="server-manager">server-manager</option>
      <option value="photo-curator">photo-curator</option>
      <option value="ssh">ssh</option>
    </select>
  </div>
  <div>
    <label htmlFor="conn-filter-action" className="sr-only">Filter by action</label>
    <select id="conn-filter-action" onChange={(e) => setFilters(f => ({ ...f, action: e.target.value || undefined }))}
      className="w-full px-2 py-2 bg-immich-bg border border-immich-border rounded text-sm text-immich-text focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary">
      <option value="">All actions</option>
      <option value="allowed">allowed</option>
      <option value="challenged">challenged</option>
      <option value="blocked">blocked</option>
      <option value="alert_sent">alert_sent</option>
    </select>
  </div>
</div>
```

- [ ] **Step 2: Wrap table in md:block and add mobile card list**

After the filter block, replace the existing table wrapper with:

```jsx
{isLoading ? (
  <p className="text-immich-muted text-sm">Loading...</p>
) : (
  <>
    {/* Desktop table */}
    <div className="hidden md:block overflow-x-auto max-h-64 sm:max-h-80 md:max-h-96 overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-immich-surface">
          <tr className="text-immich-muted text-left border-b border-immich-border">
            <th scope="col" className="pb-2 pr-4">Timestamp</th>
            <th scope="col" className="pb-2 pr-4">IP Address</th>
            <th scope="col" className="pb-2 pr-4">Service</th>
            <th scope="col" className="pb-2 pr-4">Action</th>
            <th scope="col" className="pb-2">User</th>
          </tr>
        </thead>
        <tbody>
          {connections.map((c) => (
            <tr key={`${c.timestamp}-${c.ip_address}`} className="border-b border-immich-border/50">
              <td className="py-1.5 pr-4 text-xs">{timeAgo(c.timestamp)}</td>
              <td className="py-1.5 pr-4 font-mono text-xs">{c.ip_address}</td>
              <td className="py-1.5 pr-4 text-xs">{c.service}</td>
              <td className="py-1.5 pr-4">
                <span className={`text-xs ${
                  c.action === 'allowed' ? 'text-immich-success' :
                  c.action === 'blocked' ? 'text-immich-error' :
                  c.action === 'challenged' ? 'text-immich-warning' :
                  'text-immich-log-untagged'
                }`}>{c.action}</span>
              </td>
              <td className="py-1.5 text-xs">{c.user_id || '\u2014'}</td>
            </tr>
          ))}
          {connections.length === 0 && (
            <tr><td colSpan={5} className="py-4 text-center text-immich-muted">No connections logged</td></tr>
          )}
        </tbody>
      </table>
    </div>

    {/* Mobile cards */}
    <div className="md:hidden space-y-2 max-h-96 overflow-y-auto">
      {connections.length === 0 ? (
        <p className="py-4 text-center text-immich-muted text-sm">No connections logged</p>
      ) : (
        connections.map((c) => (
          <div key={`${c.timestamp}-${c.ip_address}`} className="bg-immich-bg border border-immich-border rounded-lg p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="font-mono text-xs break-all">{c.ip_address}</span>
              <span className={`text-xs ${
                c.action === 'allowed' ? 'text-immich-success' :
                c.action === 'blocked' ? 'text-immich-error' :
                c.action === 'challenged' ? 'text-immich-warning' :
                'text-immich-log-untagged'
              }`}>{c.action}</span>
            </div>
            <div className="flex justify-between text-xs text-immich-muted">
              <span>{c.service} {c.user_id ? `· ${c.user_id}` : ''}</span>
              <span>{timeAgo(c.timestamp)}</span>
            </div>
          </div>
        ))
      )}
    </div>
  </>
)}
```

Also update the key on the old desktop `<tr>` at line 289 from `key={i}` to `key={`${c.timestamp}-${c.ip_address}`}`.

- [ ] **Step 3: Run full server-manager test suite**

Run: `cd server-manager/frontend && npm run test`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add server-manager/frontend/src/components/IPManagement.jsx
git commit -m "feat(server-manager): add mobile card layout to Connections tab and fix filter grid"
```

---

## Task 16: LogViewer DOM cap

**Files:**
- Modify: `server-manager/frontend/src/components/LogViewer.jsx`

- [ ] **Step 1: Add MAX_LINES constant and cap logic**

Near the top of `src/components/LogViewer.jsx` (after the imports), add:

```js
const MAX_LINES = 2000
```

Replace the `flushPendingLines` callback (around line 88-94):

```js
const flushPendingLines = useCallback(() => {
  flushRafRef.current = null
  if (pendingLinesRef.current.length === 0) return
  const batch = pendingLinesRef.current
  pendingLinesRef.current = []
  setLogLines((prev) => {
    const next = [...prev, ...batch]
    return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next
  })
}, [])
```

Also cap in `loadSnapshot` — the snapshot from `/api/logs/${service}` could also be large:

```js
const loadSnapshot = useCallback(async (service) => {
  setLoading(true)
  try {
    const r = await fetch(`/api/logs/${encodeURIComponent(service)}`)
    if (!r.ok) throw new Error(r.status)
    const data = await r.json()
    const lines = data.lines ?? []
    setLogLines(lines.length > MAX_LINES ? lines.slice(-MAX_LINES) : lines)
  } catch (e) {
    setLogLines([{ level: 'error', text: `Error loading logs: ${e.message}` }])
  } finally {
    setLoading(false)
  }
}, [])
```

- [ ] **Step 2: Add a "capped" hint to the header when at the cap**

In the Controls block (around line 193-216), after the "Live" label, add:

```jsx
{logLines.length >= MAX_LINES && (
  <span className="text-xs text-immich-muted">Showing last {MAX_LINES.toLocaleString()} lines</span>
)}
```

- [ ] **Step 3: Run LogViewer tests**

Run: `cd server-manager/frontend && npx vitest run src/test/LogViewer.test.jsx`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add server-manager/frontend/src/components/LogViewer.jsx
git commit -m "perf(server-manager): cap LogViewer to 2000 lines to prevent unbounded DOM growth"
```

---

## Task 17: Add `<main>` landmark and fix heading hierarchy

**Files:**
- Modify: `server-manager/frontend/src/App.jsx`
- Modify: `server-manager/frontend/src/components/SystemStatusCard.jsx`
- Modify: `server-manager/frontend/src/components/ImmichStatusCard.jsx`
- Modify: `server-manager/frontend/src/components/DiskHealthCard.jsx`
- Modify: `server-manager/frontend/src/components/BackupsCard.jsx` (already promoted in Task 10)
- Modify: `server-manager/frontend/src/components/AlertsPanel.jsx`
- Modify: `server-manager/frontend/src/components/LogViewer.jsx`
- Modify: `server-manager/frontend/src/components/DiscordConfig.jsx`
- Modify: `server-manager/frontend/src/components/IPManagement.jsx`

**Note:** `ServiceControls` and `UpdateManagement` were already promoted in Tasks 9 and 11. BackupsCard in Task 10.

- [ ] **Step 1: Wrap Server Manager dashboard in `<main>` landmark**

In `src/App.jsx`, replace lines 47-67 with:

```jsx
return (
  <ErrorBoundary>
    <div className="min-h-screen bg-immich-bg text-immich-text">
      <main id="main" className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <Header />
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5 mb-6">
          <SystemStatusCard />
          <ImmichStatusCard />
          <DiskHealthCard />
          <BackupsCard />
        </div>
        <AlertsPanel />
        <LogViewer />
        <ServiceControls />
        <DiscordConfig />
        <UpdateManagement />
        <IPManagement />
      </main>
    </div>
  </ErrorBoundary>
)
```

- [ ] **Step 2: Promote card headings to `text-sm font-semibold text-immich-text`**

For each of the following files, find the `<h2>` tag and replace:
- `text-xs font-semibold uppercase tracking-wider text-immich-muted` → `text-sm font-semibold text-immich-text`

Files to update:
- `SystemStatusCard.jsx` line 32
- `ImmichStatusCard.jsx` line 21
- `DiskHealthCard.jsx` line 22
- `AlertsPanel.jsx` line 18
- `LogViewer.jsx` line 170
- `DiscordConfig.jsx` lines 101, 111, 122

For `IPManagement.jsx` around line 323:
Replace:
```jsx
<h2 className="text-lg font-semibold">IP Security</h2>
```
with:
```jsx
<h2 className="text-sm font-semibold text-immich-text">IP Security</h2>
```

- [ ] **Step 3: Run full test suite**

Run: `cd server-manager/frontend && npm run test`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add server-manager/frontend/src/App.jsx \
        server-manager/frontend/src/components/SystemStatusCard.jsx \
        server-manager/frontend/src/components/ImmichStatusCard.jsx \
        server-manager/frontend/src/components/DiskHealthCard.jsx \
        server-manager/frontend/src/components/AlertsPanel.jsx \
        server-manager/frontend/src/components/LogViewer.jsx \
        server-manager/frontend/src/components/DiscordConfig.jsx \
        server-manager/frontend/src/components/IPManagement.jsx
git commit -m "a11y(server-manager): add main landmark and standardize heading hierarchy"
```

---

## Task 18: Add `aria-live` regions to dynamic content

**Files:**
- Modify: `server-manager/frontend/src/components/LogViewer.jsx`
- Modify: `photo-curator/frontend/src/pages/Import.jsx`
- Modify: `photo-curator/frontend/src/pages/Duplicates.jsx`

- [ ] **Step 1: LogViewer — add aria-live to output during live mode**

In `LogViewer.jsx`, update the output div (around line 253):

```jsx
<div
  ref={outputRef}
  role="log"
  aria-label="Service log output"
  aria-live={isLive ? 'polite' : 'off'}
  aria-atomic="false"
  className="bg-immich-terminal rounded-xl p-3 text-xs font-mono h-64 sm:h-80 md:h-96 lg:h-[32rem] overflow-y-auto"
>
```

- [ ] **Step 2: Import.jsx — add aria-live to job status region**

In `photo-curator/frontend/src/pages/Import.jsx`, wrap the job status/progress block in step 2 (around line 343):

```jsx
<div aria-live="polite" aria-atomic="false" className="p-4 bg-immich-surface rounded-xl border border-immich-border space-y-4">
  {job && (
    <>
      {/* ... existing progress, stats, error banner ... */}
    </>
  )}
```

(Add `aria-live="polite" aria-atomic="false"` to the existing className div; keep the children unchanged.)

- [ ] **Step 3: Duplicates.jsx — add aria-live to scan progress**

In `photo-curator/frontend/src/pages/Duplicates.jsx`, in the `ScanPanel` running state block (around line 72), update the outer div:

```jsx
return (
  <div aria-live="polite" aria-atomic="false" className="bg-immich-surface border border-immich-border rounded-xl p-5">
    <div className="flex items-center justify-between mb-3">
      {/* ... rest unchanged ... */}
```

- [ ] **Step 4: Run both test suites**

Run: `cd server-manager/frontend && npm run test`
Run: `cd photo-curator/frontend && npm run test`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add server-manager/frontend/src/components/LogViewer.jsx \
        photo-curator/frontend/src/pages/Import.jsx \
        photo-curator/frontend/src/pages/Duplicates.jsx
git commit -m "a11y: add aria-live regions to dynamic status/progress updates"
```

---

## Task 19: Import mobile fallback for webkitdirectory

**Files:**
- Modify: `photo-curator/frontend/src/pages/Import.jsx`

- [ ] **Step 1: Add webkitdirectory support detection and fallback UI**

At the top of `Import.jsx` (after imports), add:

```js
// Detect once at module load — this never changes for a given browser
const SUPPORTS_WEBKITDIRECTORY = typeof document !== 'undefined' &&
  'webkitdirectory' in document.createElement('input')
```

In the `step === 1 && source !== 'server_path'` block (around line 169), before the drop zone, add a warning when unsupported:

```jsx
{!SUPPORTS_WEBKITDIRECTORY && (
  <div className="p-3 bg-immich-warning-muted border border-immich-warning-border rounded-lg text-immich-warning text-sm">
    Folder uploads aren't supported on this browser. Use a desktop browser (Chrome, Edge, or Safari 14+), or ask an admin to use the Server Path option.
  </div>
)}
```

Then disable the drop zone and input when unsupported:

```jsx
<div
  data-testid="file-drop-zone"
  onDragOver={(e) => { if (SUPPORTS_WEBKITDIRECTORY) { e.preventDefault(); setDragOver(true) } }}
  onDragLeave={() => setDragOver(false)}
  onDrop={(e) => SUPPORTS_WEBKITDIRECTORY && handleDrop(e)}
  onClick={() => SUPPORTS_WEBKITDIRECTORY && fileInputRef.current?.click()}
  aria-disabled={!SUPPORTS_WEBKITDIRECTORY}
  className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
    !SUPPORTS_WEBKITDIRECTORY
      ? 'border-immich-border opacity-50 cursor-not-allowed'
      : dragOver
        ? 'border-immich-primary bg-immich-primary/5 cursor-pointer'
        : 'border-immich-border hover:border-immich-primary cursor-pointer'
  }`}
>
  <p className="text-immich-muted mb-1">
    {SUPPORTS_WEBKITDIRECTORY ? 'Click to select a folder, or drag and drop' : 'Folder selection unavailable on this browser'}
  </p>
  <p className="text-immich-muted text-xs">Supports JPG, PNG, HEIC, MP4, MOV and more</p>
  <input
    ref={fileInputRef}
    data-testid="file-input"
    type="file"
    className="hidden"
    webkitdirectory=""
    multiple
    disabled={!SUPPORTS_WEBKITDIRECTORY}
    onChange={handleFileChange}
  />
</div>
```

Also disable the Start Import button if unsupported:

```jsx
<button
  data-testid="btn-start-import"
  disabled={!SUPPORTS_WEBKITDIRECTORY || !files || files.length === 0 || uploadMutation.isPending}
  onClick={() => uploadMutation.mutate()}
  className="px-4 py-2 bg-immich-primary hover:bg-immich-primary-hover text-white font-medium rounded-lg disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-immich-primary"
>
  Start Import
</button>
```

- [ ] **Step 2: Run Import tests**

Run: `cd photo-curator/frontend && npx vitest run src/test/Import.test.jsx`
Expected: All tests pass (jsdom has `webkitdirectory` support so tests should still reach the happy path).

- [ ] **Step 3: Commit**

```bash
git add photo-curator/frontend/src/pages/Import.jsx
git commit -m "fix(photo-curator): gracefully handle browsers without webkitdirectory support"
```

---

## Task 20: Focus-visible consistency + index-based key fixes

**Files:**
- Modify: `photo-curator/frontend/src/pages/Preferences.jsx`
- Modify: `photo-curator/frontend/src/pages/Import.jsx`

- [ ] **Step 1: Preferences — add focus-visible ring to number input**

In `photo-curator/frontend/src/pages/Preferences.jsx` line 37:

```jsx
<input
  type="number"
  min={1}
  max={200}
  value={monthlyTarget}
  onChange={e => setMonthlyTarget(Number(e.target.value))}
  className="mt-1 w-full px-3 py-2 bg-immich-bg border border-immich-border rounded-lg text-immich-text text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary focus:border-immich-primary"
/>
```

- [ ] **Step 2: Import — add focus-visible rings to server path and source type inputs**

In `photo-curator/frontend/src/pages/Import.jsx` line 274 (server path input):

```jsx
<input
  data-testid="server-path-input"
  type="text"
  placeholder="/opt/photos-import"
  value={serverPath}
  onChange={(e) => setServerPath(e.target.value)}
  className="w-full px-3 py-2 bg-immich-bg border border-immich-border rounded-lg text-immich-text text-sm font-mono placeholder:text-immich-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary focus:border-immich-primary"
/>
```

Line 284 (source type select):

```jsx
<select
  data-testid="server-path-source-type"
  value={serverPathSourceType}
  onChange={(e) => setServerPathSourceType(e.target.value)}
  className="w-full px-3 py-2 bg-immich-bg border border-immich-border rounded-lg text-immich-text text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary focus:border-immich-primary"
>
```

- [ ] **Step 3: Run photo-curator test suite**

Run: `cd photo-curator/frontend && npm run test`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add photo-curator/frontend/src/pages/Preferences.jsx photo-curator/frontend/src/pages/Import.jsx
git commit -m "a11y(photo-curator): add focus-visible rings to Preferences and Import inputs"
```

---

## Task 21: Photo Curator ErrorBoundary

**Files:**
- Create: `photo-curator/frontend/src/components/ErrorBoundary.jsx`
- Modify: `photo-curator/frontend/src/App.jsx`

- [ ] **Step 1: Create ErrorBoundary component**

Create `photo-curator/frontend/src/components/ErrorBoundary.jsx`:

```jsx
import React from 'react'

export default class ErrorBoundary extends React.Component {
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
          <div className="bg-immich-surface border border-immich-error-border rounded-2xl p-6 max-w-lg w-full">
            <h2 className="text-immich-error font-semibold mb-2">Something went wrong</h2>
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
```

- [ ] **Step 2: Wrap AppInner with ErrorBoundary**

In `photo-curator/frontend/src/App.jsx`, add import:

```js
import ErrorBoundary from './components/ErrorBoundary'
```

Replace the default export:

```jsx
export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AppInner />
      </BrowserRouter>
    </ErrorBoundary>
  )
}
```

- [ ] **Step 3: Run tests**

Run: `cd photo-curator/frontend && npm run test`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add photo-curator/frontend/src/components/ErrorBoundary.jsx photo-curator/frontend/src/App.jsx
git commit -m "feat(photo-curator): add ErrorBoundary to prevent white-screen crashes"
```

---

## Task 22: Create Button component

**Files:**
- Create: `server-manager/frontend/src/components/Button.jsx`
- Create: `server-manager/frontend/src/test/Button.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `server-manager/frontend/src/test/Button.test.jsx`:

```jsx
import { describe, it, expect, vi } from 'vitest'
import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import Button from '../components/Button.jsx'

describe('Button', () => {
  it('renders children', () => {
    render(<Button>Click me</Button>)
    expect(screen.getByRole('button', { name: 'Click me' })).toBeInTheDocument()
  })

  it('applies primary variant by default', () => {
    render(<Button>Go</Button>)
    const btn = screen.getByRole('button')
    expect(btn.className).toMatch(/bg-immich-primary/)
  })

  it('applies danger variant', () => {
    render(<Button variant="danger">Delete</Button>)
    const btn = screen.getByRole('button')
    expect(btn.className).toMatch(/bg-immich-error/)
  })

  it('applies size sm', () => {
    render(<Button size="sm">Small</Button>)
    const btn = screen.getByRole('button')
    expect(btn.className).toMatch(/min-h-\[36px\]/)
  })

  it('applies size md by default (min 44px)', () => {
    render(<Button>Medium</Button>)
    const btn = screen.getByRole('button')
    expect(btn.className).toMatch(/min-h-\[44px\]/)
  })

  it('forwards onClick', () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Click</Button>)
    fireEvent.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('respects disabled prop', () => {
    render(<Button disabled>No</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })
})
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `cd server-manager/frontend && npx vitest run src/test/Button.test.jsx`
Expected: Fails — "Failed to resolve import".

- [ ] **Step 3: Implement Button**

Create `server-manager/frontend/src/components/Button.jsx`:

```jsx
const VARIANT_CLASSES = {
  primary: 'bg-immich-primary hover:bg-immich-primary-hover text-white focus-visible:ring-immich-primary',
  secondary: 'bg-immich-surface border border-immich-border text-immich-text hover:bg-immich-border/50 focus-visible:ring-immich-primary',
  danger: 'bg-immich-error hover:bg-immich-error/90 text-white focus-visible:ring-immich-error',
  warning: 'bg-immich-warning hover:bg-immich-warning/90 text-immich-bg focus-visible:ring-immich-warning',
  ghost: 'text-immich-muted hover:text-immich-text hover:bg-immich-border/50 focus-visible:ring-immich-primary',
}

const SIZE_CLASSES = {
  sm: 'min-h-[36px] px-3 py-1.5 text-xs',
  md: 'min-h-[44px] px-4 py-2 text-sm',
}

export default function Button({
  variant = 'primary',
  size = 'md',
  type = 'button',
  disabled = false,
  className = '',
  children,
  ...rest
}) {
  const variantClass = VARIANT_CLASSES[variant] ?? VARIANT_CLASSES.primary
  const sizeClass = SIZE_CLASSES[size] ?? SIZE_CLASSES.md
  return (
    <button
      type={type}
      disabled={disabled}
      className={`${sizeClass} ${variantClass} font-medium rounded-lg transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
```

- [ ] **Step 4: Run the test and verify it passes**

Run: `cd server-manager/frontend && npx vitest run src/test/Button.test.jsx`
Expected: All 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add server-manager/frontend/src/components/Button.jsx server-manager/frontend/src/test/Button.test.jsx
git commit -m "feat(server-manager): add reusable Button component with semantic variants"
```

---

## Task 23: Create Skeleton component and add to loading states

**Files:**
- Create: `server-manager/frontend/src/components/Skeleton.jsx`
- Create: `photo-curator/frontend/src/components/Skeleton.jsx`
- Modify: `server-manager/frontend/src/components/SystemStatusCard.jsx`
- Modify: `server-manager/frontend/src/components/ImmichStatusCard.jsx`
- Modify: `server-manager/frontend/src/components/DiskHealthCard.jsx`
- Modify: `server-manager/frontend/src/components/BackupsCard.jsx`
- Modify: `photo-curator/frontend/src/pages/Analytics.jsx`

- [ ] **Step 1: Create Skeleton primitive in server-manager**

Create `server-manager/frontend/src/components/Skeleton.jsx`:

```jsx
export default function Skeleton({ className = '', width, height }) {
  const style = {}
  if (width) style.width = width
  if (height) style.height = height
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse bg-immich-border/40 rounded-lg ${className}`}
      style={style}
    />
  )
}
```

Create the same file in `photo-curator/frontend/src/components/Skeleton.jsx` with identical content.

- [ ] **Step 2: SystemStatusCard — replace "Loading…" with skeletons**

In `src/components/SystemStatusCard.jsx`:

```jsx
import Skeleton from './Skeleton.jsx'

// ...

export default function SystemStatusCard() {
  const { data, isLoading } = useStatus()

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5">
      <h2 className="text-sm font-semibold text-immich-text mb-4">System</h2>
      {isLoading || !data ? (
        <div className="space-y-4">
          {[0, 1, 2].map((i) => (
            <div key={i}>
              <Skeleton className="mb-1" height="0.75rem" width="40%" />
              <Skeleton height="0.375rem" width="100%" />
            </div>
          ))}
        </div>
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

- [ ] **Step 3: ImmichStatusCard — replace "Loading…" with skeletons**

```jsx
import Skeleton from './Skeleton.jsx'

// in the render block:
{isLoading || !data ? (
  <div className="space-y-3">
    <div className="flex items-center justify-between">
      <Skeleton height="0.75rem" width="40%" />
      <Skeleton height="1.25rem" width="5rem" />
    </div>
    <div className="flex items-center justify-between">
      <Skeleton height="0.75rem" width="35%" />
      <Skeleton height="0.875rem" width="4rem" />
    </div>
  </div>
) : (
  // existing block unchanged
)}
```

- [ ] **Step 4: DiskHealthCard — replace "Loading…" with skeletons**

```jsx
import Skeleton from './Skeleton.jsx'

// in the render block:
{isLoading ? (
  <div className="space-y-3">
    {[0, 1].map((i) => (
      <div key={i} className="flex items-center justify-between">
        <Skeleton height="0.75rem" width="45%" />
        <Skeleton height="1.25rem" width="3.5rem" />
      </div>
    ))}
  </div>
) : disks.length === 0 ? (
  // existing empty state unchanged
) : (
  // existing block unchanged
)}
```

- [ ] **Step 5: BackupsCard — replace "Loading…" with skeletons**

```jsx
import Skeleton from './Skeleton.jsx'

// replace loading state:
{isLoading ? (
  <div className="space-y-2 mb-4 flex-1">
    {[0, 1, 2].map((i) => (
      <div key={i} className="flex items-center justify-between">
        <Skeleton height="0.75rem" width="40%" />
        <Skeleton height="1.25rem" width="4rem" />
      </div>
    ))}
  </div>
) : // existing branches unchanged
```

- [ ] **Step 6: Analytics — replace "Loading…" with skeleton stat cards**

In `photo-curator/frontend/src/pages/Analytics.jsx`:

```jsx
import Skeleton from '../components/Skeleton'

// ...

{isLoading ? (
  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
    {[0, 1, 2, 3].map((i) => (
      <div key={i} className="bg-immich-surface border border-immich-border rounded-xl p-5">
        <Skeleton height="0.875rem" width="50%" className="mb-2" />
        <Skeleton height="1.875rem" width="70%" />
      </div>
    ))}
  </div>
) : (
  // existing render unchanged
)}
```

- [ ] **Step 7: Run both test suites**

Run: `cd server-manager/frontend && npm run test`
Run: `cd photo-curator/frontend && npm run test`
Expected: All tests pass. Tests that asserted the literal text "Loading…" may need updates — if so, use `queryByText('Loading…')` to be absent while allowing skeleton divs.

- [ ] **Step 8: Commit**

```bash
git add server-manager/frontend/src/components/Skeleton.jsx \
        photo-curator/frontend/src/components/Skeleton.jsx \
        server-manager/frontend/src/components/SystemStatusCard.jsx \
        server-manager/frontend/src/components/ImmichStatusCard.jsx \
        server-manager/frontend/src/components/DiskHealthCard.jsx \
        server-manager/frontend/src/components/BackupsCard.jsx \
        photo-curator/frontend/src/pages/Analytics.jsx
git commit -m "feat(frontend): add Skeleton component and replace Loading… text in primary cards"
```

---

## Task 24: Photo Curator logo SVG

**Files:**
- Create: `photo-curator/frontend/src/components/ImmichLogoIcon.jsx`
- Modify: `photo-curator/frontend/src/components/Sidebar.jsx`
- Modify: `photo-curator/frontend/src/pages/Login.jsx`

- [ ] **Step 1: Create the logo component**

Create `photo-curator/frontend/src/components/ImmichLogoIcon.jsx`:

```jsx
export default function ImmichLogoIcon({ className = 'w-7 h-7' }) {
  return (
    <svg viewBox="0 0 32 32" className={className} fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#4250af" />
      <path d="M8 22L16 10L24 22" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="16" cy="10" r="2" fill="white" />
    </svg>
  )
}
```

- [ ] **Step 2: Use in Sidebar**

In `photo-curator/frontend/src/components/Sidebar.jsx`, add import:

```js
import ImmichLogoIcon from './ImmichLogoIcon'
```

Replace the logo block (lines 24-28):

```jsx
<div className="flex items-center gap-3 px-4 py-5 border-b border-immich-border">
  <ImmichLogoIcon className="w-8 h-8" />
  <span className="text-immich-text font-semibold text-sm">Photo Curator</span>
</div>
```

- [ ] **Step 3: Use in Login**

In `photo-curator/frontend/src/pages/Login.jsx`, add import and replace the placeholder circle:

```jsx
import ImmichLogoIcon from '../components/ImmichLogoIcon'

export default function Login({ loginUrl }) {
  return (
    <div className="min-h-screen bg-immich-bg flex items-center justify-center">
      <div className="bg-immich-surface border border-immich-border rounded-xl p-8 max-w-sm w-full text-center">
        <div className="flex justify-center mb-4">
          <ImmichLogoIcon className="w-16 h-16" />
        </div>
        <h1 className="text-immich-text text-xl font-semibold mb-2">Photo Curator</h1>
        {/* rest unchanged */}
```

- [ ] **Step 4: Run photo-curator tests**

Run: `cd photo-curator/frontend && npm run test`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add photo-curator/frontend/src/components/ImmichLogoIcon.jsx \
        photo-curator/frontend/src/components/Sidebar.jsx \
        photo-curator/frontend/src/pages/Login.jsx
git commit -m "feat(photo-curator): replace placeholder logo with Immich SVG icon"
```

---

## Task 25: BottomTabBar overflow + P3 polish

**Files:**
- Modify: `photo-curator/frontend/src/components/BottomTabBar.jsx`
- Modify: `photo-curator/frontend/src/pages/Events.jsx`

- [ ] **Step 1: BottomTabBar — hide labels on very narrow screens**

In `photo-curator/frontend/src/components/BottomTabBar.jsx`, update the NavLink content:

```jsx
<NavLink
  key={to}
  to={to}
  end={to === '/'}
  aria-label={label}
  className={({ isActive }) =>
    `flex-1 flex flex-col items-center py-2 gap-0.5 text-xs transition-colors ${
      isActive ? 'text-immich-primary' : 'text-immich-muted'
    }`
  }
>
  <Icon className="w-5 h-5" />
  <span className="hidden min-[360px]:inline">{label}</span>
</NavLink>
```

- [ ] **Step 2: Events — improve alt text**

In `photo-curator/frontend/src/pages/Events.jsx` line 38:

```jsx
{(event.thumbnails ?? []).slice(0, 3).map((url, i) => (
  <img
    key={i}
    src={url}
    alt={`${event.title ?? 'Event'} — preview ${i + 1}`}
    className="flex-1 object-cover"
    loading="lazy"
  />
))}
```

- [ ] **Step 3: Run photo-curator tests**

Run: `cd photo-curator/frontend && npm run test`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add photo-curator/frontend/src/components/BottomTabBar.jsx photo-curator/frontend/src/pages/Events.jsx
git commit -m "polish(photo-curator): BottomTabBar label overflow and Events alt text"
```

---

## Task 26: Create DEFERRED.md and run final validation

**Files:**
- Create: `docs/DEFERRED.md`

- [ ] **Step 1: Create the deferred work tracker**

Create `docs/DEFERRED.md`:

```markdown
# Deferred Work

Items intentionally scoped out of prior fix passes. Revisit when the context warrants.

## From 2026-04-08 audit fixes

- **Analytics page redesign** — Current page is a placeholder with 4-stat-card grid ("hero metrics" anti-pattern). When real charts land, redesign the layout to avoid the hero-metric template. See `photo-curator/frontend/src/pages/Analytics.jsx`.

- **Cross-app border-radius unification** — Server Manager uses `rounded-2xl` on cards; Photo Curator uses `rounded-xl`. Unifying requires a product-level decision on whether both apps should feel like one product.

- **Shared component library infrastructure** — Only `shared/tailwind-tokens.js` is currently shared. `ErrorBoundary`, `Skeleton`, and `ImmichLogoIcon` are copy-pasted between apps. Revisit when a 3rd or 4th component needs sharing.

- **LogViewer useEffect dependency refactor** — `src/components/LogViewer.jsx` has two `eslint-disable-next-line react-hooks/exhaustive-deps` comments. Working code, but the suppression hides a potential stale-closure footgun. Refactor into a reducer or properly-declared deps when next touching the file.

- **Dashboard card grid variety** — Server Manager's 4 identical status cards (System/Immich/Disk/Backups) were flagged as a minor "card grid" anti-pattern tell. Fixing requires a visual redesign, not a fix.

- **BottomTabBar overflow pattern** — Currently hides labels under 360px. If 7+ nav items are added, consider a "More" overflow menu.
```

- [ ] **Step 2: Validate zero hard-coded colors in server-manager**

Run:
```bash
grep -rnE 'text-(blue|red|green|amber|yellow|orange|gray)-[0-9]|bg-(blue|red|green|amber|yellow|orange|gray)-[0-9]|ring-(blue|red|green|amber|yellow|orange|gray)-[0-9]|border-(blue|red|green|amber|yellow|orange|gray)-[0-9]|bg-\[#' server-manager/frontend/src
```
Expected: Zero matches.

- [ ] **Step 3: Validate zero window.alert/confirm in server-manager**

Run:
```bash
grep -rnE 'window\.(alert|confirm)' server-manager/frontend/src
```
Expected: Zero matches.

- [ ] **Step 4: Build both frontends**

Run: `cd server-manager/frontend && npm run build`
Expected: Build succeeds.

Run: `cd photo-curator/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 5: Run all tests**

Run: `cd server-manager/frontend && npm run test`
Expected: All tests pass.

Run: `cd photo-curator/frontend && npm run test`
Expected: All tests pass.

- [ ] **Step 6: Commit DEFERRED.md**

```bash
git add docs/DEFERRED.md
git commit -m "docs: track deferred work from audit fixes pass"
```

- [ ] **Step 7: Report completion**

Announce: "All 26 tasks complete. Both frontends build. All tests pass. Validation greps return zero matches. Ready for an audit re-run to confirm the score improvement."

---

## Success Criteria Recap

- [ ] All 26 tasks complete
- [ ] `grep -rE 'text-(blue|red|green|amber|yellow|orange|gray)-[0-9]|bg-(blue|red|green|amber|yellow|orange|gray)-[0-9]|bg-\[#' server-manager/frontend/src` returns zero matches
- [ ] `grep -rE 'window\.(alert|confirm)' server-manager/frontend/src` returns zero matches
- [ ] `cd server-manager/frontend && npm run build` succeeds
- [ ] `cd photo-curator/frontend && npm run build` succeeds
- [ ] `cd server-manager/frontend && npm run test` passes
- [ ] `cd photo-curator/frontend && npm run test` passes
- [ ] `docs/DEFERRED.md` exists
- [ ] Re-run `/impeccable:audit` shows score ≥18/20
