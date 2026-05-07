import json
import sys
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gpu_monitor import GpuMonitor, SystemPowerMonitor, _to_float


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def test_to_float_handles_units_and_na():
    assert _to_float("80") == 80.0
    assert _to_float("80 W") == 80.0
    assert _to_float("100%") == 100.0
    assert _to_float("[N/A]") is None
    assert _to_float("not supported") is None
    assert _to_float(None) is None
    assert _to_float(45) == 45.0


# ---------------------------------------------------------------------------
# GpuMonitor — NVIDIA path
# ---------------------------------------------------------------------------


NVIDIA_CSV = (
    "0, GPU-1234, NVIDIA RTX 3060, 55, 22, 18, 4096, 12288, 78.5, 170\n"
    "1, GPU-5678, NVIDIA RTX 3060, 60, 0, 0, 1024, 12288, 12.0, 170\n"
)


@patch("src.gpu_monitor.shutil.which")
def test_detect_vendor_nvidia(mock_which):
    mock_which.side_effect = lambda c: "/usr/bin/nvidia-smi" if c == "nvidia-smi" else None
    gm = GpuMonitor()
    assert gm.available is True
    assert gm.vendor == "nvidia"


@patch("src.gpu_monitor.shutil.which", return_value=None)
def test_detect_vendor_none(mock_which):
    gm = GpuMonitor()
    assert gm.available is False
    assert gm.vendor is None
    # Query on a system without GPUs returns an empty list rather than raising.
    assert gm.query() == []


@patch("src.gpu_monitor.subprocess.run")
@patch("src.gpu_monitor.shutil.which")
def test_query_nvidia_parses_two_gpus(mock_which, mock_run):
    mock_which.side_effect = lambda c: "/usr/bin/nvidia-smi" if c == "nvidia-smi" else None
    mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_CSV, stderr="")
    gm = GpuMonitor()
    gpus = gm.query()
    assert len(gpus) == 2
    assert gpus[0]["index"] == 0
    assert gpus[0]["temperature_c"] == 55.0
    assert gpus[0]["util_percent"] == 22.0
    assert gpus[0]["power_draw_w"] == 78.5
    assert gpus[0]["power_limit_w"] == 170.0
    assert gpus[0]["mem_used_mb"] == 4096.0
    assert gpus[1]["index"] == 1
    assert gpus[1]["util_percent"] == 0.0


@patch("src.gpu_monitor.subprocess.run")
@patch("src.gpu_monitor.shutil.which")
def test_query_nvidia_handles_timeout(mock_which, mock_run):
    mock_which.side_effect = lambda c: "/usr/bin/nvidia-smi" if c == "nvidia-smi" else None
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=10)
    gm = GpuMonitor()
    assert gm.query() == []


@patch("src.gpu_monitor.subprocess.run")
@patch("src.gpu_monitor.shutil.which")
def test_query_nvidia_skips_malformed_rows(mock_which, mock_run):
    mock_which.side_effect = lambda c: "/usr/bin/nvidia-smi" if c == "nvidia-smi" else None
    bad = (
        "0, GPU-1, NVIDIA RTX 3060, 55, 22, 18, 4096, 12288, 78.5, 170\n"
        "garbage line with too few columns\n"
    )
    mock_run.return_value = MagicMock(returncode=0, stdout=bad, stderr="")
    gm = GpuMonitor()
    gpus = gm.query()
    assert len(gpus) == 1
    assert gpus[0]["index"] == 0


# ---------------------------------------------------------------------------
# GpuMonitor — AMD path
# ---------------------------------------------------------------------------


AMD_JSON = json.dumps({
    "card0": {
        "Card series": "AMD Radeon RX 7900",
        "Unique ID": "0xabc",
        "Temperature (Sensor edge) (C)": "62.0",
        "GPU use (%)": "30",
        "GPU memory use (%)": "12",
        "Average Graphics Package Power (W)": "120.0",
        "Max Graphics Package Power (W)": "300.0",
    }
})


