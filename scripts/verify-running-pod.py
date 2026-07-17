#!/usr/bin/env python3
"""Fast post-restart readiness check for a disposable RunPod."""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path


COMFYUI_DIR = Path(os.environ.get("COMFYUI_DIR", "/workspace/runpod-slim/ComfyUI"))
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")

REQUIRED_NODES = (
    "CharacterCloner",
    "VNCCS_CharacterCloneGenerator",
    "VNCCS_ControlCenter",
    "VNCCS_PoseStudio",
    "VNCCS_AutoPersonMask",
    "VNCCS_AdaptivePoseGuide",
    "VNCCS_NeutralContourPoseGuide",
    "VNCCS_AdaptiveSpritePlacement",
    "VNCCS_SavePoseSpritePackage",
)

REQUIRED_FILES = {
    "models/checkpoints/Qwen-Rapid-AIO-NSFW-v19.safetensors": 28_431_843_583,
    "models/loras/qwen/VNCCS/VNCCS_QIE2511_PoseStudio_ART_V5.9.5.safetensors": 1_179_883_808,
    "models/birefnet/BiRefNet_lite/model.safetensors": 177_634_392,
    "models/sam3dbody/model.ckpt": 2_109_129_346,
    "models/sam3dbody/assets/mhr_model.pt": 696_110_248,
    "models/sam3/sam3-fp16.safetensors": 1_720_307_872,
}


def main() -> None:
    with urllib.request.urlopen(f"{COMFYUI_URL}/object_info", timeout=30) as response:
        object_info = json.load(response)

    missing_nodes = [name for name in REQUIRED_NODES if name not in object_info]
    if missing_nodes:
        raise SystemExit("Missing registered nodes: " + ", ".join(missing_nodes))

    problems: list[str] = []
    for relative, expected_size in REQUIRED_FILES.items():
        path = COMFYUI_DIR / relative
        if not path.is_file():
            problems.append(f"missing: {path}")
        elif path.stat().st_size != expected_size:
            problems.append(
                f"wrong size: {path} ({path.stat().st_size}, expected {expected_size})"
            )

    marker = COMFYUI_DIR / "models/.vnccs-workflow-assets-verified.json"
    if not marker.is_file():
        problems.append(f"verification marker missing: {marker}")

    workflows = (
        "VNCCS_Source_Pose_To_Transparent_Sprite_Adaptive.json",
        "VNCCS_Source_Visible_Pose_To_Transparent_Sprite_No3D.json",
    )
    for name in workflows:
        path = COMFYUI_DIR / "user/default/workflows" / name
        if not path.is_file():
            problems.append(f"workflow missing: {path}")

    if problems:
        raise SystemExit("RunPod readiness check failed:\n- " + "\n- ".join(problems))

    print("RUNPOD READY: nodes, workflows and verified model assets are present.")


if __name__ == "__main__":
    main()
