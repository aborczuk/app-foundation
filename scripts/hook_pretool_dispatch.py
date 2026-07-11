#!/usr/bin/env python3
"""PreToolUse dispatcher that runs the local guard checks in one process."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

from scripts import hook_edit_paths  # noqa: E402

GUARD_SCRIPTS = (
    "hook_enforce_code_reads.py",
    "hook_enforce_refresh_guard.py",
    "hook_enforce_pyright_guard.py",
    "hook_enforce_ruff_guard.py",
    "hook_enforce_git_diff_guard.py",
)
REPO_ROOT = SCRIPT_DIR.parent
COMMAND_TOOL_NAMES = {"exec_command", "Bash"}


def _emit_deny(reason: str) -> None:
    """Emit the standard PreToolUse denial payload."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def _worktree_guard(command: str) -> str | None:
    """Return the deny reason for disallowed Git worktree-style commands."""
    if re.search(r"(?<!\S)git\s+worktree(?:\s|$)", command):
        return "Git worktrees are disabled here. Use only named branches in the main checkout."
    if re.search(r"(?<!\S)git\s+(switch|checkout)(?:\s+--detach|\s+--orphan)", command):
        return "Detached or orphan checkouts are disabled here. Use named branches only."
    if re.search(r"(?<!\S)git\s+(update-ref|symbolic-ref)", command):
        return "Low-level ref plumbing is disabled here. Use normal branch commands only."
    return None


def _grep_guard(command: str) -> str | None:
    """Return the deny reason for direct grep/rg Bash usage."""
    if re.search(r"(?<!\S)git\s+grep(?:\s|$)", command):
        return (
            "Direct `git grep` is denied. For repo search use `uv run python scripts/read_code.py "
            "context <query>`. "
            "For remote/history inspection use `uv run python scripts/github_guard.py run -- gh ...` "
            "or bounded `git log -S/-G` history queries."
        )
    for match in re.finditer(r"(?<![a-zA-Z0-9_])(grep|rg)(\s|$)", command):
        before = command[: match.start()].rstrip()
        if not before.endswith("|"):
            return (
                "Direct grep/rg Bash search is denied. Use `uv run python scripts/read_code.py "
                "context <query>` for repo lookup."
            )
    return None


