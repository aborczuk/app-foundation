#!/usr/bin/env python3
"""Run pytest with deterministic compact output while preserving full logs."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIR = REPO_ROOT / ".speckit" / "test-logs"
FORCED_PYTEST_FLAGS = ("-q", "--maxfail=1", "--tb=short")
SUMMARY_LINE_PATTERN = re.compile(r"=+ .* in [0-9.]+s =+")
FAILURE_HEADER_PATTERN = re.compile(r"^_{3,} .+ _{3,}$")


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for guarded pytest execution."""
    parser = argparse.ArgumentParser(prog="pytest_guard")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run pytest with compact output and full log capture")
    run.add_argument(
        "--log-dir",
        type=Path,
        default=DEFAULT_LOG_DIR,
        help="Directory where full pytest logs should be written.",
    )
    run.add_argument(
        "--run-id",
        type=str,
        default="",
        help="Optional run identifier suffix for the log filename.",
    )
    run.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to pytest (prefix with --).",
    )

    show = subparsers.add_parser("show", help="Show a previously captured pytest log in compact form")
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
        help="Directory where pytest logs are stored.",
    )
    show.add_argument(
        "--latest",
        action="store_true",
        help="Show the newest log file from --log-dir (default when no selector is given).",
    )
    show.add_argument(
        "--full",
        action="store_true",
        help="Print the full stored log content (default is compact summary + first failure).",
    )

    return parser


def _strip_override_flags(pytest_args: Sequence[str]) -> list[str]:
    """Drop caller-provided flags that would override the guarded first-pass contract."""
    filtered: list[str] = []
    skip_next = False
    for token in pytest_args:
        if skip_next:
            skip_next = False
            continue
        if token in {"--maxfail", "--tb"}:
            skip_next = True
            continue
        if token.startswith("--maxfail=") or token.startswith("--tb="):
            continue
        if token in {"-q", "-qq", "-v", "-vv"}:
            continue
        filtered.append(token)
    return filtered


def _build_pytest_command(pytest_args: Sequence[str]) -> list[str]:
    """Construct the guarded pytest command with required compact-output flags."""
    normalized_args = list(pytest_args)
    if normalized_args and normalized_args[0] == "--":
        normalized_args = normalized_args[1:]
    normalized_args = _strip_override_flags(normalized_args)

    if shutil.which("uv"):
        return ["uv", "run", "--no-sync", "pytest", *FORCED_PYTEST_FLAGS, *normalized_args]
    return [sys.executable, "-m", "pytest", *FORCED_PYTEST_FLAGS, *normalized_args]


def _summary_line(output: str, *, exit_code: int) -> str:
    """Return the best compact summary line for a pytest run."""
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    for line in reversed(lines):
        if SUMMARY_LINE_PATTERN.match(line.strip()):
            return line.strip()
    if lines:
        return lines[-1]
    return f"pytest exited with code {exit_code}"


def _first_failure_block(output: str) -> str:
    """Extract only the first pytest failure block from raw output."""
    lines = output.splitlines()
    try:
        failure_start = next(index for index, line in enumerate(lines) if line.strip() == "FAILURES")
    except StopIteration:
        return ""

    header_index = -1
    for index in range(failure_start + 1, len(lines)):
        if FAILURE_HEADER_PATTERN.match(lines[index].strip()):
            header_index = index
            break
    if header_index == -1:
        return ""

    end_index = len(lines)
    for index in range(header_index + 1, len(lines)):
        text = lines[index].strip()
        if text.startswith("short test summary info") or text.startswith("==="):
            end_index = index
            break
        if FAILURE_HEADER_PATTERN.match(text):
            end_index = index
            break

    block = "\n".join(lines[header_index:end_index]).strip()
    return block


def _resolve_log_dir(log_dir: Path) -> Path:
    """Resolve and create the log directory for guarded pytest output."""
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
    filename = f"pytest-{timestamp}{suffix}.log"
    return log_dir / filename


def _write_log(log_path: Path, content: str) -> None:
    """Persist complete pytest output to disk for explicit later inspection."""
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


def _run_guarded_pytest(args: argparse.Namespace) -> int:
    """Execute guarded pytest, write full logs, and print compact failure output."""
    command = _build_pytest_command(args.pytest_args)
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from uv_env import repo_uv_env

    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=repo_uv_env(),
    )
    output = f"{completed.stdout or ''}{completed.stderr or ''}"
    log_dir = _resolve_log_dir(args.log_dir)
    log_file = _log_path(log_dir, args.run_id.strip())
    _write_log(log_file, output)

    print(f"pytest_guard: exit_code={completed.returncode}")
    print(f"summary: {_summary_line(output, exit_code=completed.returncode)}")
    print(f"log_file: {log_file}")

    first_failure = _first_failure_block(output)
    if completed.returncode != 0 and first_failure:
        print("--- first_failure ---")
        print(first_failure)
        print("--- end_first_failure ---")

    return completed.returncode


def _show_log(args: argparse.Namespace) -> int:
    """Print a compact or full stored pytest log selected by path, run-id, or latest."""
    log_file = _resolve_show_log(
        log=args.log,
        run_id=args.run_id.strip(),
        log_dir=args.log_dir,
        latest=args.latest,
    )
    if log_file is None:
        print("ERROR: no pytest log matched the selector", file=sys.stderr)
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
    """Entrypoint for guarded pytest run and explicit log expansion."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run_guarded_pytest(args)
    if args.command == "show":
        return _show_log(args)
    raise ValueError(f"unknown command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
