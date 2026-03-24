# Duplicate Scanner & Cleaner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stub Duplicates page with a fully independent duplicate scanner that offers Quick Scan (Immich native) and Deep Scan (pHash, date-range, background job) modes and a side-by-side review UI for resolving groups.

**Architecture:** A `DedupScanner` class (single module-level singleton, initialized at startup) manages job state for both scan types. Database methods handle all persistence. Eight new API routes in `main.py` expose the scanner to the React frontend, which replaces the existing stub `Duplicates.jsx` with a two-zone Scan Panel + Results Panel.

**Tech Stack:** Python 3.11, FastAPI, SQLite (via existing `Database` wrapper), `imagehash` (already installed), React 18, TanStack Query v5, Tailwind CSS, Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-03-24-duplicate-scanner-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `photo-curator/src/database.py` | Migration v9 + 9 new DB methods |
| Create | `photo-curator/src/dedup_scanner.py` | DedupScanner class (both scan types) |
| Modify | `photo-curator/src/main.py` | 8 new API routes + startup init |
| Replace | `photo-curator/frontend/src/pages/Duplicates.jsx` | Full page: Scan Panel + Results Panel + Detail view |
| Create | `photo-curator/tests/test_dedup_database.py` | DB method unit tests |
| Create | `photo-curator/tests/test_dedup_scanner.py` | DedupScanner pure-logic unit tests |
| Create | `photo-curator/tests/test_dedup_routes.py` | API route integration tests |
| Create | `photo-curator/frontend/src/test/Duplicates.test.jsx` | Frontend component tests |

---

## Task 1: Database — Migration v9 + New Methods

**Files:**
- Modify: `photo-curator/src/database.py`
- Create: `photo-curator/tests/test_dedup_database.py`

- [ ] **Step 1: Write failing tests for DB methods**

Create `photo-curator/tests/test_dedup_database.py`:

```python
"""Tests for dedup-related Database methods (migration v9)."""
import pytest
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.database import Database


@pytest.fixture
def db(tmp_path):
    d = Database(db_path=str(tmp_path / "test.db"))
    return d


def test_migration_v9_creates_dedup_scans_table(db):
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dedup_scans'")
        assert cursor.fetchone() is not None


def test_migration_v9_creates_dedup_asset_metadata_table(db):
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dedup_asset_metadata'")
        assert cursor.fetchone() is not None


def test_migration_v9_adds_columns_to_duplicate_groups(db):
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(duplicate_groups)")
        cols = {row['name'] for row in cursor.fetchall()}
    assert 'scan_id' in cols
    assert 'user_id' in cols
    assert 'resolved' in cols
    assert 'recommended_keep_id' in cols


def test_create_and_get_dedup_scan(db):
    db.create_dedup_scan("scan-1", "user-1", "deep", date_from="2024-01-01", date_to="2024-12-31")
    status = db.get_dedup_scan_status("user-1")
    assert status is not None
    assert status['id'] == "scan-1"
    assert status['mode'] == "deep"
    assert status['status'] == "running"
    assert status['date_from'] == "2024-01-01"
    assert status['date_to'] == "2024-12-31"


def test_get_dedup_scan_status_returns_none_when_no_scans(db):
    assert db.get_dedup_scan_status("user-99") is None


def test_update_dedup_scan_status(db):
    db.create_dedup_scan("scan-2", "user-1", "quick")
    db.update_dedup_scan("scan-2", status="complete", groups_found=3)
    status = db.get_dedup_scan_status("user-1")
    assert status['status'] == "complete"
    assert status['groups_found'] == 3


def test_update_dedup_scan_hashed(db):
    db.create_dedup_scan("scan-3", "user-1", "deep")
    db.update_dedup_scan("scan-3", total_assets=100, hashed=25)
    status = db.get_dedup_scan_status("user-1")
    assert status['total_assets'] == 100
    assert status['hashed'] == 25


def test_upsert_dedup_asset_metadata(db):
    asset = {
        'id': 'asset-1',
        'originalFileName': 'photo.jpg',
        'fileCreatedAt': '2024-06-01T10:00:00Z',
        'exifInfo': {
            'exifImageWidth': 4032, 'exifImageHeight': 3024,
            'fileSizeInByte': 4200000,
            'make': 'Apple', 'model': 'iPhone 15 Pro',
        }
    }
    db.upsert_dedup_asset_metadata("user-1", asset)
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM dedup_asset_metadata WHERE asset_id = 'asset-1'")
        row = dict(cursor.fetchone())
    assert row['filename'] == 'photo.jpg'
    assert row['width'] == 4032
    assert row['file_size_bytes'] == 4200000
    assert row['camera_model'] == 'iPhone 15 Pro'


def test_save_and_get_dedup_groups(db):
    db.create_dedup_scan("scan-4", "user-1", "deep")
    db.save_dedup_group("scan-4", "user-1", ["a1", "a2"], "a1", "hash-abc")
    db.save_dedup_group("scan-4", "user-1", ["a3", "a4", "a5"], "a3", "hash-xyz")
    result = db.get_dedup_groups("user-1")
    assert result['total_groups'] == 2
    groups = result['groups']
    assert len(groups) == 2
    asset_id_sets = [set(json.loads(g['asset_ids'])) for g in groups]
    assert {"a1", "a2"} in asset_id_sets


def test_get_dedup_groups_excludes_resolved_by_default(db):
    db.create_dedup_scan("scan-5", "user-1", "deep")
    db.save_dedup_group("scan-5", "user-1", ["a1", "a2"], "a1", "hash-1")
    db.save_dedup_group("scan-5", "user-1", ["a3", "a4"], "a3", "hash-2")
    # resolve the first group
    result = db.get_dedup_groups("user-1")
    group_id = result['groups'][0]['id']
    db.resolve_dedup_group(group_id)
    result2 = db.get_dedup_groups("user-1")
    assert result2['total_groups'] == 1


def test_get_dedup_groups_includes_resolved_when_flag_set(db):
    db.create_dedup_scan("scan-6", "user-1", "deep")
    db.save_dedup_group("scan-6", "user-1", ["a1", "a2"], "a1", "hash-1")
    result = db.get_dedup_groups("user-1")
    gid = result['groups'][0]['id']
    db.resolve_dedup_group(gid)
    result2 = db.get_dedup_groups("user-1", include_resolved=True)
    assert result2['total_groups'] == 1


def test_get_dedup_groups_user_isolation(db):
    db.create_dedup_scan("scan-7", "user-A", "deep")
    db.save_dedup_group("scan-7", "user-A", ["a1", "a2"], "a1", "hash-1")
    result = db.get_dedup_groups("user-B")
    assert result['total_groups'] == 0


def test_dismiss_dedup_group(db):
    db.create_dedup_scan("scan-8", "user-1", "deep")
    db.save_dedup_group("scan-8", "user-1", ["a1", "a2"], "a1", "hash-1")
    result = db.get_dedup_groups("user-1")
    gid = result['groups'][0]['id']
    db.dismiss_dedup_group(gid)
    result2 = db.get_dedup_groups("user-1")
    assert result2['total_groups'] == 0


def test_upsert_perceptual_hash_inserts_new_row(db):
    db.upsert_perceptual_hash("asset-new", "user-1", 2024, 6, "abc123hash")
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT perceptual_hash, score FROM photo_scores WHERE asset_id = 'asset-new'")
        row = cursor.fetchone()
    assert row['perceptual_hash'] == "abc123hash"
    assert row['score'] == 0.0  # sentinel for hash-only rows


def test_upsert_perceptual_hash_updates_existing_without_clobbering_score(db):
    # First insert a full score row
    db.save_photo_score("asset-existing", "user-1", 2024, 6, {
        'score': 0.85, 'technical_quality': 0.9, 'blur_score': 0.8,
        'exposure_score': 0.9, 'composition_score': 0.7,
        'face_score': 0.5, 'face_count': 0,
        'perceptual_hash': None, 'width': 1920, 'height': 1080, 'megapixels': 2.07,
    })
    db.upsert_perceptual_hash("asset-existing", "user-1", 2024, 6, "newhashshould")
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT perceptual_hash, score FROM photo_scores WHERE asset_id = 'asset-existing'")
        row = cursor.fetchone()
    assert row['perceptual_hash'] == "newhashshould"
    assert row['score'] == pytest.approx(0.85)  # NOT clobbered
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd photo-curator && python -m pytest tests/test_dedup_database.py -v 2>&1 | head -30
```
Expected: errors about missing methods/tables.

- [ ] **Step 3: Add migration v9 to `database.py`**

In `photo-curator/src/database.py`, find the `MIGRATIONS` list (around line 17) and append after the last entry (version 8):

