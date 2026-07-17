#!/usr/bin/env python3
"""Download, verify, and assemble the immutable VNCCS model set."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

import requests


DEFAULT_MANIFEST = Path("/opt/vnccs/preloaded-models.json")
DEFAULT_COMFYUI = Path(os.environ.get("COMFYUI_DIR", "/workspace/runpod-slim/ComfyUI"))
PARTS_DIR = Path("/opt/vnccs/model-parts")
BUFFER_SIZE = 8 * 1024 * 1024


def load_manifest(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("schema_version") != 1:
        raise RuntimeError(f"Unsupported model manifest: {path}")
    return manifest


def get_model(manifest: dict, model_id: str) -> dict:
    for model in manifest["models"]:
        if model["id"] == model_id:
            return model
    raise RuntimeError(f"Unknown model id: {model_id}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(BUFFER_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path: Path, size: int, expected_sha256: str) -> None:
    actual_size = path.stat().st_size
    if actual_size != size:
        raise RuntimeError(f"Size mismatch for {path}: expected {size}, got {actual_size}")
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"SHA256 mismatch for {path}: expected {expected_sha256}, got {actual_sha256}"
        )


def part_count(model: dict, part_size: int) -> int:
    return math.ceil(model["size"] / part_size)


def part_path(model_id: str, index: int) -> Path:
    return PARTS_DIR / f"{model_id}.part-{index:03d}"


def stream_download(
    url: str,
    destination: Path,
    expected_size: int,
    byte_range: tuple[int, int] | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    headers = {"User-Agent": "vnccs-runpod-model-preloader/1.0"}
    if byte_range is not None:
        headers["Range"] = f"bytes={byte_range[0]}-{byte_range[1]}"

    for attempt in range(1, 6):
        partial.unlink(missing_ok=True)
        started = time.monotonic()
        downloaded = 0
        try:
            with requests.get(url, headers=headers, stream=True, timeout=(30, 120)) as response:
                response.raise_for_status()
                if byte_range is not None:
                    if response.status_code != 206:
                        raise RuntimeError(
                            f"Server ignored Range request for {url}: HTTP {response.status_code}"
                        )
                    expected_content_range = (
                        f"bytes {byte_range[0]}-{byte_range[1]}/"
                    )
                    content_range = response.headers.get("Content-Range", "")
                    if not content_range.startswith(expected_content_range):
                        raise RuntimeError(
                            f"Unexpected Content-Range for {url}: {content_range!r}"
                        )

                with partial.open("wb") as handle:
                    last_report = started
                    for chunk in response.iter_content(chunk_size=BUFFER_SIZE):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        downloaded += len(chunk)
                        now = time.monotonic()
                        if now - last_report >= 20:
                            percent = 100 * downloaded / expected_size
                            print(
                                f"  {destination.name}: {downloaded / 1e9:.2f}/"
                                f"{expected_size / 1e9:.2f} GB ({percent:.1f}%)",
                                flush=True,
                            )
                            last_report = now

            if downloaded != expected_size:
                raise RuntimeError(
                    f"Downloaded size mismatch for {url}: expected {expected_size}, got {downloaded}"
                )
            os.replace(partial, destination)
            elapsed = max(time.monotonic() - started, 0.001)
            print(
                f"Downloaded {destination} ({downloaded / 1e9:.2f} GB, "
                f"{downloaded / elapsed / 1e6:.1f} MB/s)",
                flush=True,
            )
            return
        except Exception as exc:
            partial.unlink(missing_ok=True)
            if attempt == 5:
                raise
            delay = attempt * 5
            print(f"Download attempt {attempt}/5 failed: {exc}; retrying in {delay}s", flush=True)
            time.sleep(delay)


def download_model(manifest: dict, model: dict, comfyui: Path, part_index: int | None) -> None:
    if model.get("split"):
        if part_index is None:
            raise RuntimeError(f"Split model {model['id']} requires --part-index")
        part_size = int(manifest["part_size"])
        count = part_count(model, part_size)
        if part_index < 0 or part_index >= count:
            raise RuntimeError(f"Part index for {model['id']} must be between 0 and {count - 1}")
        start = part_index * part_size
        end = min(model["size"], start + part_size) - 1
        destination = part_path(model["id"], part_index)
        expected_size = end - start + 1
        if destination.exists() and destination.stat().st_size == expected_size:
            print(f"Part already present: {destination}")
            return
        stream_download(model["url"], destination, expected_size, (start, end))
        return

    if part_index is not None:
        raise RuntimeError(f"Non-split model {model['id']} does not accept --part-index")
    destination = comfyui / model["destination"]
    if destination.exists():
        try:
            verify_file(destination, model["size"], model["sha256"])
            print(f"Model already verified: {destination}")
            return
        except RuntimeError:
            destination.unlink()
    stream_download(model["url"], destination, model["size"])
    verify_file(destination, model["size"], model["sha256"])
    print(f"Verified {model['id']}: {model['sha256']}")


def hash_parts(model: dict, part_size: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    for index in range(part_count(model, part_size)):
        path = part_path(model["id"], index)
        if not path.is_file():
            raise RuntimeError(f"Missing model part: {path}")
        expected_part_size = min(part_size, model["size"] - index * part_size)
        if path.stat().st_size != expected_part_size:
            raise RuntimeError(
                f"Part size mismatch for {path}: expected {expected_part_size}, got {path.stat().st_size}"
            )
        with path.open("rb") as handle:
            while chunk := handle.read(BUFFER_SIZE):
                total += len(chunk)
                digest.update(chunk)
    return total, digest.hexdigest()


def verify_all(manifest: dict, comfyui: Path) -> None:
    part_size = int(manifest["part_size"])
    for model in manifest["models"]:
        if model.get("split"):
            size, digest = hash_parts(model, part_size)
            if size != model["size"] or digest != model["sha256"]:
                raise RuntimeError(
                    f"Combined part verification failed for {model['id']}: "
                    f"size={size}, sha256={digest}"
                )
            print(f"Verified split model {model['id']}: {digest}")
        else:
            path = comfyui / model["destination"]
            verify_file(path, model["size"], model["sha256"])
            print(f"Verified model {model['id']}: {model['sha256']}")


def assemble_models(manifest: dict, comfyui: Path) -> None:
    part_size = int(manifest["part_size"])
    for model in manifest["models"]:
        if not model.get("split"):
            continue
        destination = comfyui / model["destination"]
        if destination.exists():
            try:
                verify_file(destination, model["size"], model["sha256"])
                print(f"Preloaded model ready: {destination}")
                continue
            except RuntimeError as exc:
                print(f"Replacing invalid assembled model: {exc}", flush=True)
                destination.unlink()

        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".assembling")
        partial.unlink(missing_ok=True)
        print(f"Assembling {model['id']} into {destination}...", flush=True)
        with partial.open("wb") as output:
            for index in range(part_count(model, part_size)):
                source = part_path(model["id"], index)
                with source.open("rb") as handle:
                    while chunk := handle.read(BUFFER_SIZE):
                        output.write(chunk)
        verify_file(partial, model["size"], model["sha256"])
        os.replace(partial, destination)
        print(f"Assembled and verified {model['id']}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--comfyui", type=Path, default=DEFAULT_COMFYUI)
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser("download")
    download.add_argument("--id", required=True)
    download.add_argument("--part-index", type=int)
    subparsers.add_parser("verify")
    subparsers.add_parser("assemble")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.manifest)
    if args.command == "download":
        download_model(manifest, get_model(manifest, args.id), args.comfyui, args.part_index)
    elif args.command == "verify":
        verify_all(manifest, args.comfyui)
    elif args.command == "assemble":
        assemble_models(manifest, args.comfyui)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr, flush=True)
        raise
