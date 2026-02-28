"""
Prometheus-compatible /metrics endpoint.

Exposes system metrics in the Prometheus text exposition format so that
`prometheus.yml` can scrape this endpoint directly — no extra exporter needed.

On Ubuntu:  apt install prometheus
Then add to /etc/prometheus/prometheus.yml:
  - job_name: 'immich-manager'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: /metrics
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .monitoring import SystemMonitor, DockerMonitor, DiskMonitor
    from .database import Database


def generate_metrics(
    system_monitor: Optional["SystemMonitor"],
    docker_monitor: Optional["DockerMonitor"],
    disk_monitor: Optional["DiskMonitor"],
    database: Optional["Database"],
) -> str:
    """Build a Prometheus text exposition payload from live data."""
    lines: list[str] = []

    def _gauge(name: str, help_text: str, value, labels: str = ""):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        label_str = f"{{{labels}}}" if labels else ""
        lines.append(f"{name}{label_str} {value}")

    # --- System metrics ---
    if system_monitor:
        try:
            m = system_monitor.get_all_metrics()
            _gauge("immich_cpu_usage_percent", "CPU usage percentage", m["cpu_percent"])
            _gauge("immich_memory_usage_percent", "Memory usage percentage", m["memory_percent"])
            _gauge("immich_memory_used_bytes", "Memory used in bytes", m["memory_used_gb"] * 1073741824)
            _gauge("immich_memory_total_bytes", "Total memory in bytes", m["memory_total_gb"] * 1073741824)
            _gauge("immich_disk_usage_percent", "Root disk usage percentage", m["disk_usage_percent"])
            _gauge("immich_disk_used_bytes", "Root disk used in bytes", m["disk_used_gb"] * 1073741824)
            _gauge("immich_disk_total_bytes", "Root disk total in bytes", m["disk_total_gb"] * 1073741824)
            _gauge("immich_network_sent_bytes", "Network bytes sent", m["network_sent_mb"] * 1048576)
            _gauge("immich_network_recv_bytes", "Network bytes received", m["network_recv_mb"] * 1048576)
        except Exception:
            pass

    # --- Docker containers ---
    if docker_monitor:
        try:
            containers = docker_monitor.get_immich_containers()
            lines.append("# HELP immich_container_up Whether an Immich container is running (1) or not (0)")
            lines.append("# TYPE immich_container_up gauge")
            for c in containers:
                name = c.get("name", "unknown")
                running = 1 if c.get("status") == "running" else 0
                lines.append(f'immich_container_up{{container="{name}"}} {running}')
        except Exception:
            pass

    # --- Disk SMART health ---
    if disk_monitor:
        try:
            disks = disk_monitor.check_all_disks()
            for d in disks:
                dev = d.get("device", "unknown")
                labels = f'device="{dev}"'
                if d.get("temperature") is not None:
                    _gauge("immich_disk_temperature_celsius", "Disk temperature", d["temperature"], labels)
                if d.get("reallocated_sectors") is not None:
                    _gauge("immich_disk_reallocated_sectors", "Reallocated sector count", d["reallocated_sectors"], labels)
                if d.get("pending_sectors") is not None:
                    _gauge("immich_disk_pending_sectors", "Current pending sector count", d["pending_sectors"], labels)
                healthy = 1 if d.get("health_ok", True) else 0
                _gauge("immich_disk_healthy", "SMART health status (1=ok, 0=failing)", healthy, labels)
        except Exception:
            pass

    # --- Backup stats ---
    if database:
        try:
            backups = database.get_recent_backups(limit=1)
            if backups:
                last = backups[0]
                success = 1 if last.get("status") == "success" else 0
                _gauge("immich_backup_last_success", "Whether the most recent backup succeeded (1/0)", success)
                if last.get("size_bytes"):
                    _gauge("immich_backup_last_size_bytes", "Size of the most recent backup", last["size_bytes"])
        except Exception:
            pass

    lines.append("")
    return "\n".join(lines)
