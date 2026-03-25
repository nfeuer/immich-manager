"""Integration tests for /api/dedup/* routes."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import Request
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


def _role_passthrough(request: Request):
    """No-op role check for tests — sets request.state._local_user and passes."""
    request.state._local_user = FAKE_USER["_local_user"]
    return FAKE_USER["_local_user"]


def _collect_dedup_role_deps():
    """Collect all require_role closure objects from /api/dedup/* routes."""
    overrides = {}
    for route in app.routes:
        if not hasattr(route, 'path') or 'dedup' not in route.path:
            continue
        if not hasattr(route, 'dependant'):
            continue
        for dep in route.dependant.dependencies:
            fn = dep.call
            if fn.__name__ == '_check' and 'require_role' in (fn.__qualname__ or ''):
                overrides[fn] = _role_passthrough
    return overrides


@pytest.fixture
def client(tmp_path):
    role_overrides = _collect_dedup_role_deps()
    app.dependency_overrides = {get_current_user: _auth_override, **role_overrides}
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
