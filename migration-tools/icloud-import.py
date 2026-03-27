#!/usr/bin/env python3
"""
iCloud Photos Data Export Import Tool
Imports photos from an Apple data export (privacy.apple.com) to Immich

Usage:
    python icloud-import.py --export-dir /path/to/icloud-export --immich-url http://localhost:2283 --api-key YOUR_KEY

How to get your iCloud data export:
    1. Go to https://privacy.apple.com
    2. Sign in with your Apple ID
    3. Request a copy of your data → select "iCloud Photos"
    4. Apple emails a download link (may take 1–7 days for large libraries)
    5. Download and extract the ZIP file(s)

Export structure Apple provides:
    Apple_Media_Services/
      iCloud Photos/
        Photos/
          2020/
            IMG_1234.HEIC
            ...
          2021/
            ...

Features:
- Reads capture dates and GPS from embedded EXIF metadata
- Falls back to directory year/file timestamps when EXIF unavailable
- Handles HEIC/HEIF (Apple's native format)
- Progress tracking and resumption
- Duplicate detection
- Batch upload with rate limiting
"""

import argparse
import json
import logging
import re
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
        logging.FileHandler('icloud-import.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff', '.bmp', '.heic', '.heif',
    # Raw formats
    '.dng', '.raw', '.arw', '.cr2', '.cr3', '.nef',
    # Videos
    '.mp4', '.mov', '.avi', '.mkv', '.m4v',
}

# Matches folder names like "2023", "2023-01", "Photos from 2023"
_YEAR_RE = re.compile(r'\b(19|20)\d{2}\b')


