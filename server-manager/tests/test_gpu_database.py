import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import Database


def test_gpu_metrics_roundtrip(tmp_path):
    db = Database(db_path=str(tmp_path / "test.db"))

    db.record_gpu_metrics([
        {
            "index": 0,
            "uuid": "GPU-A",
            "name": "RTX 3060",
            "vendor": "nvidia",
            "temperature_c": 55.0,
            "util_percent": 22.0,
            "mem_util_percent": 18.0,
            "mem_used_mb": 4096.0,
            "mem_total_mb": 12288.0,
            "power_draw_w": 78.5,
            "power_limit_w": 170.0,
        },
        {
            "index": 1,
            "uuid": "GPU-B",
            "name": "RTX 3060",
            "vendor": "nvidia",
            "temperature_c": 60.0,
            "util_percent": 0.0,
            "mem_util_percent": 0.0,
            "mem_used_mb": 1024.0,
            "mem_total_mb": 12288.0,
            "power_draw_w": 12.0,
            "power_limit_w": 170.0,
        },
    ])

    latest = db.get_latest_gpu_metrics()
    assert len(latest) == 2
    assert {row["gpu_index"] for row in latest} == {0, 1}
    g0 = next(r for r in latest if r["gpu_index"] == 0)
    assert g0["power_draw_w"] == 78.5
    assert g0["power_limit_w"] == 170.0


def test_gpu_summary_aggregates(tmp_path):
    db = Database(db_path=str(tmp_path / "test.db"))
    samples = [
        {"index": 0, "uuid": "A", "name": "GPU0", "vendor": "nvidia",
         "temperature_c": 50, "util_percent": 10, "mem_util_percent": 5,
         "mem_used_mb": 100, "mem_total_mb": 8000, "power_draw_w": 60, "power_limit_w": 200},
        {"index": 0, "uuid": "A", "name": "GPU0", "vendor": "nvidia",
         "temperature_c": 70, "util_percent": 90, "mem_util_percent": 50,
         "mem_used_mb": 4000, "mem_total_mb": 8000, "power_draw_w": 180, "power_limit_w": 200},
    ]
    db.record_gpu_metrics(samples)

    summary = db.get_gpu_summary(hours=24)
    assert len(summary) == 1
    s = summary[0]
    assert s["gpu_index"] == 0
    assert s["temp_max"] == 70
    assert s["temp_min"] == 50
    assert s["power_max"] == 180
    assert s["power_min"] == 60
    assert s["util_max"] == 90
    assert s["util_min"] == 10


def test_system_power_roundtrip(tmp_path):
    db = Database(db_path=str(tmp_path / "test.db"))
    db.record_system_power({
        "total_watts": 215.0,
        "cpu_watts": 45.0,
        "gpu_watts": 100.0,
        "baseline_watts": 70.0,
        "source": "estimated",
    })
    history = db.get_system_power_history(hours=1)
    assert len(history) == 1
    assert history[0]["total_watts"] == 215.0
    assert history[0]["source"] == "estimated"

    summary = db.get_system_power_summary(hours=24)
    assert summary["total_max"] == 215.0
    assert summary["total_min"] == 215.0


def test_gpu_history_filters_by_index(tmp_path):
    db = Database(db_path=str(tmp_path / "test.db"))
    db.record_gpu_metrics([
        {"index": 0, "uuid": "A", "name": "GPU0", "vendor": "nvidia",
         "temperature_c": 50, "util_percent": 10, "mem_util_percent": 5,
         "mem_used_mb": 100, "mem_total_mb": 8000, "power_draw_w": 60, "power_limit_w": 200},
        {"index": 1, "uuid": "B", "name": "GPU1", "vendor": "nvidia",
         "temperature_c": 60, "util_percent": 80, "mem_util_percent": 40,
         "mem_used_mb": 2000, "mem_total_mb": 8000, "power_draw_w": 130, "power_limit_w": 200},
    ])
    only_zero = db.get_gpu_history(hours=24, gpu_index=0)
    assert len(only_zero) == 1
    assert only_zero[0]["gpu_index"] == 0

    everything = db.get_gpu_history(hours=24)
    assert len(everything) == 2


def test_record_gpu_metrics_empty_is_noop(tmp_path):
    db = Database(db_path=str(tmp_path / "test.db"))
    db.record_gpu_metrics([])  # should not raise
    assert db.get_latest_gpu_metrics() == []
