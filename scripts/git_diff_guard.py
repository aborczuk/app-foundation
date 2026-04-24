#!/usr/bin/env python3
"""Run git diff with bounded output for deterministic token usage."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_OUTPUT_LINES_ENV = "SPECKIT_GIT_DIFF_MAX_LINES"
DEFAULT_MAX_OUTPUT_LINES = 200


def _build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for guarded git diff execution."""
    parser = argparse.ArgumentParser(prog="git_diff_guard")
    parser.add_argument(
        "--max-lines",
        type=int,
        default=int(os.environ.get(MAX_OUTPUT_LINES_ENV, DEFAULT_MAX_OUTPUT_LINES)),
        help="Maximum number of diff output lines to print before truncation.",
    )
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Show staged changes (`git diff --cached`).",
    )
    parser.add_argument(
        "--name-only",
        action="store_true",
        help="Show only changed file names.",
    )
    parser.add_argument(
        "--stat",
        action="store_true",
        help="Show diffstat summary.",
    )
    parser.add_argument(
        "--unified",
        type=int,
        default=3,
        help="Context lines for patch output when not using --name-only/--stat.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional repo-local paths to scope the diff.",
    )
    return parser


def _normalize_repo_path(raw_path: str) -> str:
    """Normalize a path to repo-relative POSIX form and enforce repo locality."""
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve(strict=False)
    else:
        candidate = candidate.resolve(strict=False)
    try:
        return candidate.relative_to(REPO_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError(f"path is outside repo root: {raw_path}") from exc


def _resolve_paths(raw_paths: Sequence[str]) -> list[str]:
    """Normalize and de-duplicate repo-local paths while preserving order."""
    seen: set[str] = set()
    resolved: list[str] = []
    for raw in raw_paths:
        normalized = _normalize_repo_path(raw)
        if normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return resolved


def _build_git_diff_command(args: argparse.Namespace, paths: Sequence[str]) -> list[str]:
    """Build deterministic git diff command from parsed args."""
    command: list[str] = ["git", "diff", "--no-color"]
    if args.cached:
        command.append("--cached")
    if args.name_only:
        command.append("--name-only")
    elif args.stat:
        command.append("--stat")
    else:
        command.append(f"--unified={args.unified}")
    if paths:
        command.extend(["--", *paths])
    return command


def _print_bounded_output(stdout: str, stderr: str, *, max_lines: int) -> None:
    """Print combined output up to max_lines with deterministic truncation notice."""
    combined_lines = [*stdout.splitlines(), *stderr.splitlines()]
    if max_lines <= 0 or len(combined_lines) <= max_lines:
        if combined_lines:
            print("\n".join(combined_lines))
        return
    print("\n".join(combined_lines[:max_lines]))
    omitted = len(combined_lines) - max_lines
    print(
        (
            f"... output truncated by git_diff_guard ({omitted} lines omitted; "
            "increase --max-lines to adjust)"
        ),
        file=sys.stderr,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Validate input, run git diff, and bound output."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.max_lines < 1:
        print("ERROR: --max-lines must be >= 1", file=sys.stderr)
        return 2
    if args.unified < 0:
        print("ERROR: --unified must be >= 0", file=sys.stderr)
        return 2

    try:
        paths = _resolve_paths(args.paths)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    command = _build_git_diff_command(args, paths)
    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
    )
    _print_bounded_output(result.stdout, result.stderr, max_lines=args.max_lines)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