```python
    # Version 9: standalone duplicate scanner tables
    (9, "add dedup scanner tables", [
        """CREATE TABLE IF NOT EXISTS dedup_scans (
            id              TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL,
            mode            TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'running',
            date_from       TEXT,
            date_to         TEXT,
            total_assets    INTEGER DEFAULT 0,
            hashed          INTEGER DEFAULT 0,
            groups_found    INTEGER DEFAULT 0,
            error_message   TEXT,
            started_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at    DATETIME
        )""",
        "CREATE INDEX IF NOT EXISTS idx_dedup_scans_user ON dedup_scans(user_id)",
        """CREATE TABLE IF NOT EXISTS dedup_asset_metadata (
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
        )""",
        "CREATE INDEX IF NOT EXISTS idx_dedup_meta_user ON dedup_asset_metadata(user_id)",
        "ALTER TABLE duplicate_groups ADD COLUMN scan_id TEXT",
        "ALTER TABLE duplicate_groups ADD COLUMN user_id TEXT",
        "ALTER TABLE duplicate_groups ADD COLUMN resolved INTEGER DEFAULT 0",
        "ALTER TABLE duplicate_groups ADD COLUMN recommended_keep_id TEXT",
        "CREATE INDEX IF NOT EXISTS idx_dup_groups_user ON duplicate_groups(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_dup_groups_scan ON duplicate_groups(scan_id)",
    ]),
```

- [ ] **Step 4: Add DB methods to `Database` class in `database.py`**

Append these methods to the `Database` class (after the last existing method):

```python
    # ------------------------------------------------------------------
    # Dedup Scanner
    # ------------------------------------------------------------------

    def create_dedup_scan(
        self,
        scan_id: str,
        user_id: str,
        mode: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO dedup_scans (id, user_id, mode, status, date_from, date_to)
                   VALUES (?, ?, ?, 'running', ?, ?)""",
                (scan_id, user_id, mode, date_from, date_to),
            )

    def update_dedup_scan(self, scan_id: str, **kwargs) -> None:
        allowed = {'status', 'total_assets', 'hashed', 'groups_found', 'error_message', 'completed_at'}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        if 'status' in fields and fields['status'] in ('complete', 'failed', 'cancelled'):
            fields.setdefault('completed_at', datetime.now().isoformat())
        set_clause = ', '.join(f"{k} = ?" for k in fields)
        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE dedup_scans SET {set_clause} WHERE id = ?",
                (*fields.values(), scan_id),
            )

    def get_dedup_scan_status(self, user_id: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM dedup_scans WHERE user_id = ? ORDER BY started_at DESC LIMIT 1",
                (user_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def upsert_dedup_asset_metadata(self, user_id: str, asset: Dict) -> None:
        exif = asset.get('exifInfo') or {}
        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO dedup_asset_metadata
                   (asset_id, user_id, filename, date_taken, width, height,
                    file_size_bytes, camera_make, camera_model, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(asset_id) DO UPDATE SET
                       filename=excluded.filename, date_taken=excluded.date_taken,
                       width=excluded.width, height=excluded.height,
                       file_size_bytes=excluded.file_size_bytes,
                       camera_make=excluded.camera_make, camera_model=excluded.camera_model,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    asset['id'], user_id,
                    asset.get('originalFileName'),
                    asset.get('fileCreatedAt'),
                    exif.get('exifImageWidth'), exif.get('exifImageHeight'),
                    exif.get('fileSizeInByte'),
                    exif.get('make'), exif.get('model'),
                ),
            )

    def save_dedup_group(
        self,
        scan_id: str,
        user_id: str,
        asset_ids: List[str],
        recommended_keep_id: str,
        group_hash: str,
    ) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO duplicate_groups
                   (scan_id, user_id, group_hash, asset_ids, recommended_keep_id, resolved)
                   VALUES (?, ?, ?, ?, ?, 0)""",
                (scan_id, user_id, group_hash, json.dumps(asset_ids), recommended_keep_id),
            )

    def get_dedup_groups(
        self,
        user_id: str,
        include_resolved: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            resolved_filter = "" if include_resolved else "AND resolved = 0"
            cursor.execute(
                f"SELECT COUNT(*) as cnt FROM duplicate_groups WHERE user_id = ? {resolved_filter}",
                (user_id,),
            )
            total = cursor.fetchone()['cnt']

            cursor.execute(
                f"""SELECT id, scan_id, group_hash, asset_ids, recommended_keep_id, resolved, detected_at
                    FROM duplicate_groups
                    WHERE user_id = ? {resolved_filter}
                    ORDER BY detected_at DESC LIMIT ? OFFSET ?""",
                (user_id, limit, offset),
            )
            rows = [dict(r) for r in cursor.fetchall()]

        # Enrich each group with per-asset metadata
        groups = []
        for row in rows:
            asset_ids = json.loads(row['asset_ids'])
            assets = self._fetch_asset_metadata_list(asset_ids)
            savings = sum(
                a.get('file_size_bytes') or 0
                for a in assets
                if a['asset_id'] != row['recommended_keep_id']
            )
            groups.append({**row, 'assets': assets, 'savings_bytes': savings})

        total_savings = sum(g['savings_bytes'] for g in groups)
        total_removable = sum(len(json.loads(g['asset_ids'])) - 1 for g in groups)
        return {
            'groups': groups,
            'total_groups': total,
            'total_removable_photos': total_removable,
            'total_savings_bytes': total_savings,
        }

    def _fetch_asset_metadata_list(self, asset_ids: List[str]) -> List[Dict]:
        if not asset_ids:
            return []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(asset_ids))
            cursor.execute(
                f"SELECT * FROM dedup_asset_metadata WHERE asset_id IN ({placeholders})",
                asset_ids,
            )
            meta_map = {row['asset_id']: dict(row) for row in cursor.fetchall()}
        return [
            {
                **meta_map.get(aid, {'asset_id': aid}),
                'asset_id': aid,
                'thumbnail_url': f'/api/thumbnail/{aid}',
                'megapixels': round(
                    (meta_map.get(aid, {}).get('width') or 0)
                    * (meta_map.get(aid, {}).get('height') or 0)
                    / 1_000_000,
                    1,
                ) if meta_map.get(aid, {}).get('width') else None,
            }
            for aid in asset_ids
        ]

    def resolve_dedup_group(self, group_id: int) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE duplicate_groups SET resolved = 1 WHERE id = ?", (group_id,)
            )

    def dismiss_dedup_group(self, group_id: int) -> None:
        self.resolve_dedup_group(group_id)  # same DB operation, different semantics

    def upsert_perceptual_hash(
        self, asset_id: str, user_id: str, year: int, month: int, phash: str
    ) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM photo_scores WHERE asset_id = ?", (asset_id,)
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "UPDATE photo_scores SET perceptual_hash = ? WHERE asset_id = ?",
                    (phash, asset_id),
                )
            else:
                cursor.execute(
                    """INSERT INTO photo_scores
                       (asset_id, user_id, year, month, score, perceptual_hash)
                       VALUES (?, ?, ?, ?, 0.0, ?)""",
                    (asset_id, user_id, year, month, phash),
                )
```

- [ ] **Step 5: Run tests and verify they pass**

```bash
cd photo-curator && python -m pytest tests/test_dedup_database.py -v
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add photo-curator/src/database.py photo-curator/tests/test_dedup_database.py
git commit -m "feat(dedup): add DB migration v9 and dedup database methods"
```

---

## Task 2: DedupScanner Class

**Files:**
- Create: `photo-curator/src/dedup_scanner.py`
- Create: `photo-curator/tests/test_dedup_scanner.py`

- [ ] **Step 1: Write failing tests for pure scanner logic**

Create `photo-curator/tests/test_dedup_scanner.py`:

