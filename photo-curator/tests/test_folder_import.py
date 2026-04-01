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
