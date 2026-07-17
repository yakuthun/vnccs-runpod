#!/usr/bin/env bash
set -Eeuo pipefail

CHECKPOINTS="/workspace/runpod-slim/ComfyUI/models/checkpoints"
LORAS="/workspace/runpod-slim/ComfyUI/models/loras/qwen/VNCCS"

mkdir -p "${CHECKPOINTS}" "${LORAS}"

wget -c \
  -O "${CHECKPOINTS}/Qwen-Rapid-AIO-NSFW-v19.safetensors" \
  'https://huggingface.co/Phr00t/Qwen-Image-Edit-Rapid-AIO/resolve/88c705939c00b3833a4fff1bce35e3ca648cab83/v19/Qwen-Rapid-AIO-NSFW-v19.safetensors?download=true'

wget -c \
  -O "${CHECKPOINTS}/Qwen-Rapid-AIO-NSFW-v23.safetensors" \
  'https://huggingface.co/Phr00t/Qwen-Image-Edit-Rapid-AIO/resolve/0758cce6dc3a0f5651de28369f56bad1c989d4a3/v23/Qwen-Rapid-AIO-NSFW-v23.safetensors?download=true'

wget -c \
  -O "${LORAS}/VNCCS_QIE2511_PoseStudio_ART_V5.9.5.safetensors" \
  'https://huggingface.co/MIUProject/VNCCS_PoseStudio/resolve/5719f5f86fdf33f4c5fa918c562d5ea62985d5e8/models/loras/qwen/VNCCS/VNCCS_QIE2511_PoseStudio_ART_V5.9.5.safetensors?download=true'

cd /workspace/runpod-slim/ComfyUI
sha256sum --check <<'EOF'
ba71575515709c9912560d1176b2386eaa49294fedc6ce57b9734aa57e91e5ac  models/checkpoints/Qwen-Rapid-AIO-NSFW-v19.safetensors
fdb919fc81bea63f13759967fc92c9118142e5c70d4e6795199233a35eefa233  models/checkpoints/Qwen-Rapid-AIO-NSFW-v23.safetensors
f81f7f446f56188d96a1094ffe5d4183e7e4473d27eebb43e4c9555d3537bbb8  models/loras/qwen/VNCCS/VNCCS_QIE2511_PoseStudio_ART_V5.9.5.safetensors
EOF

echo "v19, v23 ve Pose Studio LoRA indirildi ve SHA-256 ile doğrulandı."
echo "ComfyUI'yi şimdi bir kez yeniden başlatın."
