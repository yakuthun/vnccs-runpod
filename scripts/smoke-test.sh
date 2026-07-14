#!/usr/bin/env bash
set -Eeuo pipefail

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

cd /opt/ComfyUI

python main.py \
    --cpu \
    --listen 127.0.0.1 \
    --port 8188 \
    --enable-manager \
    --disable-auto-launch \
    --input-directory /workspace/input \
    --output-directory /workspace/output \
    --temp-directory /workspace/temp \
    >"${LOG}" 2>&1 &
PID=$!

for _ in $(seq 1 120); do
    if ! kill -0 "${PID}" 2>/dev/null; then
        echo "ComfyUI build smoke test sırasında kapandı."
        cat "${LOG}"
        exit 1
    fi

    if curl -fsS http://127.0.0.1:8188/object_info >"${JSON}"; then
        python /opt/scripts/verify_nodes.py "${JSON}"
        exit 0
    fi

    sleep 2
done

echo "ComfyUI build smoke test zaman aşımına uğradı."
cat "${LOG}"
exit 1
