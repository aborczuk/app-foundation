#!/usr/bin/env python3
"""PostToolUse hook: record changed repo-local paths and mark affected discovery scopes stale."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

hook_edit_paths = importlib.import_module("scripts.hook_edit_paths")
workflow_evidence = importlib.import_module("scripts.workflow_evidence")


def run_posttool_request(payload: dict) -> list[str]:
    """Track changed repo-local paths and mark affected discovery scopes stale without blocking."""
    changed_paths = hook_edit_paths.collect_changed_paths(payload, root=ROOT)
    if not changed_paths:
        return []

    try:
        workflow_evidence.record_changed_paths(ROOT, changed_paths)
        workflow_evidence.mark_paths_stale(ROOT, changed_paths)
    except OSError as exc:
        return [f"edit tracking failed: {exc}"]
    return []


def main() -> int:
    """Read the hook payload from stdin and record changed paths and staleness."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    failures = run_posttool_request(payload)
    if not failures:
        return 0
    for failure in failures:
        print(f"ERROR: {failure}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
