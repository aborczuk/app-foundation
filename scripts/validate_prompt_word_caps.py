#!/usr/bin/env python3
"""Validate word-count caps for high-frequency governance and command docs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

WORD_CAPS: dict[str, int] = {
    ".claude/commands/speckit.implement.md": 2450,
    ".claude/commands/speckit.plan.md": 2100,
    ".claude/commands/speckit.tasks.md": 1250,
    ".claude/commands/speckit.specify.md": 1700,
    "CLAUDE.md": 1500,
    "constitution.md": 1450,
}


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output.")
    return parser.parse_args(argv)


def _count_words(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").split())


def _run(repo_root: Path) -> tuple[int, dict[str, Any]]:
    results: list[dict[str, Any]] = []
    overages: list[dict[str, Any]] = []
    reasons: list[str] = []

    for rel_path, cap in WORD_CAPS.items():
        path = repo_root / rel_path
        if not path.exists():
            reasons.append(f"missing_file:{rel_path}")
            continue
        words = _count_words(path)
        delta = words - cap
        row = {
            "path": rel_path,
            "cap": cap,
            "words": words,
            "delta": delta,
            "ok": delta <= 0,
        }
        results.append(row)
        if delta > 0:
            overages.append(row)
            reasons.append(f"cap_exceeded:{rel_path}")

    payload = {
        "mode": "prompt_word_caps",
        "ok": len(reasons) == 0,
        "results": results,
        "overages": overages,
        "reasons": reasons,
    }
    return (0 if payload["ok"] else 2, payload)


def main(argv: Sequence[str] | None = None) -> int:
    """Validate configured word caps and return process exit status."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    exit_code, payload = _run(Path(".").resolve())
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"ok={payload['ok']} checked={len(payload['results'])} overages={len(payload['overages'])}")
        for row in payload["overages"]:
            print(f"- {row['path']}: {row['words']} words (cap {row['cap']}, +{row['delta']})")
        for reason in payload["reasons"]:
            if reason.startswith("missing_file:"):
                print(f"- {reason}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
