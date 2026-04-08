# Deferred Work

Items intentionally scoped out of prior fix passes. Revisit when the context warrants.

## From 2026-04-08 audit fixes

- **Analytics page redesign** — Current page is a placeholder with 4-stat-card grid ("hero metrics" anti-pattern). When real charts land, redesign the layout to avoid the hero-metric template. See `photo-curator/frontend/src/pages/Analytics.jsx`.

- **Cross-app border-radius unification** — Server Manager uses `rounded-2xl` on cards; Photo Curator uses `rounded-xl`. Unifying requires a product-level decision on whether both apps should feel like one product.

- **Shared component library infrastructure** — Only `shared/tailwind-tokens.js` is currently shared. `ErrorBoundary`, `Skeleton`, and `ImmichLogoIcon` are copy-pasted between apps. Revisit when a 3rd or 4th component needs sharing.

- **LogViewer useEffect dependency refactor** — `src/components/LogViewer.jsx` has two `eslint-disable-next-line react-hooks/exhaustive-deps` comments. Working code, but the suppression hides a potential stale-closure footgun. Refactor into a reducer or properly-declared deps when next touching the file.

- **Dashboard card grid variety** — Server Manager's 4 identical status cards (System/Immich/Disk/Backups) were flagged as a minor "card grid" anti-pattern tell. Fixing requires a visual redesign, not a fix.

- **BottomTabBar overflow pattern** — Currently hides labels under 360px. If 7+ nav items are added, consider a "More" overflow menu.

- **Button component migration** — `server-manager/frontend/src/components/Button.jsx` was extracted (with tests) but no consumer sites have been migrated. `ServiceControls`, `BackupsCard`, `UpdateManagement`, `IPManagement`, `DiscordConfig`, `ConfirmDialog`, and `LogViewer` still ship bespoke `<button>` class strings. Migrating them is a follow-up sweep that should also consolidate `ConfirmDialog`'s action buttons.
