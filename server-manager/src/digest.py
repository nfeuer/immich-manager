"""
Scheduled Discord digest builder.

Gathers system health, storage, backup, container, and alert data
into a structured set of Discord embed fields.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# Discord embed colours
COLOR_HEALTHY = 0x2ECC71   # green
COLOR_WARNING = 0xFFAA00   # amber

_MAX_STORAGE_FIELDS = 8


async def build_digest(
    database,
    system_monitor,
    disk_monitor,
    docker_monitor,
    config,
    sections: List[str],
) -> Tuple[str, str, List[Dict[str, Any]], int]:
    """
    Gather data from all requested sections and return the parts needed
    to send a Discord digest embed.

    Returns:
        (title, description, fields, color)
    """
    server_name = ""
    if config and config.alerts and config.alerts.discord:
        server_name = config.alerts.discord.server_name

    title = f"Server Digest — {server_name}" if server_name else "Server Digest"
    description = f"Summary for {datetime.now().strftime('%A, %B %-d, %Y')}"
    fields: List[Dict[str, Any]] = []
    has_warning = False

    for section in sections:
        try:
            if section == "system":
                _fields = await _build_system_section(system_monitor)
                fields.extend(_fields)

            elif section == "storage":
                _fields, warn = _build_storage_section(database)
                fields.extend(_fields)
                has_warning = has_warning or warn

            elif section == "backups":
                _fields, warn = _build_backups_section(database)
                fields.extend(_fields)
                has_warning = has_warning or warn

            elif section == "containers":
                _fields, warn = await _build_containers_section(docker_monitor)
                fields.extend(_fields)
                has_warning = has_warning or warn

            elif section == "alerts":
                _fields, warn = _build_alerts_section(database)
                fields.extend(_fields)
                has_warning = has_warning or warn

        except Exception as e:
            logger.error(f"Digest section '{section}' failed: {e}")
            fields.append({
                "name": section.capitalize(),
                "value": f"Error gathering data: {e}",
                "inline": False,
            })

    color = COLOR_WARNING if has_warning else COLOR_HEALTHY
    return title, description, fields, color


# ------------------------------------------------------------------
# Section builders
# ------------------------------------------------------------------

async def _build_system_section(system_monitor) -> List[Dict[str, Any]]:
    """CPU, memory, and disk usage as 3 inline fields."""
    if not system_monitor:
        return [{"name": "System", "value": "Monitor not available", "inline": False}]

    metrics = await asyncio.to_thread(system_monitor.get_all_metrics)

    return [
        {
            "name": "CPU",
            "value": f"{metrics.get('cpu_percent', 0):.1f}%",
            "inline": True,
        },
        {
            "name": "Memory",
            "value": (
                f"{metrics.get('memory_used_gb', 0):.1f} / "
                f"{metrics.get('memory_total_gb', 0):.1f} GB "
                f"({metrics.get('memory_percent', 0):.1f}%)"
            ),
            "inline": True,
        },
        {
            "name": "Disk",
            "value": (
                f"{metrics.get('disk_used_gb', 0):.1f} / "
                f"{metrics.get('disk_total_gb', 0):.1f} GB "
                f"({metrics.get('disk_usage_percent', 0):.1f}%)"
            ),
            "inline": True,
        },
    ]


def _build_storage_section(database) -> Tuple[List[Dict[str, Any]], bool]:
    """Per-device SMART status as inline fields."""
    if not database:
        return [{"name": "Storage", "value": "Database not available", "inline": False}], False

    disks = database.get_latest_disk_health()
    if not disks:
        return [{"name": "Storage", "value": "No disk data available", "inline": False}], False

    fields: List[Dict[str, Any]] = []
    has_warning = False

    for disk in disks[:_MAX_STORAGE_FIELDS]:
        device = disk.get("device", "unknown")
        smart = disk.get("smart_status", "unknown")
        temp = disk.get("temperature")
        hours = disk.get("power_on_hours")

        smart_label = "PASSED" if smart in (True, "PASSED", 1) else "FAILED"
        if smart_label == "FAILED":
            has_warning = True

        parts = [f"SMART: {smart_label}"]
        if temp is not None:
            parts.append(f"Temp: {temp}\u00b0C")
        if hours is not None:
            parts.append(f"Hours: {hours:,}")

        fields.append({
            "name": device,
            "value": " | ".join(parts),
            "inline": True,
        })

    remaining = len(disks) - _MAX_STORAGE_FIELDS
    if remaining > 0:
        fields.append({
            "name": "More drives",
            "value": f"...and {remaining} more drive(s)",
            "inline": True,
        })

    return fields, has_warning


def _build_backups_section(database) -> Tuple[List[Dict[str, Any]], bool]:
    """Recent backup history as a single full-width field."""
    if not database:
        return [{"name": "Backups", "value": "Database not available", "inline": False}], False

    backups = database.get_recent_backups(limit=5)
    if not backups:
        return [{"name": "Recent Backups", "value": "No backups recorded", "inline": False}], False

    has_warning = False
    lines = []
    for b in backups:
        ts = b.get("timestamp", "—")
        if isinstance(ts, str) and len(ts) > 16:
            ts = ts[:16]  # trim to YYYY-MM-DD HH:MM
        btype = b.get("backup_type", "—")
        status = b.get("status", "—")
        size_bytes = b.get("size_bytes")
        size_str = f"{size_bytes / 1_048_576:.0f} MB" if size_bytes else "—"
        duration = b.get("duration_seconds")
        dur_str = f"{duration:.0f}s" if duration else "—"

        icon = "\u2705" if status == "success" else "\u274c"
        if status != "success":
            has_warning = True

        lines.append(f"{icon} {ts} | {btype} | {status} | {size_str} | {dur_str}")

    return [{
        "name": "Recent Backups",
        "value": "\n".join(lines),
        "inline": False,
    }], has_warning


async def _build_containers_section(
    docker_monitor,
) -> Tuple[List[Dict[str, Any]], bool]:
    """Immich container status as a single full-width field."""
    if not docker_monitor:
        return [{"name": "Containers", "value": "Docker monitor not available", "inline": False}], False

    containers = await asyncio.to_thread(docker_monitor.get_immich_containers)
    if not containers:
        return [{"name": "Immich Containers", "value": "No containers found", "inline": False}], False

    has_warning = False
    lines = []
    for c in containers:
        name = c.get("name", "unknown")
        status = c.get("status", "unknown")
        running = status == "running"
        icon = "\u2705" if running else "\u274c"
        if not running:
            has_warning = True
        lines.append(f"{icon} {name}: {status}")

    return [{
        "name": "Immich Containers",
        "value": "\n".join(lines),
        "inline": False,
    }], has_warning


def _build_alerts_section(database) -> Tuple[List[Dict[str, Any]], bool]:
    """Count of unacknowledged alerts by severity."""
    if not database:
        return [{"name": "Alerts", "value": "Database not available", "inline": False}], False

    alerts = database.get_alerts(acknowledged=False, limit=200)

    # Filter to last 24 hours
    cutoff = datetime.now() - timedelta(hours=24)
    recent = []
    for a in alerts:
        ts_str = a.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts >= cutoff:
                recent.append(a)
        except (ValueError, TypeError):
            recent.append(a)  # include if timestamp unparseable

    if not recent:
        return [{
            "name": "Alerts (24h)",
            "value": "No unacknowledged alerts",
            "inline": True,
        }], False

    counts: Dict[str, int] = {}
    for a in recent:
        sev = a.get("severity", "info")
        counts[sev] = counts.get(sev, 0) + 1

    parts = []
    has_warning = False
    for sev in ("critical", "warning", "info"):
        count = counts.get(sev, 0)
        parts.append(f"{sev.capitalize()}: {count}")
        if sev == "critical" and count > 0:
            has_warning = True

    return [{
        "name": "Alerts (24h)",
        "value": " | ".join(parts),
        "inline": True,
    }], has_warning
