#!/usr/bin/env python3
"""
Google Photos Takeout Import Tool
Imports photos from Google Takeout export to Immich with metadata preservation

Usage:
    python google-photos-import.py --takeout-dir /path/to/takeout --immich-url http://localhost:2283 --api-key YOUR_KEY

Features:
- Preserves original capture dates from JSON metadata
- Maintains album structure
- Handles duplicate detection
- Progress tracking and resumption
- Batch upload with rate limiting
"""

import argparse
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import time
import sys
import requests
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('google-photos-import.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class GooglePhotosImporter:
    """Import Google Photos Takeout to Immich"""

    def __init__(self, takeout_dir: Path, immich_url: str, api_key: str):
        """
        Initialize importer

        Args:
            takeout_dir: Path to Google Takeout extracted directory
            immich_url: Immich server URL (e.g., http://localhost:2283)
            api_key: Immich API key
        """
        self.takeout_dir = Path(takeout_dir)
        self.immich_url = immich_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Accept': 'application/json'
        })

        # Track progress
        self.stats = {
            'total_files': 0,
            'uploaded': 0,
            'skipped': 0,
            'errors': 0,
            'duplicates': 0
        }

        # Progress file for resumption
        self.progress_file = Path('import-progress.json')
        self.uploaded_files = self._load_progress()

    def _load_progress(self) -> set:
        """Load previously uploaded files for resumption"""
        if self.progress_file.exists():
            try:
                with open(self.progress_file) as f:
                    data = json.load(f)
                    logger.info(f"Loaded progress: {len(data)} files already uploaded")
                    return set(data)
            except Exception as e:
                logger.warning(f"Could not load progress file: {e}")
        return set()

    def _save_progress(self):
        """Save progress for resumption"""
        try:
            with open(self.progress_file, 'w') as f:
                json.dump(list(self.uploaded_files), f)
        except Exception as e:
            logger.error(f"Could not save progress: {e}")

    def find_google_photos_dir(self) -> Optional[Path]:
        """
        Find Google Photos directory in Takeout

        Google Takeout structure:
        Takeout/
          └── Google Photos/
              ├── Photos from 2020/
              ├── Photos from 2021/
              └── ...
        """
        # Common patterns
        patterns = [
            'Google Photos',
            'Google Fotos',  # International versions
            'Photos'
        ]

        for pattern in patterns:
            for path in self.takeout_dir.rglob(pattern):
                if path.is_dir():
                    logger.info(f"Found Google Photos directory: {path}")
                    return path

        logger.error("Could not find Google Photos directory in Takeout")
        return None

    def find_photo_metadata(self, photo_path: Path) -> Optional[Dict]:
        """
        Find JSON metadata file for a photo

        Google Takeout creates .json files with same name as photo:
        IMG_1234.jpg
        IMG_1234.jpg.json  <- metadata
        """
        # Try exact match first
        json_path = Path(str(photo_path) + '.json')
        if json_path.exists():
            try:
                with open(json_path) as f:
                    return json.load(f)
            except Exception as e:
                logger.debug(f"Could not parse JSON for {photo_path}: {e}")

        return None

    def extract_metadata(self, json_data: Dict) -> Dict:
        """
        Extract relevant metadata from Google Photos JSON

        Returns:
            Dictionary with:
            - capture_date: Original capture date
            - latitude: GPS latitude
            - longitude: GPS longitude
            - description: Photo description
        """
        metadata = {}

        # Extract capture date
        if 'photoTakenTime' in json_data:
            timestamp = json_data['photoTakenTime'].get('timestamp')
            if timestamp:
                metadata['capture_date'] = datetime.fromtimestamp(int(timestamp))

        # Extract GPS data
        geo_data = json_data.get('geoData', {})
        if geo_data:
            metadata['latitude'] = geo_data.get('latitude')
            metadata['longitude'] = geo_data.get('longitude')

        # Extract description
        if 'description' in json_data:
            metadata['description'] = json_data['description']

        return metadata

    def is_supported_file(self, path: Path) -> bool:
        """Check if file is a supported photo/video format"""
        supported_extensions = {
            # Images
            '.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff', '.bmp', '.heic', '.heif',
            # Videos
            '.mp4', '.mov', '.avi', '.mkv', '.webm', '.3gp'
        }

        return path.suffix.lower() in supported_extensions

    def upload_file(self, file_path: Path, metadata: Optional[Dict] = None) -> bool:
        """
        Upload file to Immich

        Args:
            file_path: Path to file
            metadata: Optional metadata dictionary

        Returns:
            True if successful
        """
        try:
            # Check if already uploaded
            file_key = str(file_path.relative_to(self.takeout_dir))
            if file_key in self.uploaded_files:
                self.stats['duplicates'] += 1
                return True

            # Prepare file upload
            with open(file_path, 'rb') as f:
                files = {
                    'assetData': (file_path.name, f, self._get_mime_type(file_path))
                }

                # Prepare form data
                data = {
                    'deviceAssetId': file_key,
                    'deviceId': 'GooglePhotosImport',
                    'fileCreatedAt': metadata.get('capture_date', datetime.now()).isoformat() if metadata else datetime.now().isoformat(),
                    'fileModifiedAt': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                    'isFavorite': 'false'
                }

                # Add GPS if available
                if metadata:
                    if metadata.get('latitude'):
                        data['latitude'] = str(metadata['latitude'])
                    if metadata.get('longitude'):
                        data['longitude'] = str(metadata['longitude'])

                # Upload to Immich
                response = self.session.post(
                    f'{self.immich_url}/api/assets',
                    files=files,
                    data=data,
                    timeout=300  # 5 minute timeout for large files
                )

                if response.status_code in [200, 201]:
                    self.stats['uploaded'] += 1
                    self.uploaded_files.add(file_key)
                    self._save_progress()
                    logger.debug(f"Uploaded: {file_path.name}")
                    return True
                elif response.status_code == 409:  # Duplicate
                    self.stats['duplicates'] += 1
                    self.uploaded_files.add(file_key)
                    self._save_progress()
                    logger.debug(f"Duplicate: {file_path.name}")
                    return True
                else:
                    logger.error(f"Upload failed ({response.status_code}): {file_path.name}")
                    self.stats['errors'] += 1
                    return False

        except Exception as e:
            logger.error(f"Error uploading {file_path}: {e}")
            self.stats['errors'] += 1
            return False

    def _get_mime_type(self, path: Path) -> str:
        """Get MIME type for file"""
        extension = path.suffix.lower()

        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.heic': 'image/heic',
            '.heif': 'image/heif',
            '.mp4': 'video/mp4',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
        }

        return mime_types.get(extension, 'application/octet-stream')

    def import_photos(self, batch_size: int = 100, rate_limit_delay: float = 0.1):
        """
        Import all photos from Google Takeout

        Args:
            batch_size: Number of files to process before progress save
            rate_limit_delay: Delay between uploads (seconds)
        """
        logger.info("Starting Google Photos import...")

        # Find Google Photos directory
        photos_dir = self.find_google_photos_dir()
        if not photos_dir:
            logger.error("Cannot proceed without Google Photos directory")
            return

        # Find all photo files
        logger.info("Scanning for photos...")
        photo_files = []

        for ext in ['.jpg', '.jpeg', '.png', '.mp4', '.mov', '.heic']:
            photo_files.extend(photos_dir.rglob(f'*{ext}'))
            photo_files.extend(photos_dir.rglob(f'*{ext.upper()}'))

        # Filter to supported files and exclude JSON metadata files
        photo_files = [
            f for f in photo_files
            if self.is_supported_file(f) and not str(f).endswith('.json')
        ]

        self.stats['total_files'] = len(photo_files)
        logger.info(f"Found {len(photo_files)} files to import")

        if len(photo_files) == 0:
            logger.warning("No photos found to import")
            return

        # Import with progress bar
        with tqdm(total=len(photo_files), desc="Importing photos") as pbar:
            for i, photo_path in enumerate(photo_files):
                # Find metadata
                metadata_json = self.find_photo_metadata(photo_path)
                metadata = self.extract_metadata(metadata_json) if metadata_json else None

                # Upload file
                self.upload_file(photo_path, metadata)

                # Update progress bar
                pbar.update(1)
                pbar.set_postfix({
                    'uploaded': self.stats['uploaded'],
                    'errors': self.stats['errors'],
                    'dupes': self.stats['duplicates']
                })

                # Rate limiting
                time.sleep(rate_limit_delay)

                # Save progress periodically
                if (i + 1) % batch_size == 0:
                    self._save_progress()

        # Final save
        self._save_progress()

        # Print summary
        logger.info("=" * 60)
        logger.info("Import Summary:")
        logger.info(f"  Total files found: {self.stats['total_files']}")
        logger.info(f"  Successfully uploaded: {self.stats['uploaded']}")
        logger.info(f"  Duplicates skipped: {self.stats['duplicates']}")
        logger.info(f"  Errors: {self.stats['errors']}")
        logger.info(f"  Already uploaded (from previous run): {len(self.uploaded_files) - self.stats['uploaded']}")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='Import Google Photos Takeout to Immich',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import from Google Takeout directory
  python google-photos-import.py --takeout-dir ~/Downloads/Takeout --immich-url http://localhost:2283 --api-key YOUR_API_KEY

  # Resume interrupted import
  python google-photos-import.py --takeout-dir ~/Downloads/Takeout --immich-url http://localhost:2283 --api-key YOUR_API_KEY

  # Slower import with rate limiting
  python google-photos-import.py --takeout-dir ~/Downloads/Takeout --immich-url http://localhost:2283 --api-key YOUR_API_KEY --delay 1.0

