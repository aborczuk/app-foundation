#!/usr/bin/env python3
"""Run `gh` with compact output while preserving full logs for later replay."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIR = REPO_ROOT / ".speckit" / "github-logs"
FAILURE_PATTERN = re.compile(
    r"(error|failed|fatal|exception|traceback|denied|panic)", re.IGNORECASE
)
BLOCK_END_PATTERN = re.compile(r"^\s*(?:$|=+|-+|_+)$")


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for guarded GitHub CLI execution."""
    parser = argparse.ArgumentParser(prog="github_guard")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run gh with compact output and full log capture")
    run.add_argument(
        "--log-dir",
        type=Path,
        default=DEFAULT_LOG_DIR,
        help="Directory where full gh logs should be written.",
    )
    run.add_argument(
        "--run-id",
        type=str,
        default="",
        help="Optional run identifier suffix for the log filename.",
    )
    run.add_argument(
        "gh_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to gh (prefix with --).",
    )

    show = subparsers.add_parser("show", help="Show a previously captured gh log")
    show.add_argument("--log", type=Path, default=None, help="Explicit log file path.")
    show.add_argument(
        "--run-id",
        type=str,
        default="",
        help="Run identifier suffix used during `run`.",
    )
    show.add_argument(
        "--log-dir",
        type=Path,
        default=DEFAULT_LOG_DIR,
        help="Directory where gh logs are stored.",
    )
    show.add_argument(
        "--latest",
        action="store_true",
        help="Show the newest log file from --log-dir (default when no selector is given).",
    )
    show.add_argument(
        "--full",
        action="store_true",
        help="Print the full stored log content (default is compact summary + failure excerpt).",
    )

    return parser


def _is_gh_binary(token: str) -> bool:
    """Return whether a token names the gh executable."""
    return Path(token).stem == "gh"


def _normalize_gh_args(gh_args: Sequence[str]) -> list[str]:
    """Remove leading wrapper separators and validate the gh command shape."""
    normalized = list(gh_args)
    if normalized and normalized[0] == "--":
        normalized = normalized[1:]
    if not normalized:
        return []
    if _is_gh_binary(normalized[0]):
        normalized = normalized[1:]
    return normalized


def _build_gh_command(gh_args: Sequence[str]) -> list[str]:
    """Construct the guarded gh command from forwarded arguments."""
    normalized_args = _normalize_gh_args(gh_args)
    if not normalized_args:
        return []
    return ["gh", *normalized_args]


def _summary_line(output: str, *, exit_code: int) -> str:
    """Return a compact summary line for a gh run."""
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    if lines:
        return lines[-1]
    return f"gh exited with code {exit_code}"


def _first_failure_block(output: str, *, max_lines: int = 40) -> str:
    """Extract the first failure-like block from raw gh output."""
    lines = output.splitlines()
    start_index = -1
    for index, line in enumerate(lines):
        if FAILURE_PATTERN.search(line):
            start_index = index
            break
    if start_index == -1:
        return ""

    end_index = len(lines)
    for index in range(start_index + 1, len(lines)):
        text = lines[index].strip()
        if BLOCK_END_PATTERN.match(text):
            end_index = index
            break

    block_lines = lines[start_index:end_index]
    if max_lines > 0 and len(block_lines) > max_lines:
        block_lines = [*block_lines[:max_lines], "... output truncated by github_guard ..."]
    return "\n".join(block_lines).strip()


def _resolve_log_dir(log_dir: Path) -> Path:
    """Resolve and create the log directory for guarded gh output."""
    resolved = log_dir.expanduser()
    if not resolved.is_absolute():
        resolved = (REPO_ROOT / resolved).resolve()
    else:
        resolved = resolved.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _log_path(log_dir: Path, run_id: str) -> Path:
    """Return a deterministic timestamped log file path."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"-{run_id}" if run_id else ""
    filename = f"github-{timestamp}{suffix}.log"
    return log_dir / filename


def _write_log(log_path: Path, content: str) -> None:
    """Persist complete gh output to disk for explicit later inspection."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(content, encoding="utf-8")


def _resolve_show_log(*, log: Path | None, run_id: str, log_dir: Path, latest: bool) -> Path | None:
    """Resolve a log target for `show` from explicit path, run-id, or latest."""
    if log is not None:
        candidate = log.expanduser()
        if not candidate.is_absolute():
            candidate = (REPO_ROOT / candidate).resolve()
        else:
            candidate = candidate.resolve()
        return candidate

    resolved_log_dir = _resolve_log_dir(log_dir)
    if run_id:
        matches = sorted(resolved_log_dir.glob(f"*{run_id}*.log"))
        return matches[-1] if matches else None

    if latest or not run_id:
        matches = sorted(resolved_log_dir.glob("*.log"))
        return matches[-1] if matches else None

    return None


def _run_guarded_gh(args: argparse.Namespace) -> int:
    """Execute gh, write full logs, and print compact failure output."""
    command = _build_gh_command(args.gh_args)
    if not command:
        print("ERROR: github_guard run expects arguments beginning with `gh`", file=sys.stderr)
        return 2

    try:
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("ERROR: gh is not installed or not on PATH", file=sys.stderr)
        return 127

    output = f"{completed.stdout or ''}{completed.stderr or ''}"
    log_dir = _resolve_log_dir(args.log_dir)
    log_file = _log_path(log_dir, args.run_id.strip())
    _write_log(log_file, output)

    print(f"github_guard: exit_code={completed.returncode}")
    print(f"summary: {_summary_line(output, exit_code=completed.returncode)}")
    print(f"log_file: {log_file}")

    first_failure = _first_failure_block(output)
    if completed.returncode != 0 and first_failure:
        print("--- first_failure ---")
        print(first_failure)
        print("--- end_first_failure ---")

    return completed.returncode


def _show_log(args: argparse.Namespace) -> int:
    """Print a compact or full stored gh log selected by path, run-id, or latest."""
    log_file = _resolve_show_log(
        log=args.log,
        run_id=args.run_id.strip(),
        log_dir=args.log_dir,
        latest=args.latest,
    )
    if log_file is None:
        print("ERROR: no gh log matched the selector", file=sys.stderr)
        return 1
    if not log_file.is_file():
        print(f"ERROR: log file not found: {log_file}", file=sys.stderr)
        return 1
    output = log_file.read_text(encoding="utf-8")
    if args.full:
        print(output, end="")
        return 0

    summary = _summary_line(output, exit_code=1)
    first_failure = _first_failure_block(output)
    print(f"summary: {summary}")
    print(f"log_file: {log_file}")
    if first_failure:
        print("--- first_failure ---")
        print(first_failure)
        print("--- end_first_failure ---")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entrypoint for guarded gh run and explicit log expansion."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run_guarded_gh(args)
    if args.command == "show":
        return _show_log(args)
    raise ValueError(f"unknown command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
