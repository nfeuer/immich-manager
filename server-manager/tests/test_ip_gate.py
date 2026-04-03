import sqlite3
import pytest
from datetime import datetime, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.auth.ip_gate import (
    ensure_ip_gate_tables,
    get_trusted_ip,
    insert_pending_ip,
    trust_ip,
    revoke_ip,
    record_ip_connection,
    get_ip_connections_count_7d,
)


class FakeDB:
    """Minimal DB wrapper matching Database._get_connection pattern."""
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def _get_connection(self):
        from contextlib import contextmanager

        @contextmanager
        def ctx():
            yield self.conn
        return ctx()


@pytest.fixture
def db():
    d = FakeDB()
    ensure_ip_gate_tables(d)
    return d


def test_ensure_tables_creates_all_three(db):
    cursor = db.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert "trusted_ips" in tables
    assert "ip_connections" in tables
    assert "verification_tokens" in tables


def test_insert_pending_ip(db):
    insert_pending_ip(db, "1.2.3.4", source="web")
    row = get_trusted_ip(db, "1.2.3.4")
    assert row is not None
    assert row["status"] == "pending"
    assert row["source"] == "web"


def test_insert_pending_ip_duplicate_ignored(db):
    insert_pending_ip(db, "1.2.3.4", source="web")
    insert_pending_ip(db, "1.2.3.4", source="ssh")  # should not raise
    row = get_trusted_ip(db, "1.2.3.4")
    assert row["source"] == "web"  # first insert wins


def test_trust_ip(db):
    insert_pending_ip(db, "10.0.0.1", source="web")
    trust_ip(db, "10.0.0.1", access_level="admin", trust_duration="30d",
             verified_by="admin@test.com")
    row = get_trusted_ip(db, "10.0.0.1")
    assert row["status"] == "trusted"
    assert row["access_level"] == "admin"
    assert row["verified_by"] == "admin@test.com"
    assert row["expires_at"] is not None


def test_trust_ip_permanent_no_expiry(db):
    insert_pending_ip(db, "10.0.0.2", source="web")
    trust_ip(db, "10.0.0.2", access_level="user", trust_duration="permanent",
             verified_by="user@test.com")
    row = get_trusted_ip(db, "10.0.0.2")
    assert row["expires_at"] is None


def test_revoke_ip(db):
    insert_pending_ip(db, "5.5.5.5", source="web")
    trust_ip(db, "5.5.5.5", access_level="user", trust_duration="permanent",
             verified_by="u@test.com")
    revoke_ip(db, "5.5.5.5", revoked_by="admin@test.com", reason="suspicious")
    row = get_trusted_ip(db, "5.5.5.5")
    assert row["status"] == "revoked"
    assert row["revoked_by"] == "admin@test.com"
    assert row["revoke_reason"] == "suspicious"


def test_record_and_count_connections(db):
    record_ip_connection(db, "1.1.1.1", service="server-manager", action="allowed")
    record_ip_connection(db, "1.1.1.1", service="server-manager", action="allowed")
    record_ip_connection(db, "1.1.1.1", service="photo-curator", action="allowed")
    count = get_ip_connections_count_7d(db, "1.1.1.1")
    assert count == 3


def test_get_trusted_ip_returns_none_for_unknown(db):
    assert get_trusted_ip(db, "9.9.9.9") is None
