# Photo Curator React Redesign — Design Spec
Date: 2026-03-21

## Overview

Rebuild the Photo Curator frontend from 7 separate static HTML pages into a React SPA, matching the server-manager's visual design system and architecture. Fix the photo-loading workflow, add consistent navigation, and introduce a year-progress tracker for curation status.

The overarching service remains "Photo Curator." The monthly curation feature is renamed "AI Album Curator."

---

## Goals

- Consistent UI across all pages (matching server-manager design tokens and component style)
- Readable, consistent buttons throughout
- Collapsible sidebar navigation usable on mobile
- Fix photo-loading bug: photos load immediately from Immich without requiring prior analysis
- Clear, guided curation workflow
- Year tracker showing which months have been curated
- Same authentication pattern as server-manager (`shared.auth`)

---

## Architecture

### Frontend
- **Stack:** React + Vite + Tailwind CSS (same as server-manager)
- **Location:** `photo-curator/frontend/`
- **Structure mirrors server-manager:** `src/components/`, `src/hooks/`, `src/utils/`
- **Design tokens:** Copied exactly from server-manager's `tailwind.config.js`

```
immich-bg:      #0f0f11
immich-surface: #1a1a27
immich-border:  #2a2a3d
immich-text:    #f1f0ff
immich-muted:   #7c7c9a
immich-primary: #4250af
```

### Backend changes
- Add `GET /api/photos/{year}/{month}/raw` — new endpoint, fetches photos directly from Immich; does NOT replace the existing `/api/photos/{year}/{month}` (which returns scored photos for the curation flow)
- Add `GET /api/progress/year/{year}` — new endpoint, returns curation status for all 12 months
- Refactor auth to use `shared.auth` pattern (see Auth Migration section below)
- Existing endpoints (`/api/analyze/{year}/{month}`, `/api/photos/{year}/{month}`, `/api/curation/...`) remain unchanged
- FastAPI serves the built React dist at `/` (same pattern as server-manager)
- CSP header: remove the CDN `style-src` allowances (`cdn.tailwindcss.com`, `cdn.jsdelivr.net`, `unpkg.com`) as part of this migration — Tailwind and chart.js are bundled via Vite/npm

---

## API Contracts

### `GET /api/photos/{year}/{month}/raw`

Response:
```json
{
  "year": 2026,
  "month": 3,
  "photos": [
    {
      "id": "asset-uuid",
      "filename": "IMG_1234.jpg",
      "created_at": "2026-03-15T14:23:00Z",
      "scored": false
    }
  ],
  "total": 42,
  "scored_count": 10
}
```

- `scored` is `true` if this asset has a row in `photo_scores` for this user/year/month
- `scored_count` is the count of already-analyzed photos; used by the frontend to decide whether to trigger background analysis
- The frontend uses this to trigger `POST /api/analyze/{year}/{month}` automatically on page load when `scored_count < total`

### `GET /api/progress/year/{year}`

Response:
```json
{
  "year": 2026,
  "months": [
    { "month": 1, "curated": true, "album_name": "January 2026" },
    { "month": 2, "curated": false, "album_name": null },
    ...
  ]
}
```

- `curated` is `true` when `curation_sessions.completed = 1` for that user/year/month in the local DB
- Album existence is tracked locally (not re-queried from Immich on every load)

---

## Auth Migration

Replace the existing `ImmichAuth` session-cookie system with `shared.auth`:

**Remove from `photo-curator/src/main.py`:**
- `from .auth import ImmichAuth, get_current_user, get_current_user_optional, get_user_api_client`
- `app.state.immich_auth = ImmichAuth(immich_base_url)` in `lifespan`
- All `Depends(get_current_user)` → replace with `Depends(require_auth)`
- All `Depends(get_current_user_optional)` → replace with `Depends(require_auth_optional)` or remove

**Add:**
```python
from shared.auth import extract_token, validate_immich_token, get_or_create_user

async def require_auth(request: Request) -> dict:
    token = extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await validate_immich_token(app.state.immich_api_url, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return get_or_create_user(database, user, default_role=Role.USER)
```

**User dict shape** (same as before — code that reads `user['id']`, `user['access_token']`, etc. is unchanged).

---

## Navigation

### Desktop (≥768px)
Fixed left sidebar, 220px wide:
- Top: Immich logo + "Photo Curator" title
- Nav items (icon + label): AI Album Curator, Import, Duplicates, Events & Trips, Analytics, Preferences
- Bottom: user avatar, username, logout button
- "AI Album Curator" item shows a badge with count of un-curated months in the current year (hidden when all 12 are done)

