import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gpu_monitor import CpuTempMonitor, SystemPowerMonitor


def _make_coretemp(tmp_path: Path, package_mc: int, cores_mc: list[int]) -> Path:
    """Build a fake hwmon directory mimicking coretemp layout."""
    hw = tmp_path / "hwmon3"
    hw.mkdir()
    (hw / "name").write_text("coretemp\n")
    (hw / "temp1_input").write_text(f"{package_mc}\n")
    (hw / "temp1_label").write_text("Package id 0\n")
    for i, core in enumerate(cores_mc, start=2):
        (hw / f"temp{i}_input").write_text(f"{core}\n")
        (hw / f"temp{i}_label").write_text(f"Core {i - 2}\n")
    return hw


def test_cpu_temp_returns_unavailable_when_no_chip(tmp_path, monkeypatch):
    monkeypatch.setattr(CpuTempMonitor, "HWMON_ROOT", tmp_path)
    monitor = CpuTempMonitor()
    assert monitor.available is False
    result = monitor.read()
    assert result["available"] is False
    assert result["package_c"] is None
    assert result["max_core_c"] is None


def test_cpu_temp_reads_coretemp_chip(tmp_path, monkeypatch):
    # Simulate i7-6700k: 4 cores, package at 65°C, hottest core 72°C.
    monkeypatch.setattr(CpuTempMonitor, "HWMON_ROOT", tmp_path)
    _make_coretemp(tmp_path, package_mc=65000, cores_mc=[60000, 72000, 68000, 71000])
    # Add another irrelevant chip first to confirm we filter by name.
    other = tmp_path / "hwmon0"
    other.mkdir()
    (other / "name").write_text("acpitz\n")
    (other / "temp1_input").write_text("45000\n")

    monitor = CpuTempMonitor()
    assert monitor.available is True
    assert monitor.chip_path == "hwmon3"

    result = monitor.read()
    assert result["available"] is True
    assert result["package_c"] == 65.0
    assert result["max_core_c"] == 72.0
    assert sorted(result["cores_c"]) == [60.0, 68.0, 71.0, 72.0]


def test_cpu_temp_handles_unreadable_files(tmp_path, monkeypatch):
    monkeypatch.setattr(CpuTempMonitor, "HWMON_ROOT", tmp_path)
    hw = tmp_path / "hwmon0"
    hw.mkdir()
    (hw / "name").write_text("coretemp\n")
    (hw / "temp1_input").write_text("not a number\n")
    (hw / "temp2_input").write_text("70000\n")

    monitor = CpuTempMonitor()
    result = monitor.read()
    # Garbled package row is skipped; valid core row is still read.
    assert result["package_c"] is None
    assert result["max_core_c"] == 70.0


def test_hwmon_inventory_lists_chips_and_power_input(tmp_path, monkeypatch):
    # Two chips: one with power_input (would be authoritative AC source),
    # one without (just temperature sensors).
    chip0 = tmp_path / "hwmon0"
    chip0.mkdir()
    (chip0 / "name").write_text("coretemp\n")
    (chip0 / "temp1_input").write_text("55000\n")

    chip1 = tmp_path / "hwmon1"
    chip1.mkdir()
    (chip1 / "name").write_text("supermicro_pmbus\n")
    (chip1 / "power1_input").write_text("180000000\n")
    (chip1 / "temp1_input").write_text("32000\n")

    monkeypatch.setattr(SystemPowerMonitor, "HWMON_ROOT", tmp_path)
    inv = SystemPowerMonitor.hwmon_inventory()
    assert len(inv) == 2
    by_name = {c["name"]: c for c in inv}
    assert by_name["coretemp"]["has_power_input"] is False
    assert by_name["supermicro_pmbus"]["has_power_input"] is True
    assert "power1_input" in by_name["supermicro_pmbus"]["sensors"]
