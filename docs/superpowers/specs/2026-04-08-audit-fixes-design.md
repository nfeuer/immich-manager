# Audit Fixes — Server Manager & Photo Curator

**Date:** 2026-04-08
**Scope:** Fix all 23 issues (8 P1, 10 P2, 5 P3) identified in the 2026-04-07 `/impeccable:audit` run. Baseline audit health score: 12/20 (Acceptable). Target: 18+/20 (Excellent).

## Goals

1. Bring Server Manager to the same token-discipline level as Photo Curator (currently the biggest score gap).
2. Make every interactive surface usable on mobile — especially the IP Management tables.
3. Replace jarring `window.alert/confirm` with in-app confirmation UX.
4. Close accessibility gaps: landmarks, heading hierarchy, `aria-live`, focus indicators.
5. Cap LogViewer DOM growth and fix remaining performance footguns.
6. Leave the apps measurably more maintainable (shared token config, extracted Button component).

## Non-goals

- No new features. This is a fix pass.
- No cross-app visual unification (border-radius, etc.).
- No Analytics page redesign — placeholder stays until real charts arrive.
- No refactor of code unrelated to audit findings.

---

## Architecture Overview

The work is organized into six passes, each landing in its own commit(s) so review is tractable. Passes 1-4 are independent and can be parallelized if desired; passes 5-6 depend on earlier work for some items.

| Pass | Theme | Depends on |
|---|---|---|
| 1 | Shared tailwind tokens | — |
| 2 | Token migration (Server Manager) | Pass 1 |
| 3 | Confirmation pattern (hybrid) | — |
| 4 | Mobile-adaptive tables | — |
| 5 | Performance + accessibility fixes | — |
| 6 | Polish + extraction | Passes 1-3 (for Button component) |

---

## Pass 1: Shared Tailwind Tokens

**Files:**
- `shared/tailwind-tokens.js` (new) — single source of truth for `theme.extend`
- `server-manager/frontend/tailwind.config.js` — becomes a 5-line wrapper
- `photo-curator/frontend/tailwind.config.js` — becomes a 5-line wrapper

**New tokens added to `theme.extend.colors`:**

```js
'immich-primary-hover': '#5360c0',   // lighter shade of #4250af, eliminates hover→blue-600 hue shift
'immich-terminal':      '#080810',   // replaces bg-[#080810] magic in LogViewer/UpdateManagement
'immich-log-info':      '#d1d5db',   // replaces text-gray-300 in LogViewer
'immich-log-debug':     '#6b7280',   // replaces text-gray-500 in LogViewer
'immich-log-untagged':  '#fb923c',   // replaces text-orange-400 in LogViewer
```

**Validation:** `grep -rE 'bg-\[#' server-manager/frontend/src photo-curator/frontend/src` returns zero matches after Pass 2.

---

## Pass 2: Token Migration

**Goal:** Zero hard-coded Tailwind color classes in Server Manager source.

**Validation commands (must return zero matches after this pass):**
```bash
grep -rE 'text-(blue|red|green|amber|yellow|orange|gray)-[0-9]' server-manager/frontend/src
grep -rE 'bg-(blue|red|green|amber|yellow|orange|gray)-[0-9]' server-manager/frontend/src
grep -rE 'ring-(blue|red|green|amber|yellow|orange|gray)-[0-9]' server-manager/frontend/src
grep -rE 'border-(blue|red|green|amber|yellow|orange|gray)-[0-9]' server-manager/frontend/src
grep -rE 'bg-\[#' server-manager/frontend/src
```

**Files and replacements:**

