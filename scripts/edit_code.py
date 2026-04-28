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
EDIT_CODE_VERBOSE_ENV = "SPECKIT_EDIT_VERBOSE"
EDIT_CODE_COMMAND_PREVIEW_LIMIT = 10
EDIT_CODE_PATH_PREVIEW_LIMIT = 8
_RUNTIME_TEST_TRIGGER_PREFIXES = ("src/", "tests/", "scripts/")
_RUNTIME_TEST_TRIGGER_FILENAMES = {
    "pyproject.toml",
    "pytest.ini",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements-dev.txt",
    "uv.lock",
}
_DIRTY_PATH_CACHE: dict[tuple[str, ...], set[str] | None] = {}


def _reset_runtime_caches() -> None:
    """Reset per-invocation caches so one CLI run cannot affect another."""
    _DIRTY_PATH_CACHE.clear()


def _is_verbose_logging() -> bool:
    """Return whether verbose command logging is enabled for edit workflow runs."""
    raw = os.environ.get(EDIT_CODE_VERBOSE_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on", "debug", "verbose"}


def _preview_items(items: Sequence[str], *, limit: int, separator: str = " ") -> str:
    """Render a bounded preview string with a deterministic '+N more' suffix."""
    values = [str(item) for item in items]
    if len(values) <= limit:
        return separator.join(values)
    visible = separator.join(values[:limit])
    return f"{visible}{separator}+{len(values) - limit} more"


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
    validate_scope = validate.add_mutually_exclusive_group()
    validate_scope.add_argument(
        "--changed-only",
        dest="changed_only",
        action="store_true",
        default=True,
        help="Run ruff/pyright on changed files under --paths (default).",
    )
    validate_scope.add_argument(
        "--all-paths",
        dest="changed_only",
        action="store_false",
        help="Run ruff/pyright on all provided --paths.",
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
    sync.add_argument("--handoff", action="store_true", help="Run behavioral QA handoff and task closeout before sync.")
    sync.add_argument("--verdict-pass", action="store_true", help="Provide a PASS verdict to resume closeout after a generative pause.")
    sync.add_argument("--feature-id", help="Feature ID for handoff/closeout (required if --handoff or --verdict-pass is set).")
    sync.add_argument("--task-id", help="Task ID for handoff/closeout (required if --handoff is set).")
    sync_scope = sync.add_mutually_exclusive_group()
    sync_scope.add_argument(
        "--changed-only",
        dest="changed_only",
        action="store_true",
        default=True,
        help="Run ruff/pyright on changed files under --paths (default).",
    )
    sync_scope.add_argument(
        "--all-paths",
        dest="changed_only",
        action="store_false",
        help="Run ruff/pyright on all provided --paths.",
    )

    # Task subcommand
    task_p = subparsers.add_parser("task", help="Task lifecycle management (add, status).")
    task_sub = task_p.add_subparsers(dest="task_command", required=True)
    
    task_add = task_sub.add_parser("add", help="Add a new task to the backlog and materialize it.")
    task_add.add_argument("description", help="Task description (e.g. 'Fix the login bug — src/auth.py:login').")
    task_add.add_argument("--feature-id", required=True, help="Feature ID to add task to.")
    task_add.add_argument("--story", help="User story ID (e.g. US1).")
    task_add.add_argument("--points", type=int, default=1, help="Estimate points (default 1).")
    
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


def _resolve_feature_dir(feature_id: str) -> Path:
    """Resolve feature directory from exact slug or numeric feature prefix."""
    specs_root = REPO_ROOT / "specs"
    if not specs_root.is_dir():
        raise ValueError("missing_specs_root")

    explicit = specs_root / feature_id
    if explicit.is_dir():
        return explicit.resolve()

    candidates = sorted(path for path in specs_root.glob(f"{feature_id}-*") if path.is_dir())
    if not candidates:
        raise ValueError(f"feature_not_found: {feature_id}")
    if len(candidates) > 1:
        raise ValueError(
            f"feature_id_ambiguous: {feature_id} matches " + ",".join(path.name for path in candidates[:5])
        )
    return candidates[0].resolve()


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
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from uv_env import repo_uv_env

    return repo_uv_env()


def _run_command(command: list[str], *, label: str, stdin_payload: str | None = None) -> int:
    """Run a command and return its exit code with concise default logging."""
    print(f"[edit-code] {label}", flush=True)
    verbose = _is_verbose_logging()
    if verbose:
        print(f"[edit-code] cmd: {' '.join(command)}", flush=True)
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        input=stdin_payload,
        env=_runtime_env(),
    )
    if completed.returncode != 0 and not verbose:
        preview = _preview_items(command, limit=EDIT_CODE_COMMAND_PREVIEW_LIMIT)
        print(f"[edit-code] {label} failed (exit {completed.returncode})", file=sys.stderr, flush=True)
        print(f"[edit-code] cmd: {preview}", file=sys.stderr, flush=True)
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
    scope_paths = tuple(dict.fromkeys(paths or []))
    cached = _DIRTY_PATH_CACHE.get(scope_paths)
    if cached is not None or scope_paths in _DIRTY_PATH_CACHE:
        return None if cached is None else set(cached)

    # Reuse unscoped cache for scoped queries to avoid repeated git status calls.
    if scope_paths and () in _DIRTY_PATH_CACHE:
        cached_all = _DIRTY_PATH_CACHE[()]
        if cached_all is None:
            return None
        scoped = {
            candidate
            for candidate in cached_all
            if any(
                candidate == scope_path or candidate.startswith(f"{scope_path.rstrip('/')}/")
                for scope_path in scope_paths
            )
        }
        _DIRTY_PATH_CACHE[scope_paths] = set(scoped)
        return set(scoped)

    command = ["git", "status", "--porcelain", "--untracked-files=normal"]
    if scope_paths:
        command.extend(["--", *scope_paths])
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
        _DIRTY_PATH_CACHE[scope_paths] = None
        return None
    dirty = _normalize_porcelain_paths(completed.stdout or "")
    _DIRTY_PATH_CACHE[scope_paths] = set(dirty)
    return dirty


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


def _path_requires_runtime_tests(path: str) -> bool:
    """Return whether a path implies runtime test execution for this edit batch."""
    normalized = path.strip().replace("\\", "/")
    if not normalized:
        return False
    lowered = normalized.lower()
    if lowered.endswith(".py"):
        return True
    if lowered.startswith(_RUNTIME_TEST_TRIGGER_PREFIXES):
        return True
    return Path(lowered).name in _RUNTIME_TEST_TRIGGER_FILENAMES


def _should_run_pytest(paths: Sequence[str]) -> bool:
    """Return whether pytest should run for the current validation scope."""
    return any(_path_requires_runtime_tests(path) for path in paths)


def _split_dirty_candidates(
    paths: Sequence[str],
    dirty_candidates: set[str],
) -> tuple[list[str], list[str]]:
    """Partition dirty candidates into requested-scope and out-of-scope paths."""
    in_scope: list[str] = []
    out_of_scope: list[str] = []
    for candidate in sorted(dirty_candidates):
        in_requested_scope = any(
            candidate == scope_path or candidate.startswith(f"{scope_path.rstrip('/')}/")
            for scope_path in paths
        )
        if in_requested_scope:
            in_scope.append(candidate)
        else:
            out_of_scope.append(candidate)
    return in_scope, out_of_scope


def _split_dirty_paths(paths: Sequence[str]) -> tuple[list[str], list[str]]:
    """Return (in_scope_dirty, out_of_scope_dirty) from repo dirty status."""
    dirty = _dirty_paths()
    if dirty is None:
        return [], []

    return _split_dirty_candidates(paths, dirty)


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
    verbose = _is_verbose_logging()
    for attempt in range(1, max_attempts + 1):
        print(f"[edit-code] {label}", flush=True)
        if verbose:
            print(f"[edit-code] cmd: {' '.join(command)}", flush=True)
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            check=False,
            text=True,
            capture_output=True,
            env=_runtime_env(),
        )
        if completed.stdout and verbose:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        if completed.returncode != 0 and not verbose:
            preview = _preview_items(command, limit=EDIT_CODE_COMMAND_PREVIEW_LIMIT)
            print(f"[edit-code] {label} failed (exit {completed.returncode})", file=sys.stderr, flush=True)
            print(f"[edit-code] cmd: {preview}", file=sys.stderr, flush=True)
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
    changed_paths_override: Sequence[str] | None = None,
) -> int:
    """Run the validation loop for one edit batch."""
    lint_paths = list(paths)
    if changed_only:
        if changed_paths_override is None:
            lint_paths = _changed_paths(paths)
        else:
            lint_paths = sorted(dict.fromkeys(changed_paths_override))
        if lint_paths:
            if _is_verbose_logging():
                print(
                    "[edit-code] changed_only active: lint/type checks limited to changed paths: "
                    + _preview_items(lint_paths, limit=EDIT_CODE_PATH_PREVIEW_LIMIT, separator=", "),
                    flush=True,
                )
            else:
                print(
                    "[edit-code] changed_only active: lint/type checks limited to "
                    f"{len(lint_paths)} changed path(s)",
                    flush=True,
                )
        else:
            print("[edit-code] changed_only active: no changed paths detected for lint/type checks", flush=True)
    if _should_run_pytest(lint_paths):
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
    else:
        print(
            "[edit-code] pytest_guard skipped: changed paths are not runtime-relevant",
            flush=True,
        )

    if skip_ruff and skip_pyright:
        return 0

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
            ["uv", "run", "--no-sync", "python", "scripts/pyright_guard.py", *python_paths],
            label="pyright",
        )
        if rc != 0:
            return rc

    return 0


