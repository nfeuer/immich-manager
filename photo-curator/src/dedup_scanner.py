"""
Standalone duplicate scanner for Immich photos.
Manages both Quick Scan (Immich native) and Deep Scan (pHash) modes.
One scan job runs at a time; state is tracked via the dedup_scans DB table.
"""
import asyncio
import logging
import os
import tempfile
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DedupScanner:
    """
    Module-level singleton that manages dedup scan jobs.
    Initialized at app startup with just the database.
    Each scan receives a user-scoped ImmichClient at call time.
    """

    def __init__(self, database, config: Optional[Dict] = None):
        self._db = database
        self._config = config or {}
        self._current_task: Optional[asyncio.Task] = None
        self._current_scan_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        return self._current_task is not None and not self._current_task.done()

    def current_scan_id(self) -> Optional[str]:
        return self._current_scan_id

    async def estimate(
        self, user_id: str, date_from: str, date_to: str, immich_client
    ) -> Dict:
        assets = await asyncio.to_thread(
            self._fetch_assets_paginated, immich_client, date_from, date_to
        )
        total = len(assets)
        if total == 0:
            return {'total_assets': 0, 'needs_hashing': 0, 'estimated_seconds': 0, 'warning': False}

        asset_ids = [a['id'] for a in assets]
        needs_hashing = await asyncio.to_thread(self._count_needs_hashing, asset_ids)
        rate = self._config.get('hash_rate_per_second', 1.0 / 0.3)
        estimated_seconds = int(needs_hashing / rate) if rate > 0 else 0
        return {
            'total_assets': total,
            'needs_hashing': needs_hashing,
            'estimated_seconds': estimated_seconds,
            'warning': needs_hashing > 500,
        }

    async def start_deep_scan(
        self, user_id: str, date_from: str, date_to: str, immich_client
    ) -> str:
        if self.is_running():
            raise RuntimeError(f"scan_already_running:{self._current_scan_id}")
        scan_id = str(uuid.uuid4())
        self._db.create_dedup_scan(scan_id, user_id, 'deep', date_from=date_from, date_to=date_to)
        self._current_scan_id = scan_id
        self._current_task = asyncio.create_task(
            self._run_deep(scan_id, user_id, date_from, date_to, immich_client)
        )
        return scan_id

    async def start_quick_scan(self, user_id: str, immich_client) -> str:
        if self.is_running():
            raise RuntimeError(f"scan_already_running:{self._current_scan_id}")
        scan_id = str(uuid.uuid4())
        self._db.create_dedup_scan(scan_id, user_id, 'quick')
        self._current_scan_id = scan_id
        self._current_task = asyncio.create_task(
            self._run_quick(scan_id, user_id, immich_client)
        )
        return scan_id

    async def cancel(self) -> bool:
        if not self._current_scan_id:
            return False
        self._db.update_dedup_scan(self._current_scan_id, status='cancelled')
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
        return True

    # ------------------------------------------------------------------
    # Pure static helpers (tested in isolation)
    # ------------------------------------------------------------------

    @staticmethod
    def find_duplicate_groups(
        hashes: Dict[str, str], threshold: int = 5
    ) -> List[List[str]]:
        """Given {asset_id: phash_hex_str}, return groups of near-duplicates."""
        import imagehash
        asset_ids = list(hashes.keys())
        hash_objs = {}
        for aid, h in hashes.items():
            if h:
                try:
                    hash_objs[aid] = imagehash.hex_to_hash(h)
                except Exception:
                    pass

        processed: set = set()
        groups: List[List[str]] = []
        for i, aid1 in enumerate(asset_ids):
            if aid1 in processed or aid1 not in hash_objs:
                continue
            group = [aid1]
            for aid2 in asset_ids[i + 1:]:
                if aid2 in processed or aid2 not in hash_objs:
                    continue
                if (hash_objs[aid1] - hash_objs[aid2]) <= threshold:
                    group.append(aid2)
                    processed.add(aid2)
            if len(group) > 1:
                groups.append(group)
                processed.add(aid1)
        return groups

    @staticmethod
    def _score_asset(meta: Dict) -> int:
        w = meta.get('width') or 0
        h = meta.get('height') or 0
        size = meta.get('file_size_bytes') or 0
        return w * h * 1000 + size

    @staticmethod
    def _compute_recommended_keep(
        asset_ids: List[str], meta_map: Dict[str, Dict]
    ) -> str:
        scored = [(aid, DedupScanner._score_asset(meta_map.get(aid, {}))) for aid in asset_ids]
        return max(scored, key=lambda x: x[1])[0]

    @staticmethod
    def _asset_to_meta(asset: Dict) -> Dict:
        exif = asset.get('exifInfo') or {}
        return {
            'width': exif.get('exifImageWidth'),
            'height': exif.get('exifImageHeight'),
            'file_size_bytes': exif.get('fileSizeInByte'),
            'filename': asset.get('originalFileName'),
            'date_taken': asset.get('fileCreatedAt'),
            'camera_make': exif.get('make'),
            'camera_model': exif.get('model'),
        }

    @staticmethod
    def derive_phase(
        status: str, hashed: int, total_assets: int
    ) -> Optional[str]:
        if status != 'running':
            return None
        if total_assets == 0 or hashed < total_assets:
            return 'hashing'
        return 'comparing'

    # ------------------------------------------------------------------
    # Private: I/O helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_assets_paginated(immich_client, date_from: str, date_to: str) -> List[Dict]:
        assets: List[Dict] = []
        page = None
        while True:
            payload: Dict[str, Any] = {
                'takenAfter': f"{date_from}T00:00:00.000Z",
                'takenBefore': f"{date_to}T23:59:59.999Z",
                'type': 'IMAGE',
                'size': 1000,
                'withExif': True,
            }
            if page:
                payload['page'] = page
            resp = immich_client.session.post(
                f"{immich_client.api_url}/search/metadata", json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get('assets', {}).get('items', [])
            assets.extend(items)
            next_page = data.get('assets', {}).get('nextPage')
            if not next_page:
                break
            page = next_page
        return assets

    def _count_needs_hashing(self, asset_ids: List[str]) -> int:
        if not asset_ids:
            return 0
        with self._db._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(asset_ids))
            cursor.execute(
                f"SELECT COUNT(*) as cnt FROM photo_scores "
                f"WHERE asset_id IN ({placeholders}) AND perceptual_hash IS NOT NULL",
                asset_ids,
            )
            hashed_count = cursor.fetchone()['cnt']
        return len(asset_ids) - hashed_count

    def _get_existing_hash(self, asset_id: str) -> Optional[str]:
        with self._db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT perceptual_hash FROM photo_scores WHERE asset_id = ? AND perceptual_hash IS NOT NULL LIMIT 1",
                (asset_id,),
            )
            row = cursor.fetchone()
            return row['perceptual_hash'] if row else None

    @staticmethod
    def _download_and_hash(asset_id: str, immich_client) -> Optional[str]:
        from PIL import Image
        import imagehash
        tmp_path = None
        try:
            resp = immich_client.session.get(
                f"{immich_client.api_url}/assets/{asset_id}/thumbnail", timeout=30
            )
            resp.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
                f.write(resp.content)
                tmp_path = f.name
            img = Image.open(tmp_path)
            return str(imagehash.phash(img))
        except Exception as e:
            logger.warning(f"Failed to hash {asset_id}: {e}")
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ------------------------------------------------------------------
    # Private: scan runners
    # ------------------------------------------------------------------

    async def _run_deep(
        self, scan_id: str, user_id: str, date_from: str, date_to: str, immich_client
    ) -> None:
        try:
            assets = await asyncio.to_thread(
                self._fetch_assets_paginated, immich_client, date_from, date_to
            )
            self._db.update_dedup_scan(scan_id, total_assets=len(assets))

            BATCH_SIZE = 25
            hashes: Dict[str, str] = {}

            for i in range(0, len(assets), BATCH_SIZE):
                # Cancellation check
                scan_row = self._db.get_dedup_scan_status(user_id)
                if scan_row and scan_row.get('status') == 'cancelled':
                    return

                batch = assets[i: i + BATCH_SIZE]
                for asset in batch:
                    asset_id = asset['id']
                    self._db.upsert_dedup_asset_metadata(user_id, asset)

                    existing = await asyncio.to_thread(self._get_existing_hash, asset_id)
                    if existing:
                        hashes[asset_id] = existing
                    else:
                        phash = await asyncio.to_thread(
                            self._download_and_hash, asset_id, immich_client
                        )
                        if phash:
                            hashes[asset_id] = phash
                            # Derive year/month from fileCreatedAt for DB storage
                            created_at = asset.get('fileCreatedAt', '')
                            try:
                                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                                year, month = dt.year, dt.month
                            except Exception:
                                year, month = 1970, 1
                            await asyncio.to_thread(
                                self._db.upsert_perceptual_hash, asset_id, user_id, year, month, phash
                            )

                processed = min(i + BATCH_SIZE, len(assets))
                self._db.update_dedup_scan(scan_id, hashed=processed)
                await asyncio.sleep(0.5)

            # Mark hashing complete (hashed == total_assets → comparing phase)
            self._db.update_dedup_scan(scan_id, hashed=len(assets))

            groups = await asyncio.to_thread(self.find_duplicate_groups, hashes)
            asset_meta_map = {a['id']: self._asset_to_meta(a) for a in assets}

            for group_ids in groups:
                recommended = self._compute_recommended_keep(group_ids, asset_meta_map)
                group_hash = str(hash(tuple(sorted(group_ids))))
                self._db.save_dedup_group(scan_id, user_id, group_ids, recommended, group_hash)

            self._db.update_dedup_scan(scan_id, status='complete', groups_found=len(groups))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Deep scan error: {e}", exc_info=True)
            self._db.update_dedup_scan(scan_id, status='failed', error_message=str(e))

    async def _run_quick(self, scan_id: str, user_id: str, immich_client) -> None:
        try:
            resp = await asyncio.to_thread(
                lambda: immich_client.session.get(f"{immich_client.api_url}/duplicates")
            )
            if not resp.ok:
                self._db.update_dedup_scan(
                    scan_id, status='failed',
                    error_message=f"immich_unavailable:{resp.status_code}"
                )
                return

            groups_data = resp.json()
            saved_count = 0
            for group_data in groups_data:
                asset_ids = [a['id'] for a in group_data.get('assets', [])]
                if len(asset_ids) < 2:
                    continue
                for asset in group_data['assets']:
                    self._db.upsert_dedup_asset_metadata(user_id, asset)
                asset_meta_map = {a['id']: self._asset_to_meta(a) for a in group_data['assets']}
                recommended = self._compute_recommended_keep(asset_ids, asset_meta_map)
                group_hash = str(hash(tuple(sorted(asset_ids))))
                self._db.save_dedup_group(scan_id, user_id, asset_ids, recommended, group_hash)
                saved_count += 1

            self._db.update_dedup_scan(
                scan_id, status='complete', groups_found=saved_count
            )

        except Exception as e:
            logger.error(f"Quick scan error: {e}", exc_info=True)
            self._db.update_dedup_scan(scan_id, status='failed', error_message=str(e))
