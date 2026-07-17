# VNCCS RunPod Image

This repository builds a versioned RunPod image with ComfyUI, the required
VNCCS custom nodes, and the validated Q4/Anima model profile installed before
the Pod starts.

## What this prevents

- No `pip install` or `git clone` during paid Pod startup.
- The working Torch/CUDA stack from `runpod/comfyui:cuda12.8` is preserved.
- VNCCS repositories are pinned to exact commit SHAs.
- A CPU smoke test starts ComfyUI during the Docker build.
- Model sources are pinned to immutable revisions and SHA256-verified.
- Q4, Anima, SeedVR2, SAM3, Impact face detection, and their required
  encoders/VAE/LoRAs are available without runtime downloads.
- The image is not pushed unless these nodes exist:
  - `CharacterCreatorV2`
  - `VNCCS_CharacterGenerator`
  - `VNCCS_ControlCenter`
  - `VNCCS_PoseStudio`

## Preloaded model profile

`v1.1.0` contains the models used by the validated workflows:

- Qwen Image Edit 2511 GGUF Q4 (Q5 is intentionally excluded)
- Qwen 2.5 VL text encoder and Qwen Image VAE
- VNCCS Clothes Core, Pose Studio, and Qwen Lightning LoRAs
- Anima Base v1.0, Qwen 3 0.6B text encoder, and Anima Turbo LoRA
- SeedVR2 3B Q4 and its FP16 VAE
- Easy SAM3 FP16
- Impact Pack `face_yolov8m.pt` and `sam_vit_b_01ec64.pth`

GHCR limits each layer to 10 GB. The 11.85 GB Q4 model and 9.38 GB text
encoder are therefore stored as verified 3 GB image parts. On a fresh Pod,
`start.sh` assembles both from local image data before starting ComfyUI. This
uses no network and requires enough container disk for the assembled files.
Keep the RunPod container disk at **120 GB**. The image payload is about
33.84 GB and first startup materializes another 21.24 GB from the local parts.

## Build the image

1. Open the repository's **Actions** tab.
2. Select **Build VNCCS RunPod Image**.
3. Click **Run workflow**.
4. Keep the version as `v1.1.0`.
5. Wait until the workflow turns green.

After the first successful build, open the package from your GitHub profile and change package visibility to **Public**.

## RunPod template

```text
Name: VNCCS Docker v1
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

## Updating

Never overwrite a published version tag. Change pinned revisions or the model
manifest and build a new tag such as `v1.1.1`.
