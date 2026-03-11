"""
GPU/CUDA initialization and status utilities for batch photo processing.
Handles model loading, device detection, and graceful CPU fallback.
"""

import logging
from typing import Optional, Dict, Any
import torch

logger = logging.getLogger(__name__)


class GPUManager:
    """Manages GPU device selection and status reporting."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize GPU manager.

        Args:
            config: The batch_processing.gpu section of config:
                    {'enabled': bool, 'device': str}
        """
        self._config = config
        self._device: Optional[torch.device] = None
        self._initialized = False
        self._cuda_available = False
        self._device_name = "CPU"
        self._dlib_cuda = False

    def init(self) -> torch.device:
        """
        Detect and initialize the best available compute device.

        Returns torch.device to use for all model inference.
        Falls back to CPU if CUDA unavailable or disabled in config.
        """
        gpu_enabled = self._config.get("enabled", True)
        requested_device = self._config.get("device", "cuda:0")

        if gpu_enabled and torch.cuda.is_available():
            try:
                device = torch.device(requested_device)
                # Verify device is accessible
                torch.zeros(1).to(device)
                self._cuda_available = True
                self._device_name = torch.cuda.get_device_name(device)
                self._device = device
                logger.info(f"✓ GPU initialized: {self._device_name} ({requested_device})")
            except Exception as e:
                logger.warning(f"CUDA device {requested_device} failed ({e}), falling back to CPU")
                self._device = torch.device("cpu")
                self._device_name = "CPU (fallback)"
        else:
            if not gpu_enabled:
                logger.info("GPU disabled in config, using CPU")
            else:
                logger.info("CUDA not available, using CPU")
            self._device = torch.device("cpu")
            self._device_name = "CPU"

        # Check dlib CUDA support (requires dlib compiled with CUDA)
        try:
            import dlib  # noqa: PLC0415
            self._dlib_cuda = getattr(dlib, "DLIB_USE_CUDA", False)
            if self._dlib_cuda:
                logger.info("✓ dlib compiled with CUDA support")
            else:
                logger.info("ℹ dlib CUDA not available (CPU dlib), face embeddings will use CPU")
        except ImportError:
            logger.debug("dlib not available")

        self._initialized = True
        return self._device

    @property
    def device(self) -> torch.device:
        """Return current device (initialize if needed)."""
        if not self._initialized:
            self.init()
        return self._device

    def get_status(self) -> Dict[str, Any]:
        """Return GPU status dict for the API endpoint."""
        status = {
            "cuda_available": self._cuda_available,
            "device_name": self._device_name,
            "device": str(self._device) if self._device else "cpu",
            "dlib_cuda": self._dlib_cuda,
            "initialized": self._initialized,
        }

        if self._cuda_available and self._device is not None:
            try:
                idx = self._device.index if self._device.index is not None else 0
                props = torch.cuda.get_device_properties(idx)
                total_mb = props.total_memory // (1024 * 1024)
                reserved_mb = torch.cuda.memory_reserved(idx) // (1024 * 1024)
                allocated_mb = torch.cuda.memory_allocated(idx) // (1024 * 1024)
                status["vram_total_mb"] = total_mb
                status["vram_reserved_mb"] = reserved_mb
                status["vram_allocated_mb"] = allocated_mb
                status["vram_free_mb"] = total_mb - reserved_mb
            except Exception as e:
                logger.debug(f"Could not read VRAM stats: {e}")

        return status