```python
"""Tests for DedupScanner pure logic (no Immich I/O)."""
import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.dedup_scanner import DedupScanner


def test_find_duplicate_groups_groups_near_duplicates():
    """Assets with Hamming distance <= 5 should be grouped together."""
    # Identical hashes → distance 0 → duplicate
    hashes = {
        'a1': 'aaaaaaaaaaaaaaaa',
        'a2': 'aaaaaaaaaaaaaaaa',
        'a3': 'ffffffffffffffff',  # totally different
    }
    groups = DedupScanner.find_duplicate_groups(hashes, threshold=5)
    assert len(groups) == 1
    assert set(groups[0]) == {'a1', 'a2'}


def test_find_duplicate_groups_returns_empty_when_no_duplicates():
    hashes = {
        'a1': 'aaaaaaaaaaaaaaaa',
        'a2': 'ffffffffffffffff',
    }
    groups = DedupScanner.find_duplicate_groups(hashes, threshold=5)
    assert groups == []


def test_find_duplicate_groups_handles_empty_input():
    assert DedupScanner.find_duplicate_groups({}) == []


def test_compute_recommended_keep_prefers_higher_resolution():
    meta_map = {
        'low-res': {'width': 800, 'height': 600, 'file_size_bytes': 500_000},
        'high-res': {'width': 4032, 'height': 3024, 'file_size_bytes': 4_200_000},
    }
    keep = DedupScanner._compute_recommended_keep(['low-res', 'high-res'], meta_map)
    assert keep == 'high-res'


def test_compute_recommended_keep_tiebreaks_by_file_size():
    meta_map = {
        'same-res-small': {'width': 1920, 'height': 1080, 'file_size_bytes': 1_000_000},
        'same-res-large': {'width': 1920, 'height': 1080, 'file_size_bytes': 3_000_000},
    }
    keep = DedupScanner._compute_recommended_keep(
        ['same-res-small', 'same-res-large'], meta_map
    )
    assert keep == 'same-res-large'


def test_compute_recommended_keep_handles_missing_metadata():
    """Falls back gracefully when metadata is absent."""
    meta_map = {'a1': {}, 'a2': {'width': 1920, 'height': 1080, 'file_size_bytes': 2_000_000}}
    keep = DedupScanner._compute_recommended_keep(['a1', 'a2'], meta_map)
    assert keep == 'a2'


def test_asset_to_meta_extracts_correct_fields():
    asset = {
        'id': 'x1',
        'originalFileName': 'test.jpg',
        'fileCreatedAt': '2024-01-01T00:00:00Z',
        'exifInfo': {
            'exifImageWidth': 3000,
            'exifImageHeight': 2000,
            'fileSizeInByte': 2_500_000,
            'make': 'Canon',
            'model': 'EOS R5',
        },
    }
    meta = DedupScanner._asset_to_meta(asset)
    assert meta['width'] == 3000
    assert meta['height'] == 2000
    assert meta['file_size_bytes'] == 2_500_000
    assert meta['camera_make'] == 'Canon'
    assert meta['camera_model'] == 'EOS R5'
    assert meta['filename'] == 'test.jpg'


def test_derive_phase_hashing():
    assert DedupScanner.derive_phase('running', hashed=10, total_assets=100) == 'hashing'


def test_derive_phase_comparing():
    assert DedupScanner.derive_phase('running', hashed=100, total_assets=100) == 'comparing'


def test_derive_phase_null_when_not_running():
    assert DedupScanner.derive_phase('complete', hashed=100, total_assets=100) is None
    assert DedupScanner.derive_phase('idle', hashed=0, total_assets=0) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd photo-curator && python -m pytest tests/test_dedup_scanner.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'src.dedup_scanner'`

- [ ] **Step 3: Create `photo-curator/src/dedup_scanner.py`**

```python
"""
Standalone duplicate scanner for Immich photos.
Manages both Quick Scan (Immich native) and Deep Scan (pHash) modes.
One scan job runs at a time; state is tracked via the dedup_scans DB table.
"""
import asyncio
import logging
import os
import tempfile
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DedupScanner:
    """
    Module-level singleton that manages dedup scan jobs.
    Initialized at app startup with just the database.
    Each scan receives a user-scoped ImmichClient at call time.
    """

    def __init__(self, database, config: Optional[Dict] = None):
        self._db = database
        self._config = config or {}
        self._current_task: Optional[asyncio.Task] = None
        self._current_scan_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        return self._current_task is not None and not self._current_task.done()

    def current_scan_id(self) -> Optional[str]:
        return self._current_scan_id

    async def estimate(
        self, user_id: str, date_from: str, date_to: str, immich_client
    ) -> Dict:
        assets = await asyncio.to_thread(
            self._fetch_assets_paginated, immich_client, date_from, date_to
        )
        total = len(assets)
        if total == 0:
            return {'total_assets': 0, 'needs_hashing': 0, 'estimated_seconds': 0, 'warning': False}

        asset_ids = [a['id'] for a in assets]
        needs_hashing = await asyncio.to_thread(self._count_needs_hashing, asset_ids)
        rate = self._config.get('hash_rate_per_second', 1.0 / 0.3)
        estimated_seconds = int(needs_hashing / rate) if rate > 0 else 0
        return {
            'total_assets': total,
            'needs_hashing': needs_hashing,
            'estimated_seconds': estimated_seconds,
            'warning': needs_hashing > 500,
        }

    async def start_deep_scan(
        self, user_id: str, date_from: str, date_to: str, immich_client
    ) -> str:
        if self.is_running():
            raise RuntimeError(f"scan_already_running:{self._current_scan_id}")
        scan_id = str(uuid.uuid4())
        self._db.create_dedup_scan(scan_id, user_id, 'deep', date_from=date_from, date_to=date_to)
        self._current_scan_id = scan_id
        self._current_task = asyncio.create_task(
            self._run_deep(scan_id, user_id, date_from, date_to, immich_client)
        )
        return scan_id

    async def start_quick_scan(self, user_id: str, immich_client) -> str:
        if self.is_running():
            raise RuntimeError(f"scan_already_running:{self._current_scan_id}")
        scan_id = str(uuid.uuid4())
        self._db.create_dedup_scan(scan_id, user_id, 'quick')
        self._current_scan_id = scan_id
        self._current_task = asyncio.create_task(
            self._run_quick(scan_id, user_id, immich_client)
        )
        return scan_id

    async def cancel(self) -> bool:
        if not self._current_scan_id:
            return False
        self._db.update_dedup_scan(self._current_scan_id, status='cancelled')
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
        return True

    # ------------------------------------------------------------------
    # Pure static helpers (tested in isolation)
    # ------------------------------------------------------------------

    @staticmethod
    def find_duplicate_groups(
        hashes: Dict[str, str], threshold: int = 5
    ) -> List[List[str]]:
        """Given {asset_id: phash_hex_str}, return groups of near-duplicates."""
        import imagehash
        asset_ids = list(hashes.keys())
        hash_objs = {}
        for aid, h in hashes.items():
            if h:
                try:
                    hash_objs[aid] = imagehash.hex_to_hash(h)
                except Exception:
                    pass

        processed: set = set()
        groups: List[List[str]] = []
        for i, aid1 in enumerate(asset_ids):
            if aid1 in processed or aid1 not in hash_objs:
                continue
            group = [aid1]
            for aid2 in asset_ids[i + 1:]:
                if aid2 in processed or aid2 not in hash_objs:
                    continue
                if (hash_objs[aid1] - hash_objs[aid2]) <= threshold:
                    group.append(aid2)
                    processed.add(aid2)
            if len(group) > 1:
                groups.append(group)
                processed.add(aid1)
        return groups

    @staticmethod
    def _score_asset(meta: Dict) -> int:
        w = meta.get('width') or 0
        h = meta.get('height') or 0
        size = meta.get('file_size_bytes') or 0
        return w * h * 1000 + size

    @staticmethod
    def _compute_recommended_keep(
        asset_ids: List[str], meta_map: Dict[str, Dict]
    ) -> str:
        scored = [(aid, DedupScanner._score_asset(meta_map.get(aid, {}))) for aid in asset_ids]
        return max(scored, key=lambda x: x[1])[0]

    @staticmethod
    def _asset_to_meta(asset: Dict) -> Dict:
        exif = asset.get('exifInfo') or {}
        return {
            'width': exif.get('exifImageWidth'),
            'height': exif.get('exifImageHeight'),
            'file_size_bytes': exif.get('fileSizeInByte'),
            'filename': asset.get('originalFileName'),
            'date_taken': asset.get('fileCreatedAt'),
            'camera_make': exif.get('make'),
            'camera_model': exif.get('model'),
        }

    @staticmethod
    def derive_phase(
        status: str, hashed: int, total_assets: int
    ) -> Optional[str]:
        if status != 'running':
            return None
        return 'comparing' if hashed >= total_assets else 'hashing'

    # ------------------------------------------------------------------
    # Private: I/O helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_assets_paginated(immich_client, date_from: str, date_to: str) -> List[Dict]:
        assets: List[Dict] = []
        page = None
        while True:
            payload: Dict[str, Any] = {
                'takenAfter': f"{date_from}T00:00:00.000Z",
                'takenBefore': f"{date_to}T23:59:59.999Z",
                'type': 'IMAGE',
                'size': 1000,
                'withExif': True,
            }
            if page:
                payload['page'] = page
            resp = immich_client.session.post(
                f"{immich_client.api_url}/search/metadata", json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get('assets', {}).get('items', [])
            assets.extend(items)
            next_page = data.get('assets', {}).get('nextPage')
            if not next_page:
                break
            page = next_page
        return assets

    def _count_needs_hashing(self, asset_ids: List[str]) -> int:
        if not asset_ids:
            return 0
        with self._db._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(asset_ids))
            cursor.execute(
                f"SELECT COUNT(*) as cnt FROM photo_scores "
                f"WHERE asset_id IN ({placeholders}) AND perceptual_hash IS NOT NULL",
                asset_ids,
            )
            hashed_count = cursor.fetchone()['cnt']
        return len(asset_ids) - hashed_count

    def _get_existing_hash(self, asset_id: str) -> Optional[str]:
        with self._db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT perceptual_hash FROM photo_scores WHERE asset_id = ? AND perceptual_hash IS NOT NULL LIMIT 1",
                (asset_id,),
            )
            row = cursor.fetchone()
            return row['perceptual_hash'] if row else None

    @staticmethod
    def _download_and_hash(asset_id: str, immich_client) -> Optional[str]:
        from PIL import Image
        import imagehash
        tmp_path = None
        try:
            resp = immich_client.session.get(
                f"{immich_client.api_url}/assets/{asset_id}/thumbnail", timeout=30
            )
            resp.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
                f.write(resp.content)
                tmp_path = f.name
            img = Image.open(tmp_path)
            return str(imagehash.phash(img))
        except Exception as e:
            logger.warning(f"Failed to hash {asset_id}: {e}")
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ------------------------------------------------------------------
    # Private: scan runners
    # ------------------------------------------------------------------

    async def _run_deep(
        self, scan_id: str, user_id: str, date_from: str, date_to: str, immich_client
    ) -> None:
        try:
            assets = await asyncio.to_thread(
                self._fetch_assets_paginated, immich_client, date_from, date_to
            )
            self._db.update_dedup_scan(scan_id, total_assets=len(assets))

            BATCH_SIZE = 25
            hashes: Dict[str, str] = {}

            for i in range(0, len(assets), BATCH_SIZE):
                # Cancellation check
                scan_row = self._db.get_dedup_scan_status(user_id)
                if scan_row and scan_row.get('status') == 'cancelled':
                    return

                batch = assets[i: i + BATCH_SIZE]
                for asset in batch:
                    asset_id = asset['id']
                    self._db.upsert_dedup_asset_metadata(user_id, asset)

                    existing = await asyncio.to_thread(self._get_existing_hash, asset_id)
                    if existing:
                        hashes[asset_id] = existing
                    else:
                        phash = await asyncio.to_thread(
                            self._download_and_hash, asset_id, immich_client
                        )
                        if phash:
                            hashes[asset_id] = phash
                            # Derive year/month from fileCreatedAt for DB storage
                            created_at = asset.get('fileCreatedAt', '')
                            try:
                                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                                year, month = dt.year, dt.month
                            except Exception:
                                year, month = 1970, 1
                            await asyncio.to_thread(
                                self._db.upsert_perceptual_hash, asset_id, user_id, year, month, phash
                            )

                processed = min(i + BATCH_SIZE, len(assets))
                self._db.update_dedup_scan(scan_id, hashed=processed)
                await asyncio.sleep(0.5)

            # Mark hashing complete (hashed == total_assets → comparing phase)
            self._db.update_dedup_scan(scan_id, hashed=len(assets))

            groups = await asyncio.to_thread(self.find_duplicate_groups, hashes)
            asset_meta_map = {a['id']: self._asset_to_meta(a) for a in assets}

            for group_ids in groups:
                recommended = self._compute_recommended_keep(group_ids, asset_meta_map)
                group_hash = str(hash(tuple(sorted(group_ids))))
                self._db.save_dedup_group(scan_id, user_id, group_ids, recommended, group_hash)

            self._db.update_dedup_scan(scan_id, status='complete', groups_found=len(groups))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Deep scan error: {e}", exc_info=True)
            self._db.update_dedup_scan(scan_id, status='failed', error_message=str(e))

    async def _run_quick(self, scan_id: str, user_id: str, immich_client) -> None:
        try:
            resp = await asyncio.to_thread(
                lambda: immich_client.session.get(f"{immich_client.api_url}/duplicates")
            )
            if not resp.ok:
                self._db.update_dedup_scan(
                    scan_id, status='failed',
                    error_message=f"immich_unavailable:{resp.status_code}"
                )
                return

            groups_data = resp.json()
            for group_data in groups_data:
                asset_ids = [a['id'] for a in group_data.get('assets', [])]
                if len(asset_ids) < 2:
                    continue
                for asset in group_data['assets']:
                    self._db.upsert_dedup_asset_metadata(user_id, asset)
                asset_meta_map = {a['id']: self._asset_to_meta(a) for a in group_data['assets']}
                recommended = self._compute_recommended_keep(asset_ids, asset_meta_map)
                group_hash = str(hash(tuple(sorted(asset_ids))))
                self._db.save_dedup_group(scan_id, user_id, asset_ids, recommended, group_hash)

            self._db.update_dedup_scan(
                scan_id, status='complete', groups_found=len(groups_data)
            )

        except Exception as e:
            logger.error(f"Quick scan error: {e}", exc_info=True)
            self._db.update_dedup_scan(scan_id, status='failed', error_message=str(e))
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
cd photo-curator && python -m pytest tests/test_dedup_scanner.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add photo-curator/src/dedup_scanner.py photo-curator/tests/test_dedup_scanner.py
git commit -m "feat(dedup): add DedupScanner class with deep and quick scan modes"
```