def _run_refresh(paths: Sequence[str], *, changed_paths: Sequence[str] | None = None) -> int:
    """Run the repo refresh hook for changed paths."""
    refresh_paths = list(paths)
    if changed_paths is not None:
        refresh_paths = sorted(dict.fromkeys(changed_paths))
        if not refresh_paths:
            print("[edit-code] refresh_indexes skipped: no local changes in requested paths", flush=True)
            return 0
    else:
        if not _has_path_changes(paths):
            print("[edit-code] refresh_indexes skipped: no local changes in requested paths", flush=True)
            return 0
    payload = json.dumps({"tool_input": {"paths": refresh_paths}})
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
    handoff: bool = False,
    verdict_pass: bool = False,
    feature_id: str | None = None,
    task_id: str | None = None,
) -> int:
    """Run validate + refresh + git sync in one deterministic flow."""
    if verdict_pass:
        return _resume_sync_closeout(feature_id=feature_id, task_id=task_id, no_push=no_push)

    dirty = _dirty_paths()
    if dirty is None:
        in_scope_dirty = list(paths)
        out_of_scope_dirty: list[str] = []
    else:
        in_scope_dirty, out_of_scope_dirty = _split_dirty_candidates(paths, dirty)

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

    rc = _run_validate(
        paths,
        tests,
        skip_ruff=skip_ruff,
        skip_pyright=skip_pyright,
        changed_only=changed_only,
        changed_paths_override=in_scope_dirty,
    )
    if rc != 0:
        return rc

    rc = _run_refresh(paths, changed_paths=in_scope_dirty)
    if rc != 0:
        return rc

    rc = _run_git_with_retry(["git", "add", *in_scope_dirty], label="git_add")
    if rc != 0:
        return rc

    if not _has_staged_path_changes(in_scope_dirty):
        print("[edit-code] sync skipped: nothing left to commit after refresh", flush=True)
        return 0

    rc = _run_git_with_retry(["git", "commit", "-m", commit_message], label="git_commit")
    if rc != 0:
        return rc

    if handoff and feature_id and task_id:
        # Run Handoff (QA)
        try:
            feature_dir = _resolve_feature_dir(feature_id)
        except ValueError as exc:
            print(f"[edit-code] ERROR: {exc}", file=sys.stderr)
            return 1

        handoff_res = _run_handoff_logic(feature_id=feature_id, task_id=task_id)
        if handoff_res["exit_code"] != 0:
            return handoff_res["exit_code"]

        # Stage 2: Generative Handoff (Semantic Review)
        _emit_generative_qa_handoff(
            feature_id=feature_id,
            task_id=task_id,
            handoff_payload_path=handoff_res.get("payload_file"),
            behavioral_result=handoff_res.get("behavioral_result"),
        )
        
        # STOP here for Agent review
        print("\n[edit-code] Task is pending semantic QA review. Provide verdict to continue.", flush=True)
        return 0

    if no_push:
        return 0

    return _run_git_with_retry(["git", "push"], label="git_push")