@patch("src.gpu_monitor.subprocess.run")
@patch("src.gpu_monitor.shutil.which")
def test_query_amd(mock_which, mock_run):
    mock_which.side_effect = lambda c: "/usr/bin/rocm-smi" if c == "rocm-smi" else None
    mock_run.return_value = MagicMock(returncode=0, stdout=AMD_JSON, stderr="")
    gm = GpuMonitor()
    assert gm.vendor == "amd"
    gpus = gm.query()
    assert len(gpus) == 1
    g = gpus[0]
    assert g["index"] == 0
    assert g["temperature_c"] == 62.0
    assert g["util_percent"] == 30.0
    assert g["power_draw_w"] == 120.0
    assert g["vendor"] == "amd"


# ---------------------------------------------------------------------------
# SystemPowerMonitor
# ---------------------------------------------------------------------------


def test_system_power_no_data_returns_unavailable():
    spm = SystemPowerMonitor(baseline_watts=70)
    spm._rapl_paths = []  # no RAPL
    with patch("src.gpu_monitor.shutil.which", return_value=None):
        result = spm.read([])
    assert result["source"] == "unavailable"
    assert result["total_watts"] is None


def test_system_power_estimated_with_gpu_only():
    spm = SystemPowerMonitor(baseline_watts=70)
    spm._rapl_paths = []
    with patch("src.gpu_monitor.shutil.which", return_value=None):
        result = spm.read([{"power_draw_w": 100.0}, {"power_draw_w": 80.0}])
    assert result["source"] == "estimated"
    # 70 baseline + 180 GPUs, no CPU sample available
    assert result["total_watts"] == pytest.approx(250.0)
    assert result["gpu_watts"] == pytest.approx(180.0)
    assert result["cpu_watts"] is None


def test_system_power_ipmi_overrides_estimate(tmp_path):
    spm = SystemPowerMonitor(baseline_watts=70)
    spm._rapl_paths = []

    ipmi_output = (
        "Instantaneous power reading:                   215 Watts\n"
        "Minimum during sampling period:                100 Watts\n"
    )

    def fake_which(cmd):
        return "/usr/bin/ipmitool" if cmd == "ipmitool" else None

    with patch("src.gpu_monitor.shutil.which", side_effect=fake_which), \
         patch("src.gpu_monitor.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=ipmi_output, stderr="")
        result = spm.read([{"power_draw_w": 100.0}])
    assert result["source"] == "ipmi"
    assert result["total_watts"] == 215.0


def test_system_power_rapl_delta(tmp_path):
    pkg = tmp_path / "intel-rapl:0"
    pkg.mkdir()
    (pkg / "energy_uj").write_text("1000000")  # 1 J

    spm = SystemPowerMonitor(baseline_watts=50)
    spm._rapl_paths = [pkg]

    # First call: no prior sample, CPU watts must be None.
    with patch("src.gpu_monitor.shutil.which", return_value=None), \
         patch("src.gpu_monitor.time.monotonic", return_value=100.0):
        first = spm.read([{"power_draw_w": 30.0}])
    assert first["cpu_watts"] is None

    # Second call: 5 J consumed over 1 second → 5 W CPU.
    (pkg / "energy_uj").write_text(str(1_000_000 + 5_000_000))
    with patch("src.gpu_monitor.shutil.which", return_value=None), \
         patch("src.gpu_monitor.time.monotonic", return_value=101.0):
        second = spm.read([{"power_draw_w": 30.0}])
    assert second["cpu_watts"] == pytest.approx(5.0)
    assert second["gpu_watts"] == pytest.approx(30.0)
    assert second["total_watts"] == pytest.approx(85.0)  # 5 + 30 + 50 baseline


def test_system_power_rapl_counter_wrap_returns_none(tmp_path):
    pkg = tmp_path / "intel-rapl:0"
    pkg.mkdir()
    (pkg / "energy_uj").write_text("9000000")
    spm = SystemPowerMonitor(baseline_watts=50)
    spm._rapl_paths = [pkg]
    with patch("src.gpu_monitor.shutil.which", return_value=None), \
         patch("src.gpu_monitor.time.monotonic", return_value=100.0):
        spm.read([])
    # Counter wraps backwards → don't trust the sample
    (pkg / "energy_uj").write_text("100")
    with patch("src.gpu_monitor.shutil.which", return_value=None), \
         patch("src.gpu_monitor.time.monotonic", return_value=101.0):
        result = spm.read([])
    assert result["cpu_watts"] is None
