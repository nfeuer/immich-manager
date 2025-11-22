"""
Backup verification and integrity testing system
Ensures backups are restorable and valid
"""

import hashlib
import subprocess
import tempfile
import shutil
import boto3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
import gzip
import json

logger = logging.getLogger(__name__)


class BackupVerifier:
    """Verifies backup integrity and handles offsite sync"""

    def __init__(self, config):
        """
        Initialize backup verifier

        Args:
            config: Verification config with backup_dir, test_restore_dir, etc.
        """
        self.config = config
        self.backup_dir = Path(config.get('backup_dir', '/mnt/backups/immich'))
        self.test_restore_dir = Path(config.get('test_restore_dir', '/tmp/immich-restore-test'))
        self.verification_log = Path(config.get('verification_log', 'data/backup-verification.json'))

        # Offsite config
        self.offsite_enabled = config.get('offsite_sync', {}).get('enabled', False)
        self.offsite_type = config.get('offsite_sync', {}).get('type', 's3')  # 's3' or 'backblaze'

        # Email config (for notifications)
        self.email_enabled = config.get('email_notifications', {}).get('enabled', False)

        # Ensure directories exist
        self.test_restore_dir.mkdir(parents=True, exist_ok=True)
        self.verification_log.parent.mkdir(parents=True, exist_ok=True)

    def calculate_checksum(self, file_path: Path) -> str:
        """
        Calculate SHA256 checksum of a file

        Args:
            file_path: Path to file

        Returns:
            Hex string of checksum
        """
        sha256 = hashlib.sha256()

        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)

        return sha256.hexdigest()

    def verify_backup_integrity(self, backup_file: Path) -> Dict[str, Any]:
        """
        Verify backup file integrity using checksums

        Args:
            backup_file: Path to backup file

        Returns:
            Dictionary with verification results
        """
        try:
            if not backup_file.exists():
                return {
                    'status': 'failed',
                    'error': f'Backup file not found: {backup_file}'
                }

            # Calculate checksum
            checksum = self.calculate_checksum(backup_file)

            # Check if it's a valid archive
            if backup_file.name.endswith('.gz'):
                # Try to open gzip file
                try:
                    with gzip.open(backup_file, 'rb') as f:
                        # Read first 1KB to verify it's readable
                        f.read(1024)
                    archive_valid = True
                except Exception as e:
                    archive_valid = False
                    error = str(e)
            else:
                # For non-compressed files, just check readability
                try:
                    with open(backup_file, 'rb') as f:
                        f.read(1024)
                    archive_valid = True
                except Exception as e:
                    archive_valid = False
                    error = str(e)

            if not archive_valid:
                return {
                    'status': 'failed',
                    'error': f'Archive corrupted: {error}',
                    'checksum': checksum
                }

            return {
                'status': 'success',
                'checksum': checksum,
                'size_bytes': backup_file.stat().st_size,
                'size_mb': backup_file.stat().st_size / (1024**2),
                'archive_valid': True
            }

        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e)
            }

    def test_restore_backup(self, backup_file: Path) -> Dict[str, Any]:
        """
        Test restore a backup to temporary location

        Args:
            backup_file: Path to backup file to test

        Returns:
            Dictionary with test results
        """
        start_time = datetime.now()
        temp_db_name = f"immich_test_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        try:
            # Create temporary database for testing
            container_result = subprocess.run(
                ['docker', 'ps', '--filter', 'name=postgres', '--format', '{{.Names}}'],
                capture_output=True,
                text=True,
                check=True
            )
            container_name = container_result.stdout.strip().split('\n')[0]

            if not container_name:
                raise Exception("PostgreSQL container not found")

            # Create test database
            subprocess.run(
                ['docker', 'exec', container_name, 'psql', '-U', 'postgres', '-c',
                 f'CREATE DATABASE {temp_db_name}'],
                check=True,
                capture_output=True
            )

            # Decompress if needed
            temp_file = None
            if backup_file.name.endswith('.gz'):
                temp_file = self.test_restore_dir / backup_file.stem
                with gzip.open(backup_file, 'rb') as f_in:
                    with open(temp_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                restore_file = temp_file
            else:
                restore_file = backup_file

            # Restore to test database
            with open(restore_file, 'r') as f:
                subprocess.run(
                    ['docker', 'exec', '-i', container_name,
                     'psql', '-U', 'postgres', temp_db_name],
                    stdin=f,
                    check=True,
                    capture_output=True,
                    timeout=300  # 5 minute timeout
                )

            # Verify restored database
            verify_result = subprocess.run(
                ['docker', 'exec', container_name, 'psql', '-U', 'postgres', temp_db_name,
                 '-c', 'SELECT COUNT(*) FROM users'],
                capture_output=True,
                text=True,
                check=True
            )

            # Extract user count from output
            user_count = None
            for line in verify_result.stdout.split('\n'):
                line = line.strip()
                if line.isdigit():
                    user_count = int(line)
                    break

            # Clean up
            if temp_file and temp_file.exists():
                temp_file.unlink()

            # Drop test database
            subprocess.run(
                ['docker', 'exec', container_name, 'psql', '-U', 'postgres', '-c',
                 f'DROP DATABASE {temp_db_name}'],
                check=True,
                capture_output=True
            )

            duration = (datetime.now() - start_time).total_seconds()

            return {
                'status': 'success',
                'duration_seconds': duration,
                'user_count': user_count,
                'restore_valid': user_count is not None and user_count > 0
            }

        except subprocess.TimeoutExpired:
            return {
                'status': 'failed',
                'error': 'Restore test timeout (>5 minutes)',
                'duration_seconds': (datetime.now() - start_time).total_seconds()
            }
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e),
                'duration_seconds': (datetime.now() - start_time).total_seconds()
            }
        finally:
            # Ensure cleanup
            try:
                if temp_file and temp_file.exists():
                    temp_file.unlink()
                # Try to drop test database if it exists
                subprocess.run(
                    ['docker', 'exec', container_name, 'psql', '-U', 'postgres', '-c',
                     f'DROP DATABASE IF EXISTS {temp_db_name}'],
                    capture_output=True
                )
            except:
                pass

    def sync_to_offsite(self, backup_file: Path) -> Dict[str, Any]:
        """
        Sync backup to offsite location (S3 or Backblaze)

        Args:
            backup_file: Path to backup file

        Returns:
            Dictionary with sync results
        """
        if not self.offsite_enabled:
            return {'status': 'skipped', 'reason': 'Offsite sync disabled'}

        try:
            offsite_config = self.config.get('offsite_sync', {})

            # ADMIN TODO: Configure offsite sync in config.yaml
            # For S3:
            #   offsite_sync:
            #     enabled: true
            #     type: s3
            #     bucket: my-immich-backups
            #     region: us-east-1
            #     access_key: YOUR_ACCESS_KEY
            #     secret_key: YOUR_SECRET_KEY
            #
            # For Backblaze B2:
            #   offsite_sync:
            #     enabled: true
            #     type: backblaze
            #     bucket: my-immich-backups
            #     key_id: YOUR_KEY_ID
            #     application_key: YOUR_APP_KEY

            if self.offsite_type == 's3':
                # AWS S3 sync
                s3_client = boto3.client(
                    's3',
                    region_name=offsite_config.get('region', 'us-east-1'),
                    aws_access_key_id=offsite_config.get('access_key'),
                    aws_secret_access_key=offsite_config.get('secret_key')
                )

                bucket = offsite_config.get('bucket')
                key = f"backups/{backup_file.name}"

                s3_client.upload_file(str(backup_file), bucket, key)

                return {
                    'status': 'success',
                    'destination': f"s3://{bucket}/{key}",
                    'size_mb': backup_file.stat().st_size / (1024**2)
                }

            elif self.offsite_type == 'backblaze':
                # Backblaze B2 sync (uses S3-compatible API)
                s3_client = boto3.client(
                    's3',
                    endpoint_url='https://s3.us-west-004.backblazeb2.com',  # Example endpoint
                    aws_access_key_id=offsite_config.get('key_id'),
                    aws_secret_access_key=offsite_config.get('application_key')
                )

                bucket = offsite_config.get('bucket')
                key = f"backups/{backup_file.name}"

                s3_client.upload_file(str(backup_file), bucket, key)

                return {
                    'status': 'success',
                    'destination': f"b2://{bucket}/{key}",
                    'size_mb': backup_file.stat().st_size / (1024**2)
                }
            else:
                return {
                    'status': 'failed',
                    'error': f'Unknown offsite type: {self.offsite_type}'
                }

        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e)
            }

    def verify_latest_backup(self) -> Dict[str, Any]:
        """
        Verify the most recent backup

        Returns:
            Dictionary with comprehensive verification results
        """
        try:
            # Find latest database backup
            db_backups = sorted(
                self.backup_dir.glob("immich_db_*.sql*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

            if not db_backups:
                return {
                    'status': 'failed',
                    'error': 'No database backups found',
                    'timestamp': datetime.now().isoformat()
                }

            latest_backup = db_backups[0]

            results = {
                'timestamp': datetime.now().isoformat(),
                'backup_file': str(latest_backup),
                'backup_age_hours': (datetime.now() -
                                    datetime.fromtimestamp(latest_backup.stat().st_mtime)).total_seconds() / 3600
            }

            # Step 1: Integrity check
            logger.info(f"Verifying integrity of {latest_backup.name}...")
            integrity = self.verify_backup_integrity(latest_backup)
            results['integrity'] = integrity

            if integrity['status'] != 'success':
                results['status'] = 'failed'
                return results

            # Step 2: Restore test
            logger.info(f"Testing restore of {latest_backup.name}...")
            restore_test = self.test_restore_backup(latest_backup)
            results['restore_test'] = restore_test

            if restore_test['status'] != 'success':
                results['status'] = 'failed'
                return results

            # Step 3: Offsite sync
            if self.offsite_enabled:
                logger.info(f"Syncing {latest_backup.name} to offsite storage...")
                offsite = self.sync_to_offsite(latest_backup)
                results['offsite_sync'] = offsite
            else:
                results['offsite_sync'] = {'status': 'skipped'}

            # Overall status
            results['status'] = 'success'

            # Save verification log
            self._save_verification_log(results)

            return results

        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

    def _save_verification_log(self, results: Dict[str, Any]):
        """Save verification results to log file"""
        try:
            # Load existing logs
            if self.verification_log.exists():
                with open(self.verification_log, 'r') as f:
                    logs = json.load(f)
            else:
                logs = []

            # Add new result
            logs.append(results)

            # Keep only last 100 entries
            logs = logs[-100:]

            # Save
            with open(self.verification_log, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save verification log: {e}")

    def get_verification_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent verification history

        Args:
            limit: Number of recent entries to return

        Returns:
            List of verification results
        """
        try:
            if not self.verification_log.exists():
                return []

            with open(self.verification_log, 'r') as f:
                logs = json.load(f)

            return logs[-limit:]

        except Exception as e:
            logger.error(f"Failed to load verification history: {e}")
            return []

    def run_monthly_verification(self) -> Dict[str, Any]:
        """
        Run comprehensive monthly verification
        Should be scheduled via cron/systemd timer

        Returns:
            Dictionary with full verification report
        """
        logger.info("Starting monthly backup verification...")

        results = self.verify_latest_backup()

        # Send email notification if enabled and verification failed
        if self.email_enabled and results['status'] == 'failed':
            self._send_failure_notification(results)

        return results

    def _send_failure_notification(self, results: Dict[str, Any]):
        """
        Send email notification on verification failure

        Args:
            results: Verification results dictionary
        """
        # ADMIN TODO: Implement email notification
        # This should integrate with the email notifier from photo-curator
        # or implement its own SMTP sending
        logger.warning("Backup verification failed - email notification not implemented yet")
        logger.warning(f"Failure details: {results.get('error', 'Unknown error')}")


class BackupRetentionManager:
    """Manage backup retention policies"""

    def __init__(self, config):
        self.backup_dir = Path(config.get('backup_dir', '/mnt/backups/immich'))
        self.retention_policy = config.get('retention_policy', {
            'daily': 7,      # Keep 7 daily backups
            'weekly': 4,     # Keep 4 weekly backups
            'monthly': 12    # Keep 12 monthly backups
        })

    def apply_retention_policy(self) -> Dict[str, Any]:
        """
        Apply retention policy to backups
        Keep daily, weekly, and monthly backups according to policy

        Returns:
            Dictionary with retention results
        """
        try:
            all_backups = sorted(
                self.backup_dir.glob("immich_db_*.sql*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

            if not all_backups:
                return {'status': 'skipped', 'reason': 'No backups found'}

            # Categorize backups
            daily_backups = []
            weekly_backups = []
            monthly_backups = []

            now = datetime.now()

            for backup in all_backups:
                backup_time = datetime.fromtimestamp(backup.stat().st_mtime)
                age_days = (now - backup_time).days

                # Daily: backups from last 7 days
                if age_days < self.retention_policy['daily']:
                    daily_backups.append(backup)
                # Weekly: one backup per week for last 4 weeks
                elif age_days < self.retention_policy['weekly'] * 7:
                    week_num = age_days // 7
                    if not any(b for b in weekly_backups if
                              (datetime.fromtimestamp(b.stat().st_mtime) - backup_time).days // 7 == week_num):
                        weekly_backups.append(backup)
                # Monthly: one backup per month for last 12 months
                elif age_days < self.retention_policy['monthly'] * 30:
                    month_key = backup_time.strftime('%Y-%m')
                    if not any(b for b in monthly_backups if
                              datetime.fromtimestamp(b.stat().st_mtime).strftime('%Y-%m') == month_key):
                        monthly_backups.append(backup)

            # Keep these backups
            keep_backups = set(daily_backups + weekly_backups + monthly_backups)

            # Delete old backups
            deleted_count = 0
            deleted_size = 0

            for backup in all_backups:
                if backup not in keep_backups:
                    size = backup.stat().st_size
                    backup.unlink()
                    deleted_count += 1
                    deleted_size += size

            return {
                'status': 'success',
                'daily_kept': len(daily_backups),
                'weekly_kept': len(weekly_backups),
                'monthly_kept': len(monthly_backups),
                'deleted_count': deleted_count,
                'deleted_mb': deleted_size / (1024**2)
            }

        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e)
            }
