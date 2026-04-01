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
from typing import Optional, Dict, List
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


def _get_exif_date(file_path: Path) -> Optional[datetime]:
    """Read DateTimeOriginal (or DateTime) from EXIF. Returns None if not found."""
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            exif = img.getexif()
            for tag_id in (36867, 36868, 306):  # DateTimeOriginal, DateTimeDigitized, DateTime
                val = exif.get(tag_id)
                if val:
                    return datetime.strptime(val, '%Y:%m:%d %H:%M:%S')
    except Exception:
        pass
    return None


class FolderImporter:
    """Import photos from a plain folder (no export format required)."""

    def __init__(
        self,
        directory: Path,
        immich_url: str,
        api_key: str,
        create_albums: bool = False,
        root_album: bool = False,
        skip_root_folder: bool = False,
    ):
        self.directory = Path(directory)
        self.immich_url = immich_url.rstrip('/')
        self.api_key = api_key
        self.create_albums = create_albums
        self.root_album = root_album
        self.skip_root_folder = skip_root_folder
        self.session = requests.Session()
        self.session.headers.update({'Authorization': f'Bearer {api_key}', 'Accept': 'application/json'})
        self.stats = {
            'total_files': 0, 'uploaded': 0, 'duplicates': 0, 'errors': 0,
            'albums_created': 0, 'current_file': '',
        }
        self.progress_file = self.directory / 'folder-import-progress.json'
        self.uploaded_files = self._load_progress()
        # Album tracking state
        self._album_buffer: Dict[str, List[str]] = {}
        self._existing_albums: Dict[str, str] = {}
        self._albums_cache_loaded: bool = False
        self._files_since_flush: int = 0
        self._current_batch: int = 0
        self._total_batches: int = 0

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

    def _get_album_names(self, file_path: Path) -> List[str]:
        """Return the list of album names a file belongs to based on its subfolder path."""
        rel = file_path.relative_to(self.directory)
        parts = rel.parts
        if self.skip_root_folder:
            root_folder_name = parts[0] if parts else ''
            path_parts = parts[1:]
        else:
            root_folder_name = self.directory.name
            path_parts = parts
        # Only the filename remains — file is directly in the (possibly-skipped) root
        if len(path_parts) <= 1:
            if self.root_album and root_folder_name:
                return [root_folder_name]
            return []
        # Return all directory components, excluding the filename
        return list(path_parts[:-1])

    def _load_album_cache(self):
        """Fetch existing albums once and cache name→id. Called lazily on first flush."""
        if self._albums_cache_loaded:
            return
        try:
            resp = self.session.get(f'{self.immich_url}/api/albums')
            resp.raise_for_status()
            self._existing_albums = {a['albumName']: a['id'] for a in resp.json()}
        except Exception as e:
            logger.warning(f"Could not load album cache: {e}")
        self._albums_cache_loaded = True

    def _flush_albums(self):
        """Send buffered album assignments to Immich. Non-fatal on API errors."""
        if not self._album_buffer:
            return
        self._load_album_cache()

        # Capture counts before clearing — used in the log line
        flushed_counts = {name: len(ids) for name, ids in self._album_buffer.items()}

        for album_name, asset_ids in list(self._album_buffer.items()):
            try:
                if album_name in self._existing_albums:
                    album_id = self._existing_albums[album_name]
                    resp = self.session.put(
                        f'{self.immich_url}/api/albums/{album_id}/assets',
                        json={'ids': asset_ids},
                    )
                    resp.raise_for_status()
                else:
                    resp = self.session.post(
                        f'{self.immich_url}/api/albums',
                        json={'albumName': album_name, 'assetIds': asset_ids},
                    )
                    resp.raise_for_status()
                    new_id = resp.json().get('id')
                    if new_id:
                        self._existing_albums[album_name] = new_id
                    self.stats['albums_created'] += 1
            except Exception as e:
                logger.warning(f"Album '{album_name}' update failed: {e}")

        self._album_buffer.clear()
        self._current_batch += 1

        album_summary = ', '.join(f"{n}({c})" for n, c in flushed_counts.items())
        logger.info(
            f"[Import:folder] Batch {self._current_batch}/{self._total_batches} — "
            f"{self.stats['uploaded']} uploaded, {self.stats['duplicates']} duplicates, "
            f"{self.stats['errors']} errors | {album_summary}"
        )

    def _scan_files(self) -> list:
        """Scan directory recursively for supported image/video files."""
        return [
            p for p in self.directory.rglob('*')
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

    def _upload_file(self, file_path: Path) -> Optional[str]:
        """Upload a single file to Immich. Returns asset_id on success/duplicate, None on error or skip."""
        file_key = str(file_path.relative_to(self.directory))

        if file_key in self.uploaded_files:
            self.stats['duplicates'] += 1
            return None  # Already uploaded — progress-file skip; album assignment not replayed

        mime_type = MIME_TYPES.get(file_path.suffix.lower(), 'application/octet-stream')
        exif_date = _get_exif_date(file_path)
        file_created_at = (exif_date or datetime.fromtimestamp(file_path.stat().st_mtime)).isoformat()

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
                return response.json().get('id')
            elif response.status_code == 409:
                asset_id = response.json().get('id')
                self.stats['duplicates'] += 1
                self.uploaded_files.add(file_key)
                self._save_progress()
                if not asset_id:
                    logger.warning(f"Duplicate {file_path.name} — no id in 409 response, skipping album")
                return asset_id
            else:
                logger.error(f"Upload failed ({response.status_code}): {file_path.name}")
                self.stats['errors'] += 1
                return None

        except Exception as e:
            logger.error(f"Error uploading {file_path}: {e}")
            self.stats['errors'] += 1
            return None
