"""
SSH login monitor for IP gate.

Watches journalctl for successful SSH logins and sends alerts for
unrecognized IPs. Does NOT block or modify firewall rules.

Run as a systemd service: ip-gate-ssh-monitor.service
"""

import sys
import re
import subprocess
import logging
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

# Add project root to path for shared library
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.auth.ip_gate import (
    ensure_ip_gate_tables,
    get_trusted_ip,
    insert_pending_ip,
    record_ip_connection,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Matches: "Accepted publickey for username from 1.2.3.4 port 54321 ssh2"
_SSH_ACCEPTED_RE = re.compile(
    r"Accepted\s+\S+\s+for\s+(\S+)\s+from\s+(\d+\.\d+\.\d+\.\d+)\s+port"
)

DB_PATH = "data/server-manager.db"


class SimpleDB:
    """Minimal DB wrapper matching the _get_connection pattern."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def send_ssh_alert(ip_address: str, ssh_user: str):
    """Send Discord + email alert for unknown SSH login."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from config import load_config
        from alerts import AlertManager

        config, _ = load_config()
        alert_mgr = AlertManager(config.alerts)

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        title = "SSH login from unrecognized IP"
        message = (
            f"User `{ssh_user}` logged in via SSH from `{ip_address}` at {now}.\n\n"
            "This is an alert only -- no automatic action has been taken.\n"
            "If this wasn't you, investigate immediately."
        )

        alert_mgr.send_discord(title, message, "critical")

        import asyncio
        asyncio.run(alert_mgr.send_email(title, message, "critical"))

    except Exception as e:
        logger.error("Failed to send SSH alert: %s", e)


def process_line(line: str, db: SimpleDB):
    """Process a single journalctl line."""
    match = _SSH_ACCEPTED_RE.search(line)
    if not match:
        return

    ssh_user = match.group(1)
    ip_address = match.group(2)

    logger.info("SSH login detected: user=%s ip=%s", ssh_user, ip_address)

    row = get_trusted_ip(db, ip_address)

    if row and row["status"] == "trusted":
        record_ip_connection(db, ip_address, "ssh", "allowed", user_id=ssh_user)
        logger.info("SSH from trusted IP %s (user=%s)", ip_address, ssh_user)
    else:
        insert_pending_ip(db, ip_address, source="ssh")
        record_ip_connection(db, ip_address, "ssh", "alert_sent", user_id=ssh_user)
        logger.warning("SSH from UNKNOWN IP %s (user=%s) — sending alert", ip_address, ssh_user)
        send_ssh_alert(ip_address, ssh_user)


def main():
    """Main loop: follow journalctl for SSH events."""
    logger.info("Starting SSH monitor...")

    db = SimpleDB(DB_PATH)
    ensure_ip_gate_tables(db)

    cmd = ["journalctl", "-u", "ssh", "-f", "--no-pager", "-o", "short"]
    logger.info("Running: %s", " ".join(cmd))

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    try:
        for line in proc.stdout:
            line = line.strip()
            if line:
                process_line(line, db)
    except KeyboardInterrupt:
        logger.info("SSH monitor stopped by user")
    finally:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    main()
