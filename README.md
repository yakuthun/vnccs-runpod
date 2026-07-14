# VNCCS RunPod Image

This repository builds a versioned RunPod image with ComfyUI and all required VNCCS custom nodes installed before the Pod starts.

## What this prevents

- No `pip install` or `git clone` during paid Pod startup.
- The working Torch/CUDA stack from `runpod/comfyui:cuda12.8` is preserved.
- VNCCS repositories are pinned to exact commit SHAs.
- A CPU smoke test starts ComfyUI during the Docker build.
- The image is not pushed unless these nodes exist:
  - `CharacterCreatorV2`
  - `VNCCS_CharacterGenerator`
  - `VNCCS_ControlCenter`
  - `VNCCS_PoseStudio`

## Build the first image

1. Open the repository's **Actions** tab.
2. Select **Build VNCCS RunPod Image**.
3. Click **Run workflow**.
4. Keep the version as `v1.0.0`.
5. Wait until the workflow turns green.

After the first successful build, open the package from your GitHub profile and change package visibility to **Public**.

## RunPod template

```text
Name: VNCCS Docker v1
Container Image: ghcr.io/yakuthun/vnccs-runpod:v1.0.0
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

## Updating

Never overwrite `v1.0.0`. Change pinned revisions in the Dockerfile and build a new tag such as `v1.0.1`.
