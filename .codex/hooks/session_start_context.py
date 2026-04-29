#!/usr/bin/env python3
"""SessionStart hook: prime the repo-local UV cache and inject governance docs."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UV_CACHE_DIR = REPO_ROOT / ".codegraphcontext" / ".uv-cache"


def _repo_uv_cache_dir() -> Path:
    """Create and return the repo-local UV cache directory."""
    cache_dir = Path(os.environ.get("UV_CACHE_DIR", str(DEFAULT_UV_CACHE_DIR))).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _read_payload() -> dict:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _catalog_path(repo_root: Path) -> Path:
    catalog_md = repo_root / "catalog.md"
    if catalog_md.exists():
        return catalog_md
    return repo_root / "catalog.yaml"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def main() -> int:
    """Build and emit SessionStart additional context from required docs."""
    payload = _read_payload()
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        repo_root = Path(cwd)
    else:
        repo_root = Path.cwd()

    cache_dir = _repo_uv_cache_dir()
    os.environ["UV_CACHE_DIR"] = str(cache_dir)

    docs = [
        repo_root / "CLAUDE.md",
        repo_root / "constitution.md",
        _catalog_path(repo_root),
    ]

    sections: list[str] = []
    for doc in docs:
        if doc.exists() and doc.is_file():
            sections.append(f"[BEGIN {doc.name}]\n{_read_text(doc)}\n[END {doc.name}]")
        else:
            sections.append(f"[MISSING REQUIRED DOC] {doc}")

    additional_context = (
        f"Repo-local UV cache initialized at {cache_dir}.\n\n"
        "Required repo governance documents loaded in full by SessionStart hook.\n\n"
        + "\n\n".join(sections)
    )

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": additional_context,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
