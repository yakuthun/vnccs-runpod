# VNCCS RunPod Image

This repository builds a versioned RunPod image containing ComfyUI, pinned
upstream VNCCS packages, the project-owned `VNCCS_SourcePoseSprite` nodes, and
the two supported source-pose-to-transparent-sprite workflows.

## What this prevents

- No `pip install` or `git clone` during paid Pod startup.
- The working Torch/CUDA stack from `runpod/comfyui:cuda12.8` is preserved.
- VNCCS repositories are pinned to exact commit SHAs.
- A CPU smoke test starts ComfyUI during the Docker build.
- Every bundled workflow is compared with the real `/object_info` response.
- The image is not pushed unless the upstream nodes and these project nodes exist:
  - `CharacterCreatorV2`
  - `VNCCS_CharacterGenerator`
  - `VNCCS_ControlCenter`
  - `VNCCS_PoseStudio`
  - `VNCCS_CharacterCloneGenerator`
  - `VNCCS_AutoPersonMask`
  - `VNCCS_AdaptivePoseGuide`
  - `VNCCS_NeutralContourPoseGuide`
  - `VNCCS_AdaptiveSpritePlacement`
  - `VNCCS_SavePoseSpritePackage`

The last five entries are intentionally shipped by this repository. They are
not claimed to be part of the official AHEKOT package.

## Build the first image

1. Open the repository's **Actions** tab.
2. Select **Build VNCCS RunPod Image**.
3. Click **Run workflow**.
4. Use a new immutable version such as `v1.1.0`.
5. Wait until the workflow turns green.

After the first successful build, open the package from your GitHub profile and change package visibility to **Public**.

## RunPod template

```text
Name: VNCCS Sprite Docker v1.1
Container Image: ghcr.io/yakuthun/vnccs-runpod:v1.1.0
Container Disk: 120 GB
Volume Disk: 0 GB
Network Volume: none
HTTP Port Label: ComfyUI
HTTP Port: 8188
TCP Ports: empty
Start Command: completely empty
Docker Command: completely empty
```

The image starts ComfyUI itself. Do not add the old installation command to the template.

## First command on each disposable Pod

Models are intentionally not embedded in the Docker image. Run this once in
the Pod terminal:

```bash
/workspace/runpod-slim/ComfyUI/.venv-cu128/bin/python \
  /opt/vnccs/download-workflow-models.py
```

It downloads and SHA-256 verifies exactly:

- `Qwen-Rapid-AIO-NSFW-v19.safetensors` and `Qwen-Rapid-AIO-NSFW-v23.safetensors` from pinned Phr00t revisions.
- `VNCCS_QIE2511_PoseStudio_ART_V5.9.5.safetensors` from the pinned
  MIUProject revision.
- BiRefNet Lite used by `VNCCS_AutoPersonMask`.
- SAM 3D Body weights used by automatic Pose Studio Import.
- SAM3 FP16 used by sprite detail recovery.

After the command completes, restart ComfyUI once so its model lists refresh.
The workflows are already installed in `user/default/workflows`.

Then run the fast readiness check:

```bash
/workspace/runpod-slim/ComfyUI/.venv-cu128/bin/python \
  /opt/vnccs/verify-running-pod.py
```

Do not start paid workflow testing unless it prints `RUNPOD READY`.

## Updating

Never overwrite an existing image tag. Change pinned revisions only after
testing and publish a new tag.
