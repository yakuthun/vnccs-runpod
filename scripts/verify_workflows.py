#!/usr/bin/env python3
"""Fail an image build when a bundled ComfyUI workflow needs missing nodes."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def workflow_node_types(data: object) -> set[str]:
    if not isinstance(data, dict):
        raise ValueError("workflow root must be a JSON object")

    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("workflow has no nodes list")

    result: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = node.get("type") or node.get("class_type")
        if isinstance(node_type, str) and node_type:
            result.add(node_type)
    return result


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(
            "Usage: verify_workflows.py object_info.json workflow1.json [workflow2.json ...]"
        )

    object_info_path = Path(sys.argv[1])
    available = json.loads(object_info_path.read_text(encoding="utf-8"))
    if not isinstance(available, dict):
        raise SystemExit("object_info response is not a JSON object")

    failures: list[str] = []
    for raw_path in sys.argv[2:]:
        path = Path(raw_path)
        try:
            workflow = json.loads(path.read_text(encoding="utf-8"))
            required = workflow_node_types(workflow)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{path.name}: invalid workflow: {exc}")
            continue

        missing = sorted(required.difference(available))
        if missing:
            failures.append(f"{path.name}: missing nodes: {', '.join(missing)}")
        else:
            print(f"Workflow compatibility: OK - {path.name} ({len(required)} node types)")

    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
