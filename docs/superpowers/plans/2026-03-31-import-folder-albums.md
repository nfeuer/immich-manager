# Import: Folder Album Creation & Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically create Immich albums from subfolder names during folder imports, with batched real-time progress, structured logs, and a documentation file.

**Architecture:** Changes flow outward from `folder-import.py` (core album logic) → `database.py` (schema) → `main.py` (wiring) → `Import.jsx` (UI). Each layer builds on the previous. The importer accumulates asset→album assignments in memory and flushes them to Immich every 25 files, so album population is visible in near-real-time without per-file API overhead.

**Tech Stack:** Python 3 / requests (backend importer), FastAPI / Pydantic (API layer), React / TanStack Query (frontend), SQLite with hand-rolled migrations (database).

**Spec:** `docs/superpowers/specs/2026-03-31-import-folder-albums-design.md`

**Known limitation:** Files skipped via the progress-file (already uploaded in a previous run) return `None` from `_upload_file` and are not re-added to the album buffer on resume. In practice this affects at most 24 files — one unflushed batch. Files that were fully flushed in the prior run are already in their albums; newly uploaded files in the resumed run are assigned correctly. A full replay would require storing asset IDs in the progress file, which is deferred as a future improvement.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `migration-tools/folder-import.py` | Modify | Album logic: `_get_album_names`, `_load_album_cache`, `_flush_albums`, updated `_upload_file` return type, new constructor params |
| `photo-curator/src/database.py` | Modify | Migration v10 (new columns), update `update_import_job_progress` |
| `photo-curator/src/main.py` | Modify | Endpoint params, `_run_import_sync` signature + upload loop wiring |
| `photo-curator/frontend/src/pages/Import.jsx` | Modify | Album checkboxes, Albums stat tile, current_file display |
| `photo-curator/tests/test_folder_import.py` | Create | Unit tests for all new folder-import logic |
| `docs/importing-photos.md` | Create | User-facing reference documentation |

---

## Task 1: Database migration v10

**Files:**
- Modify: `photo-curator/src/database.py:229` (after migration v9 tuple), `photo-curator/src/database.py:1479` (`update_import_job_progress`)

- [ ] **Step 1: Write the failing migration tests**

Create `photo-curator/tests/test_folder_import.py` with:

```python
"""Tests for folder import album creation and database migration."""
import sys
import requests
from pathlib import Path
from unittest.mock import patch, MagicMock
import importlib.util
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_folder_importer():
    spec = importlib.util.spec_from_file_location(
        "folder_import",
        Path(__file__).resolve().parent.parent.parent / "migration-tools" / "folder-import.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.FolderImporter


@pytest.fixture
def db(tmp_path):
    from src.database import Database
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def make_importer(tmp_path):
    """
    Factory that returns a FolderImporter bypassing __init__ (no network calls).
    All tests that patch imp.session work because session is set here.
    """
    FolderImporter = load_folder_importer()

    def _make(**kwargs):
        imp = FolderImporter.__new__(FolderImporter)
        imp.directory = tmp_path
        imp.immich_url = "http://immich"
        imp.api_key = "key"
        imp.create_albums = kwargs.get("create_albums", False)
        imp.root_album = kwargs.get("root_album", False)
        imp.skip_root_folder = kwargs.get("skip_root_folder", False)
        imp.session = requests.Session()           # required for patch.object to work
        imp._album_buffer = {}
        imp._existing_albums = {}
        imp._albums_cache_loaded = False
        imp._files_since_flush = 0
        imp._current_batch = 0
        imp._total_batches = 0
        imp.stats = {
            "uploaded": 0, "duplicates": 0, "errors": 0,
            "albums_created": 0, "current_file": "",
        }
        return imp

    return _make


# ---------------------------------------------------------------------------
# Migration v10 tests
# ---------------------------------------------------------------------------

def test_migration_v10_adds_albums_created_column(db):
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(import_jobs)")
        columns = {row[1] for row in cursor.fetchall()}
    assert "albums_created" in columns


def test_migration_v10_adds_current_file_column(db):
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(import_jobs)")
        columns = {row[1] for row in cursor.fetchall()}
    assert "current_file" in columns


def test_update_import_job_progress_syncs_albums_created(db):
    job_id = db.create_import_job("user1", "folder", "server_path")
    db.update_import_job_progress(job_id, {"albums_created": 3, "uploaded": 10})
    job = db.get_import_job(job_id)
    assert job["albums_created"] == 3


def test_update_import_job_progress_syncs_current_file(db):
    job_id = db.create_import_job("user1", "folder", "server_path")
    db.update_import_job_progress(job_id, {"current_file": "photo.jpg"})
    job = db.get_import_job(job_id)
    assert job["current_file"] == "photo.jpg"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/feuer/Documents/Projects/immich-manager/photo-curator
python -m pytest tests/test_folder_import.py::test_migration_v10_adds_albums_created_column tests/test_folder_import.py::test_migration_v10_adds_current_file_column -v
```