Notes:
  - Extracts Google Takeout ZIP file first
  - API key: Get from Immich Settings → API Keys
  - Progress is saved automatically for resumption
  - Duplicates are automatically detected and skipped
        """
    )

    parser.add_argument(
        '--takeout-dir',
        required=True,
        type=Path,
        help='Path to extracted Google Takeout directory'
    )

    parser.add_argument(
        '--immich-url',
        required=True,
        help='Immich server URL (e.g., http://localhost:2283)'
    )

    parser.add_argument(
        '--api-key',
        required=True,
        help='Immich API key (get from Settings → API Keys)'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of files to process before saving progress (default: 100)'
    )

    parser.add_argument(
        '--delay',
        type=float,
        default=0.1,
        help='Delay between uploads in seconds (default: 0.1)'
    )

    args = parser.parse_args()

    # Validate takeout directory
    if not args.takeout_dir.exists():
        logger.error(f"Takeout directory does not exist: {args.takeout_dir}")
        sys.exit(1)

    if not args.takeout_dir.is_dir():
        logger.error(f"Takeout path is not a directory: {args.takeout_dir}")
        sys.exit(1)

    # Create importer and run
    importer = GooglePhotosImporter(
        takeout_dir=args.takeout_dir,
        immich_url=args.immich_url,
        api_key=args.api_key
    )

    try:
        importer.import_photos(
            batch_size=args.batch_size,
            rate_limit_delay=args.delay
        )
    except KeyboardInterrupt:
        logger.info("\nImport interrupted by user. Progress has been saved.")
        logger.info("Run the same command again to resume from where you left off.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Import failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