### Mobile (<768px)
- Sidebar hidden; replaced by a fixed bottom tab bar with 6 icon-only tabs
- Active tab highlighted with `immich-primary`
- No hamburger menu required

---

## Pages

### AI Album Curator (landing page)

**Controls:**
- Month/year switcher (prev/next arrows + "March 2026" label) at top
- Year tracker: row of 12 month pills below the switcher
  - Green pill = Immich album exists for that month
  - Gray pill = not yet curated
  - Clicking a pill navigates to that month

**Photo load flow:**
1. Page load triggers `GET /api/photos/{year}/{month}/raw` — thumbnails render immediately using `total` count
2. If `scored_count < total`, the frontend auto-triggers `POST /api/analyze/{year}/{month}` in the background
3. A subtle progress bar shows "Analyzing X of N photos…" (polling `scored_count` from a second call or SSE) without blocking the grid
4. Once `scored_count === total`, the **AI Curate** button becomes active; while analysis runs the button shows a spinner and is disabled
5. Month switcher: prev/next navigate one month at a time; future months (beyond current calendar month) are disabled; no hard lower limit (navigate as far back as Immich has photos)

**Curation flow:**
1. Click **AI Curate** → top N photos (N from preferences) get a colored border + checkmark; others dim slightly
2. Sticky footer appears: `24 selected · Recommended: 20` with **Save Album** and **Reset** buttons
3. User can click any photo to toggle selection on/off freely; no hard cap (can exceed recommendation)
4. Click **Save Album** → creates or updates the Immich album for that month; month pill in year tracker turns green

**Photo grid:** Responsive masonry/grid layout, thumbnails fetched via `/api/thumbnail/{asset_id}`

---

### Import

Step-by-step wizard retained from existing UI, restyled:
1. Choose source (Google Photos, Apple Photos, iCloud)
2. Configure path / upload export file
3. Preview discovered files with count
4. Import with live progress (file count + percentage)

---

### Duplicates

- Side-by-side comparison cards showing duplicate pairs
- Checkboxes to select which copy to keep/delete
- Sticky footer with **Delete Selected** button and count
- Card style matches server-manager dashboard cards

---

### Events & Trips

- Auto-detected event clusters as album cards
- Each card: date range, photo count, thumbnail strip
- One-click **Create Album** button per event suggestion

---

### Analytics

- Stats cards row at top: total photos, months curated, duplicates found, faces identified
- Charts below (existing chart.js charts restyled to match design tokens) — chart.js installed via npm and bundled by Vite, no CDN
- Same 4-column card grid pattern as server-manager dashboard

---

### Preferences

Mirrors the existing `UserPreferences` model and `/api/preferences` GET/PUT endpoints:

- **Album Settings:** `monthly_target` (integer — default N photos for AI curation suggestion)
- **Notifications:** `email_notifications` object with toggles: `monthly_reminders`, `quality_alerts`, `memory_lane`, `seasonal_automations`, `storage_warnings`
- **UI Settings:** `ui_suggestions` object with toggles: `sharing_suggestions`, `event_detection`, `duplicate_warnings`

Consistent input/label style matching server-manager. **Save** button at bottom of each section; PUT to `/api/preferences` on save.

---

## Authentication

Replace `ImmichAuth` session-cookie system with `shared.auth` pattern:
- `extract_token(request)` — reads cookie or `Authorization: Bearer` header
- `validate_immich_token(immich_api_url, token)` — validates against Immich API
- `get_or_create_user(database, immich_user, default_role)` — local user with role
- Unauthenticated requests receive a 401 with a redirect hint to Immich login
- React frontend detects 401 and shows a "Sign in via Immich" screen

---

## Button System

Consistent button variants used across all pages:

| Variant | Background | Text | Use case |
|---|---|---|---|
| Primary | `immich-primary` (#4250af) | white | Main actions (AI Curate, Save Album, Create Album) |
| Secondary | `immich-surface` | `immich-text` | Supporting actions (Reset, Cancel) |
| Destructive | red-600 | white | Deletes (Delete Selected, Delete Duplicate) |
| Ghost | transparent | `immich-muted` | Low-priority actions (dismiss, skip) |

All buttons: same padding (`px-4 py-2`), same border-radius (`rounded-lg`), same font weight (`font-medium`).

Additional states:
- **Disabled:** `opacity-50 cursor-not-allowed` — applied when action is unavailable (e.g., AI Curate before analysis completes)
- **Loading:** replace label with a spinner + short text (e.g., "Saving…"); button remains disabled during the request

---

## Future Work

See `docs/FUTURE_WORK.md` for the Option B plan: extracting a shared component library (`shared/ui/`) that both server-manager and photo-curator import from, once both apps are stable as React SPAs.