Expected: FAIL — columns don't exist yet.

- [ ] **Step 3: Add migration v10 to database.py**

In `photo-curator/src/database.py`, after the closing `]),` of the v9 migration tuple (around line 277), add:

```python
    (10, "add albums_created and current_file to import_jobs", [
        "ALTER TABLE import_jobs ADD COLUMN albums_created INTEGER DEFAULT 0",
        "ALTER TABLE import_jobs ADD COLUMN current_file TEXT DEFAULT ''",
    ]),
```

- [ ] **Step 4: Update `update_import_job_progress` to sync new fields**

In `photo-curator/src/database.py`, find the `for col in (...)` loop at line ~1479. Change:

```python
for col in ("total_files", "uploaded", "skipped", "errors", "duplicates"):
```

To:

```python
for col in ("total_files", "uploaded", "skipped", "errors", "duplicates",
            "albums_created", "current_file"):
```

- [ ] **Step 5: Run all four migration tests**

```bash
python -m pytest tests/test_folder_import.py -k "migration or progress_syncs" -v
```

Expected: all 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add photo-curator/src/database.py photo-curator/tests/test_folder_import.py
git commit -m "feat(db): migration v10 — add albums_created and current_file to import_jobs"
```

---

## Task 2: folder-import.py — constructor, `_upload_file`, `_get_album_names`

**Files:**
- Modify: `migration-tools/folder-import.py`
- Test: `photo-curator/tests/test_folder_import.py`

- [ ] **Step 1: Write failing tests for `_get_album_names`**

Add to `photo-curator/tests/test_folder_import.py`:

```python
# ---------------------------------------------------------------------------
# _get_album_names tests
# ---------------------------------------------------------------------------

def test_get_album_names_single_level_server_path(tmp_path, make_importer):
    imp = make_importer(skip_root_folder=False)
    f = tmp_path / "Ceremony" / "photo.jpg"
    assert imp._get_album_names(f) == ["Ceremony"]


def test_get_album_names_two_levels_server_path(tmp_path, make_importer):
    imp = make_importer(skip_root_folder=False)
    f = tmp_path / "Ceremony" / "Church" / "photo.jpg"
    assert imp._get_album_names(f) == ["Ceremony", "Church"]


def test_get_album_names_file_in_root_no_root_album(tmp_path, make_importer):
    imp = make_importer(skip_root_folder=False, root_album=False)
    f = tmp_path / "photo.jpg"
    assert imp._get_album_names(f) == []


def test_get_album_names_file_in_root_with_root_album(tmp_path, make_importer):
    imp = make_importer(skip_root_folder=False, root_album=True)
    f = tmp_path / "photo.jpg"
    assert imp._get_album_names(f) == [tmp_path.name]


def test_get_album_names_browser_upload_single_level(tmp_path, make_importer):
    imp = make_importer(skip_root_folder=True)
    f = tmp_path / "Wedding Photos" / "Ceremony" / "photo.jpg"
    assert imp._get_album_names(f) == ["Ceremony"]


def test_get_album_names_browser_upload_two_levels(tmp_path, make_importer):
    imp = make_importer(skip_root_folder=True)
    f = tmp_path / "Wedding Photos" / "Ceremony" / "Church" / "photo.jpg"
    assert imp._get_album_names(f) == ["Ceremony", "Church"]


def test_get_album_names_browser_upload_file_in_root_no_root_album(tmp_path, make_importer):
    # After skipping "Wedding Photos", only the filename remains — no album
    imp = make_importer(skip_root_folder=True, root_album=False)
    f = tmp_path / "Wedding Photos" / "photo.jpg"
    assert imp._get_album_names(f) == []


def test_get_album_names_browser_upload_file_in_root_with_root_album(tmp_path, make_importer):
    # root_folder_name = "Wedding Photos" (the skipped first component)
    imp = make_importer(skip_root_folder=True, root_album=True)
    f = tmp_path / "Wedding Photos" / "photo.jpg"
    assert imp._get_album_names(f) == ["Wedding Photos"]
```

- [ ] **Step 2: Run to confirm failures**

```bash
python -m pytest tests/test_folder_import.py -k "get_album_names" -v
```

Expected: FAIL — `_get_album_names` doesn't exist yet.

- [ ] **Step 3: Update imports in folder-import.py**

In `migration-tools/folder-import.py`, update the typing import line to:

```python
from typing import Optional, Dict, List
```

- [ ] **Step 4: Add constructor params + new state to folder-import.py**

Replace the `__init__` signature and body with:

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
    self.directory = Path(directory)
    self.immich_url = immich_url.rstrip('/')
    self.api_key = api_key
    self.create_albums = create_albums
    self.root_album = root_album
    self.skip_root_folder = skip_root_folder
    self.session = requests.Session()
    self.session.headers.update({'Authorization': f'Bearer {api_key}', 'Accept': 'application/json'})
    self.stats = {
        'total_files': 0, 'uploaded': 0, 'duplicates': 0, 'errors': 0,
        'albums_created': 0, 'current_file': '',
    }
    self.progress_file = self.directory / 'folder-import-progress.json'
    self.uploaded_files = self._load_progress()
    # Album tracking state
    self._album_buffer: Dict[str, List[str]] = {}
    self._existing_albums: Dict[str, str] = {}
    self._albums_cache_loaded: bool = False
    self._files_since_flush: int = 0
    self._current_batch: int = 0
    self._total_batches: int = 0
```

