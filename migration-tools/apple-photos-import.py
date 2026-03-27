#!/usr/bin/env python3
"""
Apple Photos Export Import Tool
Imports photos exported from Apple Photos.app to Immich with metadata preservation

Usage:
    python apple-photos-import.py --photos-dir /path/to/export --immich-url http://localhost:2283 --api-key YOUR_KEY

Supported export methods:
    - File → Export → Export Unmodified Originals (Photos.app on macOS)
    - Any directory of Apple Photos files with embedded EXIF metadata

Features:
- Reads capture dates and GPS from embedded EXIF metadata
- Handles HEIC/HEIF files (Apple's native format)
- Live Photo detection: skips companion .MOV files by default
- Progress tracking and resumption
- Duplicate detection
- Batch upload with rate limiting
"""

import argparse
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
import time
import sys
import requests
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('apple-photos-import.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Still image extensions that can have a Live Photo companion .MOV
LIVE_PHOTO_STILL_EXTENSIONS = {'.heic', '.heif', '.jpg', '.jpeg'}

SUPPORTED_EXTENSIONS = {
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff', '.bmp', '.heic', '.heif',
    # Raw formats common on Apple devices
    '.dng', '.raw', '.arw', '.cr2', '.cr3', '.nef',
    # Videos
    '.mp4', '.mov', '.avi', '.mkv', '.m4v',
}


class ApplePhotosImporter:
    """Import Apple Photos exports to Immich"""

    def __init__(
        self,
        photos_dir: Path,
        immich_url: str,
        api_key: str,
        include_live_videos: bool = False,
    ):
        """
        Args:
            photos_dir: Path to Apple Photos export directory
            immich_url: Immich server URL
            api_key: Immich API key
            include_live_videos: Whether to upload the .MOV part of Live Photos
        """
        self.photos_dir = Path(photos_dir)
        self.immich_url = immich_url.rstrip('/')
        self.api_key = api_key
        self.include_live_videos = include_live_videos

        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Accept': 'application/json'
        })

        self.stats = {
            'total_files': 0,
            'uploaded': 0,
            'skipped': 0,
            'errors': 0,
            'duplicates': 0,
            'live_videos_skipped': 0,
        }

        self.progress_file = Path('apple-import-progress.json')
        self.uploaded_files = self._load_progress()

        # Check for Pillow EXIF support once at startup
        self._pillow_available = self._check_pillow()

    def _check_pillow(self) -> bool:
        try:
            from PIL import Image  # noqa: F401
            return True
        except ImportError:
            logger.warning(
                "Pillow not installed — EXIF metadata (capture dates, GPS) will not be read. "
                "Install with: pip install Pillow>=10.0.0"
            )
            return False

    def _load_progress(self) -> set:
        if self.progress_file.exists():
            try:
                with open(self.progress_file) as f:
                    data = json.load(f)
                    logger.info(f"Resuming: {len(data)} files already uploaded")
                    return set(data)
            except Exception as e:
                logger.warning(f"Could not load progress file: {e}")
        return set()

    def _save_progress(self):
        try:
            with open(self.progress_file, 'w') as f:
                json.dump(list(self.uploaded_files), f)
        except Exception as e:
            logger.error(f"Could not save progress: {e}")

    def _read_exif_metadata(self, file_path: Path) -> Optional[Dict]:
        """Read EXIF metadata from image file using Pillow."""
        if not self._pillow_available:
            return None

        try:
            from PIL import Image
            from PIL.ExifTags import TAGS, GPSTAGS

            with Image.open(file_path) as img:
                raw_exif = img._getexif()  # type: ignore[attr-defined]
                if not raw_exif:
                    return None

            metadata: Dict = {}
            gps_info: Dict = {}

            for tag_id, value in raw_exif.items():
                tag = TAGS.get(tag_id, tag_id)

                if tag == 'DateTimeOriginal':
                    try:
                        metadata['capture_date'] = datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                    except (ValueError, TypeError):
                        pass

                elif tag == 'GPSInfo':
                    for gps_tag_id, gps_value in value.items():
                        gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                        gps_info[gps_tag] = gps_value

            if gps_info:
                lat = self._convert_gps(
                    gps_info.get('GPSLatitude'),
                    gps_info.get('GPSLatitudeRef', 'N'),
                )
                lon = self._convert_gps(
                    gps_info.get('GPSLongitude'),
                    gps_info.get('GPSLongitudeRef', 'E'),
                )
                if lat is not None:
                    metadata['latitude'] = lat
                if lon is not None:
                    metadata['longitude'] = lon

            return metadata if metadata else None

        except Exception:
            return None

    def _convert_gps(self, coord, ref: str) -> Optional[float]:
        """Convert GPS degrees/minutes/seconds to decimal degrees."""
        if not coord:
            return None
        try:
            degrees = float(coord[0])
            minutes = float(coord[1])
            seconds = float(coord[2])
            decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
            if ref in ('S', 'W'):
                decimal = -decimal
            return decimal
        except (TypeError, IndexError, ZeroDivisionError):
            return None

    def _is_live_photo_companion(self, mov_path: Path, all_stills: set) -> bool:
        """
        Return True if this .MOV is the video half of a Live Photo.

        Apple names Live Photo pairs identically:
            IMG_1234.HEIC  +  IMG_1234.MOV
        """
        if mov_path.suffix.lower() != '.mov':
            return False
        for still_ext in LIVE_PHOTO_STILL_EXTENSIONS:
            if mov_path.with_suffix(still_ext) in all_stills:
                return True
            if mov_path.with_suffix(still_ext.upper()) in all_stills:
                return True
        return False

    def _scan_files(self) -> list:
        """Scan export directory and return list of files to import."""
        logger.info(f"Scanning {self.photos_dir} ...")

        all_files = [
            p for p in self.photos_dir.rglob('*')
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

        # Build set of still-image paths for Live Photo companion detection
        still_paths = {
            p for p in all_files
            if p.suffix.lower() in LIVE_PHOTO_STILL_EXTENSIONS
        }

        result = []
        for f in all_files:
            if not self.include_live_videos and self._is_live_photo_companion(f, still_paths):
                self.stats['live_videos_skipped'] += 1
                logger.debug(f"Skipping Live Photo companion: {f.name}")
                continue
            result.append(f)

        return result

    def _get_mime_type(self, path: Path) -> str:
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.heic': 'image/heic',
            '.heif': 'image/heif',
            '.tiff': 'image/tiff',
            '.dng': 'image/x-adobe-dng',
            '.mp4': 'video/mp4',
            '.mov': 'video/quicktime',
            '.m4v': 'video/x-m4v',
            '.avi': 'video/x-msvideo',
            '.mkv': 'video/x-matroska',
        }
        return mime_types.get(path.suffix.lower(), 'application/octet-stream')

    def _upload_file(self, file_path: Path) -> bool:
        """Upload a single file to Immich. Returns True on success."""
        file_key = str(file_path.relative_to(self.photos_dir))

        if file_key in self.uploaded_files:
            self.stats['duplicates'] += 1
            return True

        # Read EXIF for images
        metadata = None
        if file_path.suffix.lower() not in {'.mp4', '.mov', '.avi', '.mkv', '.m4v'}:
            metadata = self._read_exif_metadata(file_path)

        # Determine capture date
        if metadata and metadata.get('capture_date'):
            file_created_at = metadata['capture_date'].isoformat()
        else:
            file_created_at = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()

        try:
            with open(file_path, 'rb') as f:
                files = {
                    'assetData': (file_path.name, f, self._get_mime_type(file_path))
                }
                data = {
                    'deviceAssetId': file_key,
                    'deviceId': 'ApplePhotosImport',
                    'fileCreatedAt': file_created_at,
                    'fileModifiedAt': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                    'isFavorite': 'false',
                }
                if metadata:
                    if metadata.get('latitude') is not None:
                        data['latitude'] = str(metadata['latitude'])
                    if metadata.get('longitude') is not None:
                        data['longitude'] = str(metadata['longitude'])

                response = self.session.post(
                    f'{self.immich_url}/api/assets',
                    files=files,
                    data=data,
                    timeout=300,
                )

            if response.status_code in (200, 201):
                self.stats['uploaded'] += 1
                self.uploaded_files.add(file_key)
                self._save_progress()
                logger.debug(f"Uploaded: {file_path.name}")
                return True
            elif response.status_code == 409:
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

    def import_photos(self, batch_size: int = 100, rate_limit_delay: float = 0.1):
        """Import all photos from the export directory."""
        logger.info("Starting Apple Photos import...")

        photo_files = self._scan_files()
        self.stats['total_files'] = len(photo_files)
        logger.info(
            f"Found {len(photo_files)} files to import"
            + (f" ({self.stats['live_videos_skipped']} Live Photo companion videos skipped)" if self.stats['live_videos_skipped'] else "")
        )

        if not photo_files:
            logger.warning("No photos found to import")
            return

        with tqdm(total=len(photo_files), desc="Importing photos") as pbar:
            for i, photo_path in enumerate(photo_files):
                self._upload_file(photo_path)

                pbar.update(1)
                pbar.set_postfix({
                    'uploaded': self.stats['uploaded'],
                    'errors': self.stats['errors'],
                    'dupes': self.stats['duplicates'],
                })

                time.sleep(rate_limit_delay)

                if (i + 1) % batch_size == 0:
                    self._save_progress()

        self._save_progress()

        logger.info("=" * 60)
        logger.info("Import Summary:")
        logger.info(f"  Total files found:           {self.stats['total_files']}")
        logger.info(f"  Successfully uploaded:        {self.stats['uploaded']}")
        logger.info(f"  Duplicates skipped:           {self.stats['duplicates']}")
        logger.info(f"  Live Photo videos skipped:    {self.stats['live_videos_skipped']}")
        logger.info(f"  Errors:                       {self.stats['errors']}")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='Import Apple Photos export to Immich',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