def _run_handoff_logic(
    *,
    feature_id: str,
    task_id: str,
) -> dict[str, Any]:
    """Internal helper to run QA handoff and return structured results."""
    handoff_cmd = [
        sys.executable,
        "scripts/speckit_offline_qa_handoff.py",
        "--feature-id",
        feature_id,
        "--task-id",
        task_id,
        "--json",
    ]
    print(f"[edit-code] starting behavioral QA handoff for {task_id}...", flush=True)
    completed = subprocess.run(
        handoff_cmd,
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        capture_output=True,
        env=_runtime_env(),
    )
    
    res = {"exit_code": completed.returncode, "qa_run_id": None, "payload_file": None, "behavioral_result": None}
    if completed.stdout:
        try:
            handoff_res = json.loads(completed.stdout)
            res["qa_run_id"] = handoff_res.get("qa_run_id")
            res["payload_file"] = handoff_res.get("payload_file")
            res["behavioral_result"] = handoff_res
            verdict = handoff_res.get("result_verdict", "UNKNOWN")
            print(f"[edit-code] handoff completed: verdict={verdict}, run_id={res['qa_run_id']}", flush=True)
        except json.JSONDecodeError:
            pass

    if completed.returncode != 0:
        print(f"[edit-code] behavioral QA failed (exit {completed.returncode})", file=sys.stderr, flush=True)
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
            
    return res