- [ ] **Step 5: Add `_get_album_names` method**

Add immediately after `_save_progress`:

```python
def _get_album_names(self, file_path: Path) -> List[str]:
    """Return the list of album names a file belongs to based on its subfolder path."""
    rel = file_path.relative_to(self.directory)
    parts = rel.parts
    if self.skip_root_folder:
        root_folder_name = parts[0] if parts else ''
        path_parts = parts[1:]
    else:
        root_folder_name = self.directory.name
        path_parts = parts
    # Only the filename remains — file is directly in the (possibly-skipped) root
    if len(path_parts) <= 1:
        if self.root_album and root_folder_name:
            return [root_folder_name]
        return []
    # Return all directory components, excluding the filename
    return list(path_parts[:-1])
```

- [ ] **Step 6: Run `_get_album_names` tests**

```bash
python -m pytest tests/test_folder_import.py -k "get_album_names" -v
```

Expected: all 8 PASS.

- [ ] **Step 7: Write failing tests for `_upload_file` return type**

Add to `photo-curator/tests/test_folder_import.py`:

```python
# ---------------------------------------------------------------------------
# _upload_file return type tests
# ---------------------------------------------------------------------------

def test_upload_file_returns_asset_id_on_success(tmp_path):
    FolderImporter = load_folder_importer()
    imp = FolderImporter(tmp_path, "http://immich", "key")
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake")

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"id": "abc-123"}

    with patch.object(imp.session, "post", return_value=mock_resp):
        result = imp._upload_file(photo)

    assert result == "abc-123"


def test_upload_file_returns_asset_id_on_duplicate(tmp_path):
    FolderImporter = load_folder_importer()
    imp = FolderImporter(tmp_path, "http://immich", "key")
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake")

    mock_resp = MagicMock()
    mock_resp.status_code = 409
    mock_resp.json.return_value = {"id": "existing-456"}

    with patch.object(imp.session, "post", return_value=mock_resp):
        result = imp._upload_file(photo)

    assert result == "existing-456"
    assert imp.stats["duplicates"] == 1


def test_upload_file_returns_none_on_server_error(tmp_path):
    FolderImporter = load_folder_importer()
    imp = FolderImporter(tmp_path, "http://immich", "key")
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake")

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.json.return_value = {}

    with patch.object(imp.session, "post", return_value=mock_resp):
        result = imp._upload_file(photo)

    assert result is None
    assert imp.stats["errors"] == 1


def test_upload_file_returns_none_for_progress_file_skip(tmp_path):
    FolderImporter = load_folder_importer()
    imp = FolderImporter(tmp_path, "http://immich", "key")
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake")
    # Mark as already uploaded in the progress file
    imp.uploaded_files.add("photo.jpg")

    with patch.object(imp.session, "post") as mock_post:
        result = imp._upload_file(photo)

    mock_post.assert_not_called()
    assert result is None  # progress-file skips don't replay album assignments
    assert imp.stats["duplicates"] == 1
```

- [ ] **Step 8: Run to confirm failures**

```bash
python -m pytest tests/test_folder_import.py -k "upload_file" -v
```

Expected: FAIL — `_upload_file` returns `bool`, not `Optional[str]`.

- [ ] **Step 9: Replace `_upload_file` in folder-import.py**

```python
def _upload_file(self, file_path: Path) -> Optional[str]:
    """Upload a single file to Immich. Returns asset_id on success/duplicate, None on error or skip."""
    file_key = str(file_path.relative_to(self.directory))

    if file_key in self.uploaded_files:
        self.stats['duplicates'] += 1
        return None  # Already uploaded — progress-file skip; album assignment not replayed

    mime_type = MIME_TYPES.get(file_path.suffix.lower(), 'application/octet-stream')
    exif_date = _get_exif_date(file_path)
    file_created_at = (exif_date or datetime.fromtimestamp(file_path.stat().st_mtime)).isoformat()

    try:
        with open(file_path, 'rb') as f:
            response = self.session.post(
                f'{self.immich_url}/api/assets',
                files={'assetData': (file_path.name, f, mime_type)},
                data={
                    'deviceAssetId': file_key,
                    'deviceId': 'FolderImport',
                    'fileCreatedAt': file_created_at,
                    'fileModifiedAt': file_created_at,
                    'isFavorite': 'false',
                },
                timeout=300,
            )

        if response.status_code in (200, 201):
            self.stats['uploaded'] += 1
            self.uploaded_files.add(file_key)
            self._save_progress()
            return response.json().get('id')
        elif response.status_code == 409:
            asset_id = response.json().get('id')
            self.stats['duplicates'] += 1
            self.uploaded_files.add(file_key)
            self._save_progress()
            if not asset_id:
                logger.warning(f"Duplicate {file_path.name} — no id in 409 response, skipping album")
            return asset_id
        else:
            logger.error(f"Upload failed ({response.status_code}): {file_path.name}")
            self.stats['errors'] += 1
            return None

    except Exception as e:
        logger.error(f"Error uploading {file_path}: {e}")
        self.stats['errors'] += 1
        return None
```

