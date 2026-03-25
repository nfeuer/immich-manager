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
    assert row['score'] == 0.0


def test_upsert_perceptual_hash_updates_existing_without_clobbering_score(db):
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
    assert row['score'] == pytest.approx(0.85)