How to export from Apple Photos.app (macOS):
  1. Open Photos.app
  2. Select all photos (Cmd+A) or a specific album
  3. File → Export → Export Unmodified Originals
  4. Choose a destination folder
  5. Run this script pointing at that folder

Examples:
  python apple-photos-import.py \\
    --photos-dir ~/Desktop/ApplePhotosExport \\
    --immich-url http://localhost:2283 \\
    --api-key YOUR_API_KEY

  # Include Live Photo companion videos
  python apple-photos-import.py \\
    --photos-dir ~/Desktop/ApplePhotosExport \\
    --immich-url http://localhost:2283 \\
    --api-key YOUR_API_KEY \\
    --include-live-videos

  # Resume an interrupted import
  python apple-photos-import.py \\
    --photos-dir ~/Desktop/ApplePhotosExport \\
    --immich-url http://localhost:2283 \\
    --api-key YOUR_API_KEY
  # (progress is saved automatically in apple-import-progress.json)

Notes:
  - Install Pillow for EXIF metadata support: pip install Pillow>=10.0.0
  - Without Pillow, photos are still uploaded using file timestamps
  - API key: Immich → Settings → API Keys → Create
        """
    )

    parser.add_argument('--photos-dir', required=True, type=Path,
                        help='Path to Apple Photos export directory')
    parser.add_argument('--immich-url', required=True,
                        help='Immich server URL (e.g., http://localhost:2283)')
    parser.add_argument('--api-key', required=True,
                        help='Immich API key')
    parser.add_argument('--include-live-videos', action='store_true',
                        help='Also upload the .MOV companion of Live Photos (default: skip them)')
    parser.add_argument('--batch-size', type=int, default=100,
                        help='Progress save interval in number of files (default: 100)')
    parser.add_argument('--delay', type=float, default=0.1,
                        help='Delay between uploads in seconds (default: 0.1)')

    args = parser.parse_args()

    if not args.photos_dir.exists():
        logger.error(f"Directory does not exist: {args.photos_dir}")
        sys.exit(1)
    if not args.photos_dir.is_dir():
        logger.error(f"Path is not a directory: {args.photos_dir}")
        sys.exit(1)

    importer = ApplePhotosImporter(
        photos_dir=args.photos_dir,
        immich_url=args.immich_url,
        api_key=args.api_key,
        include_live_videos=args.include_live_videos,
    )

    try:
        importer.import_photos(
            batch_size=args.batch_size,
            rate_limit_delay=args.delay,
        )
    except KeyboardInterrupt:
        logger.info("\nImport interrupted. Progress saved — run the same command to resume.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Import failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