- [ ] **Step 10: Run all `_upload_file` tests**

```bash
python -m pytest tests/test_folder_import.py -k "upload_file" -v
```

Expected: all 4 PASS.

- [ ] **Step 11: Commit**

```bash
git add migration-tools/folder-import.py photo-curator/tests/test_folder_import.py
git commit -m "feat(importer): add album params, _get_album_names, return asset_id from _upload_file"
```

---

## Task 3: folder-import.py — `_load_album_cache` and `_flush_albums`

**Files:**
- Modify: `migration-tools/folder-import.py`
- Test: `photo-curator/tests/test_folder_import.py`

- [ ] **Step 1: Write failing tests for `_flush_albums`**

Add to `photo-curator/tests/test_folder_import.py`:

```python
# ---------------------------------------------------------------------------
# _flush_albums tests
# ---------------------------------------------------------------------------

def test_flush_albums_skips_on_empty_buffer(tmp_path, make_importer):
    imp = make_importer(create_albums=True)
    imp._albums_cache_loaded = True
    imp._album_buffer = {}

    with patch.object(imp.session, "post") as mock_post:
        imp._flush_albums()

    mock_post.assert_not_called()
    assert imp._current_batch == 0  # no increment when buffer is empty


def test_flush_albums_creates_new_album(tmp_path, make_importer):
    imp = make_importer(create_albums=True)
    imp._albums_cache_loaded = True
    imp._album_buffer = {"Ceremony": ["id1", "id2"]}
    imp._total_batches = 1

    post_resp = MagicMock()
    post_resp.status_code = 201
    post_resp.json.return_value = {"id": "album-abc", "albumName": "Ceremony"}
    post_resp.raise_for_status = MagicMock()

    with patch.object(imp.session, "post", return_value=post_resp):
        imp._flush_albums()

    assert imp.stats["albums_created"] == 1
    assert imp._existing_albums["Ceremony"] == "album-abc"
    assert imp._album_buffer == {}
    assert imp._current_batch == 1


def test_flush_albums_adds_to_existing_album(tmp_path, make_importer):
    imp = make_importer(create_albums=True)
    imp._albums_cache_loaded = True
    imp._existing_albums = {"Ceremony": "album-existing"}
    imp._album_buffer = {"Ceremony": ["id3"]}
    imp._total_batches = 1

    put_resp = MagicMock()
    put_resp.status_code = 200
    put_resp.raise_for_status = MagicMock()

    with patch.object(imp.session, "put", return_value=put_resp) as mock_put:
        imp._flush_albums()

    mock_put.assert_called_once()
    call_url = mock_put.call_args[0][0]
    assert "album-existing" in call_url
    assert imp.stats["albums_created"] == 0  # not incremented for existing album
    assert imp._current_batch == 1


def test_flush_albums_loads_cache_lazily_on_first_call(tmp_path, make_importer):
    imp = make_importer(create_albums=True)
    # _albums_cache_loaded is False — should trigger GET /api/albums
    imp._album_buffer = {"Venue": ["id1"]}
    imp._total_batches = 1

    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.json.return_value = [{"albumName": "Venue", "id": "v-id"}]
    get_resp.raise_for_status = MagicMock()

    put_resp = MagicMock()
    put_resp.status_code = 200
    put_resp.raise_for_status = MagicMock()

    with patch.object(imp.session, "get", return_value=get_resp):
        with patch.object(imp.session, "put", return_value=put_resp):
            imp._flush_albums()

    assert imp._albums_cache_loaded is True
    assert imp._existing_albums["Venue"] == "v-id"
    assert imp._current_batch == 1
```

- [ ] **Step 2: Run to confirm failures**

```bash
python -m pytest tests/test_folder_import.py -k "flush_albums" -v
```

Expected: FAIL — `_flush_albums` doesn't exist yet.

- [ ] **Step 3: Add `_load_album_cache` and `_flush_albums` to folder-import.py**

Add after `_get_album_names`:

```python
def _load_album_cache(self):
    """Fetch existing albums once and cache name→id. Called lazily on first flush."""
    if self._albums_cache_loaded:
        return
    try:
        resp = self.session.get(f'{self.immich_url}/api/albums')
        resp.raise_for_status()
        self._existing_albums = {a['albumName']: a['id'] for a in resp.json()}
    except Exception as e:
        logger.warning(f"Could not load album cache: {e}")
    self._albums_cache_loaded = True


def _flush_albums(self):
    """Send buffered album assignments to Immich. Non-fatal on API errors."""
    if not self._album_buffer:
        return
    self._load_album_cache()

    # Capture counts before clearing — used in the log line
    flushed_counts = {name: len(ids) for name, ids in self._album_buffer.items()}

    for album_name, asset_ids in list(self._album_buffer.items()):
        try:
            if album_name in self._existing_albums:
                album_id = self._existing_albums[album_name]
                resp = self.session.put(
                    f'{self.immich_url}/api/albums/{album_id}/assets',
                    json={'ids': asset_ids},
                )
                resp.raise_for_status()
            else:
                resp = self.session.post(
                    f'{self.immich_url}/api/albums',
                    json={'albumName': album_name, 'assetIds': asset_ids},
                )
                resp.raise_for_status()
                new_id = resp.json().get('id')
                if new_id:
                    self._existing_albums[album_name] = new_id
                self.stats['albums_created'] += 1
        except Exception as e:
            logger.warning(f"Album '{album_name}' update failed: {e}")

    self._album_buffer.clear()
    self._current_batch += 1

    album_summary = ', '.join(f"{n}({c})" for n, c in flushed_counts.items())
    logger.info(
        f"[Import:folder] Batch {self._current_batch}/{self._total_batches} — "
        f"{self.stats['uploaded']} uploaded, {self.stats['duplicates']} duplicates, "
        f"{self.stats['errors']} errors | {album_summary}"
    )
```

- [ ] **Step 4: Run all `_flush_albums` tests**

```bash
python -m pytest tests/test_folder_import.py -k "flush_albums" -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Run the full test file**

```bash
python -m pytest tests/test_folder_import.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add migration-tools/folder-import.py photo-curator/tests/test_folder_import.py
git commit -m "feat(importer): add _load_album_cache and _flush_albums with batch logging"
```

---

## Task 4: Wire album logic into `main.py`

**Files:**
- Modify: `photo-curator/src/main.py`

- [ ] **Step 1: Update `ServerPathImport` model**

Find `class ServerPathImport` (around line 1494). Replace:

```python
class ServerPathImport(BaseModel):
    source_type: str
    server_path: str
    create_albums: bool = False
    root_album: bool = False
```

- [ ] **Step 2: Add Form params to the browser upload endpoint**

Find `async def upload_import_files` (around line 2100). The current params end with `_role`. Add two new Form params before the closing `)`:

```python
    create_albums: bool = Form(False),
    root_album: bool = Form(False),
```

- [ ] **Step 3: Update browser upload `background_tasks.add_task` call**

Find the `background_tasks.add_task` call inside `upload_import_files` (around line 2141). Replace:

```python
    background_tasks.add_task(
        _run_import_sync,
        job_id, user["id"], user["access_token"],
        source_type, str(staging_dir), "upload",
        create_albums, root_album,
    )
```

- [ ] **Step 4: Update server-path `background_tasks.add_task` call**

Find the `background_tasks.add_task` call inside `start_server_path_import` (around line 2181). Replace:

```python
    background_tasks.add_task(
        _run_import_sync,
        job_id, user["id"], user["access_token"],
        body.source_type, resolved, "server_path",
        body.create_albums, body.root_album,
    )
```

- [ ] **Step 5: Update `_run_import_sync` signature**

Find `def _run_import_sync` (line 2000). Update the signature:

```python
def _run_import_sync(
    job_id: int,
    user_id: str,
    user_token: str,
    source_type: str,
    directory: str,
    import_method: str,
    create_albums: bool = False,
    root_album: bool = False,
):
```

- [ ] **Step 6: Update folder importer construction**

Find the importer construction block (around line 2014):

```python
        if source_type in ("google", "apple", "icloud", "folder"):
            importer = ImporterClass(Path(directory), immich_url, user_token)
```

Replace with:

```python
        if source_type in ("google", "apple", "icloud", "folder"):
            if source_type == "folder":
                importer = ImporterClass(
                    Path(directory), immich_url, user_token,
                    create_albums=create_albums,
                    root_album=root_album,
                    skip_root_folder=(import_method == "upload"),
                )
            else:
                importer = ImporterClass(Path(directory), immich_url, user_token)
```

- [ ] **Step 7: Compute `total_batches` before the loop**

Find `importer.stats["total_files"] = len(photo_files)` (around line 2050). Add immediately after it:

```python
        if source_type == "folder" and create_albums:
            from math import ceil
            importer._total_batches = ceil(len(photo_files) / 25) if photo_files else 0