def _emit_generative_qa_handoff(
    *,
    feature_id: str,
    task_id: str,
    handoff_payload_path: str | None,
    behavioral_result: dict[str, Any] | None,
) -> None:
    """Emit a specialized handoff block for generative LLM QA review."""
    print("\n" + "=" * 80)
    print(f" [SPECKIT_QA_SEMANTIC_REVIEW_REQUIRED] {feature_id}/{task_id} ".center(80, "="))
    print("=" * 80)
    
    if not handoff_payload_path:
        print("ERROR: Missing handoff payload path", file=sys.stderr)
        return

    payload_path = Path(handoff_payload_path)
    if not payload_path.exists():
        print(f"ERROR: Payload file not found: {payload_path}", file=sys.stderr)
        return

    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("ERROR: Payload file contains invalid JSON", file=sys.stderr)
        return

    print(f"\n### HUD Acceptance Criteria ({task_id}):")
    ac = behavioral_result.get("acceptance_criteria") if behavioral_result else None
    if not ac:
        ac = "\n".join(payload.get("acceptance_criteria", []))
    print(ac or "No acceptance criteria found.")

    print(f"\n### File:Symbol Contract:")
    fs = behavioral_result.get("file_symbol") if behavioral_result else payload.get("file_symbol")
    print(fs or "No specific file:symbol defined.")

    print("\n### Behavioral Test Logs (Deterministic):")
    test_runs = behavioral_result.get("test_runs", []) if behavioral_result else payload.get("test_runs", [])
    if not test_runs:
        print("No test evidence found.")
    for run in test_runs:
        status = "PASS" if run.get("exit_code") == 0 else "FAIL"
        print(f"- [{status}] {run.get('command')}")

    print("\n### Implementation Diff:")
    diff = payload.get("diff", "")
    if diff:
        # Print a bounded preview of the diff to keep it token-efficient
        lines = diff.splitlines()
        if len(lines) > 100:
            print("\n".join(lines[:50]))
            print(f"\n... [{len(lines) - 100} lines truncated] ...\n")
            print("\n".join(lines[-50:]))
        else:
            print(diff)
    else:
        print("No diff found in payload.")

    print("\n" + "=" * 80)
    print(" ACTION REQUIRED: Perform semantic review as per /speckit.qa instructions ".center(80, "="))
    print("=" * 80 + "\n")


