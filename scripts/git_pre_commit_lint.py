#!/usr/bin/env python3
"""Run repo-approved lint for staged Python files during Git pre-commit."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

hook_edit_paths = importlib.import_module("scripts.hook_edit_paths")


def _staged_paths() -> list[Path]:
    """Return repo-local file paths currently staged for commit."""
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print("[pre-commit-lint] unable to inspect staged changes", file=sys.stderr)
        return []

    resolved: list[Path] = []
    for raw_line in proc.stdout.splitlines():
        candidate = raw_line.strip()
        if not candidate:
            continue
        path = (REPO_ROOT / candidate).resolve()
        try:
            path.relative_to(REPO_ROOT)
        except ValueError:
            continue
        resolved.append(path)
    return resolved


def run_pre_commit_lint() -> int:
    """Lint staged Python files through the guarded Ruff wrapper."""
    python_paths = hook_edit_paths.python_paths(_staged_paths())
    if not python_paths:
        return 0

    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "ruff_guard.py"), *[str(path) for path in python_paths]],
        cwd=REPO_ROOT,
        check=False,
    )
    if proc.returncode != 0:
        print("[pre-commit-lint] lint failed", file=sys.stderr)
    return proc.returncode


def main() -> int:
    """Execute the staged lint flow for the Git pre-commit hook."""
    return run_pre_commit_lint()


if __name__ == "__main__":
    raise SystemExit(main())
