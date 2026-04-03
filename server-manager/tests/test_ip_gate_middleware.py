# server-manager/tests/test_ip_gate_middleware.py
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ip_gate_middleware import get_client_ip, is_exempt_path


def test_get_client_ip_direct():
    request = MagicMock()
    request.client.host = "1.2.3.4"
    request.headers = {}
    assert get_client_ip(request, trusted_proxies=[]) == "1.2.3.4"


def test_get_client_ip_behind_trusted_proxy():
    request = MagicMock()
    request.client.host = "172.17.0.1"
    request.headers = {"x-forwarded-for": "98.45.12.3, 172.17.0.1"}
    assert get_client_ip(request, trusted_proxies=["172.17.0.1"]) == "98.45.12.3"


def test_get_client_ip_untrusted_proxy():
    request = MagicMock()
    request.client.host = "10.0.0.5"
    request.headers = {"x-forwarded-for": "1.2.3.4"}
    assert get_client_ip(request, trusted_proxies=["172.17.0.1"]) == "10.0.0.5"


def test_exempt_paths():
    assert is_exempt_path("/api/ip-gate/verify/abc123")
    assert is_exempt_path("/api/ip-gate/status")
    assert is_exempt_path("/api/ip-gate/challenge")
    assert is_exempt_path("/health")
    assert not is_exempt_path("/api/status")
    assert not is_exempt_path("/api/disks")