| File | Replacements |
|---|---|
| `components/LogViewer.jsx` | `text-gray-300` → `text-immich-log-info`; `text-gray-500` → `text-immich-log-debug`; `text-orange-400` → `text-immich-log-untagged`; `bg-[#080810]` → `bg-immich-terminal`; filter bar active classes → semantic equivalents |
| `components/IPManagement.jsx` | `bg-blue-*` → `bg-immich-primary(-hover)`; `bg-red-*` → `bg-immich-error-*`; `bg-green-*` → `bg-immich-success-*`; `text-yellow-*` → `text-immich-warning`; `text-orange-400` → `text-immich-warning`; `text-blue-400` → `text-immich-info` (admin badge, tab active, icon) |
| `components/ServiceControls.jsx` | `hover:bg-blue-600` → `hover:bg-immich-primary-hover`; `bg-amber-500`, `hover:bg-amber-600`, `focus-visible:ring-amber-400` → `bg-immich-warning`, `hover:bg-immich-warning/90`, `focus-visible:ring-immich-warning` |
| `components/UpdateManagement.jsx` | `bg-amber-600`, `hover:bg-amber-500` → `bg-immich-warning`, `hover:bg-immich-warning/90`; `hover:bg-blue-600` → `hover:bg-immich-primary-hover`; `text-gray-300` → `text-immich-log-info`; `bg-[#080810]` → `bg-immich-terminal` |
| `components/BackupsCard.jsx` | `hover:bg-blue-600` → `hover:bg-immich-primary-hover` |
| `components/DiscordConfig.jsx` | `hover:bg-blue-600` → `hover:bg-immich-primary-hover`; `focus-visible:ring-blue-400` → `focus-visible:ring-immich-primary` |
| `pages/ChallengePage.jsx` | `bg-blue-600`, `hover:bg-blue-700`, `text-blue-300`, `bg-blue-500/10`, `border-blue-500/30`, `focus-visible:ring-blue-400`, `hover:border-blue-500`, `focus:border-blue-500` → `immich-info`/`immich-primary` tokens |

**Test updates:** `test/AlertsPanel.test.jsx` (and any other tests asserting raw Tailwind class names) must be updated to match the new semantic classes. Run the test suites as part of validation.

---

## Pass 3: Confirmation Pattern (Hybrid)

**Goal:** Zero `window.alert` / `window.confirm` calls in Server Manager.

**Validation:**
```bash
grep -rE 'window\.(alert|confirm)' server-manager/frontend/src
# Expect: zero matches
```

**New files:**

**`components/ConfirmDialog.jsx`** — controlled dialog for destructive/irreversible actions.
- Renders a native `<dialog>` element (uses `showModal()` for built-in focus trap, backdrop, Escape handling)
- Props: `open`, `title`, `description`, `confirmLabel`, `confirmVariant` (`'danger' | 'warning' | 'primary'`), `onConfirm`, `onCancel`
- Backdrop styled via `::backdrop` CSS pseudo-element to `immich-bg/80`
- Subtle entrance animation (opacity + translateY)
- The variant maps to button styling in Pass 6's `<Button>` component (or inline for Pass 3 if Button lands later)

**`hooks/useInlineConfirm.js`** — low-ceremony two-click confirm.
- Keyed variant to support multiple independent confirms in one component (needed for `ServiceControls` which has 6 rows each with their own restart button)
- Returns `{ isArmed, trigger }`
  - `isArmed(key)` → boolean
  - `trigger(key, handler)` → arms that key if not armed; calls `handler` if already armed; both actions reset the key's 3s timer
- Internal state: `Map<key, timeoutId>`
- Consumer uses `isArmed(key)` to swap button label to "Click again to confirm"
- For single-button usage (e.g., `BackupsCard`), pass a fixed key like `'backup'`

**Replacements:**

