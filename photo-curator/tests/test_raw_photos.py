"""Tests for GET /api/photos/{year}/{month}/raw"""
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

FAKE_PHOTOS = [
    {
        "id": "asset-1",
        "fileCreatedAt": "2024-03-15T10:00:00Z",
        "exifInfo": {"exifImageWidth": 1920, "exifImageHeight": 1080},
    },
    {
        "id": "asset-2",
        "fileCreatedAt": "2024-03-20T12:00:00Z",
        "exifInfo": {"exifImageWidth": 800, "exifImageHeight": 600},
    },
]


def _auth_override():
    return FAKE_USER


def test_raw_photos_returns_list():
    app.dependency_overrides = {}
    app.dependency_overrides[get_current_user] = _auth_override

    with patch("src.main.ImmichClient") as MockClient:
        instance = MockClient.return_value
        instance.get_user_photos.return_value = FAKE_PHOTOS

        client = TestClient(app)
        resp = client.get("/api/photos/2024/3/raw")

    app.dependency_overrides = {}
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["photos"][0]["asset_id"] == "asset-1"
    assert data["photos"][0]["thumbnail_url"] == "/api/thumbnail/asset-1"
    assert data["photos"][0]["width"] == 1920
    assert data["photos"][0]["height"] == 1080


def test_raw_photos_requires_auth():
    app.dependency_overrides = {}
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/photos/2024/3/raw")
    assert resp.status_code == 401


def test_raw_photos_empty_month():
    app.dependency_overrides[get_current_user] = _auth_override

    with patch("src.main.ImmichClient") as MockClient:
        instance = MockClient.return_value
        instance.get_user_photos.return_value = []

        client = TestClient(app)
        resp = client.get("/api/photos/2024/2/raw")

    app.dependency_overrides = {}
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["photos"] == []
