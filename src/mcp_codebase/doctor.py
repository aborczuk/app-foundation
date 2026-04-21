"""Command-line doctor for graph readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from src.mcp_codebase.health import GraphHealthStatus, classify_graph_health


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check local CodeGraph readiness")
    parser.add_argument(
        "--project-root",
        "--root",
        dest="project_root",
        default=Path.cwd(),
        type=Path,
        help="Repository root to inspect",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a human-readable summary",
    )
    return parser


def render_human(result: dict[str, object]) -> str:
    recovery_hint = result.get("recovery_hint", {})
    hint_command = ""
    if isinstance(recovery_hint, dict):
        hint_command = str(recovery_hint.get("command", ""))
    lines = [
        f"status: {result.get('status')}",
        f"access_mode: {result.get('access_mode')}",
        f"detail: {result.get('detail')}",
        f"recovery_hint: {recovery_hint.get('id') if isinstance(recovery_hint, dict) else ''}",
    ]
    if hint_command:
        lines.append(f"next: {hint_command}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    result = classify_graph_health(args.project_root).to_dict()

    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(render_human(result))

    status = result.get("status")
    return 0 if status == GraphHealthStatus.HEALTHY.value else 1


if __name__ == "__main__":
    raise SystemExit(main())
