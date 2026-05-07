import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import ThresholdsConfig
from src.monitoring import DiskMonitor


def test_temp_thresholds_per_drive_type():
    t = ThresholdsConfig()
    # NVMe should be the warmest, HDD coolest.
    nvme_warn, nvme_crit = t.temp_thresholds_for("nvme")
    ssd_warn, ssd_crit = t.temp_thresholds_for("ssd")
    hdd_warn, hdd_crit = t.temp_thresholds_for("hdd")
    assert nvme_warn > ssd_warn > hdd_warn
    assert nvme_crit > ssd_crit > hdd_crit
    # Defaults: NVMe normally 50-65°C, so 70 should not fire false alarms.
    assert nvme_warn >= 65


def test_temp_thresholds_unknown_falls_back_to_hdd():
    t = ThresholdsConfig()
    assert t.temp_thresholds_for("unknown") == (t.disk_temp_warning, t.disk_temp_critical)


def _smartctl_json_for_hdd():
    return json.dumps({
        "smart_status": {"passed": True},
        "model_name": "WDC WD40EFRX",
        "serial_number": "ABC",
        "user_capacity": {"bytes": 4_000_000_000_000},
        "temperature": {"current": 38},
        "rotation_rate": 5400,
        "ata_smart_attributes": {"table": []},
    })


def _smartctl_json_for_ssd():
    return json.dumps({
        "smart_status": {"passed": True},
        "model_name": "Samsung SSD 870 EVO",
        "serial_number": "ABC",
        "user_capacity": {"bytes": 1_000_000_000_000},
        "temperature": {"current": 41},
        "rotation_rate": 0,
        "ata_smart_attributes": {"table": []},
    })


@patch("src.monitoring.subprocess.run")
def test_get_disk_health_classifies_nvme_by_path(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({
            "smart_status": {"passed": True},
            "model_name": "Samsung 980 PRO",
            "serial_number": "X",
            "user_capacity": {"bytes": 1_000_000_000_000},
            "temperature": {"current": 55},
            "ata_smart_attributes": {"table": []},
        }),
    )
    dm = DiskMonitor(["/dev/nvme0n1"])
    health = dm.get_disk_health("/dev/nvme0n1")
    assert health["drive_type"] == "nvme"


@patch("src.monitoring.subprocess.run")
def test_nvme_health_extracts_wear_and_writes(mock_run):
    # data_units_written = 1_953_125 → exactly 1.0 TB written
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({
            "smart_status": {"passed": True},
            "model_name": "Samsung 980 PRO",
            "serial_number": "X",
            "user_capacity": {"bytes": 1_000_000_000_000},
            "temperature": {"current": 55},
            "ata_smart_attributes": {"table": []},
            "nvme_smart_health_information_log": {
                "percentage_used": 7,
                "data_units_written": 1_953_125,
                "media_errors": 0,
            },
        }),
    )
    dm = DiskMonitor(["/dev/nvme0n1"])
    health = dm.get_disk_health("/dev/nvme0n1")
    assert health["wear_percent"] == 7
    assert health["tb_written"] == 1.0
    assert health["media_errors"] == 0
    assert health["health_ok"] is True


@patch("src.monitoring.subprocess.run")
def test_nvme_health_flags_high_wear(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({
            "smart_status": {"passed": True},
            "model_name": "Samsung 980 PRO",
            "serial_number": "X",
            "user_capacity": {"bytes": 1_000_000_000_000},
            "temperature": {"current": 55},
            "ata_smart_attributes": {"table": []},
            "nvme_smart_health_information_log": {
                "percentage_used": 95,
                "data_units_written": 100_000_000,
                "media_errors": 0,
            },
        }),
    )
    dm = DiskMonitor(["/dev/nvme0n1"])
    health = dm.get_disk_health("/dev/nvme0n1")
    assert health["health_ok"] is False
    assert any("95% wear" in w for w in health["warnings"])


@patch("src.monitoring.subprocess.run")
def test_get_disk_health_extracts_power_state(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({
            "smart_status": {"passed": True},
            "model_name": "WDC WD40EFRX",
            "serial_number": "ABC",
            "user_capacity": {"bytes": 4_000_000_000_000},
            "temperature": {"current": 38},
            "rotation_rate": 5400,
            "power_mode": "STANDBY",
            "ata_smart_attributes": {"table": []},
        }),
    )
    dm = DiskMonitor(["/dev/sdb"])
    health = dm.get_disk_health("/dev/sdb")
    assert health["power_state"] == "STANDBY"
    assert health["drive_type"] == "hdd"


@patch("src.monitoring.subprocess.run")
def test_get_disk_health_classifies_ssd_by_rotation_rate(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout=_smartctl_json_for_ssd())
    dm = DiskMonitor(["/dev/sda"])
    health = dm.get_disk_health("/dev/sda")
    assert health["drive_type"] == "ssd"


@patch("src.monitoring.subprocess.run")
def test_get_disk_health_classifies_hdd_by_rotation_rate(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout=_smartctl_json_for_hdd())
    dm = DiskMonitor(["/dev/sdb"])
    health = dm.get_disk_health("/dev/sdb")
    assert health["drive_type"] == "hdd"
