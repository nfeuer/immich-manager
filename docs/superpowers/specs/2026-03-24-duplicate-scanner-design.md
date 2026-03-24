# Duplicate Scanner & Cleaner — Design Spec

**Date:** 2026-03-24
**Status:** Approved

---

## Overview

Replace the stub duplicates page with a fully independent duplicate scanner and review tool. The feature is decoupled from the AI album curator. It offers two scan modes — a fast Immich-native Quick Scan and a targeted hash-based Deep Scan — both feeding into a unified review UI where users can compare near-duplicates side-by-side and delete with confidence.

---

## Goals

- Standalone dedup tool, not tied to the curator's month-by-month analysis pipeline
- Two scan modes: Quick (Immich native, instant) and Deep (pHash, date range, background job)
- Overview list + focused comparison detail view for resolving groups
- Auto-suggest which photo to keep based on resolution and file size
- Show metadata (resolution, file size, date taken, camera, filename) alongside thumbnails
- Accurate time estimates before committing to a large scan
- Background job with live progress, cancellation, partial-result persistence

---

## Non-Goals

- Video deduplication (photos only for now; architecture allows adding later)
- Cross-user duplicate detection
- ML-based similarity beyond perceptual hashing

---

## Architecture

### Backend

#### New module: `photo-curator/src/dedup_scanner.py`

Owns the Deep Scan pipeline:

1. **Fetch phase** — query Immich `POST /search/metadata` with `takenAfter`/`takenBefore` for the user's date range
2. **Hash collection phase** — check which asset IDs already have `perceptual_hash` in `photo_scores` DB table; download thumbnails only for missing assets; compute `imagehash.phash`; store in DB
3. **Comparison phase** — run pairwise Hamming distance comparison (threshold ≤ 5) on all collected hashes in-memory via `asyncio.to_thread`; build duplicate groups
4. **Persist phase** — save groups to `duplicate_groups` with `scan_id`, `recommended_keep_id`, `resolved = False`

The scanner runs as a background `asyncio.Task`. Progress is written incrementally to the `dedup_scans` table. The batch loop checks `status == 'cancelled'` between asset batches and exits cleanly, preserving any hashes already computed.

**Auto-suggest logic:** for each group, score each asset as `width * height`; tiebreak by `file_size`. The highest-scoring asset becomes `recommended_keep_id`.

#### Database changes

**New table: `dedup_scans`**
```sql
CREATE TABLE IF NOT EXISTS dedup_scans (
    id          TEXT PRIMARY KEY,
    mode        TEXT NOT NULL,           -- 'quick' | 'deep'
    status      TEXT NOT NULL,           -- 'running' | 'complete' | 'failed' | 'cancelled'
    date_from   TEXT,                    -- ISO date string, Deep Scan only
    date_to     TEXT,                    -- ISO date string, Deep Scan only
    total_assets     INTEGER DEFAULT 0,
    hashed           INTEGER DEFAULT 0,
    groups_found     INTEGER DEFAULT 0,
    started_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
)
```

**Altered table: `duplicate_groups`**
- Add `scan_id TEXT` — foreign key to `dedup_scans`
- Add `resolved INTEGER DEFAULT 0` — soft-deletes resolved groups from the review list
- Add `recommended_keep_id TEXT` — pre-computed best-keep suggestion

#### New API routes (all require `User` role)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/dedup/scan/quick` | Start a Quick Scan (calls Immich native `/api/duplicates`) |
| `POST` | `/api/dedup/scan/deep` | Start a Deep Scan; body: `{ date_from, date_to }` |
| `POST` | `/api/dedup/scan/estimate` | Estimate asset count and time; body: `{ date_from, date_to }` |
| `GET` | `/api/dedup/scan/status` | Current scan job status + progress |
| `GET` | `/api/dedup/groups` | List unresolved duplicate groups (with asset metadata) |
| `POST` | `/api/dedup/groups/{id}/resolve` | Mark group resolved; body: `{ keep_asset_id }` — deletes others via Immich API |
| `DELETE` | `/api/dedup/groups/{id}` | Dismiss group without deleting (mark resolved, keep all) |

