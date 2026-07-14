#!/usr/bin/env bash
set -Eeuo pipefail

mkdir -p \
    /workspace/models \
    /workspace/input \
    /workspace/output \
    /workspace/temp \
    /workspace/user \
    /workspace/cache

# Preserve RunPod's Web Terminal/Jupyter services from the base image.
if [[ -x /start.sh ]]; then
    /start.sh &
fi

echo "============================================================"
echo "VNCCS RunPod image başlatılıyor"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-<unset>}"
echo "NVIDIA_VISIBLE_DEVICES=${NVIDIA_VISIBLE_DEVICES:-<unset>}"
echo "============================================================"

GPU_READY=0

# Every attempt uses a new Python process, so an early CUDA failure is not cached.
for attempt in $(seq 1 120); do
    if nvidia-smi >/dev/null 2>&1 && \
       python -c 'import torch; assert torch.cuda.is_available(); print("GPU:", torch.cuda.get_device_name(0)); print("Torch:", torch.__version__, "CUDA:", torch.version.cuda)' ; then
        GPU_READY=1
        break
    fi

    echo "GPU henüz hazır değil (${attempt}/120); 2 saniye bekleniyor..."
    sleep 2
done

if [[ "${GPU_READY}" != "1" ]]; then
    echo "HATA: GPU/CUDA 4 dakika içinde hazır olmadı."
    echo "Bu hata Python paketi kurulumundan değil, Pod'un GPU bağlanmasından kaynaklanır."
    exit 70
fi

echo "Kurulu kaynak sürümleri:"
cat /opt/build-info.txt
echo

cd /opt/ComfyUI

exec python main.py \
    --listen 0.0.0.0 \
    --port 8188 \
    --enable-manager \
    --disable-auto-launch \
    --input-directory /workspace/input \
    --output-directory /workspace/output \
    --temp-directory /workspace/temp