| File | Line | Before | After |
|---|---|---|---|
| `ServiceControls.jsx` | 31 | `confirm("Restart ${service}?")` | inline confirm on row button |
| `ServiceControls.jsx` | 44 | `confirm("Restart ALL...")` | `<ConfirmDialog>` with `confirmVariant="danger"` |
| `ServiceControls.jsx` | 48 | `alert("All services restarted.")` / failure | inline success/error banner that auto-dismisses after 4s |
| `BackupsCard.jsx` | 16 | `confirm("Start a backup now?")` | inline confirm on button |
| `BackupsCard.jsx` | 20,22,25 | `alert(...)` | inline status message below button |
| `UpdateManagement.jsx` | 44 | `confirm("Apply the latest Immich update?")` | `<ConfirmDialog>` with full consequence list |
| `UpdateManagement.jsx` | 48 | `alert("Already up to date.")` | inline message in card (state flag) |
| `UpdateManagement.jsx` | 49 | `alert("Failed: ${detail}")` | inline error in card |
| `UpdateManagement.jsx` | 69 | `alert("Failed to start update")` | inline error in card |

**Bonus — DetailPanel focus trap (P2 fix):** `Duplicates.jsx` DetailPanel gets its Escape-to-close and focus trap via the same pattern. Either:
- Convert `DetailPanel` to a native `<dialog>`, OR
- Extract a `useFocusTrap` hook from `ConfirmDialog` and add a `useEffect` keydown listener for Escape

**Decision:** Extract `useFocusTrap` hook for reuse. DetailPanel stays as a slide-out (not a centered dialog), so `<dialog>` semantics are wrong — but it still needs focus trap + Escape.

---

## Pass 4: Mobile-Adaptive IP Management Tables

**Goal:** IP Management usable on phones. Touch targets ≥44px.

**Approach:** Dual-render pattern. Each tab component renders both a `<table>` (visible `md` and up) and a `<div>`-based card list (visible below `md`). Both bind the same data and handlers.

**Files changed:** `components/IPManagement.jsx` (all four tab components: `TrustedTab`, `PendingTab`, `BlacklistedTab`, `ConnectionsTab`).

**Card structure (reference — TrustedTab):**

```jsx
<div className="md:hidden space-y-3">
  {ips.map(ip => (
    <div className="bg-immich-bg border border-immich-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-sm">{ip.ip_address}</span>
        <span className="text-xs px-2 py-0.5 rounded ...">{ip.access_level}</span>
      </div>
      <dl className="space-y-1 text-xs mb-3">
        <div className="flex justify-between"><dt className="text-immich-muted">Label</dt><dd>{ip.label || '—'}</dd></div>
        <div className="flex justify-between"><dt className="text-immich-muted">User</dt><dd>{ip.verified_by || '—'}</dd></div>
        <div className="flex justify-between"><dt className="text-immich-muted">Expires</dt><dd>{ip.expires_at ? ... : 'Never'}</dd></div>
        <div className="flex justify-between"><dt className="text-immich-muted">Last seen</dt><dd>{timeAgo(ip.last_seen)}</dd></div>
      </dl>
      <div className="flex gap-2">
        <button className="flex-1 py-2.5 ...">Edit</button>
        <button className="flex-1 py-2.5 ...">Revoke</button>
      </div>
    </div>
  ))}
</div>
```

**Desktop table changes:** Action links (currently `text-xs text-blue-400`, ~16px tall) become proper buttons with `px-3 py-2` padding and a hit-area of ≥32×44. Hit area enforced by `min-h-[44px]`.

**Inline edit/revoke/approve forms** (already managed via `editingIp`/`revokeIp`/`approveIp` state): render below the cards list on mobile (currently they render below the table, same pattern works — just verify horizontal layout stacks on narrow viewports using `flex-wrap`).

**ConnectionsTab filter bar:** Change `flex gap-3` → `grid grid-cols-1 sm:grid-cols-3 gap-2`.

**Validation:** Manual test at 320px, 375px, 414px, and 768px viewports. All interactive elements reachable without horizontal scroll; all hit areas ≥44×44.

---

## Pass 5: Performance + Accessibility Fixes

