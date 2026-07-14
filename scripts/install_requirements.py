#!/usr/bin/env python3
"""Install requirements without replacing RunPod's CUDA/Torch stack."""

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

# Impact Pack lists the moving SAM2 main branch. Dockerfile installs a pinned SHA.
BLOCKED_URL_PARTS = {
    "github.com/facebookresearch/sam2",
}


def package_name(line: str) -> str | None:
    candidate = line.strip()
    if not candidate or candidate.startswith("#"):
        return None
    try:
        return canonicalize_name(Requirement(candidate).name)
    except InvalidRequirement:
        return None


def sanitize(path: Path) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    removed: list[str] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        normalized = package_name(stripped)

        if normalized in BLOCKED_PACKAGES:
            removed.append(stripped)
            continue

        lowered = stripped.lower()
        if any(part in lowered for part in BLOCKED_URL_PARTS):
            removed.append(stripped)
            continue

        kept.append(raw_line)

    return kept, removed


def install_file(path: Path) -> None:
    if not path.is_file():
        print(f"[requirements] Atlandı, bulunamadı: {path}")
        return

    kept, removed = sanitize(path)
    print(f"[requirements] Kuruluyor: {path}")
    for item in removed:
        print(f"[requirements] Koruma nedeniyle atlandı: {item}")

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
        temporary_path = Path(handle.name)

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
                str(temporary_path),
            ]
        )
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("En az bir requirements.txt yolu gerekli.")

    for argument in sys.argv[1:]:
        install_file(Path(argument))


if __name__ == "__main__":
    main()
