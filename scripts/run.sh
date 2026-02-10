#!/bin/bash
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Prefer PulseAudio/PipeWire over ALSA for audio
export SDL_AUDIODRIVER=pulse

source "$PROJECT_DIR/.venv/bin/activate"

# Ensure all NVIDIA/cuDNN libraries load from the SAME pip package to prevent
# CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH. This must happen BEFORE Python
# loads any CUDA libraries.
PYTHON_VERSION=$(ls "$PROJECT_DIR/.venv/lib/" | grep python | head -1)
VENV_SITE="$PROJECT_DIR/.venv/lib/$PYTHON_VERSION/site-packages"
NVIDIA_LIBS=""
for nvidia_pkg in nvidia/cudnn/lib nvidia/cublas/lib nvidia/cuda_runtime/lib nvidia/cuda_nvrtc/lib nvidia/cufft/lib nvidia/cusparse/lib nvidia/cusolver/lib nvidia/nccl/lib; do
    pkg_path="$VENV_SITE/$nvidia_pkg"
    if [ -d "$pkg_path" ]; then
        NVIDIA_LIBS="${NVIDIA_LIBS:+$NVIDIA_LIBS:}$pkg_path"
    fi
done
if [ -n "$NVIDIA_LIBS" ]; then
    export LD_LIBRARY_PATH="$NVIDIA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

# Add src to Python path
export PYTHONPATH="$PROJECT_DIR/src:$PYTHONPATH"

# Debug mode: uncomment to see full errors
# python "$PROJECT_DIR/src/gui.py" "$@"

# Production mode: filter ALSA noise
python "$PROJECT_DIR/src/gui.py" "$@" 2> >(grep -v "^ALSA lib\|^Expression '" >&2)
