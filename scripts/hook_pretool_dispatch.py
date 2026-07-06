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
GUARD_SCRIPTS = (
    "hook_enforce_code_reads.py",
    "hook_enforce_refresh_guard.py",
    "hook_enforce_pyright_guard.py",
    "hook_enforce_ruff_guard.py",
    "hook_enforce_git_diff_guard.py",
)


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


def _payload_contains_delete_file_marker(payload: Any) -> bool:
    """Return true when any tool-input string contains the apply_patch delete-file marker."""
    if isinstance(payload, str):
        return "*** Delete File:" in payload
    if isinstance(payload, dict):
        return any(_payload_contains_delete_file_marker(value) for value in payload.values())
    if isinstance(payload, list):
        return any(_payload_contains_delete_file_marker(value) for value in payload)
    return False


def _normalize_tool_input_command(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Normalize command-bearing tool inputs so hooks can read one canonical field."""
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

    if _payload_contains_delete_file_marker(payload.get("tool_input")):
        _emit_deny("apply_patch payloads containing `*** Delete File:` are denied.")
        return 0

    if not command:
        return 0

    payload_text = json.dumps(payload)

    deny_reason = _worktree_guard(command)
    if deny_reason is not None:
        _emit_deny(deny_reason)
        return 0

    deny_reason = _grep_guard(command)
    if deny_reason is not None:
        _emit_deny(deny_reason)
        return 0

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