**LogViewer DOM cap (P1):**
- Add `const MAX_LINES = 2000` at module top
- In `flushPendingLines`: `setLogLines((prev) => { const next = [...prev, ...batch]; return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next })`
- Header shows "last 2000 lines" muted hint when `logLines.length === MAX_LINES`

**Missing `<main>` landmark (P1):**
- `server-manager/frontend/src/App.jsx`: wrap the `<div className="max-w-[1400px] ...">` content in `<main>` with `id="main"`
- Photo Curator already has `<main>` via `Layout.jsx` — no change

**Heading hierarchy (P1):**
- Promote all card section headings in Server Manager from `text-xs font-semibold uppercase tracking-wider text-immich-muted` to `text-sm font-semibold text-immich-text` so they are visually AND semantically heading-level
- Apply to: `SystemStatusCard`, `ImmichStatusCard`, `DiskHealthCard`, `BackupsCard`, `AlertsPanel`, `LogViewer`, `ServiceControls`, `DiscordConfig`, `UpdateManagement`
- `IPManagement.jsx`: change "IP Security" h2 from `text-lg` to `text-sm font-semibold` for consistency

**`aria-live` regions (P1):**
- `LogViewer.jsx` output div: `aria-live={isLive ? 'polite' : 'off'}`, `aria-atomic="false"`
- `UpdateManagement.jsx` progress `<pre>`: `aria-live="polite"`, `aria-atomic="false"`
- `Import.jsx` job status region: `aria-live="polite"` on the status/stats block
- `Duplicates.jsx` scan progress: `aria-live="polite"` on `ScanPanel` running state

**Import mobile fallback (P1):**
- `Import.jsx`: detect `'webkitdirectory' in document.createElement('input')` once on mount
- If unsupported and source is not `server_path`, render the drop zone in a disabled state with an amber info banner: "Folder uploads aren't supported on this browser. Use a desktop browser, or select Server Path (admin only)."
- For non-admins on mobile: clear messaging that desktop is required

**Focus-visible consistency (P2):**
- `Preferences.jsx:37`, `Import.jsx:274`, `Import.jsx:284`: add `focus-visible:ring-2 focus-visible:ring-immich-primary`
- Audit all other inputs in Photo Curator for missing `focus-visible:ring` — fix any missed

**ErrorBoundary for Photo Curator (P2):**
- Create `photo-curator/frontend/src/components/ErrorBoundary.jsx` — copy from Server Manager's inline `ErrorBoundary` class
- Wrap `<AppInner />` in `photo-curator/frontend/src/App.jsx`