def _normalize_tool_input_command(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Normalize command-bearing tool inputs so hooks can read one canonical field."""
    tool_name = str(payload.get("tool_name", "")).strip()
    if tool_name not in COMMAND_TOOL_NAMES:
        return payload, ""

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return payload, ""

    command = str(tool_input.get("command", "")).strip()
    if command:
        return payload, command

    fallback_command = str(tool_input.get("cmd", "")).strip()
    if not fallback_command:
        return payload, ""

    normalized_tool_input = dict(tool_input)
    normalized_tool_input["command"] = fallback_command
    normalized_payload = dict(payload)
    normalized_payload["tool_input"] = normalized_tool_input
    return normalized_payload, fallback_command


def _redact_verbose_tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with large user-authored payload fields replaced for delegated guards."""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return payload

    redacted_tool_input = dict(tool_input)
    for key in ("patch", "content", "text"):
        value = redacted_tool_input.get(key)
        if isinstance(value, str) and value:
            redacted_tool_input[key] = f"[redacted {key}: {len(value)} chars]"

    redacted_payload = dict(payload)
    redacted_payload["tool_input"] = redacted_tool_input
    return redacted_payload


def _load_guard_main(script_name: str) -> Callable[[], int] | None:
    """Load a guard module and return its main function if available."""
    module_path = SCRIPT_DIR / script_name
    spec = importlib.util.spec_from_file_location(f"codex_hook_{module_path.stem}", module_path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None

    main = getattr(module, "main", None)
    return cast(Callable[[], int], main) if callable(main) else None


def _load_module(script_path: Path) -> Any | None:
    """Load a helper module from a repository path."""
    spec = importlib.util.spec_from_file_location(f"codex_hook_{script_path.stem}", script_path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return module


def _extract_edit_sync_args(command: str) -> dict[str, str]:
    """Extract edit sync arguments from a shell command string."""
    match = re.search(r"(?<!\\S)scripts/edit_code\\.py\\s+sync(?:\\s|$)", command)
    if match is None:
        return {}

    args: dict[str, str] = {}
    for name in ("feature-id", "task-id", "tasks-file", "actor"):
        value_match = re.search(rf"--{name}\\s+([^\\s]+)", command)
        if value_match is not None:
            args[name] = value_match.group(1).strip("\"' ")
    return args


def _payload_looks_like_edit(payload: dict[str, Any]) -> bool:
    """Return true when the tool payload looks like a direct edit/write request."""
    tool_name = str(payload.get("tool_name", "")).strip()
    if tool_name in {"Edit", "Write", "MultiEdit", "apply_patch"}:
        return True
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return False
    return any(key in tool_input for key in ("file_path", "path", "file_paths", "paths", "content", "text"))


def _direct_edit_requires_branch_guard(payload: dict[str, Any]) -> bool:
    """Return true when a direct edit payload targets any branch-guarded path."""
    changed_paths = hook_edit_paths.collect_changed_paths(payload, root=REPO_ROOT)
    if not changed_paths:
        return True
    return bool(hook_edit_paths.direct_edit_branch_guard_paths(changed_paths, root=REPO_ROOT))


def _current_branch() -> str:
    """Return the current git branch name, or an empty string when unavailable."""
    try:
        import subprocess

        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def _branch_guard() -> str | None:
    """Return a deny reason when code edits are attempted from a non-feature branch."""
    branch = _current_branch()
    if not branch:
        return "Unable to determine the current git branch before edit sync."

    common_module = _load_module(REPO_ROOT / ".specify" / "scripts" / "python" / "common.py")
    if common_module is None:
        return None

    check_feature_branch = getattr(common_module, "check_feature_branch", None)
    if not callable(check_feature_branch):
        return None

    try:
        check_feature_branch(branch, True)
    except SystemExit:
        return (
            f"Edit sync is blocked on branch '{branch}'. "
            "Switch to the feature branch for the spec before editing."
        )
    return None


def _task_start_guard(command: str) -> str | None:
    """Return a deny reason when an edit sync skips the existing task start gate."""
    sync_args = _extract_edit_sync_args(command)
    feature_id = sync_args.get("feature-id")
    task_id = sync_args.get("task-id")
    if not feature_id or not task_id:
        return None

    task_ledger_module = _load_module(SCRIPT_DIR / "task_ledger.py")
    if task_ledger_module is None:
        return None

    assert_can_start_task = getattr(task_ledger_module, "assert_can_start_task", None)
    if not callable(assert_can_start_task):
        return None

    tasks_file = Path(sync_args.get("tasks-file", REPO_ROOT / "specs" / feature_id / "tasks.md"))
    ledger_path = REPO_ROOT / ".speckit" / "task-ledger.jsonl"
    actor = sync_args.get("actor")
    try:
        assert_can_start_task(ledger_path, tasks_file, feature_id, task_id, actor=actor)
    except SystemExit:
        return (
            f"Edit sync is blocked until the existing task start gate passes for {feature_id}/{task_id}. "
            "Run the speckit implement preflight gate first."
        )
    return None


def _run_guard(main: Callable[[], int], payload_text: str) -> str:
    """Run a guard main with the provided payload and capture its stdout."""
    buffer = io.StringIO()
    original_stdin = sys.stdin
    try:
        sys.stdin = io.StringIO(payload_text)
        with contextlib.redirect_stdout(buffer):
            main()
    except Exception:
        return ""
    finally:
        sys.stdin = original_stdin

    return buffer.getvalue()


def main() -> int:
    """Evaluate the consolidated pre-tool hooks and stop at the first denial."""
    try:
        payload_text = sys.stdin.read()
    except Exception:
        return 0

    if not payload_text:
        return 0

    try:
        payload = json.loads(payload_text)
    except Exception:
        return 0

    payload, command = _normalize_tool_input_command(payload)


    edit_payload = _payload_looks_like_edit(payload)
    if not command and not edit_payload:
        return 0

    deny_reason = _worktree_guard(command)
    if deny_reason is not None:
        _emit_deny(deny_reason)
        return 0

    deny_reason = _grep_guard(command)
    if deny_reason is not None:
        _emit_deny(deny_reason)
        return 0

    edit_sync_guard = _extract_edit_sync_args(command)
    if edit_sync_guard:
        deny_reason = _branch_guard()
        if deny_reason is not None:
            _emit_deny(deny_reason)
            return 0
        deny_reason = _task_start_guard(command)
        if deny_reason is not None:
            _emit_deny(deny_reason)
            return 0

    if edit_payload and _direct_edit_requires_branch_guard(payload):
        deny_reason = _branch_guard()
        if deny_reason is not None:
            _emit_deny(deny_reason)
            return 0

    payload_text = json.dumps(_redact_verbose_tool_input(payload))

    # Load the remaining checks lazily so a cheap early deny does not pay for every import.
    for script_name in GUARD_SCRIPTS:
        guard_main = _load_guard_main(script_name)
        if guard_main is None:
            continue
        output = _run_guard(guard_main, payload_text)
        if output.strip():
            sys.stdout.write(output)
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