**Estimate response shape:**
```json
{
  "total_assets": 1240,
  "needs_hashing": 380,
  "estimated_seconds": 114,
  "warning": true
}
```
`warning: true` when `needs_hashing > 500`.

**Quick Scan fallback:** if Immich's `/api/duplicates` returns a non-200 or is unavailable, respond with `{ "error": "immich_unavailable" }` — the frontend renders a friendly message suggesting Deep Scan instead.

---

## Frontend

### Page structure

The existing `Duplicates.jsx` is replaced. The page has two vertical zones:

#### Zone 1: Scan Panel

A card with two tabs: **Quick Scan** and **Deep Scan**.

**Quick Scan tab:**
- Brief description: *"Uses Immich's built-in detection. Scans your entire library instantly."*
- "Run Quick Scan" button
- While running: spinner + "Scanning…"

**Deep Scan tab:**
- Start date + End date pickers (HTML `<input type="date">`)
- "Estimate" button — fetches `/api/dedup/scan/estimate` and shows inline result: *"~1,240 photos · ~380 need hashing · ~2 min"*
- Warning banner (yellow) when `warning: true`: *"This scan will download ~380 thumbnails and may take ~2 minutes. It will run in the background."*
- "Start Deep Scan" button (disabled until dates selected)
- While running: two-phase progress bar with label ("Collecting hashes… 240 / 380" → "Comparing…") and Cancel button

#### Zone 2: Results Panel

Visible once a scan has completed groups.

**Summary bar:**
*"14 duplicate groups found · 18 photos can be removed · ~240 MB savings"*

**Group list (overview):**
- Scrollable list of group cards
- Each card: thumbnails side-by-side (max 4, square crop), "Recommended" badge on suggested keep, one-line metadata diff (*"12MP vs 8MP · 4.2 MB vs 2.1 MB"*)
- Click a card → opens detail view

**Detail view (slide-in panel or modal):**
- Full-width thumbnails side-by-side
- Metadata table per asset: filename, resolution, file size, date taken, camera model
- Recommended keep highlighted with a badge
- "Keep this one" button under each asset (selecting overrides the recommendation)
- "Delete others & close" confirm button
- "Skip (keep all)" link — dismisses the group without deleting

**Resolved groups:** disappear from the list on resolution. A "Show resolved (N)" toggle at the top of the results panel brings them back grayed out.

---

## Scan Behavior Details

### One job at a time
Only one scan job (Quick or Deep) runs at a time. Starting a new scan while one is running returns a 409 with the current job's status.

### Polling
Frontend polls `GET /api/dedup/scan/status` every 2 seconds while a scan is running. Stops polling on `complete`, `failed`, or `cancelled`.

### Partial hash persistence
Hashes computed before a cancellation are kept in `photo_scores`. A subsequent Deep Scan over the same date range skips already-hashed assets, making retries fast.

### Batch sizing
Deep Scan downloads thumbnails in batches of 25 with a 0.5s inter-batch delay to avoid saturating Immich.

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Immich unavailable during Quick Scan | Friendly message: *"Immich duplicate detection unavailable — try a Deep Scan instead."* |
| Date range returns 0 assets | Inline message without starting a job: *"No photos found in this date range."* |
| Individual asset hash fails | Log and skip; not fatal to the job |
| Scan fails mid-run | Status set to `failed` with error message; partial hashes preserved |
| Delete fails on resolve | Show error in detail view; group not marked resolved |

---

## Data Flow Summary

```
User selects date range
        ↓
POST /api/dedup/scan/estimate → show count + time warning
        ↓
POST /api/dedup/scan/deep → job starts, returns scan_id
        ↓
Frontend polls GET /api/dedup/scan/status every 2s
        ↓
Phase 1: fetch assets → check DB → download missing thumbnails → compute pHash → store
        ↓
Phase 2: pairwise Hamming comparison → build groups → save with recommended_keep_id
        ↓
status = 'complete' → frontend loads GET /api/dedup/groups
        ↓
User reviews overview list → clicks group → detail view
        ↓
Selects keep → POST /api/dedup/groups/{id}/resolve
        ↓
Backend deletes others via Immich API → group marked resolved → disappears from list
```
