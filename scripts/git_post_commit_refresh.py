#!/usr/bin/env python3
"""Refresh local codegraph/vector indexes for the files changed in HEAD."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

workflow_evidence = importlib.import_module("scripts.workflow_evidence")


def _changed_paths_for_head() -> list[str]:
    """Return repo-relative file paths changed by the current HEAD commit."""
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", "--name-only", "--format=", "--diff-filter=AMR", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print("[post-commit-refresh] unable to inspect HEAD changes", file=sys.stderr)
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def main() -> int:
    """Refresh repo-local discovery indexes unless exact verified refresh evidence exists."""
    changed_paths = _changed_paths_for_head()
    if not changed_paths:
        print("[post-commit-refresh] no changed paths in HEAD; skipping refresh", flush=True)
        return 0

    rel_paths = workflow_evidence.normalize_repo_paths(REPO_ROOT, changed_paths)
    if rel_paths and workflow_evidence.has_valid_evidence(
        REPO_ROOT,
        validator_id="refresh",
        paths=rel_paths,
        selectors=rel_paths,
    ):
        print(
            "[post-commit-refresh] valid refresh evidence matches HEAD changes; skipping duplicate refresh",
            flush=True,
        )
        return 0

    payload = json.dumps({"tool_input": {"paths": changed_paths}})
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "hook_refresh_indexes.py")],
        cwd=REPO_ROOT,
        input=payload,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print("[post-commit-refresh] refresh failed", file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
