# VNCCS New Pod Kit

This kit contains the project-owned nodes and the two supported workflows. The
classes prefixed with `VNCCS_` in this package are compatibility names used by
the workflows; they are not represented as upstream AHEKOT nodes.

## Preferred installation

Use the immutable image built from this repository:

```text
ghcr.io/yakuthun/vnccs-runpod:v1.1.0
```

The GitHub Actions build must be green before this tag is used.

## Fallback on an already-running Pod

The Pod must already contain the pinned `ComfyUI_VNCCS` and
`ComfyUI_VNCCS_Utils` packages. Upload and extract this kit, then run from the
extracted root:

```bash
bash scripts/install-project-on-running-pod.sh
```

Restart ComfyUI once. Then download and verify all runtime model assets:

```bash
/workspace/runpod-slim/ComfyUI/.venv-cu128/bin/python \
  scripts/download-workflow-models.py
```

Restart ComfyUI once more and verify readiness:

```bash
/workspace/runpod-slim/ComfyUI/.venv-cu128/bin/python \
  scripts/verify-running-pod.py
```

Continue only if the final command prints `RUNPOD READY`.
