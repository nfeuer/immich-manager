import pytest
from unittest.mock import patch, MagicMock
from src.config import Config, ServerConfig, ImmichConfig


def _make_cfg(public_url="", port=8080, api_url="http://localhost:2283/api"):
    data = {"server": {"port": port, "public_url": public_url}, "immich": {"api_url": api_url}}
    return Config(**data)


def test_allowed_origins_includes_localhost(monkeypatch):
    from src.main import _get_allowed_origins
    monkeypatch.setattr("src.main.load_config", lambda: _make_cfg())
    origins = _get_allowed_origins()
    assert "http://localhost:8080" in origins
    assert "http://127.0.0.1:8080" in origins


def test_allowed_origins_includes_immich_base_url(monkeypatch):
    from src.main import _get_allowed_origins
    monkeypatch.setattr("src.main.load_config", lambda: _make_cfg())
    origins = _get_allowed_origins()
    assert "http://localhost:2283" in origins


def test_allowed_origins_includes_public_url_when_set(monkeypatch):
    from src.main import _get_allowed_origins
    monkeypatch.setattr("src.main.load_config",
                        lambda: _make_cfg(public_url="https://monitor.houseoffeuer.com"))
    origins = _get_allowed_origins()
    assert "https://monitor.houseoffeuer.com" in origins


def test_allowed_origins_omits_empty_public_url(monkeypatch):
    from src.main import _get_allowed_origins
    monkeypatch.setattr("src.main.load_config", lambda: _make_cfg(public_url=""))
    origins = _get_allowed_origins()
    assert "" not in origins
