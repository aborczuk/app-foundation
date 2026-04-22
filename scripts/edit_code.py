#!/usr/bin/env python3
"""Deterministic edit workflow runner for validate/refresh/sync handoffs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for edit-code commands."""
    parser = argparse.ArgumentParser(prog="edit-code")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Run tests, ruff, and pyright for touched paths")
    validate.add_argument("--paths", nargs="+", required=True, help="Touched repo-local paths.")
    validate.add_argument("--tests", nargs="+", required=True, help="Targeted pytest selectors.")
    validate.add_argument("--skip-ruff", action="store_true", help="Skip ruff check for touched Python paths.")
    validate.add_argument(
        "--skip-pyright",
        action="store_true",
        help="Skip pyright diagnostics for touched Python paths.",
    )

    refresh = subparsers.add_parser("refresh", help="Run hook_refresh_indexes.py for touched paths")
    refresh.add_argument("--paths", nargs="+", required=True, help="Touched repo-local paths.")

    sync = subparsers.add_parser(
        "sync",
        help="Run validate + refresh + commit/push for one coherent edit unit",
    )
    sync.add_argument("--paths", nargs="+", required=True, help="Touched repo-local paths.")
    sync.add_argument("--tests", nargs="+", required=True, help="Targeted pytest selectors.")
    sync.add_argument("--commit-message", required=True, help="Commit message for this edit unit.")
    sync.add_argument("--no-push", action="store_true", help="Commit locally without pushing.")
    sync.add_argument("--skip-ruff", action="store_true", help="Skip ruff check for touched Python paths.")
    sync.add_argument(
        "--skip-pyright",
        action="store_true",
        help="Skip pyright diagnostics for touched Python paths.",
    )

    return parser


def _normalize_repo_path(raw_path: str) -> str:
    """Normalize a path to a repo-relative POSIX path and enforce repo locality."""
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        return candidate.relative_to(REPO_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError(f"path is outside repo root: {raw_path}") from exc


def _resolve_paths(raw_paths: Sequence[str]) -> list[str]:
    """Normalize and de-duplicate repo-local paths while preserving order."""
    resolved: list[str] = []
    seen: set[str] = set()
    for raw_path in raw_paths:
        normalized = _normalize_repo_path(raw_path)
        if normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return resolved


def _python_paths(paths: Sequence[str]) -> list[str]:
    """Return touched Python source paths for ruff/pyright checks."""
    return [path for path in paths if path.endswith((".py", ".pyi")) and (REPO_ROOT / path).exists()]


def _run_command(command: list[str], *, label: str, stdin_payload: str | None = None) -> int:
    """Run a command and return its exit code while emitting deterministic labels."""
    print(f"[edit-code] {label}", flush=True)
    printable = " ".join(command)
    print(f"[edit-code] cmd: {printable}", flush=True)
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        input=stdin_payload,
    )
    return completed.returncode


def _has_path_changes(paths: Sequence[str]) -> bool:
    """Return whether any requested paths have local git changes."""
    command = ["git", "status", "--porcelain", "--", *paths]
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        # If git status cannot run, be conservative and continue workflow checks.
        stderr = (completed.stderr or "").strip()
        if stderr:
            print(f"[edit-code] WARN: git status probe failed: {stderr}", file=sys.stderr, flush=True)
        return True
    return bool((completed.stdout or "").strip())


def _run_git_with_retry(command: list[str], *, label: str, max_attempts: int = 3) -> int:
    """Run git commands with bounded retries for transient index.lock contention."""
    for attempt in range(1, max_attempts + 1):
        print(f"[edit-code] {label}", flush=True)
        print(f"[edit-code] cmd: {' '.join(command)}", flush=True)
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            check=False,
            text=True,
            capture_output=True,
        )
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        if completed.returncode == 0:
            return 0

        combined_error = f"{completed.stdout or ''}\n{completed.stderr or ''}".lower()
        if "index.lock" in combined_error and attempt < max_attempts:
            print(
                f"[edit-code] WARN: transient git index lock detected; retrying ({attempt}/{max_attempts})",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(0.5 * attempt)
            continue
        return completed.returncode
    return 1


def _run_validate(paths: Sequence[str], tests: Sequence[str], *, skip_ruff: bool, skip_pyright: bool) -> int:
    """Run the validation loop for one edit batch."""
    pytest_cmd = [
        "uv",
        "run",
        "--no-sync",
        "python",
        "scripts/pytest_guard.py",
        "run",
        "--",
        "-q",
        "--maxfail=1",
        "--tb=short",
        *tests,
    ]
    rc = _run_command(pytest_cmd, label="pytest_guard")
    if rc != 0:
        return rc

    python_paths = _python_paths(paths)
    if python_paths and not skip_ruff:
        rc = _run_command(
            ["uv", "run", "--no-sync", "ruff", "check", *python_paths],
            label="ruff_check",
        )
        if rc != 0:
            return rc

    if python_paths and not skip_pyright:
        rc = _run_command(
            ["uv", "run", "--no-sync", "pyright", *python_paths],
            label="pyright",
        )
        if rc != 0:
            return rc

    return 0


def _run_refresh(paths: Sequence[str]) -> int:
    """Run the repo refresh hook for changed paths."""
    if not _has_path_changes(paths):
        print("[edit-code] refresh_indexes skipped: no local changes in requested paths", flush=True)
        return 0
    payload = json.dumps({"tool_input": {"paths": list(paths)}})
    return _run_command(
        ["uv", "run", "--no-sync", "python", "scripts/hook_refresh_indexes.py"],
        label="refresh_indexes",
        stdin_payload=payload,
    )


def _run_sync(
    paths: Sequence[str],
    tests: Sequence[str],
    *,
    commit_message: str,
    no_push: bool,
    skip_ruff: bool,
    skip_pyright: bool,
) -> int:
    """Run validate + refresh + git sync in one deterministic flow."""
    rc = _run_validate(paths, tests, skip_ruff=skip_ruff, skip_pyright=skip_pyright)
    if rc != 0:
        return rc

    if not _has_path_changes(paths):
        print("[edit-code] sync skipped: nothing changed in requested paths", flush=True)
        return 0

    rc = _run_refresh(paths)
    if rc != 0:
        return rc

    rc = _run_git_with_retry(["git", "add", *paths], label="git_add")
    if rc != 0:
        return rc

    if not _has_path_changes(paths):
        print("[edit-code] sync skipped: nothing left to commit after refresh", flush=True)
        return 0

    rc = _run_git_with_retry(["git", "commit", "-m", commit_message], label="git_commit")
    if rc != 0:
        return rc

    if no_push:
        return 0

    return _run_git_with_retry(["git", "push"], label="git_push")


def main(argv: Sequence[str] | None = None) -> int:
    """Entrypoint for deterministic edit workflow execution."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        paths = _resolve_paths(args.paths)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.command == "validate":
        return _run_validate(
            paths,
            args.tests,
            skip_ruff=args.skip_ruff,
            skip_pyright=args.skip_pyright,
        )
    if args.command == "refresh":
        return _run_refresh(paths)
    if args.command == "sync":
        return _run_sync(
            paths,
            args.tests,
            commit_message=args.commit_message,
            no_push=args.no_push,
            skip_ruff=args.skip_ruff,
            skip_pyright=args.skip_pyright,
        )
    raise ValueError(f"unknown command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
