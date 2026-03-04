"""Smoke tests to verify basic project imports and structure."""
import sys
import os

# Add source directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server-manager', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'photo-curator', 'src'))


def test_server_manager_config_imports():
    """Verify server-manager config module is importable."""
    import config  # noqa: F401


def test_server_manager_logging_imports():
    """Verify server-manager logging_config module is importable."""
    import logging_config  # noqa: F401


def test_photo_curator_logging_imports():
    """Verify photo-curator logging_config module is importable."""
    # Reset to only photo-curator src on path to avoid collision
    import importlib
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "photo_curator_logging",
        os.path.join(os.path.dirname(__file__), '..', 'photo-curator', 'src', 'logging_config.py')
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod is not None
