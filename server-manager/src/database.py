"""
Database models and management for Server Manager
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Each migration is a (version, description, sql_statements) tuple.
# Migrations are applied in order and only once.  New schema changes go here.
MIGRATIONS: List[tuple] = [
    # Version 1: initial schema (already created by _init_db for fresh installs)
    (1, "initial schema", []),
    # Version 2: users table for RBAC
    (2, "add users table for RBAC", [
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            immich_user_id TEXT NOT NULL UNIQUE,
            email TEXT,
            name TEXT,
            role TEXT NOT NULL DEFAULT 'user',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_users_immich_id ON users(immich_user_id)",
    ]),
]


class Database:
    """SQLite database manager"""

    def __init__(self, db_path: str = "data/server-manager.db"):
        """
        Initialize database connection

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()
        self._run_migrations()

    @contextmanager
    def _get_connection(self):
        """Get database connection context manager"""
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

    def _init_db(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Disk health table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS disk_health (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    device TEXT NOT NULL,
                    smart_status TEXT,
                    temperature INTEGER,
                    power_on_hours INTEGER,
                    power_cycle_count INTEGER,
                    reallocated_sectors INTEGER,
                    pending_sectors INTEGER,
                    uncorrectable_sectors INTEGER,
                    raw_data TEXT
                )
            """)

            # System metrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    cpu_percent REAL,
                    memory_percent REAL,
                    memory_used_gb REAL,
                    memory_total_gb REAL,
                    disk_usage_percent REAL,
                    disk_used_gb REAL,
                    disk_total_gb REAL,
                    network_sent_mb REAL,
                    network_recv_mb REAL
                )
            """)

            # Backups table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    backup_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    file_path TEXT,
                    size_bytes INTEGER,
                    duration_seconds INTEGER,
                    error_message TEXT
                )
            """)

            # Alerts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    severity TEXT NOT NULL,
                    category TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT,
                    acknowledged BOOLEAN DEFAULT 0
                )
            """)

            # Docker containers table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS docker_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    container_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    cpu_percent REAL,
                    memory_mb REAL
                )
            """)

            # Create indices
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_disk_health_timestamp ON disk_health(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_disk_health_device ON disk_health(device)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_metrics_timestamp ON system_metrics(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_backups_timestamp ON backups(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity)")

            # Schema version tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def _run_migrations(self):
        """Apply pending database migrations in order."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
            current_version = cursor.fetchone()[0]

            for version, description, statements in MIGRATIONS:
                if version <= current_version:
                    continue
                logger.info(f"Applying migration v{version}: {description}")
                for sql in statements:
                    cursor.execute(sql)
                cursor.execute(
                    "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                    (version, description),
                )
            # If the database is brand new (no migrations recorded), mark v1 as applied
            if current_version == 0 and MIGRATIONS:
                cursor.execute("SELECT COUNT(*) FROM schema_version")
                if cursor.fetchone()[0] == 0:
                    cursor.execute(
                        "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                        (1, "initial schema"),
                    )

    def record_disk_health(self, device: str, data: Dict[str, Any]):
        """Record disk health data"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO disk_health (
                    device, smart_status, temperature, power_on_hours,
                    power_cycle_count, reallocated_sectors, pending_sectors,
                    uncorrectable_sectors, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device,
                data.get('smart_status'),
                data.get('temperature'),
                data.get('power_on_hours'),
                data.get('power_cycle_count'),
                data.get('reallocated_sectors'),
                data.get('pending_sectors'),
                data.get('uncorrectable_sectors'),
                str(data)
            ))

    def record_system_metrics(self, metrics: Dict[str, Any]):
        """Record system metrics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO system_metrics (
                    cpu_percent, memory_percent, memory_used_gb, memory_total_gb,
                    disk_usage_percent, disk_used_gb, disk_total_gb,
                    network_sent_mb, network_recv_mb
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metrics.get('cpu_percent'),
                metrics.get('memory_percent'),
                metrics.get('memory_used_gb'),
                metrics.get('memory_total_gb'),
                metrics.get('disk_usage_percent'),
                metrics.get('disk_used_gb'),
                metrics.get('disk_total_gb'),
                metrics.get('network_sent_mb'),
                metrics.get('network_recv_mb')
            ))

    def record_backup(self, backup_type: str, status: str, **kwargs):
        """Record backup status"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO backups (
                    backup_type, status, file_path, size_bytes,
                    duration_seconds, error_message
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                backup_type,
                status,
                kwargs.get('file_path'),
                kwargs.get('size_bytes'),
                kwargs.get('duration_seconds'),
                kwargs.get('error_message')
            ))

    def record_alert(self, severity: str, category: str, message: str, details: Optional[str] = None):
        """Record alert"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO alerts (severity, category, message, details)
                VALUES (?, ?, ?, ?)
            """, (severity, category, message, details))

    def record_docker_status(self, container_name: str, status: str, cpu_percent: float, memory_mb: float):
        """Record Docker container status"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO docker_status (container_name, status, cpu_percent, memory_mb)
                VALUES (?, ?, ?, ?)
            """, (container_name, status, cpu_percent, memory_mb))

    def get_latest_disk_health(self, device: Optional[str] = None) -> List[Dict]:
        """Get latest disk health data"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if device:
                cursor.execute("""
                    SELECT * FROM disk_health
                    WHERE device = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (device,))
            else:
                cursor.execute("""
                    SELECT * FROM disk_health
                    WHERE id IN (
                        SELECT MAX(id) FROM disk_health GROUP BY device
                    )
                    ORDER BY device
                """)

            return [dict(row) for row in cursor.fetchall()]

    def get_system_metrics(self, hours: int = 24) -> List[Dict]:
        """Get system metrics for specified time range"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM system_metrics
                WHERE timestamp >= datetime('now', '-' || ? || ' hours')
                ORDER BY timestamp DESC
            """, (hours,))

            return [dict(row) for row in cursor.fetchall()]

    def get_recent_backups(self, limit: int = 10) -> List[Dict]:
        """Get recent backups"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM backups
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))

            return [dict(row) for row in cursor.fetchall()]

    def get_alerts(self, acknowledged: bool = False, limit: int = 50) -> List[Dict]:
        """Get alerts"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM alerts
                WHERE acknowledged = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (1 if acknowledged else 0, limit))

            return [dict(row) for row in cursor.fetchall()]

    def acknowledge_alert(self, alert_id: int):
        """Mark alert as acknowledged"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE alerts SET acknowledged = 1
                WHERE id = ?
            """, (alert_id,))

    def cleanup_old_data(self, days: int = 90):
        """Clean up old data"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Clean old metrics (keep only aggregated data)
            cursor.execute("""
                DELETE FROM system_metrics
                WHERE timestamp < datetime('now', '-' || ? || ' days')
            """, (days,))

            # Clean old disk health data
            cursor.execute("""
                DELETE FROM disk_health
                WHERE timestamp < datetime('now', '-' || ? || ' days')
            """, (days,))

            # Keep all backups and alerts history
