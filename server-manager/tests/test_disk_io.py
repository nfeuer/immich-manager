import sys
from collections import namedtuple
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import Database
from src.monitoring import DiskIoMonitor


# psutil sdiskio counter shape (subset of fields we use).
Counters = namedtuple(
    "Counters",
    "read_bytes write_bytes read_count write_count",
)


def _make_monitor(t0_counters, t1_counters, dt=1.0):
    """Build a DiskIoMonitor pre-loaded with two synthetic samples."""
    monitor = DiskIoMonitor()
    times = [10.0, 10.0 + dt]
    monitor._time = MagicMock(monotonic=MagicMock(side_effect=times))
    with patch("src.monitoring.psutil.disk_io_counters", return_value=t0_counters):
        first = monitor.sample()
    assert first == []  # No baseline yet
    with patch("src.monitoring.psutil.disk_io_counters", return_value=t1_counters):
        return monitor.sample()


def test_disk_io_monitor_computes_rate_per_device():
    t0 = {
        "sda": Counters(read_bytes=0, write_bytes=0, read_count=0, write_count=0),
        "nvme0n1": Counters(read_bytes=0, write_bytes=0, read_count=0, write_count=0),
    }
    # 1 second elapsed: sda read 5 MB, wrote 0; nvme read 0, wrote 10 MB.
    t1 = {
        "sda": Counters(read_bytes=5_000_000, write_bytes=0, read_count=10, write_count=0),
        "nvme0n1": Counters(read_bytes=0, write_bytes=10_000_000, read_count=0, write_count=20),
    }
    samples = _make_monitor(t0, t1, dt=1.0)
    by_device = {s["device"]: s for s in samples}
    assert by_device["/dev/sda"]["read_mb_s"] == 5.0
    assert by_device["/dev/sda"]["write_mb_s"] == 0.0
    assert by_device["/dev/nvme0n1"]["write_mb_s"] == 10.0
    assert by_device["/dev/nvme0n1"]["read_count"] == 0
    assert by_device["/dev/nvme0n1"]["write_count"] == 20


def test_disk_io_monitor_skips_negative_deltas():
    t0 = {"sda": Counters(read_bytes=10_000, write_bytes=10_000, read_count=1, write_count=1)}
    t1 = {"sda": Counters(read_bytes=5_000, write_bytes=5_000, read_count=0, write_count=0)}
    samples = _make_monitor(t0, t1, dt=1.0)
    assert samples == []  # counter wrapped → ignore


def test_disk_io_monitor_filters_by_devices():
    t0 = {
        "sda": Counters(read_bytes=0, write_bytes=0, read_count=0, write_count=0),
        "sdb": Counters(read_bytes=0, write_bytes=0, read_count=0, write_count=0),
    }
    t1 = {
        "sda": Counters(read_bytes=1_000_000, write_bytes=0, read_count=0, write_count=0),
        "sdb": Counters(read_bytes=2_000_000, write_bytes=0, read_count=0, write_count=0),
    }
    monitor = DiskIoMonitor()
    monitor._time = MagicMock(monotonic=MagicMock(side_effect=[10.0, 11.0]))
    with patch("src.monitoring.psutil.disk_io_counters", return_value=t0):
        monitor.sample()
    with patch("src.monitoring.psutil.disk_io_counters", return_value=t1):
        samples = monitor.sample(devices=["/dev/sda"])
    assert len(samples) == 1
    assert samples[0]["device"] == "/dev/sda"


def test_disk_io_db_roundtrip(tmp_path):
    db = Database(db_path=str(tmp_path / "test.db"))
    db.record_disk_io([
        {"device": "/dev/sda", "read_mb_s": 1.5, "write_mb_s": 2.5,
         "read_count": 10, "write_count": 20},
        {"device": "/dev/nvme0n1", "read_mb_s": 0, "write_mb_s": 5.0,
         "read_count": 0, "write_count": 100},
    ])
    history = db.get_disk_io_history(hours=1)
    assert len(history) == 2
    only_nvme = db.get_disk_io_history(hours=1, device="/dev/nvme0n1")
    assert len(only_nvme) == 1
    assert only_nvme[0]["write_mb_s"] == 5.0
