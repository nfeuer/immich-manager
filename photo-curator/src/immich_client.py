"""
Immich API client for fetching photos and managing albums
"""

import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path
import logging
import tempfile
import os

logger = logging.getLogger(__name__)


class ImmichClient:
    """Client for interacting with Immich API"""

    def __init__(self, api_url: str, api_key: str):
        """
        Initialize Immich API client

        Args:
            api_url: Immich API base URL (e.g., http://localhost:2283/api)
            api_key: Immich API key
        """
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'x-api-key': api_key,
            'Accept': 'application/json'
        })

    def get_users(self) -> List[Dict[str, Any]]:
        """
        Get list of all users

        Returns:
            List of user dictionaries
        """
        try:
            response = self.session.get(f"{self.api_url}/users")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching users: {e}")
            return []

    def get_user_photos(
        self,
        user_id: str,
        year: int,
        month: int
    ) -> List[Dict[str, Any]]:
        """
        Get all photos for a user in a specific month

        Args:
            user_id: User ID
            year: Year (e.g., 2024)
            month: Month (1-12)

        Returns:
            List of photo dictionaries
        """
        try:
            # Calculate date range
            start_date = datetime(year, month, 1)

            # Calculate last day of month
            if month == 12:
                end_date = datetime(year + 1, 1, 1)
            else:
                end_date = datetime(year, month + 1, 1)

            # Format dates for API
            start_str = start_date.isoformat() + 'Z'
            end_str = end_date.isoformat() + 'Z'

            # Search for photos
            search_payload = {
                'takenAfter': start_str,
                'takenBefore': end_str,
                'userId': user_id,
                'type': 'IMAGE',
                'size': 10000  # Max results
            }

            response = self.session.post(
                f"{self.api_url}/search/metadata",
                json=search_payload
            )
            response.raise_for_status()

            data = response.json()
            assets = data.get('assets', {}).get('items', [])

            logger.info(f"Found {len(assets)} photos for user {user_id} in {year}-{month:02d}")

            return assets

        except Exception as e:
            logger.error(f"Error fetching photos: {e}")
            return []

    def get_asset_info(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about an asset

        Args:
            asset_id: Asset ID

        Returns:
            Asset information dictionary or None
        """
        try:
            response = self.session.get(f"{self.api_url}/assets/{asset_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching asset {asset_id}: {e}")
            return None

    def download_photo(
        self,
        asset_id: str,
        download_dir: Optional[str] = None,
        use_thumbnail: bool = True
    ) -> Optional[str]:
        """
        Download a photo for analysis

        Args:
            asset_id: Asset ID
            download_dir: Directory to save to (defaults to temp)
            use_thumbnail: Use thumbnail instead of full resolution

        Returns:
            Path to downloaded file or None
        """
        try:
            if download_dir is None:
                download_dir = tempfile.gettempdir()

            # Construct download URL
            if use_thumbnail:
                url = f"{self.api_url}/assets/{asset_id}/thumbnail"
            else:
                url = f"{self.api_url}/assets/{asset_id}/original"

            response = self.session.get(url, stream=True)
            response.raise_for_status()

            # Determine file extension
            content_type = response.headers.get('content-type', '')
            if 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            elif 'png' in content_type:
                ext = '.png'
            elif 'heic' in content_type:
                ext = '.heic'
            else:
                ext = '.jpg'

            # Save to file
            file_path = os.path.join(download_dir, f"{asset_id}{ext}")

            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.debug(f"Downloaded {asset_id} to {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Error downloading asset {asset_id}: {e}")
            return None

    def create_album(
        self,
        album_name: str,
        asset_ids: List[str],
        description: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new album with specified assets

        Args:
            album_name: Name of the album
            asset_ids: List of asset IDs to include
            description: Optional album description

        Returns:
            Album information dictionary or None
        """
        try:
            # Create album
            create_payload = {
                'albumName': album_name,
                'assetIds': asset_ids
            }

            if description:
                create_payload['description'] = description

            response = self.session.post(
                f"{self.api_url}/albums",
                json=create_payload
            )
            response.raise_for_status()

            album = response.json()
            logger.info(f"Created album '{album_name}' with {len(asset_ids)} photos")

            return album

        except Exception as e:
            logger.error(f"Error creating album: {e}")
            return None

    def get_user_albums(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all albums for a user

        Args:
            user_id: User ID

        Returns:
            List of album dictionaries
        """
        try:
            response = self.session.get(f"{self.api_url}/albums")
            response.raise_for_status()

            all_albums = response.json()

            # Filter by user
            user_albums = [
                album for album in all_albums
                if album.get('ownerId') == user_id
            ]

            return user_albums

        except Exception as e:
            logger.error(f"Error fetching albums: {e}")
            return []

    def add_assets_to_album(
        self,
        album_id: str,
        asset_ids: List[str]
    ) -> bool:
        """
        Add assets to existing album

        Args:
            album_id: Album ID
            asset_ids: List of asset IDs to add

        Returns:
            True if successful
        """
        try:
            payload = {
                'ids': asset_ids
            }

            response = self.session.put(
                f"{self.api_url}/albums/{album_id}/assets",
                json=payload
            )
            response.raise_for_status()

            logger.info(f"Added {len(asset_ids)} assets to album {album_id}")
            return True

        except Exception as e:
            logger.error(f"Error adding assets to album: {e}")
            return False

    def get_user_statistics(self, user_id: str) -> Dict[str, Any]:
        """
        Get statistics for a user

        Args:
            user_id: User ID

        Returns:
            Dictionary with statistics
        """
        try:
            response = self.session.get(
                f"{self.api_url}/server-info/statistics"
            )
            response.raise_for_status()

            stats = response.json()

            # Filter for user
            user_stats = next(
                (s for s in stats.get('usageByUser', []) if s['userId'] == user_id),
                {}
            )

            return user_stats

        except Exception as e:
            logger.error(f"Error fetching statistics: {e}")
            return {}

    def get_thumbnail_url(self, asset_id: str) -> str:
        """
        Get proxied thumbnail URL for an asset.
        Routes through the curator backend so tokens are not exposed to the browser.

        Args:
            asset_id: Asset ID

        Returns:
            Proxied thumbnail URL (no token in URL)
        """
        return f"/api/thumbnail/{asset_id}"

    def check_connection(self) -> bool:
        """
        Check if API connection is working

        Returns:
            True if connected
        """
        try:
            response = self.session.get(f"{self.api_url}/server-info/ping")
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False


class PhotoCache:
    """Manages local cache of downloaded photos"""

    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize photo cache

        Args:
            cache_dir: Directory for cache (defaults to temp)
        """
        if cache_dir is None:
            cache_dir = os.path.join(tempfile.gettempdir(), 'immich-curator-cache')

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cached_path(self, asset_id: str) -> Optional[str]:
        """
        Get cached photo path if exists

        Args:
            asset_id: Asset ID

        Returns:
            Path to cached file or None
        """
        # Check for any file with this asset ID
        for ext in ['.jpg', '.jpeg', '.png', '.heic']:
            path = self.cache_dir / f"{asset_id}{ext}"
            if path.exists():
                return str(path)

        return None

    def add_to_cache(self, asset_id: str, source_path: str) -> str:
        """
        Add photo to cache

        Args:
            asset_id: Asset ID
            source_path: Source file path

        Returns:
            Path to cached file
        """
        ext = Path(source_path).suffix
        dest_path = self.cache_dir / f"{asset_id}{ext}"

        # Copy to cache
        import shutil
        shutil.copy2(source_path, dest_path)

        return str(dest_path)

    def clear_cache(self, max_age_days: int = 7):
        """
        Clear old cache files

        Args:
            max_age_days: Maximum age in days
        """
        import time

        cutoff_time = time.time() - (max_age_days * 86400)

        for file_path in self.cache_dir.glob("*"):
            if file_path.is_file():
                if file_path.stat().st_mtime < cutoff_time:
                    file_path.unlink()
                    logger.debug(f"Removed old cache file: {file_path}")

    def get_cache_size(self) -> int:
        """
        Get total cache size in bytes

        Returns:
            Cache size in bytes
        """
        total_size = 0

        for file_path in self.cache_dir.glob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size

        return total_size
