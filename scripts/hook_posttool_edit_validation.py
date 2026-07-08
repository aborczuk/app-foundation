#!/usr/bin/env python3
"""PostToolUse hook: validate changed files and refresh scoped read-code indexes."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import hook_refresh_indexes  # noqa: E402

PYTHON_SUFFIXES = {".py", ".pyi"}


def _python_paths(paths: Iterable[Path]) -> list[Path]:
    """Return repo-local changed paths that need Python validation."""
    return [path for path in paths if path.suffix.lower() in PYTHON_SUFFIXES]


def _run_check(command: list[str], label: str) -> str | None:
    """Run one validation command and return a compact failure summary on error."""
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        return None

    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()
    details = stderr or stdout or f"exit code {proc.returncode}"
    return f"{label} failed: {details}"


def _validate_python_paths(paths: list[Path]) -> list[str]:
    """Run guarded lint, LSP, and docstring checks for changed Python paths."""
    if not paths:
        return []

    path_args = [str(path) for path in paths]
    checks = [
        (
            [sys.executable, "scripts/ruff_guard.py", *path_args],
            "ruff check",
        ),
        (
            [sys.executable, "scripts/pyright_guard.py", *path_args],
            "pyright check",
        ),
        (
            [sys.executable, "scripts/validate_python_docstrings.py", *path_args],
            "docstring validation",
        ),
    ]
    failures: list[str] = []
    for command, label in checks:
        error = _run_check(command, label)
        if error:
            failures.append(error)
    return failures


def run_posttool_request(payload: dict) -> list[str]:
    """Validate changed files and refresh scoped indexes for a PostToolUse payload."""
    changed_paths = hook_refresh_indexes._collect_changed_paths(payload)
    if not changed_paths:
        return []

    failures = _validate_python_paths(_python_paths(changed_paths))
    if failures:
        return failures
    return hook_refresh_indexes.run_refresh_request(payload)


def main() -> int:
    """Read the hook payload from stdin and enforce post-edit validation plus refresh."""
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