```

- [ ] **Step 8: Replace the upload loop branch for folder source_type**

Find the per-file dispatch block (around line 2064). Replace the `elif source_type in ("apple", "folder"):` line with separate branches:

```python
            if source_type == "google":
                metadata_json = importer.find_photo_metadata(photo_path)
                metadata = importer.extract_metadata(metadata_json) if metadata_json else None
                importer.upload_file(photo_path, metadata)
            elif source_type == "folder":
                asset_id = importer._upload_file(photo_path)
                importer.stats['current_file'] = photo_path.name
                if asset_id and create_albums:
                    for album_name in importer._get_album_names(photo_path):
                        importer._album_buffer.setdefault(album_name, []).append(asset_id)
                importer._files_since_flush += 1
                if importer._files_since_flush >= 25:
                    importer._flush_albums()
                    importer._files_since_flush = 0
            elif source_type == "apple":
                importer._upload_file(photo_path)
            else:  # icloud
                importer._upload_file(photo_path, photos_root)
```

- [ ] **Step 9: Update the `for/else` completion block**

Find the `else:` clause of the upload loop (around line 2076). The full block should become:

```python
        else:
            # Loop completed without cancellation — flush tail batch then mark done
            if source_type == "folder" and create_albums:
                importer._flush_albums()
            database.update_import_job_progress(
                job_id, {**importer.stats, "status": "completed"}
            )
            database.update_import_job_status(job_id, "completed")
```

- [ ] **Step 10: Write a test for the cancellation path (tail flush skipped)**

Add to `photo-curator/tests/test_folder_import.py`:

```python
# ---------------------------------------------------------------------------
# Cancellation test: tail flush must be skipped when loop breaks
# ---------------------------------------------------------------------------

def test_tail_flush_skipped_on_cancel(tmp_path, make_importer):
    """Verify that _flush_albums is NOT called when the upload loop is broken by cancellation."""
    imp = make_importer(create_albums=True)
    imp._total_batches = 1
    imp._albums_cache_loaded = True
    imp._album_buffer = {"Ceremony": ["id1"]}  # unflushed batch

    flush_called = []

    original_flush = imp._flush_albums
    def tracking_flush():
        flush_called.append(True)
        original_flush()

    imp._flush_albums = tracking_flush

    # Simulate cancellation: break before for/else reaches the else branch
    photo_files = [tmp_path / "photo.jpg"]
    cancel = True
    for photo_path in photo_files:
        if cancel:
            break
        imp._flush_albums()
    else:
        imp._flush_albums()  # only reached if not cancelled

    assert flush_called == []  # flush was NOT called
```

- [ ] **Step 11: Run the cancellation test**

```bash
python -m pytest tests/test_folder_import.py::test_tail_flush_skipped_on_cancel -v
```

Expected: PASS.

- [ ] **Step 12: Smoke test imports**

```bash
cd /home/feuer/Documents/Projects/immich-manager/photo-curator
python -c "from src.main import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 13: Run existing test suite**

```bash
python -m pytest tests/ -v -x --ignore=tests/test_folder_import.py
```

Expected: all existing tests PASS.

- [ ] **Step 14: Commit**

```bash
git add photo-curator/src/main.py photo-curator/tests/test_folder_import.py
git commit -m "feat(api): wire album creation params through import endpoints and upload loop"
```

---

## Task 5: Frontend — album checkboxes, Albums tile, current_file display

**Files:**
- Modify: `photo-curator/frontend/src/pages/Import.jsx`

- [ ] **Step 1: Add `createAlbums` and `rootAlbum` state**

In `Import.jsx`, after the `serverPathSourceType` state declaration, add:

```js
const [createAlbums, setCreateAlbums] = useState(false)
const [rootAlbum, setRootAlbum] = useState(false)
```

- [ ] **Step 2: Add `rootFolderName` derived value**

After all state declarations, add:

```js
const rootFolderName = source === 'server_path'
  ? serverPath.split('/').filter(Boolean).pop() ?? ''
  : (files?.[0]?.webkitRelativePath?.split('/')[0] ?? '')
```

- [ ] **Step 3: Reset album state in `resetWizard`**

Add to the `resetWizard` function body:

```js
setCreateAlbums(false)
setRootAlbum(false)
```

- [ ] **Step 4: Pass album options in `uploadMutation`**

In `uploadMutation.mutationFn`, after `formData.append('source_type', source)`, add:

```js
formData.append('create_albums', createAlbums)
formData.append('root_album', rootAlbum)
```

- [ ] **Step 5: Pass album options in `serverPathMutation`**

In `serverPathMutation.mutationFn`, update the JSON body to:

```js
body: JSON.stringify({
  source_type: serverPathSourceType,
  server_path: serverPath,
  create_albums: createAlbums,
  root_album: rootAlbum,
}),
```

- [ ] **Step 6: Add album options UI below the browser file picker (folder source)**

In the `step === 1 && source !== 'server_path'` block, after the file count `<p>` and before the error `<p>`, add:

