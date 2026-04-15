#!/usr/bin/env python3
"""PostToolUse hook: refresh CodeGraphContext and vector index after edits."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable

VECTOR_SUFFIXES = {".py", ".pyi", ".md", ".markdown", ".mdown"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _emit_warning(message: str) -> None:
    print(f"WARN: {message}", file=sys.stderr)


def _collect_changed_paths(payload: dict) -> list[Path]:
    tool_input = payload.get("tool_input") or {}
    candidates: list[str] = []

    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())

    for key in ("file_paths", "paths"):
        value = tool_input.get(key)
        if isinstance(value, list):
            candidates.extend(item.strip() for item in value if isinstance(item, str) and item.strip())

    root = _repo_root()
    resolved: set[Path] = set()
    for raw in candidates:
        path = Path(raw)
        if not path.is_absolute():
            path = (root / path).resolve()
        else:
            path = path.resolve()

        try:
            path.relative_to(root)
        except ValueError:
            continue

        if path.exists():
            resolved.add(path)

    return sorted(resolved)


def _run_refresh(command: list[str], label: str) -> None:
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode == 0:
        return

    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()
    details = stderr or stdout or f"exit code {proc.returncode}"
    _emit_warning(f"{label} refresh failed: {details}")


def _refresh_codegraph(paths: Iterable[Path]) -> None:
    script = _repo_root() / "scripts" / "cgc_safe_index.sh"
    for path in paths:
        _run_refresh(["bash", str(script), str(path)], f"codegraph {path}")


def _refresh_vector(paths: Iterable[Path]) -> None:
    vector_paths = [path for path in paths if path.suffix.lower() in VECTOR_SUFFIXES]
    if not vector_paths:
        return

    root = _repo_root()
    command = [
        "uv",
        "run",
        "--no-sync",
        "python",
        "-m",
        "src.mcp_codebase.indexer",
        "--repo-root",
        str(root),
        "refresh",
        *[str(path) for path in vector_paths],
    ]
    _run_refresh(command, "vector index")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    changed_paths = _collect_changed_paths(payload)
    if not changed_paths:
        return 0

    _refresh_codegraph(changed_paths)
    _refresh_vector(changed_paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
