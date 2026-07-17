#!/usr/bin/env python3
"""Download and verify runtime assets used by the bundled VNCCS workflows.

Custom nodes and Python dependencies belong in the immutable Docker image.
Large models are deliberately downloaded to each disposable Pod, but are
pinned to immutable Hugging Face revisions and verified by SHA-256.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download


COMFYUI_DIR = Path(os.environ.get("COMFYUI_DIR", "/workspace/runpod-slim/ComfyUI"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(path: Path, expected_size: int, expected_sha256: str) -> bool:
    if not path.is_file() or path.stat().st_size != expected_size:
        return False
    print(f"Verifying SHA-256: {path}", flush=True)
    actual = sha256(path)
    if actual != expected_sha256:
        raise RuntimeError(
            f"Hash mismatch for {path}: expected {expected_sha256}, got {actual}"
        )
    return True


def download_checkpoint_v19() -> Path:
    target = COMFYUI_DIR / "models/checkpoints/Qwen-Rapid-AIO-NSFW-v19.safetensors"
    expected_size = 28_431_843_583
    expected_hash = "ba71575515709c9912560d1176b2386eaa49294fedc6ce57b9734aa57e91e5ac"
    if verify(target, expected_size, expected_hash):
        print(f"Checkpoint already ready: {target}")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / ".hf-v19-download"
    staging.mkdir(parents=True, exist_ok=True)
    downloaded = Path(
        hf_hub_download(
            repo_id="Phr00t/Qwen-Image-Edit-Rapid-AIO",
            filename="v19/Qwen-Rapid-AIO-NSFW-v19.safetensors",
            revision="88c705939c00b3833a4fff1bce35e3ca648cab83",
            local_dir=staging,
        )
    )
    if target.exists():
        target.unlink()
    shutil.move(str(downloaded), str(target))
    verify(target, expected_size, expected_hash)
    print(f"Checkpoint ready: {target}")
    return target


def download_checkpoint_v23() -> Path:
    target = COMFYUI_DIR / "models/checkpoints/Qwen-Rapid-AIO-NSFW-v23.safetensors"
    expected_size = 28_431_840_023
    expected_hash = "fdb919fc81bea63f13759967fc92c9118142e5c70d4e6795199233a35eefa233"
    if verify(target, expected_size, expected_hash):
        print(f"Checkpoint already ready: {target}")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / ".hf-v23-download"
    staging.mkdir(parents=True, exist_ok=True)
    downloaded = Path(
        hf_hub_download(
            repo_id="Phr00t/Qwen-Image-Edit-Rapid-AIO",
            filename="v23/Qwen-Rapid-AIO-NSFW-v23.safetensors",
            revision="0758cce6dc3a0f5651de28369f56bad1c989d4a3",
            local_dir=staging,
        )
    )
    if target.exists():
        target.unlink()
    shutil.move(str(downloaded), str(target))
    verify(target, expected_size, expected_hash)
    print(f"Checkpoint ready: {target}")
    return target


def download_pose_lora() -> Path:
    relative = Path(
        "models/loras/qwen/VNCCS/"
        "VNCCS_QIE2511_PoseStudio_ART_V5.9.5.safetensors"
    )
    target = COMFYUI_DIR / relative
    expected_size = 1_179_883_808
    expected_hash = "f81f7f446f56188d96a1094ffe5d4183e7e4473d27eebb43e4c9555d3537bbb8"
    if verify(target, expected_size, expected_hash):
        print(f"Pose Studio LoRA already ready: {target}")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    downloaded = Path(
        hf_hub_download(
            repo_id="MIUProject/VNCCS_PoseStudio",
            filename=relative.as_posix(),
            revision="5719f5f86fdf33f4c5fa918c562d5ea62985d5e8",
            local_dir=COMFYUI_DIR,
        )
    )
    if downloaded.resolve() != target.resolve():
        if target.exists():
            target.unlink()
        shutil.move(str(downloaded), str(target))
    verify(target, expected_size, expected_hash)
    print(f"Pose Studio LoRA ready: {target}")
    return target


def download_birefnet() -> Path:
    target_dir = COMFYUI_DIR / "models/birefnet/BiRefNet_lite"
    target = target_dir / "model.safetensors"
    expected_size = 177_634_392
    expected_hash = "4417d89795250e698c3cb0ae8df15743810065f646f48a694fdfa7ca052d0815"
    if verify(target, expected_size, expected_hash) and (target_dir / "config.json").is_file():
        print(f"BiRefNet Lite already ready: {target_dir}")
        return target

    snapshot_download(
        repo_id="ZhengPeng7/BiRefNet_lite",
        revision="7838f1c3472f827cd8ce13ab5ccc2ce48077360f",
        local_dir=target_dir,
        allow_patterns=["*.py", "*.json", "model.safetensors"],
    )
    verify(target, expected_size, expected_hash)
    print(f"BiRefNet Lite ready: {target_dir}")
    return target


def download_sam3d_body() -> tuple[Path, Path]:
    target_dir = COMFYUI_DIR / "models/sam3dbody"
    checkpoint = target_dir / "model.ckpt"
    rig = target_dir / "assets/mhr_model.pt"
    checkpoint_ok = verify(
        checkpoint,
        2_109_129_346,
        "b5a2f9d305dd02626b967aa2e86021fba07065df66ce7a7e00ffb9664f150abf",
    )
    rig_ok = verify(
        rig,
        696_110_248,
        "352e271a6c42729c68554ceaea0c955e866970160c31e35506d782dc0f7377bc",
    )
    if checkpoint_ok and rig_ok and (target_dir / "model_config.yaml").is_file():
        print(f"SAM 3D Body already ready: {target_dir}")
        return checkpoint, rig

    snapshot_download(
        repo_id="jetjodh/sam-3d-body-dinov3",
        revision="1f026b2cc9076fd460243dae553cff9b0dcd199d",
        local_dir=target_dir,
        allow_patterns=["model.ckpt", "model_config.yaml", "assets/mhr_model.pt"],
    )
    verify(
        checkpoint,
        2_109_129_346,
        "b5a2f9d305dd02626b967aa2e86021fba07065df66ce7a7e00ffb9664f150abf",
    )
    verify(
        rig,
        696_110_248,
        "352e271a6c42729c68554ceaea0c955e866970160c31e35506d782dc0f7377bc",
    )
    print(f"SAM 3D Body ready: {target_dir}")
    return checkpoint, rig


def download_sam3_details() -> Path:
    target = COMFYUI_DIR / "models/sam3/sam3-fp16.safetensors"
    expected_size = 1_720_307_872
    expected_hash = "be55ae841767fe27e542eb3476926da61083fe58f2d95895ad5ba745fa1f41b3"
    if verify(target, expected_size, expected_hash):
        print(f"SAM3 details model already ready: {target}")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    downloaded = Path(
        hf_hub_download(
            repo_id="yolain/sam3-safetensors",
            filename="sam3-fp16.safetensors",
            revision="eb174af94625028887dfe92d2d8483ca5a5d3336",
            local_dir=target.parent,
        )
    )
    if downloaded.resolve() != target.resolve():
        if target.exists():
            target.unlink()
        shutil.move(str(downloaded), str(target))
    verify(target, expected_size, expected_hash)
    print(f"SAM3 details model ready: {target}")
    return target


def main() -> None:
    if not (COMFYUI_DIR / "main.py").is_file():
        raise SystemExit(f"ComfyUI not found at {COMFYUI_DIR}")
    download_checkpoint_v19()
    download_checkpoint_v23()
    download_pose_lora()
    download_birefnet()
    download_sam3d_body()
    download_sam3_details()
    marker = COMFYUI_DIR / "models/.vnccs-workflow-assets-verified.json"
    marker.write_text(
        json.dumps(
            {
                "checkpoint_v19": "Qwen-Rapid-AIO-NSFW-v19.safetensors",
                "checkpoint_v19_revision": "88c705939c00b3833a4fff1bce35e3ca648cab83",
                "checkpoint_v23": "Qwen-Rapid-AIO-NSFW-v23.safetensors",
                "checkpoint_v23_revision": "0758cce6dc3a0f5651de28369f56bad1c989d4a3",
                "pose_lora": "VNCCS_QIE2511_PoseStudio_ART_V5.9.5.safetensors",
                "pose_lora_revision": "5719f5f86fdf33f4c5fa918c562d5ea62985d5e8",
                "birefnet_revision": "7838f1c3472f827cd8ce13ab5ccc2ce48077360f",
                "sam3d_revision": "1f026b2cc9076fd460243dae553cff9b0dcd199d",
                "sam3_revision": "eb174af94625028887dfe92d2d8483ca5a5d3336",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("All workflow model assets are present and verified.")


if __name__ == "__main__":
    main()
