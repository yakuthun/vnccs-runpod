# syntax=docker/dockerfile:1.7

# Pin the linux/amd64 image behind cuda12.8. The mutable tag switched to the
# 1.4.4 layout, where ComfyUI is baked under /opt and copied on first startup.
FROM runpod/comfyui:cuda12.8@sha256:7078f94dbe28d079c487c245dc3524443e2c6225a6208a1fff8c7a652c1b3a40

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
    PIP_CONSTRAINT=/opt/comfyui-runtime-constraints.txt \
    COMFYUI_DIR=/workspace/runpod-slim/ComfyUI \
    COMFYUI_PYTHON=/workspace/runpod-slim/ComfyUI/.venv-cu128/bin/python

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
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
        pkg-config && \
    rm -rf /var/lib/apt/lists/*

COPY scripts/install_requirements.py /opt/vnccs/install_requirements.py

RUN if [[ ! -f /opt/comfyui-baked/main.py ]]; then \
        echo "ERROR: Base image does not contain /opt/comfyui-baked/main.py" >&2; \
        exit 19; \
    fi; \
    rm -rf "${COMFYUI_DIR}"; \
    cp -a /opt/comfyui-baked "${COMFYUI_DIR}"; \
    python3.12 -m venv --system-site-packages "${COMFYUI_DIR}/.venv-cu128"; \
    "${COMFYUI_PYTHON}" -m ensurepip; \
    if [[ ! -f "${COMFYUI_DIR}/main.py" ]]; then \
        echo "ERROR: ComfyUI main.py not found at ${COMFYUI_DIR}/main.py" >&2; \
        exit 20; \
    fi; \
    if [[ ! -x "${COMFYUI_PYTHON}" ]]; then \
        echo "ERROR: ComfyUI Python is missing or not executable at ${COMFYUI_PYTHON}" >&2; \
        exit 21; \
    fi; \
    mkdir -p "${COMFYUI_DIR}/custom_nodes"; \
    clone_ref() { \
        local url="$1" ref="$2" dest="$3"; \
        rm -rf "$dest"; \
        git init "$dest"; \
        git -C "$dest" remote add origin "$url"; \
        git -C "$dest" fetch --depth 1 origin "$ref"; \
        git -C "$dest" checkout --detach FETCH_HEAD; \
    }; \
    clone_ref https://github.com/AHEKOT/ComfyUI_VNCCS.git "$VNCCS_REF" "${COMFYUI_DIR}/custom_nodes/ComfyUI_VNCCS"; \
    clone_ref https://github.com/AHEKOT/ComfyUI_VNCCS_Utils.git "$VNCCS_UTILS_REF" "${COMFYUI_DIR}/custom_nodes/ComfyUI_VNCCS_Utils"; \
    clone_ref https://github.com/city96/ComfyUI-GGUF.git "$GGUF_REF" "${COMFYUI_DIR}/custom_nodes/ComfyUI-GGUF"; \
    clone_ref https://github.com/ltdrdata/ComfyUI-Impact-Pack.git "$IMPACT_REF" "${COMFYUI_DIR}/custom_nodes/ComfyUI-Impact-Pack"; \
    clone_ref https://github.com/ltdrdata/ComfyUI-Impact-Subpack.git "$IMPACT_SUBPACK_REF" "${COMFYUI_DIR}/custom_nodes/ComfyUI-Impact-Subpack"; \
    clone_ref https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler.git "$SEEDVR2_REF" "${COMFYUI_DIR}/custom_nodes/ComfyUI-SeedVR2_VideoUpscaler"; \
    clone_ref https://github.com/yolain/ComfyUI-Easy-Sam3.git "$EASY_SAM3_REF" "${COMFYUI_DIR}/custom_nodes/ComfyUI-Easy-Sam3"

# Keep the base image's Torch/CUDA stack untouched. The helper removes torch,
# torchvision, torchaudio, triton and llama-cpp-python from node requirements.
RUN "${COMFYUI_PYTHON}" -m pip install --no-cache-dir --upgrade "pip<26" packaging setuptools wheel && \
    "${COMFYUI_PYTHON}" -m pip install --no-cache-dir --prefer-binary \
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
    "${COMFYUI_PYTHON}" -m pip install --no-cache-dir \
        "git+https://github.com/facebookresearch/sam2.git@${SAM2_REF}" && \
    "${COMFYUI_PYTHON}" /opt/vnccs/install_requirements.py \
        "${COMFYUI_DIR}/custom_nodes/ComfyUI_VNCCS/requirements.txt" \
        "${COMFYUI_DIR}/custom_nodes/ComfyUI_VNCCS_Utils/requirements.txt" \
        "${COMFYUI_DIR}/custom_nodes/ComfyUI-GGUF/requirements.txt" \
        "${COMFYUI_DIR}/custom_nodes/ComfyUI-Impact-Pack/requirements.txt" \
        "${COMFYUI_DIR}/custom_nodes/ComfyUI-Impact-Subpack/requirements.txt" \
        "${COMFYUI_DIR}/custom_nodes/ComfyUI-SeedVR2_VideoUpscaler/requirements.txt" \
        "${COMFYUI_DIR}/custom_nodes/ComfyUI-Easy-Sam3/requirements.txt" && \
    "${COMFYUI_PYTHON}" -m pip install --no-cache-dir --no-deps --pre --upgrade comfyui-manager && \
    "${COMFYUI_PYTHON}" -c 'import torch; print("Torch preserved:", torch.__version__, "CUDA:", torch.version.cuda)'

COPY scripts/verify_nodes.py /opt/vnccs/verify_nodes.py
COPY scripts/smoke-test.sh /opt/vnccs/smoke-test.sh
COPY scripts/start.sh /opt/vnccs/start.sh

RUN chmod +x /opt/vnccs/*.sh && \
    /opt/vnccs/smoke-test.sh && \
    "${COMFYUI_PYTHON}" -m pip freeze | sort > /opt/vnccs/pip-freeze.txt && \
    printf '%s\n' \
      "BASE_IMAGE=runpod/comfyui:cuda12.8" \
      "VNCCS_REF=${VNCCS_REF}" \
      "VNCCS_UTILS_REF=${VNCCS_UTILS_REF}" \
      "GGUF_REF=${GGUF_REF}" \
      "IMPACT_REF=${IMPACT_REF}" \
      "IMPACT_SUBPACK_REF=${IMPACT_SUBPACK_REF}" \
      "SEEDVR2_REF=${SEEDVR2_REF}" \
      "EASY_SAM3_REF=${EASY_SAM3_REF}" \
      "SAM2_REF=${SAM2_REF}" \
      > /opt/vnccs/build-info.txt

WORKDIR ${COMFYUI_DIR}

EXPOSE 8188

HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8188/system_stats >/dev/null || exit 1

ENTRYPOINT []
CMD ["/opt/vnccs/start.sh"]
