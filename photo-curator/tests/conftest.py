"""Shared test fixtures for photo-curator tests."""
import pytest
from unittest.mock import MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.main import app
from src.auth import ImmichAuth


@pytest.fixture(autouse=True)
def setup_app_state():
    """Set required app.state values for tests without a live Immich instance."""
    app.state.immich_api_url = "http://localhost:2283/api"
    app.state.immich_auth = MagicMock(spec=ImmichAuth)
    # Simulate unauthenticated requests by default (returns None)
    app.state.immich_auth.get_user_from_request.return_value = None
    app.state.immich_auth.login_redirect_url.return_value = "http://localhost:2283/auth/login"
    app.state.database = None
    yield
    # Cleanup overrides after each test
    app.dependency_overrides = {}