---

## Task 3: API Routes in `main.py`

**Files:**
- Modify: `photo-curator/src/main.py`
- Create: `photo-curator/tests/test_dedup_routes.py`

- [ ] **Step 1: Write failing route tests**

Create `photo-curator/tests/test_dedup_routes.py`:

```python
"""Integration tests for /api/dedup/* routes."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.main import app
from src.auth import get_current_user
from src.database import Database

FAKE_USER = {
    "id": "user-123",
    "email": "test@example.com",
    "name": "Test User",
    "access_token": "tok-abc",
    "_local_user": {"id": 1, "role": "user"},
}


def _auth_override():
    return FAKE_USER


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides = {get_current_user: _auth_override}
    db = Database(db_path=str(tmp_path / "test.db"))
    app.state.database = db

    mock_scanner = MagicMock()
    mock_scanner.is_running.return_value = False
    mock_scanner.current_scan_id.return_value = None
    app.state.dedup_scanner = mock_scanner

    yield TestClient(app)
    app.dependency_overrides = {}


# --- estimate ---

def test_estimate_returns_shape(client):
    app.state.dedup_scanner.estimate = AsyncMock(return_value={
        'total_assets': 100,
        'needs_hashing': 40,
        'estimated_seconds': 12,
        'warning': False,
    })
    resp = client.post('/api/dedup/scan/estimate', json={'date_from': '2024-01-01', 'date_to': '2024-12-31'})
    assert resp.status_code == 200
    data = resp.json()
    assert data['total_assets'] == 100
    assert data['needs_hashing'] == 40
    assert 'warning' in data


def test_estimate_requires_auth():
    app.dependency_overrides = {}
    c = TestClient(app, raise_server_exceptions=False)
    resp = c.post('/api/dedup/scan/estimate', json={'date_from': '2024-01-01', 'date_to': '2024-12-31'})
    assert resp.status_code in (401, 307)


# --- start deep scan ---

def test_start_deep_scan_returns_scan_id(client):
    app.state.dedup_scanner.start_deep_scan = AsyncMock(return_value='scan-uuid-1')
    resp = client.post('/api/dedup/scan/deep', json={'date_from': '2024-01-01', 'date_to': '2024-12-31'})
    assert resp.status_code == 200
    data = resp.json()
    assert data['scan_id'] == 'scan-uuid-1'
    assert data['status'] == 'running'


def test_start_deep_scan_409_when_already_running(client):
    app.state.dedup_scanner.is_running.return_value = True
    app.state.dedup_scanner.current_scan_id.return_value = 'existing-scan'
    resp = client.post('/api/dedup/scan/deep', json={'date_from': '2024-01-01', 'date_to': '2024-12-31'})
    assert resp.status_code == 409


# --- start quick scan ---

def test_start_quick_scan_returns_scan_id(client):
    app.state.dedup_scanner.start_quick_scan = AsyncMock(return_value='scan-uuid-q')
    resp = client.post('/api/dedup/scan/quick')
    assert resp.status_code == 200
    assert resp.json()['scan_id'] == 'scan-uuid-q'


# --- status ---

def test_scan_status_idle_when_no_scans(client):
    resp = client.get('/api/dedup/scan/status')
    assert resp.status_code == 200
    assert resp.json()['status'] == 'idle'


def test_scan_status_returns_running_scan(client):
    app.state.database.create_dedup_scan('s1', 'user-123', 'deep', '2024-01-01', '2024-12-31')
    app.state.database.update_dedup_scan('s1', total_assets=100, hashed=30)
    resp = client.get('/api/dedup/scan/status')
    data = resp.json()
    assert data['status'] == 'running'
    assert data['total_assets'] == 100
    assert data['phase'] == 'hashing'


# --- cancel ---

def test_cancel_returns_cancelled_true(client):
    app.state.dedup_scanner.cancel = AsyncMock(return_value=True)
    resp = client.delete('/api/dedup/scan')
    assert resp.status_code == 200
    assert resp.json()['cancelled'] is True


def test_cancel_returns_false_when_not_running(client):
    app.state.dedup_scanner.cancel = AsyncMock(return_value=False)
    resp = client.delete('/api/dedup/scan')
    assert resp.json()['cancelled'] is False


# --- groups ---

def test_get_groups_returns_shape(client):
    db = app.state.database
    db.create_dedup_scan('s2', 'user-123', 'deep')
    db.save_dedup_group('s2', 'user-123', ['a1', 'a2'], 'a1', 'hash-1')
    resp = client.get('/api/dedup/groups')
    assert resp.status_code == 200
    data = resp.json()
    assert data['total_groups'] == 1
    assert len(data['groups']) == 1


def test_get_groups_user_isolation(client):
    db = app.state.database
    db.create_dedup_scan('s3', 'other-user', 'deep')
    db.save_dedup_group('s3', 'other-user', ['a9', 'a10'], 'a9', 'hash-9')
    resp = client.get('/api/dedup/groups')
    assert resp.json()['total_groups'] == 0


# --- resolve ---

def test_resolve_group_calls_immich_delete(client):
    db = app.state.database
    db.create_dedup_scan('s4', 'user-123', 'deep')
    db.upsert_dedup_asset_metadata('user-123', {'id': 'a1', 'originalFileName': 'a.jpg',
        'fileCreatedAt': '2024-01-01', 'exifInfo': {}})
    db.upsert_dedup_asset_metadata('user-123', {'id': 'a2', 'originalFileName': 'b.jpg',
        'fileCreatedAt': '2024-01-01', 'exifInfo': {}})
    db.save_dedup_group('s4', 'user-123', ['a1', 'a2'], 'a1', 'hash-4')
    result = db.get_dedup_groups('user-123')
    group_id = result['groups'][0]['id']

    with patch('src.main.ImmichClient') as MockClient:
        mock_session = MagicMock()
        mock_session.delete.return_value = MagicMock(ok=True)
        mock_session.delete.return_value.raise_for_status = MagicMock()
        MockClient.return_value.session = mock_session
        MockClient.return_value.api_url = 'http://localhost:2283/api'

        resp = client.post(f'/api/dedup/groups/{group_id}/resolve',
                           json={'keep_asset_id': 'a1'})

    assert resp.status_code == 200
    assert resp.json()['resolved'] is True
    # Group should now be marked resolved
    result2 = db.get_dedup_groups('user-123')
    assert result2['total_groups'] == 0


# --- dismiss ---

def test_dismiss_group(client):
    db = app.state.database
    db.create_dedup_scan('s5', 'user-123', 'deep')
    db.save_dedup_group('s5', 'user-123', ['a1', 'a2'], 'a1', 'hash-5')
    result = db.get_dedup_groups('user-123')
    group_id = result['groups'][0]['id']

    resp = client.delete(f'/api/dedup/groups/{group_id}')
    assert resp.status_code == 200
    assert resp.json()['dismissed'] is True
    assert db.get_dedup_groups('user-123')['total_groups'] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd photo-curator && python -m pytest tests/test_dedup_routes.py -v 2>&1 | head -30
```
Expected: 404s or attribute errors.

