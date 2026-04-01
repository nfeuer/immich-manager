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
