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
    # Version 3: auto-updater tables (snapshots + update_history)
    (3, "add auto-updater snapshot and update_history tables", [
        """CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            trigger TEXT NOT NULL,
            version_before TEXT NOT NULL,
            db_backup_path TEXT,
            compose_backup_path TEXT,
            status TEXT NOT NULL DEFAULT 'available'
        )""",
        "CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON snapshots(created_at)",
        """CREATE TABLE IF NOT EXISTS update_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            from_version TEXT,
            to_version TEXT,
            snapshot_id INTEGER REFERENCES snapshots(id),
            status TEXT NOT NULL,
            error_message TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_update_history_started_at ON update_history(started_at)",
    ]),
    # Version 4: GPU and system power tracking
    (4, "add gpu_metrics and system_power tables", [
        """CREATE TABLE IF NOT EXISTS gpu_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            gpu_index INTEGER NOT NULL,
            gpu_uuid TEXT,
            gpu_name TEXT,
            vendor TEXT,
            temperature_c REAL,
            util_percent REAL,
            mem_util_percent REAL,
            mem_used_mb REAL,
            mem_total_mb REAL,
            power_draw_w REAL,
            power_limit_w REAL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_gpu_metrics_timestamp ON gpu_metrics(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_gpu_metrics_index_ts ON gpu_metrics(gpu_index, timestamp)",
        """CREATE TABLE IF NOT EXISTS system_power (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            total_watts REAL,
            cpu_watts REAL,
            gpu_watts REAL,
            baseline_watts REAL,
            source TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_system_power_timestamp ON system_power(timestamp)",
    ]),
    # Version 5: GPU detail fields + AC wattage + alert-state persistence
    (5, "add gpu detail columns, ac watts, alert_state", [
        "ALTER TABLE gpu_metrics ADD COLUMN pstate TEXT",
        "ALTER TABLE gpu_metrics ADD COLUMN fan_speed_percent REAL",
        "ALTER TABLE gpu_metrics ADD COLUMN gfx_clock_mhz REAL",
        "ALTER TABLE gpu_metrics ADD COLUMN mem_clock_mhz REAL",
        "ALTER TABLE gpu_metrics ADD COLUMN pcie_gen REAL",
        "ALTER TABLE gpu_metrics ADD COLUMN pcie_width REAL",
        "ALTER TABLE gpu_metrics ADD COLUMN driver_version TEXT",
        "ALTER TABLE system_power ADD COLUMN ac_watts REAL",
        "ALTER TABLE system_power ADD COLUMN psu_efficiency REAL",
        """CREATE TABLE IF NOT EXISTS alert_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
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

            # GPU history is high-volume (per-minute per-GPU); cap independently at 14 days
            # so the 7-day dashboard window always has full coverage with a buffer.
            cursor.execute("""
                DELETE FROM gpu_metrics
                WHERE timestamp < datetime('now', '-14 days')
            """)
            cursor.execute("""
                DELETE FROM system_power
                WHERE timestamp < datetime('now', '-14 days')
            """)

            # Keep all backups and alerts history

    # ------------------------------------------------------------------ #
    # GPU + system power helpers                                          #
    # ------------------------------------------------------------------ #

    def record_gpu_metrics(self, gpus: List[Dict[str, Any]]) -> None:
        """Insert one row per GPU snapshot."""
        if not gpus:
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """INSERT INTO gpu_metrics (
                    gpu_index, gpu_uuid, gpu_name, vendor,
                    temperature_c, util_percent, mem_util_percent,
                    mem_used_mb, mem_total_mb, power_draw_w, power_limit_w,
                    pstate, fan_speed_percent, gfx_clock_mhz, mem_clock_mhz,
                    pcie_gen, pcie_width, driver_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        g.get("index"),
                        g.get("uuid"),
                        g.get("name"),
                        g.get("vendor"),
                        g.get("temperature_c"),
                        g.get("util_percent"),
                        g.get("mem_util_percent"),
                        g.get("mem_used_mb"),
                        g.get("mem_total_mb"),
                        g.get("power_draw_w"),
                        g.get("power_limit_w"),
                        g.get("pstate"),
                        g.get("fan_speed_percent"),
                        g.get("gfx_clock_mhz"),
                        g.get("mem_clock_mhz"),
                        g.get("pcie_gen"),
                        g.get("pcie_width"),
                        g.get("driver_version"),
                    )
                    for g in gpus
                ],
            )

    def record_system_power(self, sample: Dict[str, Any]) -> None:
        """Insert a single system-power sample."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO system_power
                   (total_watts, cpu_watts, gpu_watts, baseline_watts, source,
                    ac_watts, psu_efficiency)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    sample.get("total_watts"),
                    sample.get("cpu_watts"),
                    sample.get("gpu_watts"),
                    sample.get("baseline_watts"),
                    sample.get("source"),
                    sample.get("ac_watts"),
                    sample.get("psu_efficiency"),
                ),
            )

    # ------------------------------------------------------------------ #
    # Alert-state KV (persists transition state across service restarts)  #
    # ------------------------------------------------------------------ #

    def get_alert_state(self, key: str) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM alert_state WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else None

    def set_alert_state(self, key: str, value: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO alert_state (key, value, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(key) DO UPDATE SET
                       value = excluded.value,
                       updated_at = CURRENT_TIMESTAMP""",
                (key, value),
            )

    def get_latest_gpu_metrics(self) -> List[Dict]:
        """Return the most recent row per gpu_index."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM gpu_metrics
                   WHERE id IN (
                       SELECT MAX(id) FROM gpu_metrics GROUP BY gpu_index
                   )
                   ORDER BY gpu_index"""
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_gpu_history(
        self,
        hours: int = 168,
        gpu_index: Optional[int] = None,
    ) -> List[Dict]:
        """Return GPU metrics within a time window (default 7 days)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if gpu_index is not None:
                cursor.execute(
                    """SELECT * FROM gpu_metrics
                       WHERE timestamp >= datetime('now', '-' || ? || ' hours')
                         AND gpu_index = ?
                       ORDER BY timestamp ASC""",
                    (hours, gpu_index),
                )
            else:
                cursor.execute(
                    """SELECT * FROM gpu_metrics
                       WHERE timestamp >= datetime('now', '-' || ? || ' hours')
                       ORDER BY timestamp ASC""",
                    (hours,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_system_power_history(self, hours: int = 168) -> List[Dict]:
        """Return system power samples within a time window."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM system_power
                   WHERE timestamp >= datetime('now', '-' || ? || ' hours')
                   ORDER BY timestamp ASC""",
                (hours,),
            )
            return [dict(row) for row in cursor.fetchall()]

    # ``idle`` here = samples where the GPU was effectively doing nothing.
    # 5% util is generous enough to include idle compositor work but excludes
    # any meaningful workload.
    _IDLE_UTIL_THRESHOLD = 5.0

    def get_gpu_summary(self, hours: int = 168) -> List[Dict]:
        """Aggregate per-GPU peak vs. idle stats over a window.

        Returns one row per GPU with:
          - ``peak_*``: maximum observed temp / util / power
          - ``idle_*``: average temp / power on samples where util < 5%
            (or ``None`` if the GPU was never idle in the window)
          - ``avg_*``: window-wide averages
          - ``sample_count``: total samples in window
          - ``idle_sample_count``: samples that met the idle threshold

        Idle is computed as an average of low-utilization samples rather
        than ``MIN()`` so transient dips (e.g. between two inference batches)
        don't get reported as the idle baseline.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT
                    gpu_index,
                    MAX(gpu_name) AS gpu_name,
                    MAX(vendor) AS vendor,
                    COUNT(*) AS sample_count,
                    MAX(temperature_c) AS peak_temp,
                    MAX(util_percent) AS peak_util,
                    MAX(power_draw_w) AS peak_power,
                    AVG(temperature_c) AS avg_temp,
                    AVG(util_percent) AS avg_util,
                    AVG(power_draw_w) AS avg_power,
                    MAX(power_limit_w) AS power_limit,
                    MAX(fan_speed_percent) AS peak_fan,
                    -- Idle aggregates: AVG(...) FILTER (WHERE ...) gives us
                    -- the per-GPU mean only over low-utilization samples.
                    AVG(CASE WHEN util_percent < ?
                            THEN temperature_c END) AS idle_temp,
                    AVG(CASE WHEN util_percent < ?
                            THEN power_draw_w END) AS idle_power,
                    SUM(CASE WHEN util_percent < ? THEN 1 ELSE 0 END) AS idle_sample_count
                   FROM gpu_metrics
                   WHERE timestamp >= datetime('now', '-' || ? || ' hours')
                   GROUP BY gpu_index
                   ORDER BY gpu_index""",
                (
                    self._IDLE_UTIL_THRESHOLD,
                    self._IDLE_UTIL_THRESHOLD,
                    self._IDLE_UTIL_THRESHOLD,
                    hours,
                ),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_system_power_summary(self, hours: int = 168) -> Dict[str, Any]:
        """Aggregate system power totals over a window."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT
                    COUNT(*) AS sample_count,
                    MAX(total_watts) AS peak_watts,
                    AVG(total_watts) AS avg_watts,
                    MAX(ac_watts) AS peak_ac_watts,
                    AVG(ac_watts) AS avg_ac_watts,
                    MAX(source) AS source
                   FROM system_power
                   WHERE timestamp >= datetime('now', '-' || ? || ' hours')""",
                (hours,),
            )
            row = cursor.fetchone()
            return dict(row) if row else {}

    # ------------------------------------------------------------------ #
    # Snapshot helpers                                                     #
    # ------------------------------------------------------------------ #

    def record_snapshot(
        self,
        trigger: str,
        version_before: str,
        db_backup_path: Optional[str] = None,
        compose_backup_path: Optional[str] = None,
    ) -> int:
        """Insert a snapshot record and return its id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO snapshots
                   (trigger, version_before, db_backup_path, compose_backup_path, status)
                   VALUES (?, ?, ?, ?, 'available')""",
                (trigger, version_before, db_backup_path, compose_backup_path),
            )
            return cursor.lastrowid

    def get_snapshots(self, limit: int = 20) -> List[Dict]:
        """Return the most recent snapshots."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM snapshots ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def update_snapshot_status(self, snapshot_id: int, status: str) -> None:
        """Update the status field of a snapshot."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE snapshots SET status = ? WHERE id = ?", (status, snapshot_id)
            )

    # ------------------------------------------------------------------ #
    # Update-history helpers                                               #
    # ------------------------------------------------------------------ #

    def record_update_history(
        self,
        from_version: str,
        to_version: str,
        status: str = "in_progress",
    ) -> int:
        """Insert an in-progress update record and return its id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO update_history (from_version, to_version, status)
                   VALUES (?, ?, ?)""",
                (from_version, to_version, status),
            )
            return cursor.lastrowid

    def complete_update_history(
        self,
        history_id: int,
        status: str,
        error_message: Optional[str] = None,
        snapshot_id: Optional[int] = None,
    ) -> None:
        """Mark an update record as complete with final status and metadata."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE update_history
                   SET completed_at = CURRENT_TIMESTAMP,
                       status = ?,
                       error_message = ?,
                       snapshot_id = COALESCE(?, snapshot_id)
                   WHERE id = ?""",
                (status, error_message, snapshot_id, history_id),
            )

    def get_update_history(self, limit: int = 20) -> List[Dict]:
        """Return the most recent update history records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM update_history ORDER BY started_at DESC LIMIT ?", (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
