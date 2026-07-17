#!/usr/bin/env bash
set -Eeuo pipefail

: "${COMFYUI_DIR:?COMFYUI_DIR is required}"
: "${VNCCS_REF:?VNCCS_REF is required}"
: "${VNCCS_UTILS_REF:?VNCCS_UTILS_REF is required}"
: "${GGUF_REF:?GGUF_REF is required}"
: "${IMPACT_REF:?IMPACT_REF is required}"
: "${IMPACT_SUBPACK_REF:?IMPACT_SUBPACK_REF is required}"
: "${SEEDVR2_REF:?SEEDVR2_REF is required}"
: "${EASY_SAM3_REF:?EASY_SAM3_REF is required}"

CUSTOM_NODES_DIR="${COMFYUI_DIR}/custom_nodes"
mkdir -p "${CUSTOM_NODES_DIR}"

clone_ref() {
    local url="$1"
    local ref="$2"
    local directory_name="$3"
    local dest="${CUSTOM_NODES_DIR}/${directory_name}"
    local expected_root resolved_dest actual

    expected_root="$(realpath -m "${CUSTOM_NODES_DIR}")"
    resolved_dest="$(realpath -m "${dest}")"
    case "${resolved_dest}" in
        "${expected_root}"/*) ;;
        *)
            echo "ERROR: refusing unsafe custom-node destination: ${resolved_dest}" >&2
            exit 20
            ;;
    esac

    rm -rf -- "${resolved_dest}"
    git init "${resolved_dest}"
    git -C "${resolved_dest}" remote add origin "${url}"
    git -C "${resolved_dest}" fetch --depth 1 origin "${ref}"
    git -C "${resolved_dest}" checkout --detach FETCH_HEAD

    actual="$(git -C "${resolved_dest}" rev-parse HEAD)"
    if [[ "${actual}" != "${ref}" ]]; then
        echo "ERROR: ${directory_name} resolved to ${actual}, expected ${ref}" >&2
        exit 21
    fi
    echo "Pinned ${directory_name}: ${actual}"
}

clone_ref https://github.com/AHEKOT/ComfyUI_VNCCS.git \
    "${VNCCS_REF}" ComfyUI_VNCCS
clone_ref https://github.com/AHEKOT/ComfyUI_VNCCS_Utils.git \
    "${VNCCS_UTILS_REF}" ComfyUI_VNCCS_Utils
clone_ref https://github.com/city96/ComfyUI-GGUF.git \
    "${GGUF_REF}" ComfyUI-GGUF
clone_ref https://github.com/ltdrdata/ComfyUI-Impact-Pack.git \
    "${IMPACT_REF}" ComfyUI-Impact-Pack
clone_ref https://github.com/ltdrdata/ComfyUI-Impact-Subpack.git \
    "${IMPACT_SUBPACK_REF}" ComfyUI-Impact-Subpack
clone_ref https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler.git \
    "${SEEDVR2_REF}" ComfyUI-SeedVR2_VideoUpscaler
clone_ref https://github.com/yolain/ComfyUI-Easy-Sam3.git \
    "${EASY_SAM3_REF}" ComfyUI-Easy-Sam3
