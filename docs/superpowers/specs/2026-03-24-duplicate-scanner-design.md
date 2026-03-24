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
- Show metadata (resolution, file size, date taken, camera model, filename) alongside thumbnails
- Accurate time estimates before committing to a large scan
- Background job with live progress, cancellation, partial-result persistence
- Full user isolation — each user only sees their own scan results and groups

---

## Non-Goals

- Video deduplication (photos only; architecture allows adding later)
- Cross-user duplicate detection
- ML-based similarity beyond perceptual hashing

---

## Architecture

### Backend

#### New module: `photo-curator/src/dedup_scanner.py`

Owns the Deep Scan pipeline:

1. **Fetch phase** — query Immich `POST /search/metadata` with `takenAfter`/`takenBefore` and the user's bearer token. Response shape: `{ assets: { items: [ asset, ... ], nextPage: "cursor-or-null" } }`. Each asset includes `id`, `originalFileName`, `fileCreatedAt`, and `exifInfo` with `fileSizeInByte`, `exifImageWidth`, `exifImageHeight`, `make`, `model`. **Pagination:** Immich returns a maximum of 1,000 assets per page. If `assets.nextPage` is non-null, repeat the request with `{ page: nextPage }` until `nextPage` is null, accumulating all assets across pages. This ensures correct results for date ranges with more than 1,000 photos. Store `file_size_bytes`, `width`, `height`, `filename`, `date_taken`, `camera_make`, `camera_model` per asset in a new `dedup_asset_metadata` table (keyed by `asset_id`; upsert on each scan so data stays fresh).

