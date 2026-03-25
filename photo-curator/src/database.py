"""
Database models and management for Photo Curator
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import json

logger = logging.getLogger(__name__)

# Each migration is a (version, description, sql_statements) tuple.
# Migrations are applied in order and only once.  New schema changes go here.
MIGRATIONS: List[tuple] = [
    # Version 1: initial schema (already created by _init_db for fresh installs)
    (1, "initial schema", []),
    # Version 2: shared curation (Family Mode) tables
    (2, "add shared curation tables", [
        """CREATE TABLE IF NOT EXISTS shared_curations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id TEXT NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            collaborator_id TEXT NOT NULL,
            invited_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(owner_id, year, month, collaborator_id)
        )""",
        """CREATE TABLE IF NOT EXISTS shared_selections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id TEXT NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            contributor_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(owner_id, year, month, contributor_id, asset_id)
        )""",
    ]),
    # Version 3: users table for RBAC + album sharing with token-based guest links
    (3, "add users and album sharing tables", [
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
        """CREATE TABLE IF NOT EXISTS album_shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            album_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            share_token TEXT NOT NULL UNIQUE,
            shared_with_user_id TEXT,
            guest_label TEXT,
            can_add_photos BOOLEAN DEFAULT 0,
            expires_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            revoked BOOLEAN DEFAULT 0
        )""",
        "CREATE INDEX IF NOT EXISTS idx_album_shares_token ON album_shares(share_token)",
        "CREATE INDEX IF NOT EXISTS idx_album_shares_album ON album_shares(album_id)",
        "CREATE INDEX IF NOT EXISTS idx_album_shares_user ON album_shares(shared_with_user_id)",
        """CREATE TABLE IF NOT EXISTS album_contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            album_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            share_id INTEGER NOT NULL,
            contributor_name TEXT NOT NULL,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(album_id, asset_id),
            FOREIGN KEY (share_id) REFERENCES album_shares(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_contributions_album ON album_contributions(album_id)",
        "CREATE INDEX IF NOT EXISTS idx_contributions_share ON album_contributions(share_id)",
        """CREATE TABLE IF NOT EXISTS share_access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            share_id INTEGER NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            accessed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (share_id) REFERENCES album_shares(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_access_log_share ON share_access_log(share_id)",
    ]),
    # Version 4: face recognition and scene detection tables
    (4, "add face recognition and scene detection tables", [
        # face_identities must be created before face_embeddings (FK reference)
        """CREATE TABLE IF NOT EXISTS face_identities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            label TEXT,
            representative_embedding BLOB,
            photo_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_face_ident_user ON face_identities(user_id)",
        """CREATE TABLE IF NOT EXISTS face_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            face_index INTEGER NOT NULL DEFAULT 0,
            embedding BLOB NOT NULL,
            bbox_x INTEGER,
            bbox_y INTEGER,
            bbox_w INTEGER,
            bbox_h INTEGER,
            identity_id INTEGER,
            confidence REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(asset_id, face_index),
            FOREIGN KEY (identity_id) REFERENCES face_identities(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_face_emb_asset ON face_embeddings(asset_id)",
        "CREATE INDEX IF NOT EXISTS idx_face_emb_user ON face_embeddings(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_face_emb_identity ON face_embeddings(identity_id)",
        """CREATE TABLE IF NOT EXISTS scene_classifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            scene_category TEXT NOT NULL,
            scene_subcategory TEXT,
            confidence REAL,
            top3_scenes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_scene_asset ON scene_classifications(asset_id)",
        "CREATE INDEX IF NOT EXISTS idx_scene_user ON scene_classifications(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_scene_category ON scene_classifications(scene_category)",
    ]),
    # Version 5: import jobs for web-based photo import
    (5, "add import_jobs table", [
        """CREATE TABLE IF NOT EXISTS import_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            import_method TEXT NOT NULL,
            server_path TEXT,
            staging_dir TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            total_files INTEGER DEFAULT 0,
            uploaded INTEGER DEFAULT 0,
            skipped INTEGER DEFAULT 0,
            errors INTEGER DEFAULT 0,
            duplicates INTEGER DEFAULT 0,
            error_message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            started_at DATETIME,
            completed_at DATETIME,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_import_jobs_user ON import_jobs(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_import_jobs_status ON import_jobs(status)",
    ]),
    # Version 6: event/trip suggestions for auto-detected photo clusters
    (6, "add event_suggestions table", [
        """CREATE TABLE IF NOT EXISTS event_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            photo_count INTEGER NOT NULL,
            thumbnail_asset_id TEXT NOT NULL,
            asset_ids TEXT NOT NULL,
            dismissed INTEGER DEFAULT 0,
            album_created INTEGER DEFAULT 0,
            album_id TEXT,
            detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, start_date, end_date)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_event_sugg_user ON event_suggestions(user_id)",
    ]),
    # Version 7: add participants column to event_suggestions (labeled face names)
    (7, "add participants column to event_suggestions", [
        "ALTER TABLE event_suggestions ADD COLUMN participants TEXT",
    ]),
    # Version 8: batch photo processing tables
    (8, "add batch processing tables", [
        """CREATE TABLE IF NOT EXISTS batch_jobs (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            mode TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            total_photos INTEGER DEFAULT 0,
            processed_photos INTEGER DEFAULT 0,
            successful_photos INTEGER DEFAULT 0,
            failed_photos INTEGER DEFAULT 0,
            current_batch INTEGER DEFAULT 0,
            total_batches INTEGER DEFAULT 0,
            consecutive_failures INTEGER DEFAULT 0,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            error_message TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_batch_jobs_status ON batch_jobs(status)",
        "CREATE INDEX IF NOT EXISTS idx_batch_jobs_user ON batch_jobs(user_id)",
        """CREATE TABLE IF NOT EXISTS batch_job_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            batch_number INTEGER DEFAULT 0,
            message TEXT NOT NULL,
            level TEXT NOT NULL DEFAULT 'info',
            logged_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES batch_jobs(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_batch_logs_job ON batch_job_logs(job_id)",
        """CREATE TABLE IF NOT EXISTS batch_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            batch_number INTEGER DEFAULT 0,
            asset_id TEXT NOT NULL,
            error_type TEXT NOT NULL,
            error_message TEXT NOT NULL,
            occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES batch_jobs(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_batch_errors_job ON batch_errors(job_id)",
        "CREATE INDEX IF NOT EXISTS idx_batch_errors_asset ON batch_errors(asset_id)",
    ]),
    # Version 9: standalone duplicate scanner tables
    (9, "add dedup scanner tables", [
        """CREATE TABLE IF NOT EXISTS dedup_scans (
            id              TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL,
            mode            TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'running',
            date_from       TEXT,
            date_to         TEXT,
            total_assets    INTEGER DEFAULT 0,
            hashed          INTEGER DEFAULT 0,
            groups_found    INTEGER DEFAULT 0,
            error_message   TEXT,
            started_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at    DATETIME
        )""",
        "CREATE INDEX IF NOT EXISTS idx_dedup_scans_user ON dedup_scans(user_id)",
        """CREATE TABLE IF NOT EXISTS dedup_asset_metadata (
            asset_id         TEXT PRIMARY KEY,
            user_id          TEXT NOT NULL,
            filename         TEXT,
            date_taken       TEXT,
            width            INTEGER,
            height           INTEGER,
            file_size_bytes  INTEGER,
            camera_make      TEXT,
            camera_model     TEXT,
            updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_dedup_meta_user ON dedup_asset_metadata(user_id)",
        "ALTER TABLE duplicate_groups ADD COLUMN scan_id TEXT",
        "ALTER TABLE duplicate_groups ADD COLUMN user_id TEXT",
        "ALTER TABLE duplicate_groups ADD COLUMN resolved INTEGER DEFAULT 0",
        "ALTER TABLE duplicate_groups ADD COLUMN recommended_keep_id TEXT",
        "CREATE INDEX IF NOT EXISTS idx_dup_groups_user ON duplicate_groups(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_dup_groups_scan ON duplicate_groups(scan_id)",
    ]),
]


class Database:
    """SQLite database manager for Photo Curator"""

    def __init__(self, db_path: str = "data/curator.db"):
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

            # Photo scores table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS photo_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    month INTEGER NOT NULL,
                    score REAL NOT NULL,
                    technical_quality REAL,
                    blur_score REAL,
                    exposure_score REAL,
                    composition_score REAL,
                    face_score REAL,
                    face_count INTEGER,
                    perceptual_hash TEXT,
                    width INTEGER,
                    height INTEGER,
                    megapixels REAL,
                    analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """)

            # Curation sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS curation_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    month INTEGER NOT NULL,
                    total_photos INTEGER,
                    ai_suggested INTEGER,
                    user_selected TEXT,
                    user_added TEXT,
                    user_removed TEXT,
                    album_id TEXT,
                    album_name TEXT,
                    completed BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME,
                    UNIQUE(user_id, year, month)
                )
            """)

            # User preferences table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT PRIMARY KEY,
                    monthly_target INTEGER DEFAULT 50,
                    reminder_enabled BOOLEAN DEFAULT 1,
                    last_reminder_sent DATETIME,
                    preferences TEXT
                )
            """)

            # Duplicate groups table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS duplicate_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_hash TEXT NOT NULL,
                    asset_ids TEXT NOT NULL,
                    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indices
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scores_user_date ON photo_scores(user_id, year, month)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scores_asset ON photo_scores(asset_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON curation_sessions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scores_hash ON photo_scores(perceptual_hash)")

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

    def save_photo_score(self, asset_id: str, user_id: str, year: int, month: int, scores: Dict[str, Any]):
        """Save or update photo score"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Prepare metadata
            metadata = {
                k: v for k, v in scores.items()
                if k not in ['score', 'technical_quality', 'blur_score', 'exposure_score',
                             'composition_score', 'face_score', 'face_count', 'perceptual_hash',
                             'width', 'height', 'megapixels']
            }

            cursor.execute("""
                INSERT OR REPLACE INTO photo_scores (
                    asset_id, user_id, year, month, score,
                    technical_quality, blur_score, exposure_score,
                    composition_score, face_score, face_count,
                    perceptual_hash, width, height, megapixels, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                asset_id, user_id, year, month, scores.get('score', 0),
                scores.get('technical_quality'), scores.get('blur_score'),
                scores.get('exposure_score'), scores.get('composition_score'),
                scores.get('face_score'), scores.get('face_count', 0),
                scores.get('perceptual_hash'),
                scores.get('width'), scores.get('height'), scores.get('megapixels'),
                json.dumps(metadata)
            ))

    def get_photo_scores(self, user_id: str, year: int, month: int) -> List[Dict]:
        """Get all photo scores for a user/month"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM photo_scores
                WHERE user_id = ? AND year = ? AND month = ?
                ORDER BY score DESC
            """, (user_id, year, month))

            return [dict(row) for row in cursor.fetchall()]

    def delete_photo_score(self, asset_id: str):
        """Delete a photo score by asset ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM photo_scores
                WHERE asset_id = ?
            """, (asset_id,))

    def get_top_photos(self, user_id: str, year: int, month: int, limit: int = 50) -> List[Dict]:
        """Get top N photos by score"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM photo_scores
                WHERE user_id = ? AND year = ? AND month = ?
                ORDER BY score DESC
                LIMIT ?
            """, (user_id, year, month, limit))

            return [dict(row) for row in cursor.fetchall()]

    def create_curation_session(
        self,
        user_id: str,
        year: int,
        month: int,
        total_photos: int,
        ai_suggested: List[str]
    ) -> int:
        """Create new curation session"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO curation_sessions (
                    user_id, year, month, total_photos, ai_suggested,
                    user_selected, user_added, user_removed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, year, month, total_photos,
                json.dumps(ai_suggested), json.dumps([]),
                json.dumps([]), json.dumps([])
            ))

            return cursor.lastrowid

    def update_curation_session(
        self,
        user_id: str,
        year: int,
        month: int,
        selected: Optional[List[str]] = None,
        added: Optional[List[str]] = None,
        removed: Optional[List[str]] = None
    ):
        """Update curation session selections"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            updates = []
            params = []

            if selected is not None:
                updates.append("user_selected = ?")
                params.append(json.dumps(selected))

            if added is not None:
                updates.append("user_added = ?")
                params.append(json.dumps(added))

            if removed is not None:
                updates.append("user_removed = ?")
                params.append(json.dumps(removed))

            params.extend([user_id, year, month])

            cursor.execute(f"""
                UPDATE curation_sessions
                SET {', '.join(updates)}
                WHERE user_id = ? AND year = ? AND month = ?
            """, params)

    def complete_curation_session(
        self,
        user_id: str,
        year: int,
        month: int,
        album_id: str,
        album_name: str
    ):
        """Mark curation session as completed"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE curation_sessions
                SET completed = 1, completed_at = CURRENT_TIMESTAMP,
                    album_id = ?, album_name = ?
                WHERE user_id = ? AND year = ? AND month = ?
            """, (album_id, album_name, user_id, year, month))

    def get_year_progress(self, user_id: str, year: int) -> dict:
        """
        Return curation status for all 12 months of a year.

        Returns:
            Dict mapping month (1-12) to bool (True = completed album exists)
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT month FROM curation_sessions
                WHERE user_id = ? AND year = ? AND completed = 1 AND album_id IS NOT NULL
                """,
                (user_id, year),
            ).fetchall()
        curated = {row[0] for row in rows}
        return {month: month in curated for month in range(1, 13)}

    def get_curation_session(self, user_id: str, year: int, month: int) -> Optional[Dict]:
        """Get curation session"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM curation_sessions
                WHERE user_id = ? AND year = ? AND month = ?
            """, (user_id, year, month))

            row = cursor.fetchone()
            if row:
                session = dict(row)
                # Parse JSON fields
                session['ai_suggested'] = json.loads(session['ai_suggested'])
                session['user_selected'] = json.loads(session['user_selected'])
                session['user_added'] = json.loads(session['user_added'])
                session['user_removed'] = json.loads(session['user_removed'])
                return session

            return None

    def get_user_progress(self, user_id: str) -> Dict[str, Any]:
        """Get user's curation progress"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Count completed months
            cursor.execute("""
                SELECT COUNT(*) as completed_count
                FROM curation_sessions
                WHERE user_id = ? AND completed = 1
            """, (user_id,))

            completed = cursor.fetchone()['completed_count']

            # Get recent sessions
            cursor.execute("""
                SELECT year, month, completed, album_name
                FROM curation_sessions
                WHERE user_id = ?
                ORDER BY year DESC, month DESC
                LIMIT 12
            """, (user_id,))

            sessions = [dict(row) for row in cursor.fetchall()]

            return {
                'completed_months': completed,
                'recent_sessions': sessions
            }

    def save_duplicate_group(self, asset_ids: List[str]):
        """Save duplicate group"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Create hash from sorted IDs
            group_hash = hash(tuple(sorted(asset_ids)))

            cursor.execute("""
                INSERT OR IGNORE INTO duplicate_groups (group_hash, asset_ids)
                VALUES (?, ?)
            """, (str(group_hash), json.dumps(asset_ids)))

    def get_duplicates_for_user(self, user_id: str, year: int, month: int) -> List[List[str]]:
        """Get duplicate groups for user's photos"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Get all asset IDs for user/month
            cursor.execute("""
                SELECT asset_id FROM photo_scores
                WHERE user_id = ? AND year = ? AND month = ?
            """, (user_id, year, month))

            user_assets = {row['asset_id'] for row in cursor.fetchall()}

            # Get duplicate groups
            cursor.execute("SELECT asset_ids FROM duplicate_groups")

            duplicates = []
            for row in cursor.fetchall():
                group = json.loads(row['asset_ids'])
                # Check if any assets in this group belong to user
                if any(asset_id in user_assets for asset_id in group):
                    duplicates.append(group)

            return duplicates

    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Get user preferences"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM user_preferences WHERE user_id = ?
            """, (user_id,))

            row = cursor.fetchone()
            if row:
                prefs = dict(row)
                if prefs.get('preferences'):
                    prefs['preferences'] = json.loads(prefs['preferences'])
                return prefs

            # Return defaults
            return {
                'user_id': user_id,
                'monthly_target': 50,
                'reminder_enabled': True,
                'preferences': {}
            }

    def update_user_preferences(self, user_id: str, preferences: Dict[str, Any]):
        """Update user preferences"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO user_preferences (
                    user_id, monthly_target, reminder_enabled, preferences
                ) VALUES (?, ?, ?, ?)
            """, (
                user_id,
                preferences.get('monthly_target', 50),
                preferences.get('reminder_enabled', True),
                json.dumps(preferences.get('preferences', {}))
            ))

    def save_user_preferences(self, user_id: str, monthly_target: int, preferences: Dict):
        """Save user preferences"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO user_preferences (
                    user_id, monthly_target, preferences
                ) VALUES (?, ?, ?)
            """, (user_id, monthly_target, json.dumps(preferences)))

    def get_statistics(self) -> Dict[str, Any]:
        """Get overall statistics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            stats = {}

            # Total photos analyzed
            cursor.execute("SELECT COUNT(*) as count FROM photo_scores")
            stats['total_photos_analyzed'] = cursor.fetchone()['count']

            # Total curation sessions
            cursor.execute("SELECT COUNT(*) as count FROM curation_sessions WHERE completed = 1")
            stats['completed_sessions'] = cursor.fetchone()['count']

            # Average score
            cursor.execute("SELECT AVG(score) as avg_score FROM photo_scores")
            stats['average_score'] = cursor.fetchone()['avg_score'] or 0

            # Photos with faces
            cursor.execute("SELECT COUNT(*) as count FROM photo_scores WHERE face_count > 0")
            stats['photos_with_faces'] = cursor.fetchone()['count']

            return stats

    def get_analytics_data(self, period_days: int = 30) -> Dict[str, Any]:
        """Get comprehensive analytics data for admin dashboard"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            analytics = {}

            # Total unique users
            cursor.execute("SELECT COUNT(DISTINCT user_id) as count FROM photo_scores")
            analytics['total_users'] = cursor.fetchone()['count']

            # Total photos curated (completed sessions)
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM curation_sessions
                WHERE completed = 1
            """)
            analytics['photos_curated'] = cursor.fetchone()['count']

            # Total albums created (same as completed sessions)
            analytics['albums_created'] = analytics['photos_curated']

            # Average quality score
            cursor.execute("SELECT AVG(score) as avg FROM photo_scores")
            avg_score = cursor.fetchone()['avg']
            analytics['avg_quality'] = round(avg_score, 2) if avg_score else 0

            # Upload trend (photos per month for last 12 months)
            cursor.execute("""
                SELECT
                    year || '-' || printf('%02d', month) as month_label,
                    COUNT(*) as count
                FROM photo_scores
                WHERE analyzed_at >= date('now', '-12 months')
                GROUP BY year, month
                ORDER BY year, month
            """)
            analytics['upload_trend'] = [
                {'month': row['month_label'], 'count': row['count']}
                for row in cursor.fetchall()
            ]

            # User activity (photos per user)
            cursor.execute("""
                SELECT
                    user_id,
                    COUNT(*) as photo_count
                FROM photo_scores
                GROUP BY user_id
                ORDER BY photo_count DESC
            """)
            analytics['user_activity'] = [
                {'user_id': row['user_id'], 'count': row['photo_count']}
                for row in cursor.fetchall()
            ]

            # Detailed user statistics
            cursor.execute("""
                SELECT
                    ps.user_id,
                    COUNT(DISTINCT ps.id) as total_photos,
                    AVG(ps.score) as avg_score,
                    COUNT(DISTINCT cs.id) as albums_created,
                    MAX(ps.analyzed_at) as last_active
                FROM photo_scores ps
                LEFT JOIN curation_sessions cs ON
                    ps.user_id = cs.user_id AND cs.completed = 1
                GROUP BY ps.user_id
                ORDER BY total_photos DESC
            """)
            analytics['user_stats'] = [
                {
                    'user_id': row['user_id'],
                    'total_photos': row['total_photos'],
                    'avg_score': round(row['avg_score'], 2) if row['avg_score'] else 0,
                    'albums_created': row['albums_created'],
                    'last_active': row['last_active']
                }
                for row in cursor.fetchall()
            ]

            return analytics

    # ------------------------------------------------------------------
    # Year in Review
    # ------------------------------------------------------------------

    def get_year_in_review(self, user_id: str, year: int) -> Dict[str, Any]:
        """Build an annual summary for a single user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            review: Dict[str, Any] = {"user_id": user_id, "year": year}

            # Photos per month
            cursor.execute("""
                SELECT month, COUNT(*) as count, AVG(score) as avg_score,
                       MAX(score) as best_score
                FROM photo_scores
                WHERE user_id = ? AND year = ?
                GROUP BY month ORDER BY month
            """, (user_id, year))
            review["months"] = [
                {
                    "month": r["month"],
                    "photo_count": r["count"],
                    "avg_score": round(r["avg_score"], 2) if r["avg_score"] else 0,
                    "best_score": round(r["best_score"], 2) if r["best_score"] else 0,
                }
                for r in cursor.fetchall()
            ]

            # Total photos
            cursor.execute("""
                SELECT COUNT(*) as total FROM photo_scores
                WHERE user_id = ? AND year = ?
            """, (user_id, year))
            review["total_photos"] = cursor.fetchone()["total"]

            # Sessions completed
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM curation_sessions
                WHERE user_id = ? AND year = ? AND completed = 1
            """, (user_id, year))
            review["months_curated"] = cursor.fetchone()["cnt"]

            # Top 10 photos of the year
            cursor.execute("""
                SELECT asset_id, month, score, face_count
                FROM photo_scores
                WHERE user_id = ? AND year = ?
                ORDER BY score DESC LIMIT 10
            """, (user_id, year))
            review["top_photos"] = [dict(r) for r in cursor.fetchall()]

            # Face stats
            cursor.execute("""
                SELECT SUM(face_count) as total_faces,
                       COUNT(CASE WHEN face_count > 0 THEN 1 END) as photos_with_faces
                FROM photo_scores
                WHERE user_id = ? AND year = ?
            """, (user_id, year))
            row = cursor.fetchone()
            review["total_faces"] = row["total_faces"] or 0
            review["photos_with_faces"] = row["photos_with_faces"] or 0

            # Duplicate savings
            cursor.execute("""
                SELECT COUNT(*) as dup_groups FROM duplicate_groups
            """)
            review["duplicate_groups_found"] = cursor.fetchone()["dup_groups"]

            return review

    # ------------------------------------------------------------------
    # Photo map data (GPS from EXIF metadata JSON)
    # ------------------------------------------------------------------

    def get_photos_with_location(self, user_id: str, year: Optional[int] = None,
                                  month: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return photos that have GPS coordinates in their metadata."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT asset_id, year, month, score, metadata FROM photo_scores WHERE user_id = ?"
            params: list = [user_id]
            if year:
                query += " AND year = ?"
                params.append(year)
            if month:
                query += " AND month = ?"
                params.append(month)
            cursor.execute(query, params)

            results = []
            for row in cursor.fetchall():
                meta = row["metadata"]
                if not meta:
                    continue
                try:
                    meta_dict = json.loads(meta) if isinstance(meta, str) else meta
                except (json.JSONDecodeError, TypeError):
                    continue

                lat = meta_dict.get("latitude") or meta_dict.get("lat")
                lon = meta_dict.get("longitude") or meta_dict.get("lng") or meta_dict.get("lon")
                if lat and lon:
                    results.append({
                        "asset_id": row["asset_id"],
                        "year": row["year"],
                        "month": row["month"],
                        "score": row["score"],
                        "latitude": float(lat),
                        "longitude": float(lon),
                    })
            return results

    # ------------------------------------------------------------------
    # Shared curation (Family Mode)
    # ------------------------------------------------------------------

    def invite_collaborator(self, owner_id: str, year: int, month: int,
                            collaborator_id: str):
        """Invite another user to contribute picks."""
        with self._get_connection() as conn:
            conn.cursor().execute("""
                INSERT OR IGNORE INTO shared_curations
                    (owner_id, year, month, collaborator_id)
                VALUES (?, ?, ?, ?)
            """, (owner_id, year, month, collaborator_id))

    def get_collaborators(self, owner_id: str, year: int, month: int) -> List[str]:
        """Get collaborator IDs for a session."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT collaborator_id FROM shared_curations
                WHERE owner_id = ? AND year = ? AND month = ?
            """, (owner_id, year, month))
            return [r["collaborator_id"] for r in cursor.fetchall()]

    def get_shared_sessions(self, collaborator_id: str) -> List[Dict[str, Any]]:
        """Get sessions where the user has been invited as collaborator."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT owner_id, year, month, invited_at FROM shared_curations
                WHERE collaborator_id = ?
                ORDER BY invited_at DESC
            """, (collaborator_id,))
            return [dict(r) for r in cursor.fetchall()]

    def add_shared_selection(self, owner_id: str, year: int, month: int,
                             contributor_id: str, asset_id: str):
        """A collaborator adds a photo pick to a shared session."""
        with self._get_connection() as conn:
            conn.cursor().execute("""
                INSERT OR IGNORE INTO shared_selections
                    (owner_id, year, month, contributor_id, asset_id)
                VALUES (?, ?, ?, ?, ?)
            """, (owner_id, year, month, contributor_id, asset_id))

    def get_shared_selections(self, owner_id: str, year: int, month: int) -> List[Dict[str, Any]]:
        """Get all collaborator selections for a session."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT contributor_id, asset_id, added_at FROM shared_selections
                WHERE owner_id = ? AND year = ? AND month = ?
                ORDER BY added_at
            """, (owner_id, year, month))
            return [dict(r) for r in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Album sharing (token-based guest links + user shares)
    # ------------------------------------------------------------------

    def create_share(
        self,
        album_id: str,
        owner_id: str,
        shared_with_user_id: Optional[str] = None,
        guest_label: Optional[str] = None,
        can_add_photos: bool = False,
        expires_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a share link for an album.

        For user shares, *shared_with_user_id* is set and *expires_at*
        is forced to NULL.  For guest links, a token-based URL is
        generated.
        """
        import secrets
        token = secrets.token_urlsafe(32)

        # User shares never expire
        if shared_with_user_id:
            expires_at = None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO album_shares
                    (album_id, owner_id, share_token, shared_with_user_id,
                     guest_label, can_add_photos, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (album_id, owner_id, token, shared_with_user_id,
                  guest_label, can_add_photos, expires_at))
            return {
                "id": cursor.lastrowid,
                "album_id": album_id,
                "owner_id": owner_id,
                "share_token": token,
                "shared_with_user_id": shared_with_user_id,
                "guest_label": guest_label,
                "can_add_photos": can_add_photos,
                "expires_at": expires_at,
                "revoked": False,
            }

    def get_share_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Look up a share by token.  Returns None if revoked or expired."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM album_shares
                WHERE share_token = ?
                  AND revoked = 0
                  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            """, (token,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def revoke_share(self, share_id: int, owner_id: str) -> bool:
        """Revoke a share (soft-delete).  Only the owner can revoke."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE album_shares SET revoked = 1 WHERE id = ? AND owner_id = ?",
                (share_id, owner_id),
            )
            return cursor.rowcount > 0

    def get_album_shares(self, album_id: str) -> List[Dict[str, Any]]:
        """Get all shares for an album (including revoked, for admin view)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM album_shares WHERE album_id = ? ORDER BY created_at",
                (album_id,),
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_shared_albums_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        """Get active (non-expired, non-revoked) shares for an Immich user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM album_shares
                WHERE shared_with_user_id = ?
                  AND revoked = 0
                  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                ORDER BY created_at DESC
            """, (user_id,))
            return [dict(r) for r in cursor.fetchall()]

    def update_share(
        self,
        share_id: int,
        owner_id: str,
        can_add_photos: Optional[bool] = None,
        expires_at: Optional[str] = None,
    ) -> bool:
        """Update share settings.  Only the owner can update."""
        updates = []
        params: list = []
        if can_add_photos is not None:
            updates.append("can_add_photos = ?")
            params.append(can_add_photos)
        if expires_at is not None:
            updates.append("expires_at = ?")
            params.append(expires_at)
        if not updates:
            return False
        params.extend([share_id, owner_id])
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE album_shares SET {', '.join(updates)} "
                "WHERE id = ? AND owner_id = ?",
                params,
            )
            return cursor.rowcount > 0

    def add_contribution(
        self, album_id: str, asset_id: str, share_id: int, contributor_name: str
    ):
        """Record a photo contribution to a shared album."""
        with self._get_connection() as conn:
            conn.cursor().execute("""
                INSERT OR IGNORE INTO album_contributions
                    (album_id, asset_id, share_id, contributor_name)
                VALUES (?, ?, ?, ?)
            """, (album_id, asset_id, share_id, contributor_name))

    def get_contributions(self, album_id: str) -> List[Dict[str, Any]]:
        """Get all contributions for an album with contributor info."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.id, c.album_id, c.asset_id, c.share_id,
                       c.contributor_name, c.added_at,
                       s.guest_label, s.shared_with_user_id
                FROM album_contributions c
                JOIN album_shares s ON c.share_id = s.id
                WHERE c.album_id = ?
                ORDER BY c.added_at
            """, (album_id,))
            return [dict(r) for r in cursor.fetchall()]

    def delete_contribution(self, album_id: str, asset_id: str, share_id: int) -> bool:
        """Delete a contribution.  Only the contributor (by share_id) can delete."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM album_contributions "
                "WHERE album_id = ? AND asset_id = ? AND share_id = ?",
                (album_id, asset_id, share_id),
            )
            return cursor.rowcount > 0

    def delete_contribution_as_owner(self, contribution_id: int, album_id: str) -> bool:
        """Delete any contribution (for album owner / admin)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM album_contributions WHERE id = ? AND album_id = ?",
                (contribution_id, album_id),
            )
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Face Recognition
    # ------------------------------------------------------------------

    def save_face_embedding(
        self,
        asset_id: str,
        user_id: str,
        face_index: int,
        embedding_bytes: bytes,
        bbox: tuple,
        identity_id: Optional[int] = None,
        confidence: Optional[float] = None,
    ) -> int:
        """Save or replace a face embedding for one detected face. Returns row id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            x, y, w, h = bbox
            cursor.execute(
                """INSERT OR REPLACE INTO face_embeddings
                       (asset_id, user_id, face_index, embedding,
                        bbox_x, bbox_y, bbox_w, bbox_h,
                        identity_id, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (asset_id, user_id, face_index, embedding_bytes,
                 x, y, w, h, identity_id, confidence),
            )
            return cursor.lastrowid

    def get_face_embeddings_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all face embeddings for a user (used for clustering)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, asset_id, face_index, embedding,
                          bbox_x, bbox_y, bbox_w, bbox_h,
                          identity_id, confidence
                   FROM face_embeddings WHERE user_id = ?""",
                (user_id,),
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_face_embeddings_for_asset(self, asset_id: str) -> List[Dict[str, Any]]:
        """Get all face embeddings for a specific photo."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT fe.id, fe.asset_id, fe.face_index, fe.embedding,
                          fe.bbox_x, fe.bbox_y, fe.bbox_w, fe.bbox_h,
                          fe.identity_id, fe.confidence,
                          fi.label as identity_label
                   FROM face_embeddings fe
                   LEFT JOIN face_identities fi ON fe.identity_id = fi.id
                   WHERE fe.asset_id = ?
                   ORDER BY fe.face_index""",
                (asset_id,),
            )
            return [dict(r) for r in cursor.fetchall()]

    def create_face_identity(
        self,
        user_id: str,
        label: Optional[str] = None,
        representative_embedding: Optional[bytes] = None,
    ) -> int:
        """Create a new face identity cluster. Returns identity id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO face_identities
                       (user_id, label, representative_embedding)
                   VALUES (?, ?, ?)""",
                (user_id, label, representative_embedding),
            )
            return cursor.lastrowid

    def update_face_identity_label(self, identity_id: int, user_id: str, label: str) -> bool:
        """Let user name a face cluster. Only updates own identities."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE face_identities
                   SET label = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND user_id = ?""",
                (label, identity_id, user_id),
            )
            return cursor.rowcount > 0

    def assign_face_to_identity(self, face_embedding_id: int, identity_id: int):
        """Assign a detected face embedding to an identity cluster."""
        with self._get_connection() as conn:
            conn.cursor().execute(
                "UPDATE face_embeddings SET identity_id = ? WHERE id = ?",
                (identity_id, face_embedding_id),
            )

    def update_face_identity_photo_count(self, identity_id: int, count: int):
        """Update the photo count for an identity cluster."""
        with self._get_connection() as conn:
            conn.cursor().execute(
                """UPDATE face_identities
                   SET photo_count = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (count, identity_id),
            )

    def get_face_identities(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all face identity clusters for a user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, user_id, label, photo_count, created_at, updated_at
                   FROM face_identities
                   WHERE user_id = ?
                   ORDER BY photo_count DESC""",
                (user_id,),
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_face_identity(self, identity_id: int, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a single face identity (user-scoped)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM face_identities WHERE id = ? AND user_id = ?",
                (identity_id, user_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_photos_by_identity(
        self, identity_id: int, user_id: str
    ) -> List[Dict[str, Any]]:
        """Get all photos (asset_ids) that contain a specific person."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT DISTINCT fe.asset_id, fe.bbox_x, fe.bbox_y,
                          fe.bbox_w, fe.bbox_h, fe.confidence,
                          ps.score, ps.year, ps.month
                   FROM face_embeddings fe
                   LEFT JOIN photo_scores ps ON fe.asset_id = ps.asset_id
                   WHERE fe.identity_id = ? AND fe.user_id = ?
                   ORDER BY ps.score DESC""",
                (identity_id, user_id),
            )
            return [dict(r) for r in cursor.fetchall()]

    def merge_face_identities(
        self, user_id: str, source_id: int, target_id: int
    ) -> bool:
        """Merge source identity cluster into target. User must own both."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Verify ownership of both
            cursor.execute(
                "SELECT id FROM face_identities WHERE id IN (?, ?) AND user_id = ?",
                (source_id, target_id, user_id),
            )
            if len(cursor.fetchall()) != 2:
                return False
            # Re-assign all embeddings from source to target
            cursor.execute(
                "UPDATE face_embeddings SET identity_id = ? WHERE identity_id = ? AND user_id = ?",
                (target_id, source_id, user_id),
            )
            # Recalculate photo count for target
            cursor.execute(
                """UPDATE face_identities
                   SET photo_count = (
                       SELECT COUNT(DISTINCT asset_id) FROM face_embeddings
                       WHERE identity_id = ?
                   ), updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (target_id, target_id),
            )
            # Delete empty source
            cursor.execute(
                "DELETE FROM face_identities WHERE id = ? AND user_id = ?",
                (source_id, user_id),
            )
            return True

    # ------------------------------------------------------------------
    # Scene Detection
    # ------------------------------------------------------------------

    def save_scene_classification(
        self,
        asset_id: str,
        user_id: str,
        scene_category: str,
        scene_subcategory: Optional[str],
        confidence: Optional[float],
        top3_json: str,
    ):
        """Save or replace scene classification for a photo."""
        with self._get_connection() as conn:
            conn.cursor().execute(
                """INSERT OR REPLACE INTO scene_classifications
                       (asset_id, user_id, scene_category, scene_subcategory,
                        confidence, top3_scenes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (asset_id, user_id, scene_category, scene_subcategory,
                 confidence, top3_json),
            )

    def get_scene_classification(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """Get scene classification for a single photo."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM scene_classifications WHERE asset_id = ?",
                (asset_id,),
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get("top3_scenes"):
                    result["top3_scenes"] = json.loads(result["top3_scenes"])
                return result
            return None

    def get_photos_by_scene(
        self,
        user_id: str,
        scene_category: str,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get photos filtered by scene super-category."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT sc.asset_id, sc.scene_category, sc.scene_subcategory,
                       sc.confidence, ps.score, ps.year, ps.month
                FROM scene_classifications sc
                LEFT JOIN photo_scores ps ON sc.asset_id = ps.asset_id
                WHERE sc.user_id = ? AND sc.scene_category = ?
            """
            params: list = [user_id, scene_category]
            if year is not None:
                query += " AND ps.year = ?"
                params.append(year)
            if month is not None:
                query += " AND ps.month = ?"
                params.append(month)
            query += " ORDER BY ps.score DESC"
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def get_scene_distribution(
        self, user_id: str, year: Optional[int] = None
    ) -> Dict[str, int]:
        """Return count of photos per scene super-category for a user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT sc.scene_category, COUNT(*) as count
                FROM scene_classifications sc
                LEFT JOIN photo_scores ps ON sc.asset_id = ps.asset_id
                WHERE sc.user_id = ?
            """
            params: list = [user_id]
            if year is not None:
                query += " AND ps.year = ?"
                params.append(year)
            query += " GROUP BY sc.scene_category ORDER BY count DESC"
            cursor.execute(query, params)
            return {r["scene_category"]: r["count"] for r in cursor.fetchall()}

    def log_share_access(self, share_id: int, ip_address: str, user_agent: str):
        """Record an access to a share link for auditing."""
        with self._get_connection() as conn:
            conn.cursor().execute(
                "INSERT INTO share_access_log (share_id, ip_address, user_agent) "
                "VALUES (?, ?, ?)",
                (share_id, ip_address, user_agent),
            )

    def get_share_access_log(self, share_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Get access log for a share."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM share_access_log WHERE share_id = ? "
                "ORDER BY accessed_at DESC LIMIT ?",
                (share_id, limit),
            )
            return [dict(r) for r in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Import jobs
    # ------------------------------------------------------------------

    def create_import_job(
        self,
        user_id: str,
        source_type: str,
        import_method: str,
        server_path: Optional[str] = None,
        staging_dir: Optional[str] = None,
    ) -> int:
        """Create a new import job and return its ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO import_jobs
                       (user_id, source_type, import_method, server_path, staging_dir)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, source_type, import_method, server_path, staging_dir),
            )
            return cursor.lastrowid

    def update_import_job_progress(self, job_id: int, stats: Dict[str, Any]):
        """Update progress counters and optionally status for an import job."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            fields = []
            values: list = []
            for col in ("total_files", "uploaded", "skipped", "errors", "duplicates"):
                if col in stats:
                    fields.append(f"{col} = ?")
                    values.append(stats[col])
            if "status" in stats:
                fields.append("status = ?")
                values.append(stats["status"])
                if stats["status"] == "running" and "started_at" not in stats:
                    fields.append("started_at = COALESCE(started_at, CURRENT_TIMESTAMP)")
            fields.append("updated_at = CURRENT_TIMESTAMP")
            values.append(job_id)
            cursor.execute(
                f"UPDATE import_jobs SET {', '.join(fields)} WHERE id = ?",
                values,
            )

    def update_import_job_status(
        self, job_id: int, status: str, error_message: Optional[str] = None
    ):
        """Set job status (and optionally error message). Marks completed_at for terminal states."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status in ("completed", "failed", "cancelled"):
                cursor.execute(
                    "UPDATE import_jobs SET status = ?, error_message = ?, "
                    "completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = ?",
                    (status, error_message, job_id),
                )
            else:
                cursor.execute(
                    "UPDATE import_jobs SET status = ?, error_message = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (status, error_message, job_id),
                )

    def get_import_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Return a single import job or None."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM import_jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_import_jobs_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        """Return all import jobs for a user, newest first."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM import_jobs WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
            return [dict(r) for r in cursor.fetchall()]

    # ── Event / Trip Suggestions ─────────────────────────────────────────────

    def save_event_suggestions(self, user_id: str, events: List[Dict[str, Any]]):
        """Upsert a list of detected event suggestions.

        Rows whose (user_id, start_date, end_date) already exist are updated
        only when they haven't been dismissed or turned into an album yet.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for evt in events:
                cursor.execute(
                    """INSERT INTO event_suggestions
                           (user_id, title, start_date, end_date, photo_count,
                            thumbnail_asset_id, asset_ids, participants)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(user_id, start_date, end_date) DO UPDATE SET
                           title              = excluded.title,
                           photo_count        = excluded.photo_count,
                           thumbnail_asset_id = excluded.thumbnail_asset_id,
                           asset_ids          = excluded.asset_ids,
                           participants       = excluded.participants,
                           detected_at        = CURRENT_TIMESTAMP
                       WHERE dismissed = 0 AND album_created = 0""",
                    (
                        user_id,
                        evt["title"],
                        evt["start_date"],
                        evt["end_date"],
                        evt["photo_count"],
                        evt["thumbnail_asset_id"],
                        json.dumps(evt["asset_ids"]),
                        json.dumps(evt.get("participants") or []),
                    ),
                )

    def get_event_suggestions(self, user_id: str) -> List[Dict[str, Any]]:
        """Return non-dismissed, non-completed suggestions for a user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM event_suggestions
                   WHERE user_id = ?
                     AND dismissed = 0
                     AND album_created = 0
                   ORDER BY start_date DESC""",
                (user_id,),
            )
            rows = [dict(r) for r in cursor.fetchall()]
            for row in rows:
                if isinstance(row.get("asset_ids"), str):
                    row["asset_ids"] = json.loads(row["asset_ids"])
                if isinstance(row.get("participants"), str):
                    row["participants"] = json.loads(row["participants"])
                elif row.get("participants") is None:
                    row["participants"] = []
            return rows

    def dismiss_event_suggestion(self, user_id: str, event_id: int) -> bool:
        """Permanently hide a suggestion so it never reappears."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE event_suggestions SET dismissed = 1 WHERE id = ? AND user_id = ?",
                (event_id, user_id),
            )
            return cursor.rowcount > 0

    def mark_event_album_created(self, user_id: str, event_id: int, album_id: str) -> bool:
        """Mark a suggestion as completed after the album is created."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE event_suggestions
                   SET album_created = 1, album_id = ?
                   WHERE id = ? AND user_id = ?""",
                (album_id, event_id, user_id),
            )
            return cursor.rowcount > 0

    def get_scene_distribution_for_assets(
        self, user_id: str, asset_ids: List[str]
    ) -> Dict[str, int]:
        """Return {scene_category: photo_count} for a batch of asset_ids."""
        if not asset_ids:
            return {}
        placeholders = ",".join("?" * len(asset_ids))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""SELECT scene_category, COUNT(*) AS cnt
                    FROM scene_classifications
                    WHERE user_id = ? AND asset_id IN ({placeholders})
                    GROUP BY scene_category
                    ORDER BY cnt DESC""",
                [user_id] + list(asset_ids),
            )
            return {row["scene_category"]: row["cnt"] for row in cursor.fetchall()}

    def get_labeled_faces_for_assets(
        self, user_id: str, asset_ids: List[str], min_photos: int = 2
    ) -> List[str]:
        """Return labeled face identity names that appear in ≥ min_photos of the given assets.

        Results are sorted by number of photos descending (most prominent person first).
        Only identities with a user-assigned label are returned.
        """
        if not asset_ids:
            return []
        placeholders = ",".join("?" * len(asset_ids))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""SELECT fi.label, COUNT(DISTINCT fe.asset_id) AS photo_count
                    FROM face_embeddings fe
                    JOIN face_identities fi ON fe.identity_id = fi.id
                    WHERE fe.user_id = ?
                      AND fe.asset_id IN ({placeholders})
                      AND fi.label IS NOT NULL
                      AND fi.label != ''
                    GROUP BY fi.id, fi.label
                    HAVING photo_count >= ?
                    ORDER BY photo_count DESC""",
                [user_id] + list(asset_ids) + [min_photos],
            )
            return [row["label"] for row in cursor.fetchall()]

    def get_best_scored_asset(
        self, user_id: str, asset_ids: List[str]
    ) -> Optional[str]:
        """Return the asset_id with the highest AI quality score from the given list."""
        if not asset_ids:
            return None
        placeholders = ",".join("?" * len(asset_ids))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""SELECT asset_id FROM photo_scores
                    WHERE user_id = ? AND asset_id IN ({placeholders})
                    ORDER BY score DESC
                    LIMIT 1""",
                [user_id] + list(asset_ids),
            )
            row = cursor.fetchone()
            return row["asset_id"] if row else None

    # ------------------------------------------------------------------
    # Dedup Scanner
    # ------------------------------------------------------------------

    def create_dedup_scan(
        self,
        scan_id: str,
        user_id: str,
        mode: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO dedup_scans (id, user_id, mode, status, date_from, date_to)
                   VALUES (?, ?, ?, 'running', ?, ?)""",
                (scan_id, user_id, mode, date_from, date_to),
            )

    def update_dedup_scan(self, scan_id: str, **kwargs) -> None:
        allowed = {'status', 'total_assets', 'hashed', 'groups_found', 'error_message', 'completed_at'}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        if 'status' in fields and fields['status'] in ('complete', 'failed', 'cancelled'):
            fields.setdefault('completed_at', datetime.now().isoformat())
        set_clause = ', '.join(f"{k} = ?" for k in fields)
        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE dedup_scans SET {set_clause} WHERE id = ?",
                (*fields.values(), scan_id),
            )

    def get_dedup_scan_status(self, user_id: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM dedup_scans WHERE user_id = ? ORDER BY started_at DESC LIMIT 1",
                (user_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def upsert_dedup_asset_metadata(self, user_id: str, asset: Dict) -> None:
        exif = asset.get('exifInfo') or {}
        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO dedup_asset_metadata
                   (asset_id, user_id, filename, date_taken, width, height,
                    file_size_bytes, camera_make, camera_model, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(asset_id) DO UPDATE SET
                       filename=excluded.filename, date_taken=excluded.date_taken,
                       width=excluded.width, height=excluded.height,
                       file_size_bytes=excluded.file_size_bytes,
                       camera_make=excluded.camera_make, camera_model=excluded.camera_model,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    asset['id'], user_id,
                    asset.get('originalFileName'),
                    asset.get('fileCreatedAt'),
                    exif.get('exifImageWidth'), exif.get('exifImageHeight'),
                    exif.get('fileSizeInByte'),
                    exif.get('make'), exif.get('model'),
                ),
            )

    def save_dedup_group(
        self,
        scan_id: str,
        user_id: str,
        asset_ids: List[str],
        recommended_keep_id: str,
        group_hash: str,
    ) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO duplicate_groups
                   (scan_id, user_id, group_hash, asset_ids, recommended_keep_id, resolved)
                   VALUES (?, ?, ?, ?, ?, 0)""",
                (scan_id, user_id, group_hash, json.dumps(asset_ids), recommended_keep_id),
            )

    def get_dedup_groups(
        self,
        user_id: str,
        include_resolved: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            resolved_filter = "" if include_resolved else "AND resolved = 0"
            cursor.execute(
                f"SELECT COUNT(*) as cnt FROM duplicate_groups WHERE user_id = ? {resolved_filter}",
                (user_id,),
            )
            total = cursor.fetchone()['cnt']

            cursor.execute(
                f"""SELECT id, scan_id, group_hash, asset_ids, recommended_keep_id, resolved, detected_at
                    FROM duplicate_groups
                    WHERE user_id = ? {resolved_filter}
                    ORDER BY detected_at DESC LIMIT ? OFFSET ?""",
                (user_id, limit, offset),
            )
            rows = [dict(r) for r in cursor.fetchall()]

        # Enrich each group with per-asset metadata
        groups = []
        for row in rows:
            asset_ids = json.loads(row['asset_ids'])
            assets = self._fetch_asset_metadata_list(asset_ids)
            savings = sum(
                a.get('file_size_bytes') or 0
                for a in assets
                if a['asset_id'] != row['recommended_keep_id']
            )
            groups.append({**row, 'assets': assets, 'savings_bytes': savings})

        total_savings = sum(g['savings_bytes'] for g in groups)
        total_removable = sum(len(json.loads(g['asset_ids'])) - 1 for g in groups)
        return {
            'groups': groups,
            'total_groups': total,
            'total_removable_photos': total_removable,
            'total_savings_bytes': total_savings,
        }

    def _fetch_asset_metadata_list(self, asset_ids: List[str]) -> List[Dict]:
        if not asset_ids:
            return []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(asset_ids))
            cursor.execute(
                f"SELECT * FROM dedup_asset_metadata WHERE asset_id IN ({placeholders})",
                asset_ids,
            )
            meta_map = {row['asset_id']: dict(row) for row in cursor.fetchall()}
        return [
            {
                **meta_map.get(aid, {'asset_id': aid}),
                'asset_id': aid,
                'thumbnail_url': f'/api/thumbnail/{aid}',
                'megapixels': round(
                    (meta_map.get(aid, {}).get('width') or 0)
                    * (meta_map.get(aid, {}).get('height') or 0)
                    / 1_000_000,
                    1,
                ) if meta_map.get(aid, {}).get('width') else None,
            }
            for aid in asset_ids
        ]

    def resolve_dedup_group(self, group_id: int) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE duplicate_groups SET resolved = 1 WHERE id = ?", (group_id,)
            )

    def dismiss_dedup_group(self, group_id: int) -> None:
        self.resolve_dedup_group(group_id)  # same DB operation, different semantics

    def upsert_perceptual_hash(
        self, asset_id: str, user_id: str, year: int, month: int, phash: str
    ) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM photo_scores WHERE asset_id = ?", (asset_id,)
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "UPDATE photo_scores SET perceptual_hash = ? WHERE asset_id = ?",
                    (phash, asset_id),
                )
            else:
                cursor.execute(
                    """INSERT INTO photo_scores
                       (asset_id, user_id, year, month, score, perceptual_hash)
                       VALUES (?, ?, ?, ?, 0.0, ?)""",
                    (asset_id, user_id, year, month, phash),
                )