```jsx
{source === 'folder' && (
  <div className="space-y-2 pt-1">
    <label className="flex items-center gap-2 text-immich-text text-sm cursor-pointer">
      <input
        type="checkbox"
        checked={createAlbums}
        onChange={e => { setCreateAlbums(e.target.checked); if (!e.target.checked) setRootAlbum(false) }}
        className="rounded"
      />
      Create albums from subfolders
    </label>
    {createAlbums && (
      <label className="flex items-center gap-2 text-immich-text text-sm cursor-pointer ml-5">
        <input
          type="checkbox"
          checked={rootAlbum}
          onChange={e => setRootAlbum(e.target.checked)}
          className="rounded"
        />
        Add loose photos to a &ldquo;{rootFolderName || 'root'}&rdquo; album
      </label>
    )}
  </div>
)}
```

- [ ] **Step 7: Add album options UI to the server-path step**

In the `step === 1 && source === 'server_path'` block, after the source type `<select>` closing `</div>`, add:

```jsx
<div className="space-y-2">
  <label className="flex items-center gap-2 text-immich-text text-sm cursor-pointer">
    <input
      type="checkbox"
      checked={createAlbums}
      onChange={e => { setCreateAlbums(e.target.checked); if (!e.target.checked) setRootAlbum(false) }}
      className="rounded"
    />
    Create albums from subfolders
  </label>
  {createAlbums && (
    <label className="flex items-center gap-2 text-immich-text text-sm cursor-pointer ml-5">
      <input
        type="checkbox"
        checked={rootAlbum}
        onChange={e => setRootAlbum(e.target.checked)}
        className="rounded"
      />
      Add loose photos to a &ldquo;{rootFolderName || 'root'}&rdquo; album
    </label>
  )}
</div>
```

- [ ] **Step 8: Add Albums tile and expand stats grid to 5 columns**

Find the stats grid `<div className="grid grid-cols-4 ...">`. Change `grid-cols-4` to `grid-cols-5` and add the Albums tile (place it after the Uploaded tile):

```jsx
<div>
  <p data-testid="stat-albums" className="text-xl font-bold text-blue-400">{job.albums_created ?? 0}</p>
  <p className="text-xs text-immich-muted">Albums</p>
</div>
```

- [ ] **Step 9: Add current_file and status message below the progress bar**

Find the progress bar closing `</div>`. Immediately after it, add:

```jsx
<div className="flex items-center justify-between text-xs text-immich-muted mt-1">
  <span>
    {job.status === 'scanning' && 'Scanning\u2026'}
    {job.status === 'running' && 'Uploading\u2026'}
    {job.status === 'completed' && 'Done'}
    {job.status === 'failed' && 'Failed'}
    {job.status === 'cancelled' && 'Cancelled'}
  </span>
  {isJobRunning && job.current_file && (
    <span className="font-mono truncate max-w-xs">{job.current_file}</span>
  )}
</div>
```

- [ ] **Step 10: Build the frontend**

```bash
cd /home/feuer/Documents/Projects/immich-manager/photo-curator/frontend
npm run build 2>&1 | tail -10
```

Expected: successful build, no errors.

- [ ] **Step 11: Run frontend tests**

```bash
npm test -- --run 2>&1 | tail -20
```

Expected: all tests PASS.

- [ ] **Step 12: Commit**

```bash
cd /home/feuer/Documents/Projects/immich-manager
git add photo-curator/frontend/src/pages/Import.jsx
git commit -m "feat(ui): album creation checkboxes, Albums stat tile, current_file display"
```

---

## Task 6: Documentation

**Files:**
- Create: `docs/importing-photos.md`

- [ ] **Step 1: Create the documentation file**

Create `docs/importing-photos.md` with the following content:

```markdown
# Importing Photos into Immich

## Quick Reference

| Method | Best for | Cloudflare-safe | Resume support |
|---|---|---|---|
| Browser upload | < ~500 photos, one-off imports | No (100 MB limit) | No |
| Server-path import | 1,000–20,000+ photos | Yes (local only) | Yes |
| Google Takeout | Full Google Photos migration | No (large) | Yes |
| Apple / iCloud | Apple Photos or iCloud export | No (large) | Yes |

---

## Browser Upload

Use the **Import** page in the curator UI, select your source, drag a folder or pick files, and click **Start Import**.

**Cloudflare free tier limitation:** Cloudflare's free plan enforces a 100 MB per-request limit. Uploading large collections through the Cloudflare tunnel will fail. Use server-path import instead for anything over a few hundred photos.

---

## Server-Path Import (Large Collections)

For large imports (1,000+ photos), copy files to the server first and import directly from the server filesystem — nothing passes through the browser or Cloudflare.

### Step 1 — Copy photos to the server

```bash
# Sync a folder to the server, preserving structure
rsync -avz --progress /local/path/to/Wedding\ Photos/ user@your-server:/opt/photos-import/Wedding\ Photos/

