#!/usr/bin/env bash
set -Eeuo pipefail

C="${COMFYUI_DIR:-/workspace/runpod-slim/ComfyUI}"
P="${COMFYUI_PYTHON:-$C/.venv-cu128/bin/python}"
LOG=/tmp/comfyui-build-smoke.log
JSON=/tmp/comfyui-object-info.json
PID=""

cleanup() {
    if [[ -n "${PID}" ]] && kill -0 "${PID}" 2>/dev/null; then
        kill "${PID}" 2>/dev/null || true
        wait "${PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT

cd "$C"

"$P" main.py \
    --cpu \
    --listen 127.0.0.1 \
    --port 8199 \
    --enable-manager \
    --disable-auto-launch \
    >"${LOG}" 2>&1 &
PID=$!

for _ in $(seq 1 120); do
    if ! kill -0 "${PID}" 2>/dev/null; then
        echo "ComfyUI exited during image build smoke test."
        cat "${LOG}"
        exit 1
    fi

    if curl -fsS http://127.0.0.1:8199/object_info >"${JSON}"; then
        "$P" /opt/vnccs/verify_nodes.py "${JSON}"
        "$P" /opt/vnccs/verify_workflows.py \
            "${JSON}" \
            /opt/vnccs/workflows/*.json
        exit 0
    fi
    sleep 2
done

echo "ComfyUI image build smoke test timed out."
cat "${LOG}"
exit 1
