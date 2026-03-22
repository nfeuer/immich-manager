"""Tests for GET /api/progress/year/{year}"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from src.auth import get_current_user
from src.main import app

FAKE_USER = {
    "id": "user-123",
    "email": "test@example.com",
    "name": "Test User",
    "access_token": "tok-abc",
    "_local_user": {"id": 1, "role": "user"},
}


def _auth_override():
    return FAKE_USER


def test_year_progress_returns_12_months():
    original_db = getattr(app.state, "database", None)
    app.dependency_overrides[get_current_user] = _auth_override
    mock_db = MagicMock()
    mock_db.get_year_progress.return_value = {m: m in (1, 3) for m in range(1, 13)}
    app.state.database = mock_db
    try:
        client = TestClient(app)
        resp = client.get("/api/progress/year/2024")
    finally:
        app.dependency_overrides = {}
        app.state.database = original_db
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 12
    assert data["1"] is True
    assert data["3"] is True
    assert data["2"] is False
    assert data["12"] is False


def test_year_progress_requires_auth():
    app.dependency_overrides = {}
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/progress/year/2024")
    assert resp.status_code == 401
