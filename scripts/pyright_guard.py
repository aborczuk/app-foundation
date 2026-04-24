"""Run pyright with deterministic path validation and bounded failure output."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uv_env import repo_uv_env

DEFAULT_MAX_OUTPUT_LINES = 120
MAX_OUTPUT_LINES_ENV = "PYRIGHT_GUARD_MAX_OUTPUT_LINES"
PYTHON_SUFFIXES = {".py", ".pyi"}


def _max_output_lines() -> int:
    """Return the configured output-line cap for failing pyright runs."""
    raw = os.environ.get(MAX_OUTPUT_LINES_ENV, str(DEFAULT_MAX_OUTPUT_LINES)).strip()
    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_MAX_OUTPUT_LINES
    return parsed if parsed > 0 else DEFAULT_MAX_OUTPUT_LINES


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for guarded Pyright checks."""
    parser = argparse.ArgumentParser(
        description="Run pyright with deterministic path validation and bounded failure output."
    )
    parser.add_argument("paths", nargs="+", help="Python file paths to type-check")
    return parser


def _validate_paths(raw_paths: Sequence[str]) -> tuple[list[str], list[str]]:
    """Return normalized python paths plus a list of invalid path reasons."""
    normalized: list[str] = []
    errors: list[str] = []
    for raw in raw_paths:
        candidate = Path(raw).expanduser()
        if candidate.suffix not in PYTHON_SUFFIXES:
            errors.append(f"{raw}: unsupported suffix {candidate.suffix or '<none>'}; expected .py or .pyi")
            continue
        if not candidate.exists():
            errors.append(f"{raw}: path does not exist")
            continue
        normalized.append(str(candidate))
    return normalized, errors


def _emit_failure_output(stdout: str, stderr: str, *, cap: int) -> None:
    """Print bounded failure output and summarize omitted lines when truncated."""
    combined_lines: list[str] = []
    if stdout.strip():
        combined_lines.extend(stdout.splitlines())
    if stderr.strip():
        combined_lines.extend(stderr.splitlines())
    if not combined_lines:
        return
    if len(combined_lines) <= cap:
        print("\n".join(combined_lines), file=sys.stderr)
        return
    visible = combined_lines[:cap]
    omitted = len(combined_lines) - cap
    print("\n".join(visible), file=sys.stderr)
    print(
        (
            f"... output truncated by pyright_guard ({omitted} lines omitted; "
            f"set {MAX_OUTPUT_LINES_ENV} to adjust cap)"
        ),
        file=sys.stderr,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Validate targets, run Pyright, and bound output for deterministic token usage."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    valid_paths, errors = _validate_paths(args.paths)
    if errors:
        print("ERROR: pyright_guard rejected one or more inputs:", file=sys.stderr)
        for detail in errors:
            print(f"- {detail}", file=sys.stderr)
        return 2

    cmd = ["uv", "run", "--no-sync", "pyright", *valid_paths]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=repo_uv_env())
    if result.returncode == 0:
        if result.stdout.strip():
            print(result.stdout, end="")
        if result.stderr.strip():
            print(result.stderr, end="", file=sys.stderr)
        return 0

    _emit_failure_output(result.stdout, result.stderr, cap=_max_output_lines())
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
