"""Tests for DedupScanner pure logic (no Immich I/O)."""
import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.dedup_scanner import DedupScanner


def test_find_duplicate_groups_groups_near_duplicates():
    """Assets with Hamming distance <= 5 should be grouped together."""
    # Identical hashes → distance 0 → duplicate
    hashes = {
        'a1': 'aaaaaaaaaaaaaaaa',
        'a2': 'aaaaaaaaaaaaaaaa',
        'a3': 'ffffffffffffffff',  # totally different
    }
    groups = DedupScanner.find_duplicate_groups(hashes, threshold=5)
    assert len(groups) == 1
    assert set(groups[0]) == {'a1', 'a2'}


def test_find_duplicate_groups_returns_empty_when_no_duplicates():
    hashes = {
        'a1': 'aaaaaaaaaaaaaaaa',
        'a2': 'ffffffffffffffff',
    }
    groups = DedupScanner.find_duplicate_groups(hashes, threshold=5)
    assert groups == []


def test_find_duplicate_groups_handles_empty_input():
    assert DedupScanner.find_duplicate_groups({}) == []


def test_compute_recommended_keep_prefers_higher_resolution():
    meta_map = {
        'low-res': {'width': 800, 'height': 600, 'file_size_bytes': 500_000},
        'high-res': {'width': 4032, 'height': 3024, 'file_size_bytes': 4_200_000},
    }
    keep = DedupScanner._compute_recommended_keep(['low-res', 'high-res'], meta_map)
    assert keep == 'high-res'


def test_compute_recommended_keep_tiebreaks_by_file_size():
    meta_map = {
        'same-res-small': {'width': 1920, 'height': 1080, 'file_size_bytes': 1_000_000},
        'same-res-large': {'width': 1920, 'height': 1080, 'file_size_bytes': 3_000_000},
    }
    keep = DedupScanner._compute_recommended_keep(
        ['same-res-small', 'same-res-large'], meta_map
    )
    assert keep == 'same-res-large'


def test_compute_recommended_keep_handles_missing_metadata():
    """Falls back gracefully when metadata is absent."""
    meta_map = {'a1': {}, 'a2': {'width': 1920, 'height': 1080, 'file_size_bytes': 2_000_000}}
    keep = DedupScanner._compute_recommended_keep(['a1', 'a2'], meta_map)
    assert keep == 'a2'


def test_asset_to_meta_extracts_correct_fields():
    asset = {
        'id': 'x1',
        'originalFileName': 'test.jpg',
        'fileCreatedAt': '2024-01-01T00:00:00Z',
        'exifInfo': {
            'exifImageWidth': 3000,
            'exifImageHeight': 2000,
            'fileSizeInByte': 2_500_000,
            'make': 'Canon',
            'model': 'EOS R5',
        },
    }
    meta = DedupScanner._asset_to_meta(asset)
    assert meta['width'] == 3000
    assert meta['height'] == 2000
    assert meta['file_size_bytes'] == 2_500_000
    assert meta['camera_make'] == 'Canon'
    assert meta['camera_model'] == 'EOS R5'
    assert meta['filename'] == 'test.jpg'


def test_derive_phase_hashing():
    assert DedupScanner.derive_phase('running', hashed=10, total_assets=100) == 'hashing'


def test_derive_phase_comparing():
    assert DedupScanner.derive_phase('running', hashed=100, total_assets=100) == 'comparing'


def test_derive_phase_null_when_not_running():
    assert DedupScanner.derive_phase('complete', hashed=100, total_assets=100) is None
    assert DedupScanner.derive_phase('idle', hashed=0, total_assets=0) is None