- [ ] **Step 3: Add `dedup_scanner` to globals and startup in `main.py`**

Note: `app.state.immich_api_url` is set by the autouse fixture in `conftest.py` — the resolve route test depends on this. If that fixture is ever changed, `app.state.immich_api_url` must be set explicitly in the test client fixture.

In `main.py`, add to the `global` declaration in `startup_event` (line ~185):
```python
global config, database, admin_immich_client, photo_cache, analyzer, scheduler, email_notifier, batch_processor, gpu_manager, dedup_scanner
```

Add the import near the top of `main.py` (after existing `.` imports):
```python
from .dedup_scanner import DedupScanner
```

Add module-level declaration before `startup_event`:
```python
dedup_scanner: Optional[DedupScanner] = None
```

In `startup_event`, after `database = Database()`:
```python
        dedup_scanner = DedupScanner(database, config.get('dedup', {}))
        app.state.dedup_scanner = dedup_scanner
```

- [ ] **Step 4: Add the 8 dedup routes to `main.py`**

Add this block after the existing `# Duplicate Management` section (around line 1080):

```python
# ====================================================================
# Standalone Dedup Scanner
# ====================================================================

class DedupDeepScanRequest(BaseModel):
    date_from: str  # ISO date: YYYY-MM-DD
    date_to: str


class DedupEstimateRequest(BaseModel):
    date_from: str
    date_to: str


class DedupResolveRequest(BaseModel):
    keep_asset_id: str


@app.post("/api/dedup/scan/estimate")
async def dedup_estimate(
    request: Request,
    body: DedupEstimateRequest,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    if not database or not app.state.dedup_scanner:
        raise HTTPException(status_code=503, detail="Service not initialized")
    user_client = ImmichClient(app.state.immich_api_url, user['access_token'], use_bearer=True)
    result = await app.state.dedup_scanner.estimate(
        user['id'], body.date_from, body.date_to, user_client
    )
    return result


@app.post("/api/dedup/scan/deep")
async def dedup_start_deep(
    request: Request,
    body: DedupDeepScanRequest,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    if not database or not app.state.dedup_scanner:
        raise HTTPException(status_code=503, detail="Service not initialized")
    scanner = app.state.dedup_scanner
    if scanner.is_running():
        raise HTTPException(
            status_code=409,
            detail={"error": "scan_already_running", "scan_id": scanner.current_scan_id()}
        )
    user_client = ImmichClient(app.state.immich_api_url, user['access_token'], use_bearer=True)
    scan_id = await scanner.start_deep_scan(user['id'], body.date_from, body.date_to, user_client)
    return {"scan_id": scan_id, "status": "running"}


@app.post("/api/dedup/scan/quick")
async def dedup_start_quick(
    request: Request,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    if not database or not app.state.dedup_scanner:
        raise HTTPException(status_code=503, detail="Service not initialized")
    scanner = app.state.dedup_scanner
    if scanner.is_running():
        raise HTTPException(
            status_code=409,
            detail={"error": "scan_already_running", "scan_id": scanner.current_scan_id()}
        )
    user_client = ImmichClient(app.state.immich_api_url, user['access_token'], use_bearer=True)
    scan_id = await scanner.start_quick_scan(user['id'], user_client)
    return {"scan_id": scan_id, "status": "running"}


@app.get("/api/dedup/scan/status")
async def dedup_scan_status(
    request: Request,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")
    scan = database.get_dedup_scan_status(user['id'])
    if not scan:
        return {"status": "idle"}
    # DedupScanner already imported at module level — no inline import needed
    phase = DedupScanner.derive_phase(
        scan['status'], scan.get('hashed', 0), scan.get('total_assets', 0)
    )
    return {**scan, "phase": phase}


@app.delete("/api/dedup/scan")
async def dedup_cancel_scan(
    request: Request,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    if not app.state.dedup_scanner:
        return {"cancelled": False}
    cancelled = await app.state.dedup_scanner.cancel()
    return {"cancelled": cancelled}


@app.get("/api/dedup/groups")
async def dedup_get_groups(
    request: Request,
    include_resolved: bool = False,
    limit: int = 50,
    offset: int = 0,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")
    limit = min(limit, 200)
    return database.get_dedup_groups(user['id'], include_resolved=include_resolved, limit=limit, offset=offset)


@app.post("/api/dedup/groups/{group_id}/resolve")
@limiter.limit("30/minute")
async def dedup_resolve_group(
    request: Request,
    group_id: int,
    body: DedupResolveRequest,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")
    result = database.get_dedup_groups(user['id'])
    group = next((g for g in result['groups'] if g['id'] == group_id), None)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    asset_ids = json.loads(group['asset_ids']) if isinstance(group['asset_ids'], str) else group['asset_ids']
    to_delete = [aid for aid in asset_ids if aid != body.keep_asset_id]

    user_client = ImmichClient(app.state.immich_api_url, user['access_token'], use_bearer=True)
    deleted = 0
    try:
        for asset_id in to_delete:
            resp = user_client.session.delete(
                f"{user_client.api_url}/assets", json={"ids": [asset_id]}
            )
            resp.raise_for_status()
            database.delete_photo_score(asset_id)
            deleted += 1
    except Exception as e:
        logger.error(f"Immich delete failed during group resolve: {e}")
        return {"resolved": False, "error": "immich_delete_failed", "detail": str(e)}

    database.resolve_dedup_group(group_id)
    return {"resolved": True, "deleted_count": deleted}


@app.delete("/api/dedup/groups/{group_id}")
async def dedup_dismiss_group(
    request: Request,
    group_id: int,
    user: Dict = Depends(get_current_user),
    _role=Depends(require_role(Role.USER)),
):
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")
    database.dismiss_dedup_group(group_id)
    return {"dismissed": True}
```