class ICloudImporter:
    """Import iCloud Photos data export (privacy.apple.com) to Immich"""

    def __init__(self, export_dir: Path, immich_url: str, api_key: str):
        """
        Args:
            export_dir: Path to extracted Apple data export directory
            immich_url: Immich server URL
            api_key: Immich API key
        """
        self.export_dir = Path(export_dir)
        self.immich_url = immich_url.rstrip('/')
        self.api_key = api_key

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
        }

        self.progress_file = Path('icloud-import-progress.json')
        self.uploaded_files = self._load_progress()
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

    def find_photos_root(self) -> Optional[Path]:
        """
        Locate the photos directory within the iCloud export.

        Apple's export places photos under a path like:
            Apple_Media_Services/iCloud Photos/Photos/
        but this can vary between export batches.
        """
        # Look for a 'Photos' directory that contains year-named subdirs or image files
        candidates = []
        for d in self.export_dir.rglob('*'):
            if not d.is_dir():
                continue
            name_lower = d.name.lower()
            if 'photo' in name_lower:
                # Check it contains actual media
                if any(
                    f.suffix.lower() in SUPPORTED_EXTENSIONS
                    for f in d.rglob('*')
                    if f.is_file()
                ):
                    candidates.append(d)

        if not candidates:
            logger.warning(
                "Could not auto-detect photos directory; scanning entire export directory."
            )
            return self.export_dir

        # Prefer the deepest 'Photos' directory (most specific)
        candidates.sort(key=lambda p: len(p.parts), reverse=True)
        found = candidates[0]
        logger.info(f"Found photos directory: {found}")
        return found

    def _read_exif_metadata(self, file_path: Path) -> Optional[Dict]:
        """Read EXIF metadata from an image file using Pillow."""
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

    def _infer_date_from_path(self, file_path: Path) -> Optional[datetime]:
        """
        Try to infer a capture year from parent directory names (e.g., "2023", "2023-06").
        Used as a fallback when EXIF is unavailable.
        """
        for part in reversed(file_path.parts):
            m = _YEAR_RE.search(part)
            if m:
                year = int(m.group())
                # Try to extract month too (e.g. "2023-06" or "2023_06")
                month_match = re.search(r'[-_](0[1-9]|1[0-2])\b', part)
                month = int(month_match.group(1)) if month_match else 1
                return datetime(year, month, 1, 12, 0, 0)
        return None

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

    def _upload_file(self, file_path: Path, photos_root: Path) -> bool:
        """Upload a single file to Immich. Returns True on success."""
        file_key = str(file_path.relative_to(self.export_dir))

        if file_key in self.uploaded_files:
            self.stats['duplicates'] += 1
            return True

        # Read EXIF for image files
        metadata = None
        if file_path.suffix.lower() not in {'.mp4', '.mov', '.avi', '.mkv', '.m4v'}:
            metadata = self._read_exif_metadata(file_path)

        # Determine capture date: EXIF → directory name → file mtime
        if metadata and metadata.get('capture_date'):
            file_created_at = metadata['capture_date'].isoformat()
        else:
            inferred = self._infer_date_from_path(file_path)
            if inferred:
                file_created_at = inferred.isoformat()
            else:
                file_created_at = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()

        try:
            with open(file_path, 'rb') as f:
                files = {
                    'assetData': (file_path.name, f, self._get_mime_type(file_path))
                }
                data = {
                    'deviceAssetId': file_key,
                    'deviceId': 'iCloudImport',
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
        """Import all photos from the iCloud export directory."""
        logger.info("Starting iCloud Photos import...")

        photos_root = self.find_photos_root()

        logger.info(f"Scanning {photos_root} ...")
        photo_files = [
            p for p in photos_root.rglob('*')
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

        self.stats['total_files'] = len(photo_files)
        logger.info(f"Found {len(photo_files)} files to import")

        if not photo_files:
            logger.warning("No photos found to import")
            return

        with tqdm(total=len(photo_files), desc="Importing photos") as pbar:
            for i, photo_path in enumerate(photo_files):
                self._upload_file(photo_path, photos_root)

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
        logger.info(f"  Total files found:      {self.stats['total_files']}")
        logger.info(f"  Successfully uploaded:  {self.stats['uploaded']}")
        logger.info(f"  Duplicates skipped:     {self.stats['duplicates']}")
        logger.info(f"  Errors:                 {self.stats['errors']}")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='Import iCloud Photos data export (privacy.apple.com) to Immich',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
How to get your iCloud data export:
  1. Go to https://privacy.apple.com and sign in
  2. Click "Request a copy of your data"
  3. Select "iCloud Photos" (and any other data you want)
  4. Choose maximum file size and submit
  5. Apple emails a download link within 1-7 days
  6. Download all parts and extract the ZIP file(s)

Examples:
  python icloud-import.py \\
    --export-dir ~/Downloads/Apple_Media_Services \\
    --immich-url http://localhost:2283 \\
    --api-key YOUR_API_KEY

  # Slower import for large libraries
  python icloud-import.py \\
    --export-dir ~/Downloads/Apple_Media_Services \\
    --immich-url http://localhost:2283 \\
    --api-key YOUR_API_KEY \\
    --delay 0.5

  # Resume an interrupted import
  python icloud-import.py \\
    --export-dir ~/Downloads/Apple_Media_Services \\
    --immich-url http://localhost:2283 \\
    --api-key YOUR_API_KEY
  # (progress is saved automatically in icloud-import-progress.json)

Notes:
  - Install Pillow for EXIF metadata: pip install Pillow>=10.0.0
  - Without Pillow, dates are inferred from directory names (e.g., "2023/")
  - API key: Immich → Settings → API Keys → Create
  - Large libraries may take several hours
        """
    )

    parser.add_argument('--export-dir', required=True, type=Path,
                        help='Path to extracted Apple data export directory')
    parser.add_argument('--immich-url', required=True,
                        help='Immich server URL (e.g., http://localhost:2283)')
    parser.add_argument('--api-key', required=True,
                        help='Immich API key')
    parser.add_argument('--batch-size', type=int, default=100,
                        help='Progress save interval in number of files (default: 100)')
    parser.add_argument('--delay', type=float, default=0.1,
                        help='Delay between uploads in seconds (default: 0.1)')

    args = parser.parse_args()

    if not args.export_dir.exists():
        logger.error(f"Directory does not exist: {args.export_dir}")
        sys.exit(1)
    if not args.export_dir.is_dir():
        logger.error(f"Path is not a directory: {args.export_dir}")
        sys.exit(1)

    importer = ICloudImporter(
        export_dir=args.export_dir,
        immich_url=args.immich_url,
        api_key=args.api_key,
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
