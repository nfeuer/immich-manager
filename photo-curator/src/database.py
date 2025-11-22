"""
Database models and management for Photo Curator
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import json


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
