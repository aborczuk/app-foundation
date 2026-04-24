#!/usr/bin/env python3
"""SessionStart hook: inject full required governance docs into Codex context."""

from __future__ import annotations

import json
import sys
from pathlib import Path


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
