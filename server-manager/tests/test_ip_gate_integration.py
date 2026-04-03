# server-manager/tests/test_ip_gate_integration.py
"""
Integration test for the full IP gate flow:
unknown IP -> challenge -> submit email -> verify token -> trusted.
"""
import pytest
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.auth.ip_gate import (
    ensure_ip_gate_tables, get_trusted_ip, create_verification_token,
    validate_verification_token,
)
from ip_gate_routes import ip_gate_router
from ip_gate_middleware import IPGateMiddleware


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
def full_app():
    app = FastAPI()
    db = FakeDB()
    ensure_ip_gate_tables(db)

    # Also need users table for get_or_create_user
    from shared.auth import ensure_users_table
    ensure_users_table(db)

    ip_gate_config = MagicMock(
        enabled=True,
        token_expiry_minutes=15,
        trusted_proxy_ips=[],
        cloudflare=MagicMock(enabled=False),
    )

    app.state.ip_gate_db = db
    app.state.ip_gate_config = ip_gate_config
    app.state.alert_manager = MagicMock()
    app.state.alert_manager.send_email_to = AsyncMock(return_value=True)
    app.state.alert_manager.send_discord = MagicMock(return_value=True)
    app.state.alert_manager.send_email = AsyncMock(return_value=True)
    app.state.immich_api_url = "http://localhost:2283/api"
    app.state.public_url = "http://localhost:8080"

    app.add_middleware(IPGateMiddleware)
    app.include_router(ip_gate_router)

    # Add a test endpoint that requires IP gate
    @app.get("/api/test")
    async def test_endpoint():
        return {"ok": True}

    return app, db


def test_full_verification_flow(full_app):
    app, db = full_app
    client = TestClient(app, raise_server_exceptions=True)

    # 1. Request to /api/test from an unknown IP should be challenged.
    #    The middleware returns 403 with JSON when Accept: application/json.
    resp = client.get(
        "/api/test",
        headers={"accept": "application/json"},
        follow_redirects=False,
    )
    assert resp.status_code == 403
    body = resp.json()
    # The challenge_url is inside the JSON body returned by the middleware
    assert "challenge_url" in body

    # 2. Check status — IP was inserted as pending by the middleware
    resp = client.get("/api/ip-gate/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"

    # 3. Submit challenge email — mock Immich user lookup to return a valid user
    mock_user = {"id": "user-123", "email": "admin@example.com", "name": "Admin User"}
    with patch("ip_gate_routes.validate_immich_email", return_value=mock_user):
        resp = client.post("/api/ip-gate/challenge", json={"email": "admin@example.com"})
        assert resp.status_code == 200
        assert "verification email" in resp.json()["message"].lower()

    # 4. Get the token from the DB directly and verify it
    with db._get_connection() as conn:
        row = conn.cursor().execute(
            "SELECT token FROM verification_tokens LIMIT 1"
        ).fetchone()
        assert row is not None, "Expected a verification token to be created"
        token = row["token"]

    # 5. Verify the token. Mock user lookup as admin so IP gets admin access level.
    #    The server-manager only allows "admin" access level through (check_ip_access
    #    blocks "user" level for this service), so we must resolve the user as admin.
    mock_admin_user = {"role": "admin"}
    with patch("ip_gate_routes.validate_immich_email", return_value=mock_user), \
         patch("ip_gate_routes.get_or_create_user", return_value=(mock_admin_user, False)):
        resp = client.get(f"/api/ip-gate/verify/{token}?duration=7d")
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_level"] == "admin"
        assert data["trust_duration"] == "7d"

    # 6. The IP should now be trusted in the DB
    ip_row = get_trusted_ip(db, "testclient")
    assert ip_row is not None, "Expected IP record to exist after verification"
    assert ip_row["status"] == "trusted"
    assert ip_row["trust_duration"] == "7d"
    assert ip_row["access_level"] == "admin"

    # 7. Request to /api/test should now succeed — middleware allows trusted admin IPs
    resp = client.get("/api/test")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_challenge_missing_email_rejected(full_app):
    """Submit with an invalid email format is rejected immediately (no DB changes)."""
    app, db = full_app
    client = TestClient(app)

    resp = client.post("/api/ip-gate/challenge", json={"email": "not-an-email"})
    assert resp.status_code == 400


def test_revoked_ip_blocked(full_app):
    """A revoked IP receives 403 even for /api/test."""
    app, db = full_app
    client = TestClient(app)

    # Insert and then revoke the testclient IP
    from shared.auth.ip_gate import insert_pending_ip, revoke_ip
    insert_pending_ip(db, "testclient")
    revoke_ip(db, "testclient", revoked_by="admin:test", reason="test block")

    resp = client.get(
        "/api/test",
        headers={"accept": "application/json"},
        follow_redirects=False,
    )
    assert resp.status_code == 403
    assert "blocked" in resp.json()["detail"].lower()


def test_token_verify_invalid_token(full_app):
    """Verifying with a bogus token returns 400."""
    app, db = full_app
    client = TestClient(app)

    resp = client.get("/api/ip-gate/verify/notavalidtoken123?duration=7d")
    assert resp.status_code == 400


def test_challenge_no_immich_user_still_returns_200(full_app):
    """
    If the submitted email is not in Immich, the response is still 200
    (intentional — no information leak about valid emails).
    """
    app, db = full_app
    client = TestClient(app)

    with patch("ip_gate_routes.validate_immich_email", return_value=None):
        resp = client.post("/api/ip-gate/challenge", json={"email": "unknown@example.com"})
        assert resp.status_code == 200
        assert "verification email" in resp.json()["message"].lower()

    # No verification token should have been created for an unknown email
    with db._get_connection() as conn:
        count = conn.cursor().execute(
            "SELECT COUNT(*) FROM verification_tokens"
        ).fetchone()[0]
    assert count == 0
