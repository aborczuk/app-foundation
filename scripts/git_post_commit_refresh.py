#!/usr/bin/env python3
"""Refresh local codegraph/vector indexes for the files changed in HEAD."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


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
    """Refresh repo-local discovery indexes for the current commit's changed paths."""
    changed_paths = _changed_paths_for_head()
    if not changed_paths:
        print("[post-commit-refresh] no changed paths in HEAD; skipping refresh", flush=True)
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
