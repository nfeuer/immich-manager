import pytest
import json
import subprocess
from unittest.mock import MagicMock, patch, PropertyMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# DiskMonitor
# ---------------------------------------------------------------------------

from src.monitoring import DiskMonitor


def _make_disk_monitor(devices=None):
    return DiskMonitor(devices or ["/dev/sda"])


SMARTCTL_JSON = json.dumps({
    "smart_status": {"passed": True},
    "model_name": "Samsung SSD 870",
    "serial_number": "S123456",
    "user_capacity": {"bytes": 500107862016},
    "temperature": {"current": 34},
    "ata_smart_attributes": {
        "table": [
            {"id": 9, "name": "Power_On_Hours", "raw": {"value": 12345}},
            {"id": 12, "name": "Power_Cycle_Count", "raw": {"value": 99}},
            {"id": 5, "name": "Reallocated_Sector_Ct", "raw": {"value": 0}},
            {"id": 197, "name": "Current_Pending_Sector", "raw": {"value": 0}},
            {"id": 198, "name": "Offline_Uncorrectable", "raw": {"value": 0}},
            {"id": 194, "name": "Temperature_Celsius", "raw": {"value": 8590065698}},
        ]
    },
})


@patch("src.monitoring.subprocess.run")
def test_check_smart_available_true(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    dm = _make_disk_monitor()
    assert dm.check_smart_available() is True


@patch("src.monitoring.subprocess.run", side_effect=FileNotFoundError)
def test_check_smart_available_false(mock_run):
    dm = _make_disk_monitor()
    assert dm.check_smart_available() is False


@patch("src.monitoring.subprocess.run")
def test_get_disk_health_success(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout=SMARTCTL_JSON)
    dm = _make_disk_monitor()
    health = dm.get_disk_health("/dev/sda")

    assert health["device"] == "/dev/sda"
    assert health["smart_status"] is True
    assert health["model"] == "Samsung SSD 870"
    assert health["temperature"] == 34
    assert health["power_on_hours"] == 12345
    assert health["power_cycle_count"] == 99
    assert health["reallocated_sectors"] == 0
    assert health["health_ok"] is True
    assert health["warnings"] == []


@patch("src.monitoring.subprocess.run")
def test_get_disk_health_smartctl_unavailable(mock_run):
    mock_run.side_effect = FileNotFoundError
    dm = _make_disk_monitor()
    health = dm.get_disk_health("/dev/sda")
    assert health["smart_status"] == "unknown"
    assert "not available" in health["error"]


@patch("src.monitoring.subprocess.run")
def test_get_disk_health_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="smartctl", timeout=30)
    dm = _make_disk_monitor()
    # smartctl availability check also calls subprocess.run, so patch both calls
    with patch.object(dm, "check_smart_available", return_value=True):
        health = dm.get_disk_health("/dev/sda")
    assert health["smart_status"] == "timeout"


@patch("src.monitoring.subprocess.run")
def test_get_disk_health_bad_json(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="not json")
    dm = _make_disk_monitor()
    with patch.object(dm, "check_smart_available", return_value=True):
        health = dm.get_disk_health("/dev/sda")
    assert health["smart_status"] == "parse_error"


@patch("src.monitoring.subprocess.run")
def test_get_disk_health_reallocated_sectors_warning(mock_run):
    bad_disk = json.loads(SMARTCTL_JSON)
    for attr in bad_disk["ata_smart_attributes"]["table"]:
        if attr["id"] == 5:
            attr["raw"]["value"] = 8
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(bad_disk))
    dm = _make_disk_monitor()
    health = dm.get_disk_health("/dev/sda")
    assert health["health_ok"] is False
    assert any("Reallocated sectors: 8" in w for w in health["warnings"])


@patch("src.monitoring.subprocess.run")
def test_get_disk_health_pending_sectors_warning(mock_run):
    bad_disk = json.loads(SMARTCTL_JSON)
    for attr in bad_disk["ata_smart_attributes"]["table"]:
        if attr["id"] == 197:
            attr["raw"]["value"] = 3
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(bad_disk))
    dm = _make_disk_monitor()
    health = dm.get_disk_health("/dev/sda")
    assert health["health_ok"] is False
    assert any("Pending sectors: 3" in w for w in health["warnings"])


@patch("src.monitoring.subprocess.run")
def test_check_all_disks(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout=SMARTCTL_JSON)
    dm = DiskMonitor(["/dev/sda", "/dev/sdb"])
    results = dm.check_all_disks()
    assert len(results) == 2
    assert results[0]["device"] == "/dev/sda"
    assert results[1]["device"] == "/dev/sdb"


# ---------------------------------------------------------------------------
# SystemMonitor
# ---------------------------------------------------------------------------

from src.monitoring import SystemMonitor


@patch("src.monitoring.psutil.cpu_percent", return_value=42.5)
def test_get_cpu_usage(mock_cpu):
    sm = SystemMonitor()
    assert sm.get_cpu_usage() == 42.5


@patch("src.monitoring.psutil.virtual_memory")
def test_get_memory_usage(mock_mem):
    mock_mem.return_value = MagicMock(
        percent=65.3,
        used=8 * 1024**3,
        total=16 * 1024**3,
        available=6 * 1024**3,
    )
    sm = SystemMonitor()
    mem = sm.get_memory_usage()
    assert mem["percent"] == 65.3
    assert abs(mem["used_gb"] - 8.0) < 0.01
    assert abs(mem["total_gb"] - 16.0) < 0.01
    assert abs(mem["available_gb"] - 6.0) < 0.01


