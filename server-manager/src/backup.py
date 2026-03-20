"""
Backup management for Immich database and files
"""

import subprocess
import os
import shutil
import gzip
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import time

logger = logging.getLogger(__name__)


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

    def _encrypt_file(self, file_path: Path) -> Path:
        """Encrypt a backup file using age if encryption is enabled.
        Returns the path to the encrypted file (original is removed)."""
        enc = getattr(self.config, 'encryption', None)
        if not enc or not enc.enabled or not enc.public_key:
            return file_path

        encrypted_path = file_path.with_suffix(file_path.suffix + '.age')
        try:
            subprocess.run(
                ['age', '-r', enc.public_key, '-o', str(encrypted_path), str(file_path)],
                check=True, capture_output=True
            )
            file_path.unlink()
            logger.info("Backup encrypted: %s", encrypted_path.name)
            return encrypted_path
        except FileNotFoundError:
            logger.warning("'age' not installed — skipping encryption. Install: sudo apt install age")
            return file_path
        except subprocess.CalledProcessError as e:
            logger.error("Encryption failed: %s", e.stderr.decode() if e.stderr else str(e))
            # Keep the unencrypted file rather than losing the backup
            if encrypted_path.exists():
                encrypted_path.unlink()
            return file_path

    @staticmethod
    def _decrypt_file(file_path: Path, key_file: str) -> Path:
        """Decrypt an age-encrypted backup file. Returns path to decrypted file."""
        if not str(file_path).endswith('.age'):
            return file_path

        decrypted_path = Path(str(file_path)[:-4])  # strip .age
        subprocess.run(
            ['age', '-d', '-i', key_file, '-o', str(decrypted_path), str(file_path)],
            check=True, capture_output=True
        )
        return decrypted_path

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

            # Encrypt if enabled
            backup_file = self._encrypt_file(backup_file)

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

            # Encrypt if enabled
            backup_file = self._encrypt_file(backup_file)

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
        temp_files = []

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

            # Decrypt if needed
            working_path = backup_path
            if str(working_path).endswith('.age'):
                key_file = os.environ.get(
                    'BACKUP_KEY_FILE', '/etc/immich-ecosystem/backup-key.txt'
                )
                if not Path(key_file).exists():
                    raise FileNotFoundError(
                        f"Decryption key not found at {key_file}. "
                        "Set BACKUP_KEY_FILE env var or place key at default path."
                    )
                working_path = self._decrypt_file(working_path, key_file)
                temp_files.append(working_path)

            # Decompress if needed
            temp_file = None
            if str(working_path).endswith('.gz'):
                temp_file = working_path.with_suffix('')
                with gzip.open(working_path, 'rb') as f_in:
                    with open(temp_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                restore_file = temp_file
                temp_files.append(temp_file)
            else:
                restore_file = working_path

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

            # Clean up temp files
            for tf in temp_files:
                if tf and tf.exists():
                    tf.unlink()

            duration = time.time() - start_time

            return {
                'status': 'success',
                'duration_seconds': duration
            }

        except Exception as e:
            duration = time.time() - start_time

            # Clean up temp files
            for tf in temp_files:
                if tf and tf.exists():
                    tf.unlink()

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
