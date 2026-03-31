# =============================================================================
# Photo Curator — CUDA-enabled image for GPU-accelerated photo analysis
# =============================================================================
# Base: NVIDIA CUDA 11.8 + cuDNN 8 development image (Ubuntu 22.04)
# GPU: GTX 1080 (CUDA 11.x capable, 8GB VRAM)
# =============================================================================

FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04

# Prevent interactive prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# --- System dependencies ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3-pip \
    python3.11-venv \
    # Build tools for dlib (CUDA) and OpenCV
    build-essential \
    cmake \
    git \
    pkg-config \
    # OpenCV runtime dependencies
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # Image format libraries
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libwebp-dev \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Use python3.11 as default python
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && python3 -m pip install --upgrade pip

WORKDIR /app

# --- Core Python dependencies (fast to install) ---
COPY photo-curator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- PyTorch with CUDA 11.8 support ---
# NOTE: Do NOT install from requirements-ml.txt for torch — we need the CUDA build
RUN pip install --no-cache-dir \
    torch torchvision \
    --index-url https://download.pytorch.org/whl/cu118

# --- dlib with CUDA support ---
# Build from source with DLIB_USE_CUDA=1 so face_locations can use CNN detector on GPU
RUN pip install --no-cache-dir cmake && \
    git clone --depth 1 https://github.com/davisking/dlib.git /tmp/dlib && \
    cd /tmp/dlib && \
    DLIB_USE_CUDA=1 CUDA_HOST_COMPILER=/usr/bin/gcc python setup.py install && \
    rm -rf /tmp/dlib

# --- face_recognition (depends on dlib, already built above) ---
RUN pip install --no-cache-dir face_recognition

# --- Copy application code ---
COPY photo-curator/ .
COPY shared/ /app/shared/

# Create data directories
RUN mkdir -p data/models data/curator.db.dir

# --- Health check ---
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8081/')" \
    || exit 1

# Run the application
CMD ["python3", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8081"]
