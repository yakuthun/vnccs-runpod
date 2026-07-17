#!/usr/bin/env bash
set -Eeuo pipefail

C="${COMFYUI_DIR:-/workspace/runpod-slim/ComfyUI}"
P="${COMFYUI_PYTHON:-$C/.venv-cu128/bin/python}"

echo "============================================================"
echo "VNCCS immutable RunPod image"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-<unset>}"
echo "NVIDIA_VISIBLE_DEVICES=${NVIDIA_VISIBLE_DEVICES:-<unset>}"
echo "============================================================"

GPU_READY=0

# Each probe is a fresh process; a temporary early CUDA failure cannot stay cached.
for attempt in $(seq 1 120); do
    if nvidia-smi >/dev/null 2>&1 && \
       "$P" -c 'import torch; assert torch.cuda.is_available(); print("GPU:", torch.cuda.get_device_name(0)); print("Torch:", torch.__version__, "CUDA:", torch.version.cuda)' ; then
        GPU_READY=1
        break
    fi
    echo "GPU not ready yet (${attempt}/120); waiting 2 seconds..."
    sleep 2
done

if [[ "${GPU_READY}" != "1" ]]; then
    echo "ERROR: GPU/CUDA did not become available within 4 minutes."
    exit 70
fi

cat /opt/vnccs/build-info.txt

# GHCR limits individual layers to 10 GB. The two largest immutable model
# files are stored as verified 3 GB parts and assembled once on the Pod's
# local container disk before ComfyUI starts. No network access is used here.
"$P" /opt/vnccs/preload_models.py assemble

cd "$C"

exec "$P" main.py \
    --listen 0.0.0.0 \
    --port 8188 \
    --enable-manager \
    --disable-auto-launch