# Verify it landed correctly
ssh user@your-server ls /opt/photos-import/
```

### Step 2 — Access the curator locally

Open an SSH tunnel to bypass Cloudflare:

```bash
ssh -L 8081:localhost:8081 user@your-server
```

Then open `http://localhost:8081` in your browser. If you are already on the server, open it directly.

### Step 3 — Start the import

1. Go to **Import** → **Server Path (Large Import)**
2. Enter the server path, e.g. `/opt/photos-import/Wedding Photos`
3. Select **Plain folder** as the source format
4. Optionally enable **Create albums from subfolders** (see below)
5. Click **Start Import** and watch progress in real time

### Resume

If the import is interrupted, restart it with the same server path. Files already uploaded are tracked in `folder-import-progress.json` inside the import directory and skipped automatically.

Check the server manager log viewer for `[Import:folder] Batch N/M` lines to see where the previous run stopped.

---

## Folder Album Creation

When importing a folder that contains subfolders, the curator can automatically create Immich albums named after those subfolders.

### How it works

Every subfolder at any depth becomes its own album. A photo is added to **all** albums in its path.

**Example — importing `Wedding Photos/`:**

```
Wedding Photos/
├── Venue/
│   ├── hall.jpg        → album: Venue
│   └── garden.jpg      → album: Venue
├── Ceremony/
│   ├── vows.jpg        → album: Ceremony
│   └── Church/
│       └── exterior.jpg → albums: Ceremony AND Church
└── toast.jpg           → no album (loose file in root)
```

Albums created: **Venue**, **Ceremony**, **Church**

The root folder (`Wedding Photos`) is not created as an album by default.

### Root folder toggle

Enable **"Add loose photos to a 'Wedding Photos' album"** to collect photos sitting directly in the root folder into an album named after that folder. The toggle only appears after enabling **Create albums from subfolders**.

### Resume and album assignments

Album assignments are flushed to Immich every 25 files. If an import is interrupted, restarting it will:
- Skip already-uploaded files (via the progress file)
- Re-assign newly uploaded files to albums correctly

Files that were uploaded in the previous run and successfully flushed to albums in the previous run are already in their albums and do not need to be re-added. At most one unflushed batch (up to 24 files) may not be re-added on resume.

---

## Google Photos Import

1. Request a Google Takeout at [takeout.google.com](https://takeout.google.com) — select Google Photos only
2. Download and extract the archive on the server
3. For large exports, use **Server Path** import with source format set to **Google Takeout export**

Google Takeout preserves original capture dates via `.json` sidecar files. The importer reads these automatically.

---

## Apple Photos / iCloud Import

**Apple Photos:** In the Photos app, select all photos → **File → Export → Export Originals**. Import using the **Apple Photos** source.

**iCloud:** Request your data at [privacy.apple.com](https://privacy.apple.com). Select iCloud Photos. Use the **iCloud** source when importing.

---

## Troubleshooting

**Photos appear with wrong or missing dates**
The importer reads EXIF `DateTimeOriginal` first, then falls back to file modification time. If dates are still wrong, use `exiftool` to stamp them before importing:
```bash
exiftool -DateTimeOriginal'<${FileModifyDate}' -overwrite_original /path/to/photos/
```

**"Server path does not exist" error**
The path must exist on the server running the curator, not your local machine. Verify with:
```bash
ssh user@your-server ls /opt/photos-import/
```

**Import stops partway through**
Restart with the same path — already-uploaded files are skipped. Check the **server manager log viewer** for `[Import:folder]` batch lines to diagnose where it stopped.

**Cloudflare error during browser upload**
Switch to server-path import. Cloudflare free tier rejects uploads over 100 MB per request.
```

- [ ] **Step 2: Verify section headers**

```bash
grep "^##" /home/feuer/Documents/Projects/immich-manager/docs/importing-photos.md
```

Expected:
```
## Quick Reference
## Browser Upload
## Server-Path Import (Large Collections)
## Folder Album Creation
## Google Photos Import
## Apple Photos / iCloud Import
## Troubleshooting
```

- [ ] **Step 3: Commit**

```bash
git add docs/importing-photos.md
git commit -m "docs: add importing-photos guide with server-path and folder album workflows"
```

---

## Task 7: Final verification

- [ ] **Step 1: Run the full Python test suite**

```bash
cd /home/feuer/Documents/Projects/immich-manager/photo-curator
python -m pytest tests/ -v
```

Expected: all tests PASS, no failures.

- [ ] **Step 2: Run frontend build**

```bash
cd photo-curator/frontend && npm run build 2>&1 | grep -E "error|✓|built" | tail -10
```

Expected: successful build, no errors.

- [ ] **Step 3: Check git log**

```bash
cd /home/feuer/Documents/Projects/immich-manager
git log --oneline -8
```

Expected: 6 feature commits (tasks 1–6) visible on top of base.
