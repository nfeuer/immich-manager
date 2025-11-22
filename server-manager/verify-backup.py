#!/usr/bin/env python3
"""
Manual backup verification CLI tool
Run backup verification on demand
"""

import sys
import argparse
import yaml
from pathlib import Path
from src.backup_verifier import BackupVerifier, BackupRetentionManager


def main():
    parser = argparse.ArgumentParser(
        description='Immich Backup Verification Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify latest backup
  python verify-backup.py --verify

  # Apply retention policy
  python verify-backup.py --retention

  # View verification history
  python verify-backup.py --history

  # Full verification with offsite sync
  python verify-backup.py --verify --offsite
        """
    )

    parser.add_argument('--verify', action='store_true',
                       help='Verify latest backup integrity and restore')
    parser.add_argument('--retention', action='store_true',
                       help='Apply retention policy to backups')
    parser.add_argument('--history', action='store_true',
                       help='Show verification history')
    parser.add_argument('--offsite', action='store_true',
                       help='Force offsite sync (use with --verify)')
    parser.add_argument('--config', default='config/config.yaml',
                       help='Path to config file (default: config/config.yaml)')

    args = parser.parse_args()

    # Load configuration
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        print("💡 Copy config.yaml.example to config.yaml and configure it")
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    verification_config = config.get('backup_verification', {})

    # Show history
    if args.history:
        verifier = BackupVerifier(verification_config)
        history = verifier.get_verification_history(limit=10)

        if not history:
            print("📋 No verification history found")
            return

        print("\n📊 Backup Verification History (last 10)\n")
        print("=" * 80)

        for i, entry in enumerate(reversed(history), 1):
            status_icon = "✅" if entry['status'] == 'success' else "❌"
            print(f"\n{i}. {status_icon} {entry['timestamp']}")
            print(f"   Backup: {Path(entry.get('backup_file', 'N/A')).name}")
            print(f"   Age: {entry.get('backup_age_hours', 0):.1f} hours")

            if entry.get('integrity'):
                int_status = "✅" if entry['integrity']['status'] == 'success' else "❌"
                print(f"   Integrity: {int_status} {entry['integrity'].get('size_mb', 0):.1f} MB")

            if entry.get('restore_test'):
                restore_status = "✅" if entry['restore_test']['status'] == 'success' else "❌"
                print(f"   Restore Test: {restore_status} ({entry['restore_test'].get('duration_seconds', 0):.1f}s)")

            if entry.get('offsite_sync') and entry['offsite_sync']['status'] != 'skipped':
                offsite_status = "✅" if entry['offsite_sync']['status'] == 'success' else "❌"
                print(f"   Offsite Sync: {offsite_status}")

            if entry['status'] == 'failed':
                print(f"   ⚠️  Error: {entry.get('error', 'Unknown error')}")

        print("\n" + "=" * 80 + "\n")
        return

    # Run verification
    if args.verify:
        print("\n🔍 Starting backup verification...\n")

        # Temporarily enable offsite if requested
        if args.offsite:
            verification_config['offsite_sync'] = verification_config.get('offsite_sync', {})
            verification_config['offsite_sync']['enabled'] = True

        verifier = BackupVerifier(verification_config)
        results = verifier.verify_latest_backup()

        print("\n📊 Verification Results\n")
        print("=" * 80)

        # Backup info
        if results.get('backup_file'):
            print(f"\n📁 Backup File:")
            print(f"   Path: {results['backup_file']}")
            print(f"   Age: {results.get('backup_age_hours', 0):.1f} hours")

        # Integrity check
        if results.get('integrity'):
            integrity = results['integrity']
            status_icon = "✅" if integrity['status'] == 'success' else "❌"
            print(f"\n{status_icon} Integrity Check:")
            print(f"   Status: {integrity['status']}")
            if integrity['status'] == 'success':
                print(f"   Size: {integrity.get('size_mb', 0):.2f} MB")
                print(f"   Checksum: {integrity.get('checksum', 'N/A')[:16]}...")
            else:
                print(f"   Error: {integrity.get('error', 'Unknown error')}")

        # Restore test
        if results.get('restore_test'):
            restore = results['restore_test']
            status_icon = "✅" if restore['status'] == 'success' else "❌"
            print(f"\n{status_icon} Restore Test:")
            print(f"   Status: {restore['status']}")
            if restore['status'] == 'success':
                print(f"   Duration: {restore.get('duration_seconds', 0):.1f}s")
                print(f"   Users Found: {restore.get('user_count', 'N/A')}")
                print(f"   Valid: {'Yes' if restore.get('restore_valid') else 'No'}")
            else:
                print(f"   Error: {restore.get('error', 'Unknown error')}")

        # Offsite sync
        if results.get('offsite_sync'):
            offsite = results['offsite_sync']
            if offsite['status'] != 'skipped':
                status_icon = "✅" if offsite['status'] == 'success' else "❌"
                print(f"\n{status_icon} Offsite Sync:")
                print(f"   Status: {offsite['status']}")
                if offsite['status'] == 'success':
                    print(f"   Destination: {offsite.get('destination', 'N/A')}")
                    print(f"   Size: {offsite.get('size_mb', 0):.2f} MB")
                else:
                    print(f"   Error: {offsite.get('error', 'Unknown error')}")
            else:
                print(f"\nℹ️  Offsite Sync: Disabled (configure in config.yaml)")

        # Overall status
        print(f"\n{'=' * 80}")
        if results['status'] == 'success':
            print("\n✅ Verification completed successfully!")
        else:
            print("\n❌ Verification failed!")
            print(f"   Error: {results.get('error', 'See details above')}")

        print("\n" + "=" * 80 + "\n")

        sys.exit(0 if results['status'] == 'success' else 1)

    # Apply retention policy
    if args.retention:
        print("\n🗄️  Applying backup retention policy...\n")

        manager = BackupRetentionManager(verification_config)
        results = manager.apply_retention_policy()

        print("📊 Retention Policy Results\n")
        print("=" * 80)

        if results['status'] == 'success':
            print(f"\n✅ Retention policy applied successfully!")
            print(f"\nKept:")
            print(f"   Daily backups: {results['daily_kept']}")
            print(f"   Weekly backups: {results['weekly_kept']}")
            print(f"   Monthly backups: {results['monthly_kept']}")
            print(f"\nDeleted:")
            print(f"   Files: {results['deleted_count']}")
            print(f"   Space freed: {results['deleted_mb']:.2f} MB")
        else:
            print(f"\n❌ Retention policy failed!")
            print(f"   Error: {results.get('error', 'Unknown error')}")

        print("\n" + "=" * 80 + "\n")

        sys.exit(0 if results['status'] == 'success' else 1)

    # No action specified
    parser.print_help()
    sys.exit(1)


if __name__ == '__main__':
    main()
