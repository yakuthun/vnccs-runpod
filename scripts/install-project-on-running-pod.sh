#!/usr/bin/env bash
set -Eeuo pipefail

# Portable fallback for an already-running stock RunPod. The preferred path is
# the immutable Docker image, but this installs only project-owned files and
# never runs pip, git, apt, or a ComfyUI update.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -n "${COMFYUI_DIR:-}" ]]; then
    C="$COMFYUI_DIR"
elif [[ -f /workspace/runpod-slim/ComfyUI/main.py ]]; then
    C=/workspace/runpod-slim/ComfyUI
elif [[ -f /workspace/ComfyUI/main.py ]]; then
    C=/workspace/ComfyUI
else
    echo "ERROR: ComfyUI directory not found. Set COMFYUI_DIR explicitly."
    exit 2
fi

if [[ ! -d "$C/custom_nodes/ComfyUI_VNCCS" ]]; then
    echo "ERROR: upstream ComfyUI_VNCCS is missing."
    exit 3
fi
if [[ ! -d "$C/custom_nodes/ComfyUI_VNCCS_Utils" ]]; then
    echo "ERROR: upstream ComfyUI_VNCCS_Utils is missing."
    exit 4
fi

if [[ -x "$C/.venv-cu128/bin/python" ]]; then
    P="$C/.venv-cu128/bin/python"
elif [[ -x "$C/.venv/bin/python" ]]; then
    P="$C/.venv/bin/python"
else
    echo "ERROR: ComfyUI virtual-environment Python was not found."
    exit 5
fi

install_project_files() {
    local target="$1"

    install -d "$target/custom_nodes/VNCCS_SourcePoseSprite/web"
    install -m 0644 "$ROOT/custom_nodes/VNCCS_SourcePoseSprite/__init__.py" \
        "$target/custom_nodes/VNCCS_SourcePoseSprite/__init__.py"
    install -m 0644 "$ROOT/custom_nodes/VNCCS_SourcePoseSprite/source_pose_sprite_nodes.py" \
        "$target/custom_nodes/VNCCS_SourcePoseSprite/source_pose_sprite_nodes.py"
    install -m 0644 "$ROOT/custom_nodes/VNCCS_SourcePoseSprite/masked_replacement_nodes.py" \
        "$target/custom_nodes/VNCCS_SourcePoseSprite/masked_replacement_nodes.py"
    install -m 0644 "$ROOT/custom_nodes/VNCCS_SourcePoseSprite/web/adaptive_pose_studio.js" \
        "$target/custom_nodes/VNCCS_SourcePoseSprite/web/adaptive_pose_studio.js"

    install -d "$target/user/default/workflows"
    install -m 0644 "$ROOT/VNCCS_Source_Pose_To_Transparent_Sprite_Adaptive.json" \
        "$target/user/default/workflows/VNCCS_Source_Pose_To_Transparent_Sprite_Adaptive.json"
    install -m 0644 "$ROOT/VNCCS_Source_Visible_Pose_To_Transparent_Sprite_No3D.json" \
        "$target/user/default/workflows/VNCCS_Source_Visible_Pose_To_Transparent_Sprite_No3D.json"
    install -m 0644 "$ROOT/Qwen_Two_Image_Pose_Character_Replacement_v19.json" \
        "$target/user/default/workflows/Qwen_Two_Image_Pose_Character_Replacement_v19.json"
}

install_project_files "$C"

# RunPod's stock /start.sh restores /workspace from this baked tree during a
# container restart.  Patch it too, otherwise a correct hotfix is overwritten
# by the older image contents on the next restart.
BAKED=/opt/comfyui-baked
if [[ -f "$BAKED/main.py" && "$BAKED" != "$C" ]]; then
    install_project_files "$BAKED"
    echo "Baked RunPod ComfyUI source updated: $BAKED"
fi

"$P" -m py_compile \
    "$C/custom_nodes/VNCCS_SourcePoseSprite/source_pose_sprite_nodes.py" \
    "$C/custom_nodes/VNCCS_SourcePoseSprite/masked_replacement_nodes.py"

echo "Runtime and baked project node packages/workflows installed successfully."
echo "Restart the existing ComfyUI process once, then verify /object_info."
