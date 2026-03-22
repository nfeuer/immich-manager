# Future Work

## Option B: Shared Component Library

Currently, the server-manager and photo-curator each maintain their own React component trees with duplicated design tokens and UI patterns (cards, buttons, badges, headers).

**The idea:** Extract shared UI components into `shared/ui/` — a lightweight internal package that both apps import. Components would include: `Card`, `Button`, `Badge`, `Header`, `Sidebar`, `StatusBadge`, and the Tailwind design token config.

**Why defer:** Both apps need to stabilize on React first (photo-curator is being migrated in the current sprint). Extracting too early risks building the wrong abstractions. Revisit once both apps have been running as React SPAs for a while and duplication patterns are clear.

**Starting point when ready:**
1. Identify components that are identical or near-identical between the two apps
2. Create `shared/ui/` with a `package.json` and Tailwind preset
3. Update both apps' `vite.config.js` to resolve the shared package
4. Migrate components one at a time, keeping both apps working throughout