Note: `json` is NOT imported at module level in `main.py` — add `import json` to the top-level imports section of `main.py` as part of this step.

- [ ] **Step 5: Run route tests and verify they pass**

```bash
cd photo-curator && python -m pytest tests/test_dedup_routes.py -v
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add photo-curator/src/main.py photo-curator/tests/test_dedup_routes.py
git commit -m "feat(dedup): add 8 dedup API routes and scanner startup initialization"
```

---

## Task 4: Frontend — Scan Panel

**Files:**
- Replace: `photo-curator/frontend/src/pages/Duplicates.jsx`
- Create: `photo-curator/frontend/src/test/Duplicates.test.jsx`

- [ ] **Step 1: Write failing frontend tests**

Create `photo-curator/frontend/src/test/Duplicates.test.jsx`:

```jsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import Duplicates from '../pages/Duplicates'
import * as api from '../utils/api'

function wrap(ui) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
    if (url === '/api/dedup/scan/status') return Promise.resolve({ status: 'idle' })
    if (url === '/api/dedup/groups') return Promise.resolve({ groups: [], total_groups: 0, total_removable_photos: 0, total_savings_bytes: 0 })
    return Promise.resolve({})
  })
})

describe('Scan Panel', () => {
  it('renders Quick Scan and Deep Scan tabs', () => {
    wrap(<Duplicates />)
    expect(screen.getByTestId('tab-quick')).toBeInTheDocument()
    expect(screen.getByTestId('tab-deep')).toBeInTheDocument()
  })

  it('Quick Scan tab is active by default', () => {
    wrap(<Duplicates />)
    expect(screen.getByTestId('tab-quick')).toHaveAttribute('aria-selected', 'true')
  })

  it('clicking Deep Scan tab shows date pickers', () => {
    wrap(<Duplicates />)
    fireEvent.click(screen.getByTestId('tab-deep'))
    expect(screen.getByTestId('input-date-from')).toBeInTheDocument()
    expect(screen.getByTestId('input-date-to')).toBeInTheDocument()
  })

  it('Start Deep Scan button is disabled without dates', () => {
    wrap(<Duplicates />)
    fireEvent.click(screen.getByTestId('tab-deep'))
    expect(screen.getByTestId('btn-start-deep')).toBeDisabled()
  })

  it('Start Deep Scan button enables after both dates selected', () => {
    wrap(<Duplicates />)
    fireEvent.click(screen.getByTestId('tab-deep'))
    fireEvent.change(screen.getByTestId('input-date-from'), { target: { value: '2024-01-01' } })
    fireEvent.change(screen.getByTestId('input-date-to'), { target: { value: '2024-12-31' } })
    expect(screen.getByTestId('btn-start-deep')).not.toBeDisabled()
  })

  it('Estimate button calls /api/dedup/scan/estimate', async () => {
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url === '/api/dedup/scan/status') return Promise.resolve({ status: 'idle' })
      if (url === '/api/dedup/groups') return Promise.resolve({ groups: [], total_groups: 0, total_removable_photos: 0, total_savings_bytes: 0 })
      if (url === '/api/dedup/scan/estimate') return Promise.resolve({
        total_assets: 500, needs_hashing: 200, estimated_seconds: 60, warning: false,
      })
      return Promise.resolve({})
    })
    wrap(<Duplicates />)
    fireEvent.click(screen.getByTestId('tab-deep'))
    fireEvent.change(screen.getByTestId('input-date-from'), { target: { value: '2024-01-01' } })
    fireEvent.change(screen.getByTestId('input-date-to'), { target: { value: '2024-12-31' } })
    fireEvent.click(screen.getByTestId('btn-estimate'))
    await waitFor(() => expect(screen.getByTestId('estimate-result')).toBeInTheDocument())
    expect(screen.getByTestId('estimate-result')).toHaveTextContent('500')
  })

  it('shows warning banner when estimate warning is true', async () => {
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url === '/api/dedup/scan/status') return Promise.resolve({ status: 'idle' })
      if (url === '/api/dedup/groups') return Promise.resolve({ groups: [], total_groups: 0, total_removable_photos: 0, total_savings_bytes: 0 })
      if (url === '/api/dedup/scan/estimate') return Promise.resolve({
        total_assets: 2000, needs_hashing: 800, estimated_seconds: 240, warning: true,
      })
      return Promise.resolve({})
    })
    wrap(<Duplicates />)
    fireEvent.click(screen.getByTestId('tab-deep'))
    fireEvent.change(screen.getByTestId('input-date-from'), { target: { value: '2023-01-01' } })
    fireEvent.change(screen.getByTestId('input-date-to'), { target: { value: '2024-12-31' } })
    fireEvent.click(screen.getByTestId('btn-estimate'))
    await waitFor(() => expect(screen.getByTestId('estimate-warning')).toBeInTheDocument())
  })

  it('shows progress bar when scan is running (hashing phase)', async () => {
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url === '/api/dedup/scan/status') return Promise.resolve({
        status: 'running', phase: 'hashing', hashed: 50, total_assets: 200,
        mode: 'deep', scan_id: 'x', groups_found: 0,
      })
      if (url === '/api/dedup/groups') return Promise.resolve({ groups: [], total_groups: 0, total_removable_photos: 0, total_savings_bytes: 0 })
      return Promise.resolve({})
    })
    wrap(<Duplicates />)
    await waitFor(() => expect(screen.getByTestId('scan-progress')).toBeInTheDocument())
    expect(screen.getByTestId('scan-progress')).toHaveTextContent('50')
    expect(screen.getByTestId('btn-cancel-scan')).toBeInTheDocument()
  })
})

describe('Results Panel', () => {
  it('shows empty state when no groups', async () => {
    wrap(<Duplicates />)
    await waitFor(() => expect(screen.getByTestId('no-groups-message')).toBeInTheDocument())
  })

  it('renders group cards when groups exist', async () => {
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url === '/api/dedup/scan/status') return Promise.resolve({ status: 'complete' })
      if (url.startsWith('/api/dedup/groups')) return Promise.resolve({
        groups: [{
          id: 1, resolved: false, recommended_keep_id: 'a1',
          asset_ids: JSON.stringify(['a1', 'a2']),
          savings_bytes: 2100000,
          assets: [
            { asset_id: 'a1', thumbnail_url: '/api/thumbnail/a1', width: 4032, height: 3024, file_size_bytes: 4200000, megapixels: 12.2, filename: 'good.jpg', date_taken: '2024-01-01', camera_model: 'iPhone 15' },
            { asset_id: 'a2', thumbnail_url: '/api/thumbnail/a2', width: 2000, height: 1500, file_size_bytes: 2100000, megapixels: 3.0, filename: 'small.jpg', date_taken: '2024-01-01', camera_model: null },
          ],
        }],
        total_groups: 1,
        total_removable_photos: 1,
        total_savings_bytes: 2100000,
      })
      return Promise.resolve({})
    })
    wrap(<Duplicates />)
    await waitFor(() => expect(screen.getByTestId('group-card-1')).toBeInTheDocument())
    expect(screen.getByTestId('recommended-badge')).toBeInTheDocument()
  })

  it('clicking group card opens detail view', async () => {
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url === '/api/dedup/scan/status') return Promise.resolve({ status: 'complete' })
      if (url.startsWith('/api/dedup/groups')) return Promise.resolve({
        groups: [{
          id: 1, resolved: false, recommended_keep_id: 'a1',
          asset_ids: JSON.stringify(['a1', 'a2']),
          savings_bytes: 2100000,
          assets: [
            { asset_id: 'a1', thumbnail_url: '/api/thumbnail/a1', width: 4032, height: 3024, file_size_bytes: 4200000, megapixels: 12.2, filename: 'good.jpg', date_taken: '2024-01-01', camera_model: 'iPhone 15' },
            { asset_id: 'a2', thumbnail_url: '/api/thumbnail/a2', width: 2000, height: 1500, file_size_bytes: 2100000, megapixels: 3.0, filename: 'small.jpg', date_taken: '2024-01-01', camera_model: null },
          ],
        }],
        total_groups: 1,
        total_removable_photos: 1,
        total_savings_bytes: 2100000,
      })
      return Promise.resolve({})
    })
    wrap(<Duplicates />)
    await waitFor(() => screen.getByTestId('group-card-1'))
    fireEvent.click(screen.getByTestId('group-card-1'))
    await waitFor(() => expect(screen.getByTestId('detail-panel')).toBeInTheDocument())
    expect(screen.getByTestId('btn-delete-others')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd photo-curator/frontend && npm test -- --reporter=verbose src/test/Duplicates.test.jsx 2>&1 | tail -20
```
Expected: tests fail with missing `data-testid` attributes.

