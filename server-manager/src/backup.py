"""
Backup management for Immich database and files
"""

import subprocess
import os
import shutil
import gzip
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import time


class BackupManager:
    """Manages backups of Immich database and files"""

    def __init__(self, config):
        """
        Initialize backup manager

        Args:
            config: BackupConfig object
        """
        self.config = config
        self.backup_dir = Path(config.local_path)

        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def backup_database(self) -> Dict[str, Any]:
        """
        Backup Immich PostgreSQL database

        Returns:
            Dictionary with backup status and details
        """
        start_time = time.time()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"immich_db_{timestamp}.sql"

        try:
            # Get database container name
            result = subprocess.run(
                ['docker', 'ps', '--filter', 'name=postgres', '--format', '{{.Names}}'],
                capture_output=True,
                text=True,
                check=True
            )
            container_name = result.stdout.strip().split('\n')[0]

            if not container_name:
                raise Exception("PostgreSQL container not found")

            # Dump database
            with open(backup_file, 'w') as f:
                subprocess.run(
                    [
                        'docker', 'exec', container_name,
                        'pg_dump', '-U', 'postgres', 'immich'
                    ],
                    stdout=f,
                    stderr=subprocess.PIPE,
                    check=True
                )

            # Compress if enabled
            if self.config.compression:
                with open(backup_file, 'rb') as f_in:
                    with gzip.open(f"{backup_file}.gz", 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)

                # Remove uncompressed file
                backup_file.unlink()
                backup_file = Path(f"{backup_file}.gz")

            duration = time.time() - start_time
            size_bytes = backup_file.stat().st_size

            return {
                'status': 'success',
                'file_path': str(backup_file),
                'size_bytes': size_bytes,
                'size_mb': size_bytes / (1024**2),
                'duration_seconds': duration,
                'timestamp': timestamp
            }

        except subprocess.CalledProcessError as e:
            duration = time.time() - start_time
            error_msg = e.stderr.decode() if e.stderr else str(e)

            # Clean up failed backup
            if backup_file.exists():
                backup_file.unlink()

            return {
                'status': 'failed',
                'error': error_msg,
                'duration_seconds': duration
            }

        except Exception as e:
            duration = time.time() - start_time

            # Clean up failed backup
            if backup_file.exists():
                backup_file.unlink()

            return {
                'status': 'failed',
                'error': str(e),
                'duration_seconds': duration
            }

    def backup_config(self) -> Dict[str, Any]:
        """
        Backup Immich configuration files

        Returns:
            Dictionary with backup status
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"immich_config_{timestamp}.tar.gz"

        try:
            # Find Immich installation directory
            immich_dirs = [
                "/opt/immich",
                "/opt/immich-app",
                "/home/*/immich",
            ]

            config_dir = None
            for dir_pattern in immich_dirs:
                matches = list(Path("/").glob(dir_pattern.lstrip("/")))
                if matches and (matches[0] / "docker-compose.yml").exists():
                    config_dir = matches[0]
                    break

            if not config_dir:
                return {
                    'status': 'skipped',
                    'error': 'Immich directory not found'
                }

            # Backup docker-compose.yml and .env files
            subprocess.run(
                [
                    'tar', 'czf', str(backup_file),
                    '-C', str(config_dir),
                    'docker-compose.yml',
                    '.env'
                ],
                check=True,
                capture_output=True
            )

            size_bytes = backup_file.stat().st_size

            return {
                'status': 'success',
                'file_path': str(backup_file),
                'size_bytes': size_bytes,
                'size_mb': size_bytes / (1024**2)
            }

        except Exception as e:
            if backup_file.exists():
                backup_file.unlink()

            return {
                'status': 'failed',
                'error': str(e)
            }

    def cleanup_old_backups(self) -> Dict[str, Any]:
        """
        Remove backups older than retention period

        Returns:
            Dictionary with cleanup results
        """
        if self.config.retention_days <= 0:
            return {'status': 'skipped', 'reason': 'retention disabled'}

        cutoff_date = datetime.now() - timedelta(days=self.config.retention_days)
        removed_files = []
        removed_bytes = 0

        try:
            for backup_file in self.backup_dir.glob("immich_*"):
                if backup_file.is_file():
                    file_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
                    if file_time < cutoff_date:
                        size = backup_file.stat().st_size
                        backup_file.unlink()
                        removed_files.append(backup_file.name)
                        removed_bytes += size

            return {
                'status': 'success',
                'removed_count': len(removed_files),
                'removed_mb': removed_bytes / (1024**2),
                'files': removed_files
            }

        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e),
                'removed_count': len(removed_files),
                'removed_mb': removed_bytes / (1024**2)
            }

    def list_backups(self) -> List[Dict[str, Any]]:
        """
        List all available backups

        Returns:
            List of backup info dictionaries
        """
        backups = []

        for backup_file in sorted(self.backup_dir.glob("immich_*"), reverse=True):
            if backup_file.is_file():
                stat = backup_file.stat()
                backups.append({
                    'filename': backup_file.name,
                    'path': str(backup_file),
                    'size_bytes': stat.st_size,
                    'size_mb': stat.st_size / (1024**2),
                    'created': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'type': 'database' if '_db_' in backup_file.name else 'config'
                })

        return backups

    def restore_database(self, backup_file: str) -> Dict[str, Any]:
        """
        Restore database from backup

        Args:
            backup_file: Path to backup file

        Returns:
            Dictionary with restore status
        """
        start_time = time.time()

        try:
            backup_path = Path(backup_file)
            if not backup_path.exists():
                raise FileNotFoundError(f"Backup file not found: {backup_file}")

            # Get database container name
            result = subprocess.run(
                ['docker', 'ps', '--filter', 'name=postgres', '--format', '{{.Names}}'],
                capture_output=True,
                text=True,
                check=True
            )
            container_name = result.stdout.strip().split('\n')[0]

            if not container_name:
                raise Exception("PostgreSQL container not found")

            # Decompress if needed
            temp_file = None
            if backup_file.endswith('.gz'):
                temp_file = backup_path.with_suffix('')
                with gzip.open(backup_path, 'rb') as f_in:
                    with open(temp_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                restore_file = temp_file
            else:
                restore_file = backup_path

            # Restore database
            with open(restore_file, 'r') as f:
                subprocess.run(
                    [
                        'docker', 'exec', '-i', container_name,
                        'psql', '-U', 'postgres', 'immich'
                    ],
                    stdin=f,
                    check=True,
                    capture_output=True
                )

            # Clean up temp file
            if temp_file and temp_file.exists():
                temp_file.unlink()

            duration = time.time() - start_time

            return {
                'status': 'success',
                'duration_seconds': duration
            }

        except Exception as e:
            duration = time.time() - start_time

            # Clean up temp file
            if temp_file and temp_file.exists():
                temp_file.unlink()

            return {
                'status': 'failed',
                'error': str(e),
                'duration_seconds': duration
            }

    def run_full_backup(self) -> Dict[str, Any]:
        """
        Run complete backup (database + config)

        Returns:
            Dictionary with combined backup results
        """
        results = {
            'timestamp': datetime.now().isoformat(),
            'database': self.backup_database(),
            'config': self.backup_config(),
            'cleanup': self.cleanup_old_backups()
        }

        # Overall status
        results['status'] = 'success' if results['database']['status'] == 'success' else 'failed'

        return results