2. **Hash collection phase** — for each asset ID, check `photo_scores` by `asset_id` using the existing `idx_scores_asset` index (cross-month lookup — no `user_id`/`year`/`month` filter needed here since the index covers all rows). If `perceptual_hash` is present, reuse it. Otherwise download the thumbnail via `GET /assets/{id}/thumbnail`, compute `imagehash.phash`, then persist the hash using a targeted write: `UPDATE photo_scores SET perceptual_hash = ? WHERE asset_id = ?` if the row exists, or `INSERT INTO photo_scores (asset_id, user_id, year, month, perceptual_hash) VALUES (?, ?, ?, ?, ?)` (with `year`/`month` derived from the asset's `fileCreatedAt`) if no row exists yet. This avoids overwriting quality scores that the curator pipeline may have already stored for the same asset. Process in batches of 25 with a 0.5s inter-batch delay. Write `hashed` count to `dedup_scans` after each batch.

3. **Comparison phase** — run pairwise Hamming distance (threshold ≤ 5) on all collected hashes in-memory via `asyncio.to_thread`. Build duplicate groups.

4. **Persist phase** — for each group, score assets as `width * height`, tiebreak by `file_size_bytes` (higher is better); set `recommended_keep_id` to the top scorer. Save to `duplicate_groups` with `scan_id`, `user_id`, `resolved = 0`, `recommended_keep_id`. Compute `group_hash` as `str(hash(tuple(sorted(asset_ids))))` — same logic as existing curator code.

The scanner runs as a background `asyncio.Task`. Progress is written incrementally to `dedup_scans`. The batch loop checks `status == 'cancelled'` between asset batches and exits cleanly, preserving any hashes already computed.

#### New module: `photo-curator/src/dedup_quick.py`

Owns the Quick Scan pipeline:

1. Call Immich `GET /api/duplicates` using the user's bearer token.
2. Immich response shape: `[ { "duplicateId": "uuid", "assets": [ asset, ... ] }, ... ]`. Each `asset` is a full Immich asset object with `id`, `originalFileName`, `fileCreatedAt`, `exifInfo`.
3. For each returned group: upsert asset metadata into `dedup_asset_metadata`. Compute `group_hash = str(hash(tuple(sorted(asset_ids))))`. Score assets to pick `recommended_keep_id` using same `width * height` / `file_size_bytes` logic. Insert into `duplicate_groups` with `scan_id`, `user_id`, `resolved = 0`.
4. Quick Scan does not store or compute pHashes — it only uses what Immich returns.

#### New table: `dedup_asset_metadata`

Stores per-asset metadata needed for the review UI. Populated/upserted during both scan types.

```sql
CREATE TABLE IF NOT EXISTS dedup_asset_metadata (
    asset_id         TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    filename         TEXT,
    date_taken       TEXT,
    width            INTEGER,
    height           INTEGER,
    file_size_bytes  INTEGER,
    camera_make      TEXT,
    camera_model     TEXT,
    updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

#### New table: `dedup_scans`

```sql
CREATE TABLE IF NOT EXISTS dedup_scans (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    mode            TEXT NOT NULL,          -- 'quick' | 'deep'
    status          TEXT NOT NULL,          -- 'running' | 'complete' | 'failed' | 'cancelled'
    date_from       TEXT,                   -- ISO date string, Deep Scan only, nullable
    date_to         TEXT,                   -- ISO date string, Deep Scan only, nullable
    total_assets    INTEGER DEFAULT 0,
    hashed          INTEGER DEFAULT 0,      -- Deep Scan only
    groups_found    INTEGER DEFAULT 0,
    error_message   TEXT,
    started_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at    DATETIME
)
```

#### Migration: version 9

```sql
-- New table: dedup_scans
CREATE TABLE IF NOT EXISTS dedup_scans (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    mode            TEXT NOT NULL,
    status          TEXT NOT NULL,
    date_from       TEXT,
    date_to         TEXT,
    total_assets    INTEGER DEFAULT 0,
    hashed          INTEGER DEFAULT 0,
    groups_found    INTEGER DEFAULT 0,
    error_message   TEXT,
    started_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at    DATETIME
);

-- New table: dedup_asset_metadata
CREATE TABLE IF NOT EXISTS dedup_asset_metadata (
    asset_id         TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    filename         TEXT,
    date_taken       TEXT,
    width            INTEGER,
    height           INTEGER,
    file_size_bytes  INTEGER,
    camera_make      TEXT,
    camera_model     TEXT,
    updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dedup_scans_user ON dedup_scans(user_id);
CREATE INDEX IF NOT EXISTS idx_dedup_meta_user ON dedup_asset_metadata(user_id);

-- Alter existing duplicate_groups table
ALTER TABLE duplicate_groups ADD COLUMN scan_id TEXT;
ALTER TABLE duplicate_groups ADD COLUMN user_id TEXT;
ALTER TABLE duplicate_groups ADD COLUMN resolved INTEGER DEFAULT 0;
ALTER TABLE duplicate_groups ADD COLUMN recommended_keep_id TEXT;
CREATE INDEX IF NOT EXISTS idx_dup_groups_user ON duplicate_groups(user_id);
CREATE INDEX IF NOT EXISTS idx_dup_groups_scan ON duplicate_groups(scan_id);
```

Existing `duplicate_groups` rows (from the old curator pipeline) receive `scan_id = NULL`, `user_id = NULL`, `resolved = 0`, `recommended_keep_id = NULL` via SQLite's `ALTER TABLE` defaults. These rows are excluded from `GET /api/dedup/groups` which always filters `WHERE user_id = ?`. New inserts must always provide `user_id`.

#### New API routes (all require User role)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/dedup/scan/quick` | Start a Quick Scan |
| `POST` | `/api/dedup/scan/deep` | Start a Deep Scan; body: `{ date_from, date_to }` |
| `POST` | `/api/dedup/scan/estimate` | Estimate before deep scan; body: `{ date_from, date_to }` |
| `GET` | `/api/dedup/scan/status` | Current scan job status + progress |
| `DELETE` | `/api/dedup/scan` | Cancel the running scan |
| `GET` | `/api/dedup/groups` | List duplicate groups for current user |
| `POST` | `/api/dedup/groups/{id}/resolve` | Resolve group; body: `{ keep_asset_id }` |
| `DELETE` | `/api/dedup/groups/{id}` | Dismiss group without deleting any photos |

**One job at a time:** starting a new scan while one is `running` returns HTTP 409 with `{ "error": "scan_already_running", "scan_id": "..." }`.

---

### Response Shapes

**`POST /api/dedup/scan/deep` and `POST /api/dedup/scan/quick`**
```json
{ "scan_id": "uuid", "status": "running" }
```

**`POST /api/dedup/scan/estimate`**
```json
{
  "total_assets": 1240,
  "needs_hashing": 380,
  "estimated_seconds": 114,
  "warning": true
}
```
`estimated_seconds = needs_hashing * 0.3` (constant defined in config, default 0.3s/thumbnail).
`warning = true` when `needs_hashing > 500`.
Returns `{ "total_assets": 0 }` immediately if the date range yields no assets — no job is created.

**`GET /api/dedup/scan/status`**
```json
{
  "scan_id": "uuid",
  "mode": "deep",
  "status": "running",
  "phase": "hashing",
  "total_assets": 1240,
  "hashed": 240,
  "groups_found": 0,
  "date_from": "2024-01-01",
  "date_to": "2024-12-31",
  "started_at": "2026-03-24T10:00:00",
  "error_message": null
}
```
`phase` values: `"hashing"` (phase 1), `"comparing"` (phase 2), `null` when not running.
When no scan has ever run for the user: `{ "status": "idle" }`.

**`DELETE /api/dedup/scan`**
```json
{ "cancelled": true }
```
Returns `{ "cancelled": false }` if no scan is running.

**`GET /api/dedup/groups`**

Query params: `?include_resolved=false` (default false). When `true`, resolved groups are included. `?limit=50&offset=0` for pagination (default limit 50, max 200). Response includes `total_groups` so the frontend can show page controls or an infinite scroll trigger.

```json
{
  "groups": [
    {
      "id": 42,
      "scan_id": "uuid",
      "resolved": false,
      "recommended_keep_id": "asset-id-1",
      "savings_bytes": 2200000,
      "assets": [
        {
          "id": "asset-id-1",
          "filename": "IMG_1234.jpg",
          "date_taken": "2024-06-15T14:22:00",
          "width": 4032,
          "height": 3024,
          "megapixels": 12.2,
          "file_size_bytes": 4200000,
          "camera_make": "Apple",
          "camera_model": "iPhone 15 Pro",
          "thumbnail_url": "/api/thumbnail/asset-id-1"
        }
      ]
    }
  ],
  "total_groups": 14,
  "total_removable_photos": 18,
  "total_savings_bytes": 52428800
}
```

`savings_bytes` per group = sum of file sizes of all non-recommended assets.
`thumbnail_url` is the fully resolved path — the backend substitutes the real asset ID before returning.
Asset metadata comes from `dedup_asset_metadata`, joined to `duplicate_groups` via the stored `asset_ids` JSON array.

**`POST /api/dedup/groups/{id}/resolve`**

Body: `{ "keep_asset_id": "asset-id-1" }`

Backend: calls Immich `DELETE /assets` for all asset IDs in the group except `keep_asset_id`. On success, sets `resolved = 1` on the group. Returns:
```json
{ "resolved": true, "deleted_count": 2 }
```
If Immich deletion fails, group is NOT marked resolved and the error is returned:
```json
{ "resolved": false, "error": "immich_delete_failed", "detail": "..." }
```

**`DELETE /api/dedup/groups/{id}` (dismiss)**

Sets `resolved = 1` without deleting any photos.
```json
{ "dismissed": true }
```

**Quick Scan unavailable:**
```json
{ "error": "immich_unavailable", "detail": "Immich /api/duplicates returned 404" }
```
Frontend renders: *"Immich duplicate detection unavailable — try a Deep Scan instead."*

---

## Frontend

### Page structure — `Duplicates.jsx`

Two vertical zones:

#### Zone 1: Scan Panel

A card with two tabs: **Quick Scan** and **Deep Scan**.

**Quick Scan tab:**
- Description: *"Uses Immich's built-in detection. Scans your entire library instantly."*
- "Run Quick Scan" button
- Running state: spinner + "Scanning…" (polls `GET /api/dedup/scan/status`)
- On `immich_unavailable` error: yellow banner with suggestion to use Deep Scan

**Deep Scan tab:**
- Start date + End date pickers (`<input type="date">`)
- "Estimate" button — calls `/api/dedup/scan/estimate`, shows inline: *"~1,240 photos · ~380 need hashing · ~2 min"*
- Warning banner (yellow) when `warning: true`: *"This scan will download ~380 thumbnails and may take ~2 minutes. It will run in the background."*
- "Start Deep Scan" button (disabled until both dates selected)
- Running state: progress bar with phase label:
  - Phase `hashing`: "Collecting hashes… 240 / 1240"
  - Phase `comparing`: "Comparing hashes…"
  - Plus a Cancel button (calls `DELETE /api/dedup/scan`)

Polling: `GET /api/dedup/scan/status` every 2 seconds while `status === 'running'`. Stops on `complete`, `failed`, or `cancelled`.

#### Zone 2: Results Panel

Visible when the latest scan is `complete` and groups exist.

**Summary bar:**
*"14 duplicate groups found · 18 photos can be removed · ~50 MB savings"*
Sizes formatted with a human-readable helper (bytes → KB/MB/GB).

**Group list (overview):**
- Scrollable list of group cards
- Each card: thumbnails side-by-side (max 4, square crop), "Recommended" badge on `recommended_keep_id` asset, one-line metadata diff (*"12MP vs 8MP · 4.2 MB vs 2.1 MB"*)
- Click card → opens detail view
- "Show resolved (N)" toggle at top — client-side: re-fetches with `?include_resolved=true`, renders resolved cards grayed out

**Detail view (slide-in panel):**
- Full-width thumbnails side-by-side (scrollable if > 2 assets)
- Metadata table per asset: filename, resolution, file size, date taken, camera model
- Recommended keep highlighted with a badge
- "Keep this one" button under each thumbnail (overrides recommendation — local state only until "Delete others" is clicked)
- "Delete others & close" button — calls `POST /api/dedup/groups/{id}/resolve` with the currently-selected keep ID
- "Skip (keep all)" link — calls `DELETE /api/dedup/groups/{id}`, closes panel, group disappears
- Error state: inline red message if resolve fails, panel stays open

Resolved groups disappear from the list immediately on resolution (optimistic update via `queryClient.invalidateQueries`).

---

## Implementation Notes

- **`photo_scores` fallback INSERT:** The `score` column is `NOT NULL` with no default. When inserting a hash-only row (no quality analysis done), supply `score = 0.0` as a sentinel to satisfy the constraint.
- **`phase` field derivation:** `dedup_scans` has no `phase` column. Derive it at query time: if `status = 'running'` and `hashed < total_assets`, phase is `"hashing"`; if `hashed >= total_assets`, phase is `"comparing"`. Return `null` for any non-running status.

---

## Scan Behavior Details

### Partial hash persistence
Hashes computed before a cancellation are stored in `photo_scores`. A subsequent Deep Scan over the same or overlapping date range skips already-hashed assets, making retries fast.

### Batch sizing
Deep Scan processes thumbnails in batches of 25 with a 0.5s inter-batch delay.

### Thumbnail cleanup
Thumbnails downloaded during Deep Scan are written to a temp directory and deleted immediately after hashing. They are not stored in any cache.

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Immich unavailable during Quick Scan | `{ "error": "immich_unavailable" }` → friendly UI message |
| Date range returns 0 assets | Return estimate with `total_assets: 0`; no job started |
| Individual asset hash fails | Log and skip; not fatal |
| Scan fails mid-run | `status = 'failed'`, `error_message` set; partial hashes preserved |
| Delete fails on resolve | Group not marked resolved; error shown in detail view |
| New scan started while one running | HTTP 409 with current scan ID |

---

## Data Flow Summary

```
[Deep Scan]
User selects date range
        ↓
POST /api/dedup/scan/estimate → count assets, check DB for existing hashes → return estimate
        ↓
POST /api/dedup/scan/deep → background job starts, returns scan_id
        ↓
Frontend polls GET /api/dedup/scan/status every 2s
        ↓
Phase 1 (hashing): fetch assets from Immich → check photo_scores by asset_id →
  download missing thumbnails in batches → compute pHash → store → update hashed count
        ↓
Phase 2 (comparing): pairwise Hamming comparison → build groups → score → save with recommended_keep_id
        ↓
status = 'complete' → frontend loads GET /api/dedup/groups
        ↓
User reviews overview → clicks group → detail view
        ↓
Selects keep → POST /api/dedup/groups/{id}/resolve
        ↓
Backend deletes others via Immich API → group marked resolved → disappears from list

[Quick Scan]
POST /api/dedup/scan/quick
        ↓
GET Immich /api/duplicates → map to duplicate_groups → score → save
        ↓
status = 'complete' → frontend loads GET /api/dedup/groups
        ↓
Same review UI as Deep Scan
```
