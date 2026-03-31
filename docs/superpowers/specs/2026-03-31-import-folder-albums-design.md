# Import: Folder Album Creation & Progress Design

**Date:** 2026-03-31
**Status:** Approved

## Overview

Two related improvements to the photo curator's import system:

1. **Folder album creation** — automatically create Immich albums from subfolder names during a folder import, with real-time batched progress and resume safety
2. **Import documentation** — a markdown reference doc covering all import methods with usage examples

## Background & Motivation

When importing large photo collections that are already organized into folders (e.g. `Wedding Photos/Ceremony/`, `Wedding Photos/Venue/`), users want those folders to become albums in Immich automatically. Currently the importer uploads files but ignores folder structure entirely.

For 20k+ photo imports the user runs locally via server-path import (bypassing Cloudflare's 100MB limit). Progress visibility and resume capability are critical at this scale.

## Requirements

### Album Creation Behavior

- Every subfolder at **any depth** becomes an album named after that folder
- A photo is added to **all albums in its path** — `Ceremony/Church/photo.jpg` goes into both "Ceremony" and "Church"
- Photos sitting **directly in the import root** (no subfolder): default to no album (option A), with a toggle to add them to an album named after the root folder (option B)
- Album creation is **opt-in** via a checkbox — default off
- Root-album toggle is **opt-in** — default off, only shown when album creation is enabled

### Folder Name Resolution

| Import method | Root folder name | Album name source |
|---|---|---|
| Browser upload | First component of `webkitRelativePath` (e.g. `Wedding Photos`) — skip when computing albums | Components 1…N-1 of relative path |
| Server-path import | `basename` of the server path (e.g. `Wedding Photos` from `/opt/import/Wedding Photos`) | Components 0…N-1 of relative path |

Example — browser upload of `Wedding Photos/Ceremony/Church/photo.jpg`:
- Root folder: `Wedding Photos`
- Albums: `Ceremony`, `Church`
- With root-album toggle on: also `Wedding Photos`

Example — server-path import of the same file with path `/opt/import/Wedding Photos`:
- Root folder: `Wedding Photos` (basename of server path)
- Albums: `Ceremony`, `Church` (no root skip needed)
- With root-album toggle on: also `Wedding Photos`

### Resume Safety

Uploads are already resume-safe via `folder-import-progress.json`. Album additions are idempotent — Immich silently deduplicates assets already in an album — so album state requires no additional save file. On restart: uploads are skipped via the progress file, album additions are safely replayed.

### Batching

Album asset assignments are buffered in memory and flushed to Immich every **25 files**. Each flush is one API call per album in the buffer: `POST /api/albums` (new) or `PUT /api/albums/{id}/assets` (existing). The tail batch (< 25 files) is flushed after the loop completes, **only if the job was not cancelled** (the existing `for/else` structure in `_run_import_sync` already gates this).

### Duplicate Upload Response

On HTTP 200/201: extract `response.json()["id"]` — this is the new asset's ID.
On HTTP 409 (duplicate): Immich's single-asset upload endpoint returns the existing asset object including its `id`. Extract `response.json()["id"]`. Duplicates **are** assigned to albums so that re-imports correctly populate album membership even for previously-uploaded photos.

If the 409 response body does not contain `id` (malformed or unexpected), treat as `None` — skip album assignment for that file and log a warning.

### Logging

At every batch boundary the importer emits a structured log line via Python's standard `logging` module:

```
[Import:folder] Batch 3/40 — 75 uploaded, 2 duplicates, 0 errors | Albums: Ceremony(12), Venue(8)
[Import:folder] Batch 40/40 — 1000 uploaded, 23 duplicates, 1 error | Albums created: 5
```

These feed into journald and are automatically picked up by the server manager's log viewer with no additional wiring.

## Component Changes

### `migration-tools/folder-import.py`

**Constructor additions:**
```python
def __init__(
    self,
    directory: Path,
    immich_url: str,
    api_key: str,
    create_albums: bool = False,
    root_album: bool = False,
    skip_root_folder: bool = False,
):
```

- `create_albums` — enable subfolder → album mapping
- `root_album` — add root-level photos to an album named after the root folder
- `skip_root_folder` — skip first path component when computing album names; set `True` for browser uploads

**New internal state:**
```python
self._album_buffer: Dict[str, List[str]] = {}   # album_name → [asset_id, ...]
self._existing_albums: Dict[str, str] = {}       # album_name → album_id (eager-loaded once at first flush)
self._albums_cache_loaded: bool = False
self._files_since_flush: int = 0
self._current_batch: int = 0                     # incremented by _flush_albums before emitting log line
self._total_batches: int = 0                     # set by caller before loop starts
```

**`_upload_file` return type change:**
Returns `Optional[str]` (asset_id) instead of `bool`. The caller (upload loop) is responsible for album buffering — `_upload_file` stays focused on upload only. This preserves single responsibility and makes `_upload_file` easier to test.

**New `_get_album_names(file_path: Path) -> List[str]`:**
Computes which albums a file belongs to:
1. Compute `rel = file_path.relative_to(self.directory)`
2. If `skip_root_folder`, drop `rel.parts[0]`; use remaining parts as `path_parts`
3. If `root_album` and `len(path_parts) == 1` (file directly in root, no subdir): return `[root_folder_name]`
4. Otherwise: return `list(path_parts[:-1])` — all directory components, excluding the filename

`root_folder_name` is `rel.parts[0]` when `skip_root_folder=True`, or `self.directory.name` when `False`.

**New `_load_album_cache()`:**
Called once at the start of the first `_flush_albums()` call (guarded by `_albums_cache_loaded`). Calls `GET /api/albums` and populates `_existing_albums = {a['albumName']: a['id'] for a in response}`. This prevents duplicate album creation for albums that already exist from a previous import run.

**New `_flush_albums()`:**
1. If `_album_buffer` is empty, return immediately
2. Call `_load_album_cache()` if not yet loaded
3. For each `(album_name, asset_ids)` in buffer:
   - If `album_name` in `_existing_albums`: call `PUT /api/albums/{id}/assets` with `{"ids": asset_ids}`
   - Otherwise: call `POST /api/albums` with `{"albumName": album_name, "assetIds": asset_ids}`. On success, extract `response.json()["id"]` and store in `_existing_albums[album_name]`. Increment `stats['albums_created']`
   - On API error: log a warning, continue (non-fatal)
4. Clear `_album_buffer`
5. Increment `self._current_batch`
6. Emit batch log line: `[Import:folder] Batch {_current_batch}/{_total_batches} — ...`

**Stats dict additions:**
```python
self.stats = {
    ...,
    'albums_created': 0,
    'current_file': '',
}
```

**Upload loop (in `_scan_files` / caller):**
`_scan_files` return type is unchanged — it still returns `List[Path]`. `total_batches` is computed by the caller in `_run_import_sync` as `ceil(len(photo_files) / 25)` and passed to the importer as `self._total_batches` before the loop starts.

### `photo-curator/src/database.py`

**Schema migration (version 10):**
Add a new tuple to the `MIGRATIONS` list in `database.py` as version 10:
```python
(10, "add albums_created and current_file to import_jobs", [
    "ALTER TABLE import_jobs ADD COLUMN albums_created INTEGER DEFAULT 0",
    "ALTER TABLE import_jobs ADD COLUMN current_file TEXT DEFAULT ''",
]),
```

`update_import_job_progress` must be updated to sync both new fields from the stats dict.

Note: `_upload_file` return type change (`bool` → `Optional[str]`) applies only to `FolderImporter`. Other importer classes (`GooglePhotosImporter`, `ApplePhotosImporter`, `ICloudImporter`) are separate classes and are not affected.

### `photo-curator/src/main.py`

**`ServerPathImport` model:**
```python
class ServerPathImport(BaseModel):
    source_type: str
    server_path: str
    create_albums: bool = False
    root_album: bool = False
```

**`/api/import/upload` endpoint:**
```python
create_albums: bool = Form(False)
root_album: bool = Form(False)
```

**`_run_import_sync` signature:**
```python
def _run_import_sync(
    job_id, user_id, user_token,
    source_type, directory, import_method,
    create_albums=False, root_album=False,
):
```

**Updated `background_tasks.add_task` call — browser upload:**
```python
background_tasks.add_task(
    _run_import_sync,
    job_id, user["id"], user["access_token"],
    source_type, str(staging_dir), "upload",
    create_albums, root_album,
)
```

**Updated `background_tasks.add_task` call — server-path:**
```python
background_tasks.add_task(
    _run_import_sync,
    job_id, user["id"], user["access_token"],
    body.source_type, resolved, "server_path",
    body.create_albums, body.root_album,
)
```

**Folder importer construction in `_run_import_sync`:**
```python
if source_type == "folder":
    importer = FolderImporter(
        Path(directory), immich_url, user_token,
        create_albums=create_albums,
        root_album=root_album,
        skip_root_folder=(import_method == "upload"),
    )
else:
    importer = ImporterClass(Path(directory), immich_url, user_token)
```

**Upload loop additions** (folder source_type):
```python
for i, photo_path in enumerate(photo_files):
    # ... existing cancel check ...

    asset_id = importer._upload_file(photo_path)
    importer.stats['current_file'] = photo_path.name

    if asset_id and importer.create_albums:
        album_names = importer._get_album_names(photo_path)
        for name in album_names:
            importer._album_buffer.setdefault(name, []).append(asset_id)

    importer._files_since_flush += 1
    if importer._files_since_flush >= 25:
        importer._flush_albums()
        importer._files_since_flush = 0

    if (i + 1) % 10 == 0:
        database.update_import_job_progress(job_id, importer.stats)
else:
    # Loop completed without cancellation — flush tail batch
    if importer.create_albums:
        importer._flush_albums()
    database.update_import_job_progress(job_id, {**importer.stats, "status": "completed"})
    database.update_import_job_status(job_id, "completed")
```

The tail flush is inside the `else` clause of the `for` loop, so it is skipped if the job was cancelled (which `break`s the loop, bypassing `else`).

### `photo-curator/frontend/src/pages/Import.jsx`

**New form state:**
```js
const [createAlbums, setCreateAlbums] = useState(false)
const [rootAlbum, setRootAlbum] = useState(false)
```

**Root folder name** (derived client-side, no extra API call needed):
- Browser upload: extracted from the first file's `webkitRelativePath` — `files[0]?.webkitRelativePath?.split('/')[0] ?? ''`
- Server-path: extracted from the path input — `serverPath.split('/').filter(Boolean).pop() ?? ''`

**Album options UI** (shown in step 1 for `folder` and `server_path` sources, below the file picker / path input):
```jsx
<label>
  <input type="checkbox" checked={createAlbums} onChange={e => { setCreateAlbums(e.target.checked); if (!e.target.checked) setRootAlbum(false) }} />
  Create albums from subfolders
</label>
{createAlbums && (
  <label>
    <input type="checkbox" checked={rootAlbum} onChange={e => setRootAlbum(e.target.checked)} />
    Add loose photos to a "{rootFolderName || 'root'}" album
  </label>
)}
```

**Passed in requests:**
- Browser upload: `formData.append('create_albums', createAlbums)` and `formData.append('root_album', rootAlbum)`
- Server-path: `{ source_type: serverPathSourceType, server_path: serverPath, create_albums: createAlbums, root_album: rootAlbum }`

**Progress card additions:**
- "Albums" tile added to the stats grid (alongside Uploaded / Duplicates / Errors / Total): `job.albums_created ?? 0`
- Current file line below progress bar: `<p className="text-immich-muted text-xs font-mono truncate">{job.current_file}</p>` — only shown when job is running
- Status message derived from `job.status`: `scanning` → "Scanning…", `running` → "Uploading…", `completed` → "Done", `failed` → "Failed", `cancelled` → "Cancelled"

### `docs/importing-photos.md`

A single reference document covering:

1. **Overview** — four import methods at a glance (table: method, best for, Cloudflare-safe, resume support)
2. **Browser upload** — small collections via drag-and-drop; note Cloudflare free tier 100MB limit
3. **Server-path import** — large collections; full rsync workflow with example commands, SSH tunnel setup
4. **Folder album creation** — how it works, the Wedding Photos example, depth behavior, root album toggle, resume behavior
5. **Google / Apple / iCloud imports** — brief notes on required export formats
6. **Troubleshooting** — common errors and fixes

## Data Flow

```
_run_import_sync (main.py):
  total_batches = ceil(len(photo_files) / 25)
  importer._total_batches = total_batches

  for i, photo_path in photo_files:
    asset_id = importer._upload_file(photo_path)   ← upload only, returns id or None
    importer.stats['current_file'] = photo_path.name

    if asset_id and create_albums:
      album_names = importer._get_album_names(photo_path)
      for name in album_names:
        importer._album_buffer[name].append(asset_id)

    if files_since_flush >= 25:
      importer._flush_albums()     ← batch API calls + log line
      files_since_flush = 0

  else:                            ← only if not cancelled
    importer._flush_albums()       ← tail batch
```

```
_flush_albums():
  _load_album_cache() if not loaded   ← one GET /api/albums
  for album_name, ids in buffer:
    if album exists → PUT /api/albums/{id}/assets
    else            → POST /api/albums (capture new id)
  clear buffer
  emit log: [Import:folder] Batch N/M — ...
```

## Error Handling

- Album creation/update failure is non-fatal: logged as a warning, upload stats are unaffected, import continues
- No `album_errors` stat is tracked — failures are warning-log-only to keep the stats surface simple
- Upload failures follow existing behavior (counted in `stats['errors']`, logged per file)

## Testing Considerations

- Unit test `_get_album_names` for:
  - Browser upload paths (`skip_root=True`): 1-deep, 2-deep, file in root, file in root with `root_album=True`
  - Server-path paths (`skip_root=False`): same cases
- Unit test `_flush_albums` with mixed new/existing albums; assert `_existing_albums` is populated from POST response
- Unit test resume: pre-populate progress file, assert skipped files are not re-uploaded, album assignments are still buffered and flushed
- Assert tail flush is skipped when loop exits via `break` (cancelled path)
- Integration: import a 3-level nested folder, assert all expected albums exist in Immich with correct asset membership