def _resume_sync_closeout(
    *,
    feature_id: str | None,
    task_id: str | None,
    no_push: bool,
) -> int:
    """Resume the sync flow after a generative verdict has been provided."""
    if not feature_id or not task_id:
        print("ERROR: --feature-id and --task-id are required to resume closeout", file=sys.stderr)
        return 1

    try:
        feature_dir = _resolve_feature_dir(feature_id)
    except ValueError as exc:
        print(f"[edit-code] ERROR: {exc}", file=sys.stderr)
        return 1

    # 1. Get current commit SHA
    commit_sha_proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True, check=True
    )
    current_sha = commit_sha_proc.stdout.strip()

    # 2. Run Closeout
    closeout_rc = _run_closeout(
        feature_id=feature_id,
        task_id=task_id,
        feature_dir=feature_dir,
        commit_sha=current_sha,
        qa_run_id=f"generative-pass-{current_sha[:8]}",
    )
    if closeout_rc != 0:
        return closeout_rc

    # 3. Amend commit with tasks.md update
    tasks_file = feature_dir / "tasks.md"
    try:
        tasks_rel_path = tasks_file.relative_to(REPO_ROOT).as_posix()
        _run_git_with_retry(["git", "add", tasks_rel_path], label="git_add_tasks_md")
        _run_git_with_retry(["git", "commit", "--amend", "--no-edit"], label="git_amend_closeout")
    except ValueError:
        pass

    if no_push:
        return 0

    return _run_git_with_retry(["git", "push"], label="git_push")


def _run_handoff_and_closeout(
    *,
    feature_id: str,
    task_id: str,
    paths: Sequence[str],
) -> int:
    """Run behavioral QA handoff and task closeout sequence."""
    try:
        feature_dir = _resolve_feature_dir(feature_id)
    except ValueError as exc:
        print(f"[edit-code] ERROR: {exc}", file=sys.stderr)
        return 1

    # 1. Run Handoff (Builds payload and runs Offline QA)
    handoff_cmd = [
        sys.executable,
        "scripts/speckit_offline_qa_handoff.py",
        "--feature-id",
        feature_id,
        "--task-id",
        task_id,
        "--json",
    ]
    print(f"[edit-code] starting behavioral QA handoff for {task_id}...", flush=True)
    completed = subprocess.run(
        handoff_cmd,
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        capture_output=True,
        env=_runtime_env(),
    )
    if completed.stdout:
        try:
            handoff_res = json.loads(completed.stdout)
            verdict = handoff_res.get("result_verdict", "UNKNOWN")
            qa_run_id = handoff_res.get("qa_run_id", "none")
            print(f"[edit-code] handoff completed: verdict={verdict}, run_id={qa_run_id}", flush=True)
        except json.JSONDecodeError:
            print("[edit-code] handoff output was not valid JSON", file=sys.stderr)

    if completed.returncode != 0:
        print(f"[edit-code] behavioral QA failed (exit {completed.returncode})", file=sys.stderr, flush=True)
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
        return completed.returncode

    # 2. Run Closeout (Audit Ledger and HUD)
    # We need the commit SHA, but we haven't committed yet in the sync flow.
    # Wait! speckit_closeout_task.py requires --commit-sha.
    # In the sync flow, we usually validate -> refresh -> add -> commit -> push.
    # So handoff/closeout should happen AFTER commit but BEFORE push.
    return 0


