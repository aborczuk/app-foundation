#!/usr/bin/env python3
"""Deterministic edit workflow runner for validate/refresh/sync handoffs."""

from __future__ import annotations

import argparse
import json
import os
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
    validate.add_argument(
        "--changed-only",
        action="store_true",
        help="Run ruff/pyright on changed files under --paths instead of all provided paths.",
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
    sync.add_argument(
        "--changed-only",
        action="store_true",
        help="Run ruff/pyright on changed files under --paths instead of all provided paths.",
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


def _runtime_env() -> dict[str, str]:
    """Build runtime env and default UV cache to a repo-local directory when unset."""
    env = os.environ.copy()
    cache_dir = Path(
        env.get("UV_CACHE_DIR", str(REPO_ROOT / ".codegraphcontext" / ".uv-cache"))
    ).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    env["UV_CACHE_DIR"] = str(cache_dir)
    return env


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
        env=_runtime_env(),
    )
    return completed.returncode


def _normalize_porcelain_paths(payload: str) -> set[str]:
    """Parse git porcelain output into normalized repo-relative paths."""
    normalized: set[str] = set()
    for raw in payload.splitlines():
        line = raw.rstrip("\n")
        if not line.strip() or len(line) < 4:
            continue
        candidate = line[3:].strip()
        if not candidate:
            continue
        parts = [part.strip() for part in candidate.split(" -> ")] if " -> " in candidate else [candidate]
        for part in parts:
            text = part.strip('"').replace("\\", "/")
            if text.startswith("./"):
                text = text[2:]
            if text:
                normalized.add(text)
    return normalized


def _dirty_paths(paths: Sequence[str] | None = None) -> set[str] | None:
    """Return dirty repo paths from git status, optionally scoped to requested paths."""
    command = ["git", "status", "--porcelain", "--untracked-files=normal"]
    if paths:
        command.extend(["--", *paths])
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        capture_output=True,
        env=_runtime_env(),
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        if stderr:
            print(f"[edit-code] WARN: git status probe failed: {stderr}", file=sys.stderr, flush=True)
        return None
    return _normalize_porcelain_paths(completed.stdout or "")


def _has_path_changes(paths: Sequence[str]) -> bool:
    """Return whether any requested paths have local git changes."""
    dirty = _dirty_paths(paths)
    if dirty is None:
        # If git status cannot run, be conservative and continue workflow checks.
        return True
    return bool(dirty)


def _changed_paths(paths: Sequence[str]) -> list[str]:
    """Return changed paths under the requested scope for changed-only validation."""
    dirty = _dirty_paths(paths)
    if dirty is None:
        return list(paths)
    return sorted(dirty)


def _split_dirty_paths(paths: Sequence[str]) -> tuple[list[str], list[str]]:
    """Return (in_scope_dirty, out_of_scope_dirty) from repo dirty status."""
    dirty = _dirty_paths()
    if dirty is None:
        return [], []

    in_scope: list[str] = []
    out_of_scope: list[str] = []
    for candidate in sorted(dirty):
        in_requested_scope = any(
            candidate == scope_path or candidate.startswith(f"{scope_path.rstrip('/')}/")
            for scope_path in paths
        )
        if in_requested_scope:
            in_scope.append(candidate)
        else:
            out_of_scope.append(candidate)
    return in_scope, out_of_scope


def _has_staged_path_changes(paths: Sequence[str]) -> bool:
    """Return whether requested paths currently have staged git changes."""
    command = ["git", "diff", "--cached", "--name-only", "--", *paths]
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        capture_output=True,
        env=_runtime_env(),
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        if stderr:
            print(f"[edit-code] WARN: staged diff probe failed: {stderr}", file=sys.stderr, flush=True)
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
            env=_runtime_env(),
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


def _run_validate(
    paths: Sequence[str],
    tests: Sequence[str],
    *,
    skip_ruff: bool,
    skip_pyright: bool,
    changed_only: bool,
) -> int:
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

    lint_paths = _changed_paths(paths) if changed_only else list(paths)
    if changed_only:
        if lint_paths:
            print(
                f"[edit-code] changed_only active: lint/type checks limited to changed paths: {', '.join(lint_paths)}",
                flush=True,
            )
        else:
            print("[edit-code] changed_only active: no changed paths detected for lint/type checks", flush=True)
    python_paths = _python_paths(lint_paths)
    if python_paths and not skip_ruff:
        rc = _run_command(
            ["uv", "run", "--no-sync", "python", "scripts/ruff_guard.py", *python_paths],
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
    changed_only: bool,
) -> int:
    """Run validate + refresh + git sync in one deterministic flow."""
    rc = _run_validate(
        paths,
        tests,
        skip_ruff=skip_ruff,
        skip_pyright=skip_pyright,
        changed_only=changed_only,
    )
    if rc != 0:
        return rc

    in_scope_dirty, out_of_scope_dirty = _split_dirty_paths(paths)
    if out_of_scope_dirty:
        preview = ", ".join(out_of_scope_dirty[:8])
        if len(out_of_scope_dirty) > 8:
            preview += ", ..."
        print(
            "[edit-code] WARN: unrelated dirty paths detected outside requested scope; "
            f"sync will continue for requested paths only: {preview}",
            file=sys.stderr,
            flush=True,
        )

    if not in_scope_dirty:
        print("[edit-code] sync skipped: nothing changed in requested paths", flush=True)
        return 0

    rc = _run_refresh(paths)
    if rc != 0:
        return rc

    rc = _run_git_with_retry(["git", "add", *paths], label="git_add")
    if rc != 0:
        return rc

    if not _has_staged_path_changes(paths):
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
            changed_only=args.changed_only,
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
            changed_only=args.changed_only,
        )
    raise ValueError(f"unknown command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
