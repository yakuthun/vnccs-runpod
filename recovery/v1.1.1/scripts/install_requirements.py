#!/usr/bin/env python3
"""Install custom-node requirements without replacing CUDA/Torch packages."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

BLOCKED_PACKAGES = {
    "torch",
    "torchvision",
    "torchaudio",
    "triton",
    "llama-cpp-python",
}

BLOCKED_URL_PARTS = {
    "github.com/facebookresearch/sam2",
}


def requirement_name(line: str) -> str | None:
    value = line.strip()
    if not value or value.startswith("#"):
        return None
    try:
        return canonicalize_name(Requirement(value).name)
    except InvalidRequirement:
        return None


def sanitize(path: Path) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    removed: list[str] = []

    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if requirement_name(stripped) in BLOCKED_PACKAGES:
            removed.append(stripped)
            continue
        if any(part in stripped.lower() for part in BLOCKED_URL_PARTS):
            removed.append(stripped)
            continue
        kept.append(raw)

    return kept, removed


def install(path: Path) -> None:
    if not path.is_file():
        print(f"[requirements] Missing, skipped: {path}")
        return

    kept, removed = sanitize(path)
    print(f"[requirements] Installing: {path}")
    for item in removed:
        print(f"[requirements] Protected package skipped: {item}")

    content = "\n".join(kept).strip()
    if not content:
        return

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".txt",
        delete=False,
    ) as handle:
        handle.write(content + "\n")
        temp_path = Path(handle.name)

    try:
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-cache-dir",
                "--prefer-binary",
                "--upgrade-strategy",
                "only-if-needed",
                "-r",
                str(temp_path),
            ]
        )
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("At least one requirements.txt path is required.")
    for argument in sys.argv[1:]:
        install(Path(argument))


if __name__ == "__main__":
    main()