**Index-based keys (P2):**
- `BackupsCard.jsx:43`: `key={b.timestamp}` (assumes unique per history row)
- `UpdateManagement.jsx:148`: progress lines — `key={\`\${l.step}-\${i}\`}` is acceptable since progress lines are append-only
- `UpdateManagement.jsx:172`: history rows — `key={h.timestamp ?? \`row-\${i}\`}`
- `IPManagement.jsx:289`: connections — `key={\`\${c.timestamp}-\${c.ip_address}\`}`
- `Events.jsx:38`: leave as-is (thumbnails within a single event don't reorder)

---

## Pass 6: Polish + Extraction

**Button component extraction (P2):**
- Create `server-manager/frontend/src/components/Button.jsx`
- Props: `variant` (`primary` | `secondary` | `danger` | `warning` | `ghost`), `size` (`sm` | `md`), `type`, `disabled`, `onClick`, `children`, standard HTML props via rest
- Encapsulates: `focus-visible:ring-2 focus-visible:ring-immich-primary`, `disabled:opacity-40`, `transition-colors duration-150`, proper hover states, `min-h-[44px]` for `md` and `min-h-[36px]` for `sm`
- Migrate consumers: `ServiceControls`, `BackupsCard`, `UpdateManagement`, `DiscordConfig`, `IPManagement`, `ChallengePage`
- Photo Curator stays untouched — less duplication there, migration can happen later if needed

**Photo Curator logo (P2):**
- Create `photo-curator/frontend/src/components/ImmichLogoIcon.jsx` — copy the SVG from `server-manager/frontend/src/components/Header.jsx`
- Use in `Sidebar.jsx` (replaces the `bg-immich-primary` circle with "I") and `Login.jsx`

**Loading skeletons (P2):**
- Create `server-manager/frontend/src/components/Skeleton.jsx` and `photo-curator/frontend/src/components/Skeleton.jsx` (copy-paste, small file)
- Primitive: `<div className="animate-pulse bg-immich-border/40 rounded-lg" style={{width, height}} />`
- Add skeletons replacing the plain "Loading…" text in:
  - Server Manager: `SystemStatusCard` (3 metric rows), `ImmichStatusCard` (2 key/value rows), `DiskHealthCard` (2-3 disk rows), `BackupsCard` (3 history rows + button), `AlertsPanel` stays as-is (conditional render), `UpdateManagement` (version rows)
  - Photo Curator: `AlbumCurator` (photo grid placeholders), `Analytics` (4 stat cards), `Events` (card placeholders)

**BottomTabBar overflow (P2):**
- Below 360px viewport: hide labels, show icons only
- Implementation: `<span className="hidden min-[360px]:inline">` wrapping the label
- `aria-label` on the NavLink is already present via route path — verify each tab has proper accessible name

**P3 polish pass:**
- `LogViewer.jsx`: tab bar — remove redundant `border-b` on outer container OR remove `border-b-2` on individual tabs (keep one, not both)
- `Events.jsx`: alt text → `alt={\`\${event.title ?? 'Event'} — preview \${i + 1} of \${previewCount}\`}`
- `transition-colors duration-150` dedupe happens naturally as part of the Button component migration

**Deferred work tracker:**
- Create `docs/DEFERRED.md` documenting:
  - Analytics page: replace placeholder stat-cards with charts + non-hero-metric layout when charts feature lands
  - Cross-app border-radius unification (Server Manager `rounded-2xl` vs Photo Curator `rounded-xl`)
  - Shared component library infrastructure — defer until a 3rd component needs sharing
  - `LogViewer.jsx` `useEffect` dependency refactor — working code, but eslint-disabled comments hide a potential stale-closure footgun
  - Dashboard card grid variety — audit flagged the 4 identical status cards as a minor anti-pattern; redesign out of scope for a fix pass
  - BottomTabBar overflow pattern — only if 7+ nav items are added later

---

## Testing Strategy

1. **Run existing test suites** in both apps after each pass. Fix any test regressions before moving to the next pass (primarily affects Pass 2 where test assertions reference raw class names).
2. **Manual mobile smoke test** after Pass 4: open Server Manager on a phone or DevTools mobile emulation at 375px. Verify IP Management tabs are usable, touch targets ≥44px, no horizontal overflow.
3. **Manual screen reader smoke test** after Pass 5: use VoiceOver/NVDA to navigate Server Manager. Verify `<main>` landmark, heading levels, and that live log updates are announced.
4. **Grep-based validation commands** run after each pass (see individual pass sections) to confirm completeness.
5. **Build both frontends** (`npm run build` in each) after all passes complete — ensure no type/lint errors.
6. **Re-run `/impeccable:audit`** at the end. Target: score ≥ 18/20.

---

## Rollout

All six passes land on the current branch `claude/immich-server-manager-012giFRno49m7TQDqYMw8HNV`. Each pass = one commit minimum (may be multiple for passes 2, 3, 6). No feature flags needed — these are all surgical fixes that preserve existing behavior.

## Success Criteria

- [ ] All grep validation commands return zero matches
- [ ] Both frontend builds succeed
- [ ] Existing test suites pass
- [ ] Manual mobile smoke test passes at 375px
- [ ] Re-run audit shows score ≥ 18/20
- [ ] `docs/DEFERRED.md` exists and lists deferred items
