#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_NODES = (
    "CharacterCreatorV2",
    "VNCCS_CharacterGenerator",
    "VNCCS_ControlCenter",
    "VNCCS_PoseStudio",
)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: verify_nodes.py object_info.json")

    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    missing = [name for name in REQUIRED_NODES if name not in data]
    if missing:
        raise SystemExit("Missing VNCCS nodes: " + ", ".join(missing))

    print("VNCCS node smoke test: OK")
    for name in REQUIRED_NODES:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