- [ ] **Step 3: Replace `Duplicates.jsx` with new implementation**

Replace entire contents of `photo-curator/frontend/src/pages/Duplicates.jsx`:

```jsx
import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'
import { TrashIcon, XMarkIcon } from '@heroicons/react/24/outline'

// ─── Utilities ────────────────────────────────────────────────────────────────

function formatBytes(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

function formatSeconds(s) {
  if (s < 60) return `~${s}s`
  return `~${Math.round(s / 60)} min`
}

// ─── Scan Panel ───────────────────────────────────────────────────────────────

function ScanPanel({ scanStatus, onScanStarted }) {
  const [activeTab, setActiveTab] = useState('quick')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [estimate, setEstimate] = useState(null)
  const [estimating, setEstimating] = useState(false)

  const isRunning = scanStatus?.status === 'running'

  const quickMutation = useMutation({
    mutationFn: () => apiFetch('/api/dedup/scan/quick', { method: 'POST' }),
    onSuccess: onScanStarted,
  })

  const deepMutation = useMutation({
    mutationFn: () =>
      apiFetch('/api/dedup/scan/deep', {
        method: 'POST',
        body: JSON.stringify({ date_from: dateFrom, date_to: dateTo }),
      }),
    onSuccess: onScanStarted,
  })

  const cancelMutation = useMutation({
    mutationFn: () => apiFetch('/api/dedup/scan', { method: 'DELETE' }),
    onSuccess: onScanStarted,
  })

  const handleEstimate = async () => {
    setEstimating(true)
    setEstimate(null)
    try {
      const result = await apiFetch('/api/dedup/scan/estimate', {
        method: 'POST',
        body: JSON.stringify({ date_from: dateFrom, date_to: dateTo }),
      })
      setEstimate(result)
    } finally {
      setEstimating(false)
    }
  }

  if (isRunning) {
    const { phase, hashed, total_assets, mode } = scanStatus
    const pct = total_assets > 0 ? Math.round((hashed / total_assets) * 100) : 0
    const label =
      phase === 'hashing'
        ? `Collecting hashes… ${hashed} / ${total_assets}`
        : 'Comparing hashes…'
    return (
      <div className="bg-immich-surface border border-immich-border rounded-xl p-5">
        <div className="flex items-center justify-between mb-3">
          <p className="text-immich-text text-sm font-medium">
            {mode === 'quick' ? 'Quick Scan' : 'Deep Scan'} running
          </p>
          <button
            data-testid="btn-cancel-scan"
            onClick={() => cancelMutation.mutate()}
            className="text-xs text-red-400 hover:text-red-300"
          >
            Cancel
          </button>
        </div>
        <div
          data-testid="scan-progress"
          className="w-full bg-immich-border rounded-full h-2 mb-1"
        >
          <div
            className="bg-immich-primary h-2 rounded-full transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="text-immich-muted text-xs">{label}</p>
      </div>
    )
  }

  return (
    <div className="bg-immich-surface border border-immich-border rounded-xl p-5">
      <div className="flex gap-2 mb-4">
        {['quick', 'deep'].map((tab) => (
          <button
            key={tab}
            data-testid={`tab-${tab}`}
            aria-selected={activeTab === tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab
                ? 'bg-immich-primary text-white'
                : 'text-immich-muted hover:text-immich-text'
            }`}
          >
            {tab === 'quick' ? 'Quick Scan' : 'Deep Scan'}
          </button>
        ))}
      </div>

      {activeTab === 'quick' ? (
        <div>
          <p className="text-immich-muted text-xs mb-3">
            Uses Immich's built-in detection. Scans your entire library instantly.
          </p>
          {quickMutation.error?.message?.includes('immich_unavailable') && (
            <p className="text-yellow-400 text-xs mb-3">
              Immich duplicate detection unavailable — try a Deep Scan instead.
            </p>
          )}
          <button
            onClick={() => quickMutation.mutate()}
            disabled={quickMutation.isPending}
            className="px-4 py-2 bg-immich-primary text-white text-sm font-medium rounded-lg hover:opacity-90 disabled:opacity-50"
          >
            {quickMutation.isPending ? 'Scanning…' : 'Run Quick Scan'}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-immich-muted text-xs block mb-1">From</label>
              <input
                data-testid="input-date-from"
                type="date"
                value={dateFrom}
                onChange={(e) => { setDateFrom(e.target.value); setEstimate(null) }}
                className="w-full bg-immich-bg border border-immich-border rounded-lg px-3 py-1.5 text-immich-text text-sm"
              />
            </div>
            <div className="flex-1">
              <label className="text-immich-muted text-xs block mb-1">To</label>
              <input
                data-testid="input-date-to"
                type="date"
                value={dateTo}
                onChange={(e) => { setDateTo(e.target.value); setEstimate(null) }}
                className="w-full bg-immich-bg border border-immich-border rounded-lg px-3 py-1.5 text-immich-text text-sm"
              />
            </div>
          </div>

          {dateFrom && dateTo && (
            <button
              data-testid="btn-estimate"
              onClick={handleEstimate}
              disabled={estimating}
              className="text-immich-muted text-xs underline hover:text-immich-text"
            >
              {estimating ? 'Estimating…' : 'Estimate scan time'}
            </button>
          )}

          {estimate && (
            <div data-testid="estimate-result" className="text-immich-muted text-xs">
              ~{estimate.total_assets.toLocaleString()} photos · ~{estimate.needs_hashing.toLocaleString()} need hashing · {formatSeconds(estimate.estimated_seconds)}
            </div>
          )}

          {estimate?.warning && (
            <div
              data-testid="estimate-warning"
              className="bg-yellow-900/30 border border-yellow-700 rounded-lg px-3 py-2 text-yellow-300 text-xs"
            >
              This scan will download ~{estimate.needs_hashing.toLocaleString()} thumbnails and may take {formatSeconds(estimate.estimated_seconds)}. It will run in the background.
            </div>
          )}

          <button
            data-testid="btn-start-deep"
            onClick={() => deepMutation.mutate()}
            disabled={!dateFrom || !dateTo || deepMutation.isPending}
            className="px-4 py-2 bg-immich-primary text-white text-sm font-medium rounded-lg hover:opacity-90 disabled:opacity-50"
          >
            {deepMutation.isPending ? 'Starting…' : 'Start Deep Scan'}
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Group Card (overview) ─────────────────────────────────────────────────────

function GroupCard({ group, onClick }) {
  const assets = group.assets || []
  const preview = assets.slice(0, 4)

  const recommended = assets.find((a) => a.asset_id === group.recommended_keep_id)
  const others = assets.filter((a) => a.asset_id !== group.recommended_keep_id)
  const keepMp = recommended?.megapixels
  const otherMp = others[0]?.megapixels
  const keepSize = recommended?.file_size_bytes
  const otherSize = others[0]?.file_size_bytes

  const metaDiff = keepMp && otherMp
    ? `${keepMp}MP vs ${otherMp}MP · ${formatBytes(keepSize)} vs ${formatBytes(otherSize)}`
    : null

  return (
    <button
      data-testid={`group-card-${group.id}`}
      onClick={onClick}
      className="bg-immich-surface border border-immich-border rounded-xl p-4 text-left hover:border-immich-primary transition-colors w-full"
    >
      <div className="flex gap-2 mb-3">
        {preview.map((asset) => (
          <div key={asset.asset_id} className="relative flex-1">
            <img
              src={asset.thumbnail_url}
              alt=""
              className="w-full aspect-square object-cover rounded-lg"
            />
            {asset.asset_id === group.recommended_keep_id && (
              <span
                data-testid="recommended-badge"
                className="absolute top-1 left-1 bg-immich-primary text-white text-[10px] px-1.5 py-0.5 rounded font-medium"
              >
                Keep
              </span>
            )}
          </div>
        ))}
      </div>
      <p className="text-immich-muted text-xs">
        {assets.length} duplicates{metaDiff ? ` · ${metaDiff}` : ''}
      </p>
    </button>
  )
}

// ─── Detail Panel ─────────────────────────────────────────────────────────────

function DetailPanel({ group, onClose }) {
  const [keepId, setKeepId] = useState(group.recommended_keep_id)
  const queryClient = useQueryClient()

  const resolveMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/api/dedup/groups/${group.id}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ keep_asset_id: keepId }),
      }),
    onSuccess: (data) => {
      if (data.resolved) {
        queryClient.invalidateQueries({ queryKey: ['dedup-groups'] })
        onClose()
      }
    },
  })

  const dismissMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/api/dedup/groups/${group.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dedup-groups'] })
      onClose()
    },
  })

  const assets = group.assets || []

  return (
    <div
      data-testid="detail-panel"
      className="fixed inset-y-0 right-0 w-full max-w-2xl bg-immich-surface border-l border-immich-border shadow-xl z-50 overflow-y-auto"
    >
      <div className="flex items-center justify-between p-4 border-b border-immich-border">
        <h2 className="text-immich-text font-semibold">{assets.length} Similar Photos</h2>
        <button onClick={onClose} className="text-immich-muted hover:text-immich-text">
          <XMarkIcon className="w-5 h-5" />
        </button>
      </div>

      <div className="p-4 space-y-6">
        {/* Thumbnails */}
        <div className="flex gap-3">
          {assets.map((asset) => (
            <div key={asset.asset_id} className="flex-1">
              <button
                onClick={() => setKeepId(asset.asset_id)}
                className={`w-full rounded-xl overflow-hidden ring-2 transition-all ${
                  keepId === asset.asset_id
                    ? 'ring-immich-primary'
                    : 'ring-transparent opacity-60 hover:opacity-90'
                }`}
              >
                <img
                  src={asset.thumbnail_url}
                  alt=""
                  className="w-full aspect-square object-cover"
                />
              </button>
              {keepId === asset.asset_id && (
                <p className="text-center text-immich-primary text-xs mt-1 font-medium">
                  {asset.asset_id === group.recommended_keep_id ? '★ Recommended keep' : 'Selected keep'}
                </p>
              )}
            </div>
          ))}
        </div>

        {/* Metadata table */}
        <table className="w-full text-xs text-immich-muted">
          <thead>
            <tr className="border-b border-immich-border">
              <th className="text-left py-1 font-medium">Field</th>
              {assets.map((a) => (
                <th key={a.asset_id} className="text-left py-1 font-medium">
                  {a.filename || a.asset_id.slice(0, 8)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[
              ['Resolution', (a) => a.megapixels ? `${a.megapixels}MP (${a.width}×${a.height})` : '—'],
              ['File size', (a) => formatBytes(a.file_size_bytes)],
              ['Date taken', (a) => a.date_taken ? new Date(a.date_taken).toLocaleDateString() : '—'],
              ['Camera', (a) => a.camera_model || '—'],
            ].map(([label, fmt]) => (
              <tr key={label} className="border-b border-immich-border/50">
                <td className="py-1.5">{label}</td>
                {assets.map((a) => (
                  <td key={a.asset_id} className="py-1.5">{fmt(a)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>

        {/* Actions */}
        {resolveMutation.data && !resolveMutation.data.resolved && (
          <p className="text-red-400 text-xs">
            Delete failed: {resolveMutation.data.detail}
          </p>
        )}

        <div className="flex items-center gap-3">
          <button
            data-testid="btn-delete-others"
            onClick={() => resolveMutation.mutate()}
            disabled={resolveMutation.isPending}
            className="flex items-center gap-1.5 px-4 py-2 bg-red-700 text-white text-sm font-medium rounded-lg hover:bg-red-600 disabled:opacity-50"
          >
            <TrashIcon className="w-4 h-4" />
            {resolveMutation.isPending ? 'Deleting…' : 'Delete others & close'}
          </button>
          <button
            onClick={() => dismissMutation.mutate()}
            disabled={dismissMutation.isPending}
            className="text-immich-muted text-sm hover:text-immich-text"
          >
            Skip (keep all)
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Results Panel ─────────────────────────────────────────────────────────────

function ResultsPanel({ groupsData, isLoading }) {
  const [selectedGroup, setSelectedGroup] = useState(null)
  const [showResolved, setShowResolved] = useState(false)
  const queryClient = useQueryClient()

  const handleIncludeResolvedToggle = () => {
    setShowResolved((v) => !v)
    queryClient.invalidateQueries({ queryKey: ['dedup-groups'] })
  }

  const groups = groupsData?.groups ?? []
  const totalGroups = groupsData?.total_groups ?? 0
  const removable = groupsData?.total_removable_photos ?? 0
  const savings = groupsData?.total_savings_bytes ?? 0

  if (isLoading) return <p className="text-immich-muted text-sm">Loading…</p>

  return (
    <div>
      {totalGroups > 0 && (
        <div className="flex items-center justify-between mb-4">
          <p className="text-immich-muted text-sm">
            {totalGroups} duplicate groups · {removable} photos removable · {formatBytes(savings)} savings
          </p>
          <button
            onClick={handleIncludeResolvedToggle}
            className="text-immich-muted text-xs underline hover:text-immich-text"
          >
            {showResolved ? 'Hide resolved' : 'Show resolved'}
          </button>
        </div>
      )}

      {groups.length === 0 ? (
        <div data-testid="no-groups-message" className="text-center py-16 text-immich-muted">
          No duplicates found. Run a scan to check your library.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {groups.map((group) => (
            <div key={group.id} className={group.resolved ? 'opacity-40' : ''}>
              <GroupCard
                group={group}
                onClick={() => !group.resolved && setSelectedGroup(group)}
              />
            </div>
          ))}
        </div>
      )}

      {selectedGroup && (
        <DetailPanel
          group={selectedGroup}
          onClose={() => setSelectedGroup(null)}
        />
      )}
    </div>
  )
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export default function Duplicates() {
  const queryClient = useQueryClient()

  const { data: scanStatus } = useQuery({
    queryKey: ['dedup-scan-status'],
    queryFn: () => apiFetch('/api/dedup/scan/status'),
    refetchInterval: (query) =>
      query.state.data?.status === 'running' ? 2000 : false,
  })

  const { data: groupsData, isLoading: groupsLoading } = useQuery({
    queryKey: ['dedup-groups'],
    queryFn: () => apiFetch('/api/dedup/groups'),
  })

  const handleScanStarted = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['dedup-scan-status'] })
    queryClient.invalidateQueries({ queryKey: ['dedup-groups'] })
  }, [queryClient])

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-immich-text text-2xl font-semibold">Duplicates</h1>
      <ScanPanel scanStatus={scanStatus} onScanStarted={handleScanStarted} />
      <ResultsPanel groupsData={groupsData} isLoading={groupsLoading} />
    </div>
  )
}
```

- [ ] **Step 4: Run frontend tests and verify they pass**

```bash
cd photo-curator/frontend && npm test -- --reporter=verbose src/test/Duplicates.test.jsx
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add photo-curator/frontend/src/pages/Duplicates.jsx photo-curator/frontend/src/test/Duplicates.test.jsx
git commit -m "feat(dedup): replace stub Duplicates page with scan panel and review UI"
```

---

## Task 5: Build Frontend and Final Smoke Test

**Files:**
- Build: `photo-curator/frontend/`

- [ ] **Step 1: Run all backend tests**

```bash
cd photo-curator && python -m pytest tests/ -v
```
Expected: all existing + new tests pass with no failures.

- [ ] **Step 2: Run all frontend tests**

```bash
cd photo-curator/frontend && npm test
```
Expected: all tests pass.

- [ ] **Step 3: Build frontend dist**

```bash
cd photo-curator/frontend && npm run build
```
Expected: build succeeds with no errors. New `dist/assets/index-*.js` created.

- [ ] **Step 4: Stage build artifacts and commit**

```bash
git add photo-curator/frontend/dist/
git commit -m "build: rebuild frontend dist with duplicate scanner UI"
```

- [ ] **Step 5: Final commit — clean up old stub routes**

The old `POST /api/duplicates/delete` and `GET /duplicates` HTML routes in `main.py` are now superseded. Remove them (lines ~1019–1080 in `main.py`). The old `static/duplicates.html` can also be removed.

```bash
git add photo-curator/src/main.py photo-curator/static/duplicates.html
git commit -m "chore(dedup): remove old stub duplicate routes and static HTML"
```
