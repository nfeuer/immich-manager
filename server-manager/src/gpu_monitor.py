"""
GPU and system power monitoring.

Collects per-GPU temperature, utilization, memory, and power draw via
``nvidia-smi`` (NVIDIA) or ``rocm-smi`` (AMD), and estimates total system
power draw from CPU RAPL counters plus GPU draw plus a configurable
baseline. When IPMI/DCMI is available it is used as the authoritative
source for system power.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .utils import CLEAN_ENV

logger = logging.getLogger(__name__)


_NVIDIA_QUERY_FIELDS = (
    "index,uuid,name,temperature.gpu,utilization.gpu,utilization.memory,"
    "memory.used,memory.total,power.draw,power.limit"
)


class GpuMonitor:
    """Per-GPU metrics collector with NVIDIA and AMD support.

    The monitor is robust to missing tools — when ``nvidia-smi`` and
    ``rocm-smi`` are both unavailable it returns an empty list rather than
    raising, so the rest of the dashboard keeps working on systems
    without a discrete GPU.
    """

    def __init__(self, nvidia_smi: str = "nvidia-smi", rocm_smi: str = "rocm-smi"):
        self.nvidia_smi = nvidia_smi
        self.rocm_smi = rocm_smi
        self._vendor = self._detect_vendor()

    def _detect_vendor(self) -> Optional[str]:
        if shutil.which(self.nvidia_smi):
            return "nvidia"
        if shutil.which(self.rocm_smi):
            return "amd"
        return None

    @property
    def available(self) -> bool:
        return self._vendor is not None

    @property
    def vendor(self) -> Optional[str]:
        return self._vendor

    # ------------------------------------------------------------------ #
    # NVIDIA path                                                         #
    # ------------------------------------------------------------------ #

    def _query_nvidia(self) -> List[Dict[str, Any]]:
        try:
            result = subprocess.run(
                [
                    self.nvidia_smi,
                    f"--query-gpu={_NVIDIA_QUERY_FIELDS}",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                env=CLEAN_ENV,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning("nvidia-smi failed: %s", exc)
            return []

        if result.returncode != 0:
            logger.warning("nvidia-smi exited %s: %s", result.returncode, result.stderr)
            return []

        gpus: List[Dict[str, Any]] = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 10:
                continue
            try:
                gpu = {
                    "index": int(parts[0]),
                    "uuid": parts[1],
                    "name": parts[2],
                    "temperature_c": _to_float(parts[3]),
                    "util_percent": _to_float(parts[4]),
                    "mem_util_percent": _to_float(parts[5]),
                    "mem_used_mb": _to_float(parts[6]),
                    "mem_total_mb": _to_float(parts[7]),
                    "power_draw_w": _to_float(parts[8]),
                    "power_limit_w": _to_float(parts[9]),
                    "vendor": "nvidia",
                }
            except (ValueError, IndexError) as exc:
                logger.warning("Failed to parse nvidia-smi row %r: %s", line, exc)
                continue
            gpus.append(gpu)
        return gpus

    # ------------------------------------------------------------------ #
    # AMD path                                                            #
    # ------------------------------------------------------------------ #

    def _query_amd(self) -> List[Dict[str, Any]]:
        try:
            result = subprocess.run(
                [self.rocm_smi, "--showid", "--showtemp", "--showuse",
                 "--showmemuse", "--showpower", "--showproductname", "--json"],
                capture_output=True,
                text=True,
                timeout=10,
                env=CLEAN_ENV,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning("rocm-smi failed: %s", exc)
            return []

        if result.returncode != 0:
            return []

        import json
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        gpus: List[Dict[str, Any]] = []
        for key, info in data.items():
            if not key.startswith("card"):
                continue
            try:
                idx = int(key.replace("card", ""))
            except ValueError:
                continue
            gpus.append({
                "index": idx,
                "uuid": info.get("Unique ID", key),
                "name": info.get("Card series") or info.get("Card model") or "AMD GPU",
                "temperature_c": _to_float(info.get("Temperature (Sensor edge) (C)")),
                "util_percent": _to_float(info.get("GPU use (%)")),
                "mem_util_percent": _to_float(info.get("GPU memory use (%)")),
                "mem_used_mb": None,
                "mem_total_mb": None,
                "power_draw_w": _to_float(info.get("Average Graphics Package Power (W)")),
                "power_limit_w": _to_float(info.get("Max Graphics Package Power (W)")),
                "vendor": "amd",
            })
        return gpus

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def query(self) -> List[Dict[str, Any]]:
        """Return a list of GPU metric dicts (one per GPU, empty if none)."""
        if self._vendor == "nvidia":
            return self._query_nvidia()
        if self._vendor == "amd":
            return self._query_amd()
        return []


# ---------------------------------------------------------------------------- #
# System power estimation                                                       #
# ---------------------------------------------------------------------------- #


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s.lower() in {"n/a", "[n/a]", "not supported", "unknown"}:
        return None
    # Strip trailing units like "W", "C", "%", "MiB" if rocm-smi sneaks any in.
    for suffix in ("W", "C", "%", "MiB", "MB"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    try:
        return float(s)
    except ValueError:
        return None


class SystemPowerMonitor:
    """Estimate total system wall power draw.

    Strategy, in order of preference:
      1. IPMI DCMI power reading (``ipmitool dcmi power reading``) — exact
         input wattage from the BMC when available.
      2. Sum of CPU package power (Intel RAPL) + GPU draw + configurable
         baseline wattage for motherboard / drives / fans.

    The RAPL read computes a delta in joules between two timestamps to
    derive watts. The first call after construction returns ``None`` for
    the CPU component, since a delta is required.
    """

    RAPL_ROOT = Path("/sys/class/powercap")

    def __init__(self, baseline_watts: float = 65.0, ipmitool: str = "ipmitool"):
        self.baseline_watts = baseline_watts
        self.ipmitool = ipmitool
        self._rapl_paths = self._find_rapl_packages()
        self._last_rapl_uj: Optional[int] = None
        self._last_rapl_ts: Optional[float] = None

    @classmethod
    def _find_rapl_packages(cls) -> List[Path]:
        if not cls.RAPL_ROOT.exists():
            return []
        paths: List[Path] = []
        for p in cls.RAPL_ROOT.iterdir():
            name = p.name
            # Only top-level package domains (intel-rapl:0, intel-rapl:1, ...)
            if name.startswith("intel-rapl:") and ":" not in name.split("intel-rapl:", 1)[1]:
                if (p / "energy_uj").exists():
                    paths.append(p)
        return paths

    def _read_ipmi_watts(self) -> Optional[float]:
        if not shutil.which(self.ipmitool):
            return None
        try:
            result = subprocess.run(
                [self.ipmitool, "dcmi", "power", "reading"],
                capture_output=True,
                text=True,
                timeout=5,
                env=CLEAN_ENV,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.lower().startswith("instantaneous power reading"):
                # Format: "Instantaneous power reading:                   215 Watts"
                parts = line.split(":", 1)
                if len(parts) == 2:
                    tokens = parts[1].strip().split()
                    if tokens:
                        try:
                            return float(tokens[0])
                        except ValueError:
                            return None
        return None

    def _read_cpu_watts(self) -> Optional[float]:
        if not self._rapl_paths:
            return None
        total_uj = 0
        for p in self._rapl_paths:
            try:
                total_uj += int((p / "energy_uj").read_text().strip())
            except (OSError, ValueError):
                return None
        now = time.monotonic()
        prev_uj = self._last_rapl_uj
        prev_ts = self._last_rapl_ts
        self._last_rapl_uj = total_uj
        self._last_rapl_ts = now
        if prev_uj is None or prev_ts is None:
            return None
        elapsed = now - prev_ts
        if elapsed <= 0:
            return None
        delta_uj = total_uj - prev_uj
        # RAPL counter wraps; if it went backwards we can't trust this sample.
        if delta_uj < 0:
            return None
        return (delta_uj / 1_000_000.0) / elapsed

    def read(self, gpus: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute current system power draw given a list of GPU snapshots."""
        gpu_watts = sum((g.get("power_draw_w") or 0.0) for g in gpus) or None

        ipmi_watts = self._read_ipmi_watts()
        if ipmi_watts is not None:
            return {
                "total_watts": ipmi_watts,
                "source": "ipmi",
                "cpu_watts": self._read_cpu_watts(),
                "gpu_watts": gpu_watts,
                "baseline_watts": self.baseline_watts,
            }

        cpu_watts = self._read_cpu_watts()
        components = [w for w in (cpu_watts, gpu_watts) if w is not None]
        if not components and cpu_watts is None and gpu_watts is None:
            return {
                "total_watts": None,
                "source": "unavailable",
                "cpu_watts": None,
                "gpu_watts": None,
                "baseline_watts": self.baseline_watts,
            }
        total = (cpu_watts or 0.0) + (gpu_watts or 0.0) + self.baseline_watts
        return {
            "total_watts": total,
            "source": "estimated",
            "cpu_watts": cpu_watts,
            "gpu_watts": gpu_watts,
            "baseline_watts": self.baseline_watts,
        }
