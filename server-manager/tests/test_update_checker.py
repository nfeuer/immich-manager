from unittest.mock import MagicMock, patch
import pytest
from src.update_checker import UpdateChecker


def _make_checker(api_url="http://localhost:2283/api"):
    docker_monitor = MagicMock()
    docker_monitor.get_immich_containers.return_value = []
    return UpdateChecker(docker_monitor, immich_api_url=api_url)


def test_get_version_from_immich_api_success():
    checker = _make_checker()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"major": 1, "minor": 126, "patch": 1}
    with patch("src.update_checker.requests.get", return_value=mock_resp):
        result = checker._get_version_from_immich_api()
    assert result == "1.126.1"


def test_get_version_from_immich_api_connection_error():
    import requests
    checker = _make_checker()
    with patch("src.update_checker.requests.get", side_effect=requests.exceptions.ConnectionError()):
        result = checker._get_version_from_immich_api()
    assert result is None


def test_get_version_from_immich_api_non_200():
    checker = _make_checker()
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.raise_for_status.side_effect = Exception("503")
    with patch("src.update_checker.requests.get", return_value=mock_resp):
        result = checker._get_version_from_immich_api()
    assert result is None


def test_get_running_version_with_reachability_api_success():
    checker = _make_checker()
    with patch.object(checker, "_get_version_from_immich_api", return_value="1.126.1"):
        version, reachable = checker.get_running_version_with_reachability()
    assert version == "1.126.1"
    assert reachable is True


def test_get_running_version_with_reachability_api_fails_docker_fallback():
    checker = _make_checker()
    with patch.object(checker, "_get_version_from_immich_api", return_value=None):
        with patch.object(checker, "get_running_version", return_value="1.120.0"):
            version, reachable = checker.get_running_version_with_reachability()
    assert version == "1.120.0"
    assert reachable is False


def test_get_running_version_with_reachability_both_fail():
    checker = _make_checker()
    with patch.object(checker, "_get_version_from_immich_api", return_value=None):
        with patch.object(checker, "get_running_version", return_value=None):
            version, reachable = checker.get_running_version_with_reachability()
    assert version is None
    assert reachable is False


def test_check_for_update_uses_api_version():
    """check_for_update must use get_running_version_with_reachability so it works with release tag."""
    checker = _make_checker()
    with patch.object(checker, "get_running_version_with_reachability", return_value=("1.120.0", True)):
        with patch.object(checker, "get_latest_github_version", return_value="1.126.1"):
            result = checker.check_for_update()
    assert result is not None
    assert result["running_version"] == "1.120.0"
    assert result["latest_version"] == "1.126.1"
