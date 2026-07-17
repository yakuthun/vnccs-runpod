#!/usr/bin/env bash
set -Eeuo pipefail

# ComfyUI enables cudaMallocAsync automatically on CUDA 12.x.  On some
# RunPod driver/GPU combinations this can reject tiny allocations even while
# nvidia-smi reports almost all VRAM free.  Persist the official ComfyUI
# fallback before handing control to RunPod's stock entrypoint.
ARGS_FILE="/workspace/runpod-slim/comfyui_args.txt"
mkdir -p "$(dirname "${ARGS_FILE}")"
touch "${ARGS_FILE}"

if ! grep -Fxq -- "--disable-cuda-malloc" "${ARGS_FILE}"; then
    printf '%s\n' '--disable-cuda-malloc' >> "${ARGS_FILE}"
fi

exec /start.sh
