# server-manager/tests/test_ip_gate_routes.py
import pytest
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.auth.ip_gate import ensure_ip_gate_tables, insert_pending_ip, get_trusted_ip


class FakeDB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def _get_connection(self):
        from contextlib import contextmanager

        @contextmanager
        def ctx():
            yield self.conn
        return ctx()


@pytest.fixture
def app_with_db():
    from fastapi import FastAPI
    from ip_gate_routes import ip_gate_router

    app = FastAPI()
    db = FakeDB()
    ensure_ip_gate_tables(db)

    app.state.ip_gate_db = db
    app.state.ip_gate_config = MagicMock(
        enabled=True,
        token_expiry_minutes=15,
        trusted_proxy_ips=["127.0.0.1"],
    )
    app.state.alert_manager = None
    app.state.immich_api_url = "http://localhost:2283/api"

    app.include_router(ip_gate_router)
    return app, db


@pytest.fixture
def client(app_with_db):
    app, db = app_with_db
    return TestClient(app), db


def test_status_unknown_ip(client):
    tc, db = client
    resp = tc.get("/api/ip-gate/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unknown"


def test_status_pending_ip(client):
    tc, db = client
    insert_pending_ip(db, "testclient")
    resp = tc.get("/api/ip-gate/status")
    data = resp.json()
    assert data["status"] == "pending"


def test_challenge_submit_invalid_email(client):
    tc, db = client
    resp = tc.post("/api/ip-gate/challenge", json={"email": "not-an-email"})
    assert resp.status_code == 400


def test_challenge_submit_valid_email_no_immich_user(client):
    tc, db = client
    with patch("ip_gate_routes.validate_immich_email") as mock_validate:
        mock_validate.return_value = None
        resp = tc.post("/api/ip-gate/challenge", json={"email": "user@example.com"})
        assert resp.status_code == 200
        assert "verification email" in resp.json()["message"].lower()
