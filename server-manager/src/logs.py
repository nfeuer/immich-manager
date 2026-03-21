"""
Log fetching for server-manager services.

Supports Docker containers and systemd journal services.
"""

import logging
import subprocess
from typing import Generator, List

import docker
from .utils import CLEAN_ENV

logger = logging.getLogger(__name__)

# Map service names to Docker container name filters or journalctl unit names
_DOCKER_SERVICES = {
    "immich_server",
    "immich_machine_learning",
    "immich_postgres",
    "immich_redis",
}

_JOURNALCTL_UNITS = {
    "server_manager": "immich-server-manager",
    "photo_curator": "photo-curator",
}


def _container_name(service: str) -> str:
    """Convert service key to Docker container name (underscore → hyphen prefix match)."""
    return service.replace("_", "-")


def get_log_snapshot(service: str, lines: int = 200) -> List[str]:
    """Return the last `lines` log lines for the given service."""
    if service in _DOCKER_SERVICES:
        return _docker_snapshot(service, lines)
    if service in _JOURNALCTL_UNITS:
        return _journal_snapshot(_JOURNALCTL_UNITS[service], lines)
    if service == "system":
        return _journal_snapshot(None, lines)
    logger.warning("Unknown log service requested: %s", service)
    return []


def stream_log_lines(service: str) -> Generator[str, None, None]:
    """Yield new log lines indefinitely for the given service."""
    if service in _DOCKER_SERVICES:
        yield from _docker_stream(service)
    elif service in _JOURNALCTL_UNITS:
        yield from _journal_stream(_JOURNALCTL_UNITS[service])
    elif service == "system":
        yield from _journal_stream(None)
    else:
        logger.warning("Unknown log service stream requested: %s", service)


# --- Docker helpers ---

def _docker_snapshot(service: str, lines: int) -> List[str]:
    try:
        client = docker.from_env()
        name_filter = _container_name(service)
        matches = client.containers.list(filters={"name": name_filter})
        if not matches:
            logger.warning("No Docker container matching '%s' found", name_filter)
            return []
        container = matches[0]
        raw = container.logs(tail=lines, stream=False)
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        return text.splitlines()
    except Exception as exc:
        logger.warning("Docker log snapshot failed for %s: %s", service, exc)
        return []


def _docker_stream(service: str) -> Generator[str, None, None]:
    try:
        client = docker.from_env()
        name_filter = _container_name(service)
        matches = client.containers.list(filters={"name": name_filter})
        if not matches:
            logger.warning("No Docker container matching '%s' found for streaming", name_filter)
            return
        container = matches[0]
        for chunk in container.logs(stream=True, follow=True):
            line = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk
            yield line.rstrip("\n")
    except Exception as exc:
        logger.warning("Docker log stream failed for %s: %s", service, exc)


# --- Journalctl helpers ---

def _journal_snapshot(unit: str | None, lines: int) -> List[str]:
    cmd = ["journalctl", "-n", str(lines), "--no-pager", "--output=short"]
    if unit:
        cmd += ["-u", unit]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=CLEAN_ENV)
        return result.stdout.splitlines()
    except Exception as exc:
        logger.warning("journalctl snapshot failed (unit=%s): %s", unit, exc)
        return []


def _journal_stream(unit: str | None) -> Generator[str, None, None]:
    cmd = ["journalctl", "-f", "--no-pager", "--output=short"]
    if unit:
        cmd += ["-u", unit]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=CLEAN_ENV)
        for line in proc.stdout:
            yield line.rstrip("\n")
    except Exception as exc:
        logger.warning("journalctl stream failed (unit=%s): %s", unit, exc)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