def _run_closeout(
    *,
    feature_id: str,
    task_id: str,
    feature_dir: Path,
    commit_sha: str,
    qa_run_id: str | None = None,
) -> int:
    """Run canonical task closeout logic."""
    tasks_file = feature_dir / "tasks.md"
    ledger_file = REPO_ROOT / ".speckit" / "task-ledger.jsonl"

    closeout_cmd = [
        sys.executable,
        "scripts/speckit_closeout_task.py",
        "--feature-id",
        feature_id,
        "--task-id",
        task_id,
        "--tasks-file",
        str(tasks_file),
        "--ledger-file",
        str(ledger_file),
        "--commit-sha",
        commit_sha,
        "--qa-run-id",
        qa_run_id or "pending",
        "--json",
    ]
    print(f"[edit-code] closing out task {task_id}...", flush=True)
    return _run_command(closeout_cmd, label="task_closeout")


def _run_task_add(
    *,
    description: str,
    feature_id: str,
    story: str | None = None,
    points: int = 1,
) -> int:
    """Add a task to tasks.md and materialize its HUD/Ledger state."""
    try:
        feature_dir = _resolve_feature_dir(feature_id)
    except ValueError as exc:
        print(f"[edit-code] ERROR: {exc}", file=sys.stderr)
        return 1

    tasks_file = feature_dir / "tasks.md"
    if not tasks_file.exists():
        # Scaffold from template if missing
        template = REPO_ROOT / ".specify/templates/tasks-template.md"
        if template.exists():
            print(f"[edit-code] Initializing {tasks_file} from template...")
            tasks_file.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            print(f"[edit-code] WARNING: tasks template missing. Creating empty {tasks_file}...", file=sys.stderr)
            tasks_file.write_text("# Tasks\n\n", encoding="utf-8")

    # 1. Resolve Next Task ID
    content = tasks_file.read_text(encoding="utf-8")
    task_ids = re.findall(r"\bT(\d{3})\b", content)
    next_id_num = max([int(tid) for tid in task_ids]) + 1 if task_ids else 1
    next_id = f"T{next_id_num:03d}"

    # 2. Append to tasks.md
    if " — " not in description and " - " not in description:
        print("[edit-code] WARNING: No ' — File:Symbol' annotation found. HUD will be a template only.", file=sys.stderr)

    story_label = f" [{story}]" if story else ""
    task_line = f"- [ ] {next_id}{story_label} {description}\n"
    
    # Try to find a good place to append (e.g. before Dependencies or at the end)
    if "## Dependencies" in content:
        new_content = content.replace("## Dependencies", f"{task_line}## Dependencies")
    else:
        new_content = content + ("\n" if not content.endswith("\n") else "") + task_line
    
    tasks_file.write_text(new_content, encoding="utf-8")
    print(f"[edit-code] Registered {next_id} in tasks.md")

    # 3. Materialize HUD
    print(f"[edit-code] Materializing HUD for {next_id}...")
    rc = subprocess.run([
        sys.executable, "scripts/speckit_remake_huds.py",
        "--feature-dir", str(feature_dir),
        "--task-id", next_id
    ], check=False).returncode
    
    if rc == 0:
        print(f"[edit-code] Task {next_id} registered and HUD generated.")
    else:
        print(f"[edit-code] WARNING: HUD materialization failed (exit code {rc}).", file=sys.stderr)
    
    return rc


def main(argv: Sequence[str] | None = None) -> int:
    """Entrypoint for deterministic edit workflow execution."""
    _reset_runtime_caches()
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
    if args.command == "task":
        if args.task_command == "add":
            return _run_task_add(
                description=args.description,
                feature_id=args.feature_id,
                story=args.story,
                points=args.points,
            )
    if args.command == "sync":
        if args.handoff or args.verdict_pass:
            if not args.feature_id or not args.task_id:
                print("ERROR: --feature-id and --task-id are required for handoff/verdict", file=sys.stderr)
                return 1

        return _run_sync(
            paths,
            args.tests,
            commit_message=args.commit_message,
            no_push=args.no_push,
            skip_ruff=args.skip_ruff,
            skip_pyright=args.skip_pyright,
            changed_only=args.changed_only,
            handoff=args.handoff,
            verdict_pass=args.verdict_pass,
            feature_id=args.feature_id,
            task_id=args.task_id,
        )
    raise ValueError(f"unknown command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
