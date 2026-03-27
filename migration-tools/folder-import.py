#!/usr/bin/env python3
"""
Plain Folder Import Tool
Imports photos from any directory to Immich without requiring a specific export format.
Scans recursively for supported image/video files and uploads each one.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
import requests

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff', '.bmp',
    '.heic', '.heif', '.dng', '.raw', '.arw', '.cr2', '.cr3', '.nef',
    '.mp4', '.mov', '.avi', '.mkv', '.m4v', '.webm', '.3gp',
}

MIME_TYPES = {
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


class FolderImporter:
    """Import photos from a plain folder (no export format required)."""

    def __init__(self, directory: Path, immich_url: str, api_key: str):
        self.directory = Path(directory)
        self.immich_url = immich_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({'Authorization': f'Bearer {api_key}', 'Accept': 'application/json'})
        self.stats = {'total_files': 0, 'uploaded': 0, 'duplicates': 0, 'errors': 0}
        self.progress_file = self.directory / 'folder-import-progress.json'
        self.uploaded_files = self._load_progress()

    def _load_progress(self) -> set:
        if self.progress_file.exists():
            try:
                with open(self.progress_file) as f:
                    return set(json.load(f))
            except Exception:
                pass
        return set()

    def _save_progress(self):
        try:
            with open(self.progress_file, 'w') as f:
                json.dump(list(self.uploaded_files), f)
        except Exception:
            pass

    def _scan_files(self) -> list:
        """Scan directory recursively for supported image/video files."""
        return [
            p for p in self.directory.rglob('*')
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

    def _upload_file(self, file_path: Path) -> bool:
        """Upload a single file to Immich. Returns True on success."""
        file_key = str(file_path.relative_to(self.directory))

        if file_key in self.uploaded_files:
            self.stats['duplicates'] += 1
            return True

        mime_type = MIME_TYPES.get(file_path.suffix.lower(), 'application/octet-stream')
        file_created_at = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()

        try:
            with open(file_path, 'rb') as f:
                response = self.session.post(
                    f'{self.immich_url}/api/assets',
                    files={'assetData': (file_path.name, f, mime_type)},
                    data={
                        'deviceAssetId': file_key,
                        'deviceId': 'FolderImport',
                        'fileCreatedAt': file_created_at,
                        'fileModifiedAt': file_created_at,
                        'isFavorite': 'false',
                    },
                    timeout=300,
                )

            if response.status_code in (200, 201):
                self.stats['uploaded'] += 1
                self.uploaded_files.add(file_key)
                self._save_progress()
                return True
            elif response.status_code == 409:
                self.stats['duplicates'] += 1
                self.uploaded_files.add(file_key)
                self._save_progress()
                return True
            else:
                logger.error(f"Upload failed ({response.status_code}): {file_path.name}")
                self.stats['errors'] += 1
                return False

        except Exception as e:
            logger.error(f"Error uploading {file_path}: {e}")
            self.stats['errors'] += 1
            return False
