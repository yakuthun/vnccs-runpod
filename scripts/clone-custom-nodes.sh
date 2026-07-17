#!/usr/bin/env bash
set -Eeuo pipefail

on_error() {
    local exit_code="$?"
    echo "ERROR: custom-node bootstrap failed at line ${BASH_LINENO[0]} while running: ${BASH_COMMAND}" >&2
    exit "${exit_code}"
}
trap on_error ERR

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

case "${CUSTOM_NODES_DIR}" in
    /*) ;;
    *)
        echo "ERROR: COMFYUI_DIR must be an absolute path, got: ${COMFYUI_DIR}" >&2
        exit 20
        ;;
esac

if ! command -v git >/dev/null 2>&1; then
    echo "ERROR: git is not installed in the base image." >&2
    exit 21
fi

echo "Bootstrapping pinned custom nodes into ${CUSTOM_NODES_DIR}"
git --version

fetch_pinned_ref() {
    local dest="$1"
    local ref="$2"
    local attempt

    for attempt in 1 2 3; do
        if GIT_TERMINAL_PROMPT=0 git -C "${dest}" \
            -c http.version=HTTP/1.1 fetch --depth=1 origin "${ref}"; then
            return 0
        fi
        echo "WARN: fetch attempt ${attempt}/3 failed for ${ref}; retrying..." >&2
        sleep "${attempt}"
    done

    echo "ERROR: could not fetch pinned ref ${ref} after three attempts." >&2
    return 1
}

clone_ref() {
    local url="$1"
    local ref="$2"
    local directory_name="$3"
    local dest="${CUSTOM_NODES_DIR}/${directory_name}"
    local actual

    case "${directory_name}" in
        ComfyUI_VNCCS|ComfyUI_VNCCS_Utils|ComfyUI-GGUF|ComfyUI-Impact-Pack|ComfyUI-Impact-Subpack|ComfyUI-SeedVR2_VideoUpscaler|ComfyUI-Easy-Sam3) ;;
        *)
            echo "ERROR: unsupported custom-node destination: ${directory_name}" >&2
            exit 22
            ;;
    esac

    echo "Installing ${directory_name} at pinned ref ${ref}"
    rm -rf -- "${dest}"
    git init --quiet "${dest}"
    git -C "${dest}" remote add origin "${url}"
    fetch_pinned_ref "${dest}" "${ref}"
    git -C "${dest}" checkout --detach --quiet FETCH_HEAD

    actual="$(git -C "${dest}" rev-parse HEAD)"
    if [[ "${actual}" != "${ref}" ]]; then
        echo "ERROR: ${directory_name} resolved to ${actual}, expected ${ref}" >&2
        exit 23
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