@patch("src.monitoring.psutil.disk_usage")
def test_get_disk_usage(mock_disk):
    mock_disk.return_value = MagicMock(
        percent=72.0,
        used=500 * 1024**3,
        total=1000 * 1024**3,
        free=500 * 1024**3,
    )
    sm = SystemMonitor()
    disk = sm.get_disk_usage("/")
    assert disk["percent"] == 72.0
    assert abs(disk["used_gb"] - 500.0) < 0.01
    assert abs(disk["free_gb"] - 500.0) < 0.01


@patch("src.monitoring.psutil.net_io_counters")
def test_get_network_usage(mock_net):
    mock_net.return_value = MagicMock(
        bytes_sent=100 * 1024**2,
        bytes_recv=200 * 1024**2,
    )
    sm = SystemMonitor()
    net = sm.get_network_usage()
    assert abs(net["sent_mb"] - 100.0) < 0.01
    assert abs(net["recv_mb"] - 200.0) < 0.01


@patch("src.monitoring.psutil.net_io_counters")
@patch("src.monitoring.psutil.disk_usage")
@patch("src.monitoring.psutil.virtual_memory")
@patch("src.monitoring.psutil.cpu_percent", return_value=55.0)
def test_get_all_metrics(mock_cpu, mock_mem, mock_disk, mock_net):
    mock_mem.return_value = MagicMock(percent=60, used=8*1024**3, total=16*1024**3, available=8*1024**3)
    mock_disk.return_value = MagicMock(percent=50, used=500*1024**3, total=1000*1024**3, free=500*1024**3)
    mock_net.return_value = MagicMock(bytes_sent=1024**2, bytes_recv=2*1024**2)

    sm = SystemMonitor()
    metrics = sm.get_all_metrics()

    expected_keys = [
        "timestamp", "cpu_percent", "memory_percent", "memory_used_gb",
        "memory_total_gb", "disk_usage_percent", "disk_used_gb",
        "disk_total_gb", "network_sent_mb", "network_recv_mb",
    ]
    for key in expected_keys:
        assert key in metrics, f"Missing key: {key}"
    assert metrics["cpu_percent"] == 55.0


# ---------------------------------------------------------------------------
# DockerMonitor
# ---------------------------------------------------------------------------

from src.monitoring import DockerMonitor


@patch("src.monitoring.docker.from_env", side_effect=Exception("Docker not running"))
def test_docker_monitor_init_unavailable(mock_docker):
    dm = DockerMonitor()
    assert dm.available is False
    assert dm.client is None


@patch("src.monitoring.docker.from_env")
def test_docker_monitor_init_available(mock_docker):
    mock_docker.return_value = MagicMock()
    dm = DockerMonitor()
    assert dm.available is True


@patch("src.monitoring.docker.from_env")
def test_get_immich_containers(mock_docker):
    mock_container = MagicMock()
    mock_container.name = "immich_server"
    mock_container.status = "running"
    mock_container.image.tags = ["ghcr.io/immich-app/immich-server:v1.126.1"]

    mock_client = MagicMock()
    mock_client.containers.list.return_value = [mock_container]
    mock_docker.return_value = mock_client

    dm = DockerMonitor()
    containers = dm.get_immich_containers()
    assert len(containers) == 1
    assert containers[0]["name"] == "immich_server"
    assert containers[0]["status"] == "running"


@patch("src.monitoring.docker.from_env")
def test_check_immich_healthy_all_running(mock_docker):
    containers = []
    for name in ["immich_server", "immich_ml", "immich_postgres", "immich_redis"]:
        c = MagicMock()
        c.name = name
        c.status = "running"
        c.image.tags = [f"{name}:latest"]
        containers.append(c)

    mock_client = MagicMock()
    mock_client.containers.list.return_value = containers
    mock_docker.return_value = mock_client

    dm = DockerMonitor()
    assert dm.check_immich_healthy() is True


@patch("src.monitoring.docker.from_env")
def test_check_immich_healthy_one_stopped(mock_docker):
    running = MagicMock()
    running.name = "immich_server"
    running.status = "running"
    running.image.tags = ["immich_server:latest"]

    stopped = MagicMock()
    stopped.name = "immich_ml"
    stopped.status = "exited"
    stopped.image.tags = ["immich_ml:latest"]

    mock_client = MagicMock()
    mock_client.containers.list.return_value = [running, stopped]
    mock_docker.return_value = mock_client

    dm = DockerMonitor()
    assert dm.check_immich_healthy() is False


@patch("src.monitoring.docker.from_env")
def test_check_immich_healthy_no_containers(mock_docker):
    mock_client = MagicMock()
    mock_client.containers.list.return_value = []
    mock_docker.return_value = mock_client

    dm = DockerMonitor()
    assert dm.check_immich_healthy() is False


@patch("src.monitoring.docker.from_env", side_effect=Exception("Docker not running"))
def test_get_immich_containers_docker_unavailable(mock_docker):
    dm = DockerMonitor()
    assert dm.get_immich_containers() == []


@patch("src.monitoring.docker.from_env")
def test_get_container_stats(mock_docker):
    mock_container = MagicMock()
    mock_container.status = "running"
    mock_container.stats.return_value = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 200},
            "system_cpu_usage": 10000,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 100},
            "system_cpu_usage": 9000,
        },
        "memory_stats": {"usage": 256 * 1024**2},
    }

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_container
    mock_docker.return_value = mock_client

    dm = DockerMonitor()
    stats = dm.get_container_stats("immich_server")
    assert stats["name"] == "immich_server"
    assert stats["status"] == "running"
    assert stats["cpu_percent"] == pytest.approx(10.0)
    assert stats["memory_mb"] == pytest.approx(256.0)


@patch("src.monitoring.docker.from_env", side_effect=Exception("Docker not running"))
def test_get_container_stats_docker_unavailable(mock_docker):
    dm = DockerMonitor()
    assert dm.get_container_stats("immich_server") is None
