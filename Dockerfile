# syntax=docker/dockerfile:1.7

# RunPod's versioned PyTorch/CUDA base image.
FROM runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404

ARG COMFYUI_REF=0aecac867d7840b56ad790aa76c5e76e33c74c3d
ARG VNCCS_REF=050cb4b15875a7eefc180d1f00b97bf5e8b17104
ARG VNCCS_UTILS_REF=1908ddfa8a5084a360783ca596f27678743c5496
ARG GGUF_REF=6ea2651e7df66d7585f6ffee804b20e92fb38b8a
ARG IMPACT_REF=429d0159ad429e64d2b3916e6e7be9c22d025c3c
ARG IMPACT_SUBPACK_REF=50c7b71a6a224734cc9b21963c6d1926816a97f1
ARG SEEDVR2_REF=4490bd1f482e026674543386bb2a4d176da245b9
ARG EASY_SAM3_REF=88fe578a1a5e03d95281197303d5d3a73fd5a089
ARG SAM2_REF=2b90b9f5ceec907a1c18123530e92e794ad901a4

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:${PATH} \
    COMFYUI_DIR=/opt/ComfyUI \
    HF_HOME=/workspace/cache/huggingface \
    TORCH_HOME=/workspace/cache/torch \
    XDG_CACHE_HOME=/workspace/cache

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        aria2 \
        build-essential \
        ca-certificates \
        cmake \
        curl \
        ffmpeg \
        git \
        git-lfs \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        ninja-build \
        pkg-config \
        python3-venv \
        unzip \
        wget && \
    rm -rf /var/lib/apt/lists/*

# Keep RunPod's tested CUDA/Torch installation in the base image, while isolating
# every extra Python package inside a dedicated virtual environment.
RUN python -m venv --system-site-packages /opt/venv && \
    python -m pip install --no-cache-dir --upgrade "pip<26" setuptools wheel packaging

COPY scripts/install_requirements.py /opt/scripts/install_requirements.py

RUN clone_ref() { \
        local url="$1" ref="$2" dest="$3"; \
        git init "$dest"; \
        git -C "$dest" remote add origin "$url"; \
        git -C "$dest" fetch --depth 1 origin "$ref"; \
        git -C "$dest" checkout --detach FETCH_HEAD; \
    }; \
    clone_ref https://github.com/Comfy-Org/ComfyUI.git "$COMFYUI_REF" /opt/ComfyUI; \
    mkdir -p /opt/ComfyUI/custom_nodes; \
    clone_ref https://github.com/AHEKOT/ComfyUI_VNCCS.git "$VNCCS_REF" /opt/ComfyUI/custom_nodes/ComfyUI_VNCCS; \
    clone_ref https://github.com/AHEKOT/ComfyUI_VNCCS_Utils.git "$VNCCS_UTILS_REF" /opt/ComfyUI/custom_nodes/ComfyUI_VNCCS_Utils; \
    clone_ref https://github.com/city96/ComfyUI-GGUF.git "$GGUF_REF" /opt/ComfyUI/custom_nodes/ComfyUI-GGUF; \
    clone_ref https://github.com/ltdrdata/ComfyUI-Impact-Pack.git "$IMPACT_REF" /opt/ComfyUI/custom_nodes/ComfyUI-Impact-Pack; \
    clone_ref https://github.com/ltdrdata/ComfyUI-Impact-Subpack.git "$IMPACT_SUBPACK_REF" /opt/ComfyUI/custom_nodes/ComfyUI-Impact-Subpack; \
    clone_ref https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler.git "$SEEDVR2_REF" /opt/ComfyUI/custom_nodes/ComfyUI-SeedVR2_VideoUpscaler; \
    clone_ref https://github.com/yolain/ComfyUI-Easy-Sam3.git "$EASY_SAM3_REF" /opt/ComfyUI/custom_nodes/ComfyUI-Easy-Sam3

# Versions already proven compatible in the working Pod repair.
RUN python -m pip install --no-cache-dir --prefer-binary \
        "av==16.0.1" \
        "gguf==0.13.0" \
        "iopath==0.1.10" \
        "kornia==0.7.4" \
        "omegaconf==2.3.0" \
        "peft==0.17.0" \
        "pycocotools==2.0.10" \
        "rotary-embedding-torch==0.5.3" \
        "stringzilla==3.12.6" \
        "timm==1.0.17" \
        "transformers==4.57.6" \
        "ultralytics==8.3.162" && \
    python -m pip install --no-cache-dir \
        "git+https://github.com/facebookresearch/sam2.git@${SAM2_REF}" && \
    python /opt/scripts/install_requirements.py \
        /opt/ComfyUI/requirements.txt \
        /opt/ComfyUI/custom_nodes/ComfyUI_VNCCS/requirements.txt \
        /opt/ComfyUI/custom_nodes/ComfyUI_VNCCS_Utils/requirements.txt \
        /opt/ComfyUI/custom_nodes/ComfyUI-GGUF/requirements.txt \
        /opt/ComfyUI/custom_nodes/ComfyUI-Impact-Pack/requirements.txt \
        /opt/ComfyUI/custom_nodes/ComfyUI-Impact-Subpack/requirements.txt \
        /opt/ComfyUI/custom_nodes/ComfyUI-SeedVR2_VideoUpscaler/requirements.txt \
        /opt/ComfyUI/custom_nodes/ComfyUI-Easy-Sam3/requirements.txt && \
    python -m pip install --no-cache-dir --pre comfyui-manager

# Ephemeral Pod data lives under /workspace. No Network Volume is required.
RUN mkdir -p \
        /workspace/models \
        /workspace/input \
        /workspace/output \
        /workspace/temp \
        /workspace/user \
        /workspace/cache && \
    rm -rf \
        /opt/ComfyUI/models \
        /opt/ComfyUI/input \
        /opt/ComfyUI/output \
        /opt/ComfyUI/temp \
        /opt/ComfyUI/user && \
    ln -s /workspace/models /opt/ComfyUI/models && \
    ln -s /workspace/input /opt/ComfyUI/input && \
    ln -s /workspace/output /opt/ComfyUI/output && \
    ln -s /workspace/temp /opt/ComfyUI/temp && \
    ln -s /workspace/user /opt/ComfyUI/user

COPY scripts/verify_nodes.py /opt/scripts/verify_nodes.py
COPY scripts/smoke-test.sh /opt/scripts/smoke-test.sh
COPY scripts/start.sh /opt/scripts/start.sh

RUN chmod +x /opt/scripts/*.sh && \
    /opt/scripts/smoke-test.sh && \
    python -m pip freeze | sort > /opt/pip-freeze.txt && \
    printf '%s\n' \
      "COMFYUI_REF=${COMFYUI_REF}" \
      "VNCCS_REF=${VNCCS_REF}" \
      "VNCCS_UTILS_REF=${VNCCS_UTILS_REF}" \
      "GGUF_REF=${GGUF_REF}" \
      "IMPACT_REF=${IMPACT_REF}" \
      "IMPACT_SUBPACK_REF=${IMPACT_SUBPACK_REF}" \
      "SEEDVR2_REF=${SEEDVR2_REF}" \
      "EASY_SAM3_REF=${EASY_SAM3_REF}" \
      "SAM2_REF=${SAM2_REF}" \
      > /opt/build-info.txt

WORKDIR /opt/ComfyUI

EXPOSE 8188

HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8188/system_stats >/dev/null || exit 1

ENTRYPOINT []
CMD ["/opt/scripts/start.sh"]
