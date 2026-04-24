#!/usr/bin/env python3
"""PreToolUse hook that denies direct `git diff` commands."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

_GIT_SCOPE_FLAGS = {"-C", "--git-dir", "--work-tree"}


def _emit_deny(reason: str) -> None:
    """Emit a Codex hook denial payload with the provided reason."""
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


def _contains_git_diff_invocation(tokens: list[str]) -> bool:
    """Return whether command tokens contain a direct `git diff` invocation."""
    for index, token in enumerate(tokens):
        if Path(token).name != "git":
            continue
        cursor = index + 1
        while cursor < len(tokens):
            current = tokens[cursor]
            if current in _GIT_SCOPE_FLAGS:
                cursor += 2
                continue
            if current.startswith("-C") and current != "-C":
                cursor += 1
                continue
            if current.startswith("-"):
                cursor += 1
                continue
            break
        if cursor < len(tokens) and tokens[cursor] == "diff":
            return True
    return False


def _uses_git_diff_guard(tokens: list[str]) -> bool:
    """Return whether command tokens already route through git_diff_guard.py."""
    return any(Path(token).name == "git_diff_guard.py" for token in tokens)


def main() -> int:
    """Deny direct git diff calls and require deterministic guard routing."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    command = str(payload.get("tool_input", {}).get("command", "")).strip()
    if not command:
        return 0

    try:
        tokens = shlex.split(command)
    except ValueError:
        return 0

    if not _contains_git_diff_invocation(tokens):
        return 0
    if _uses_git_diff_guard(tokens):
        return 0

    _emit_deny(
        "Direct git diff calls are denied. Use `python scripts/git_diff_guard.py [diff args]` "
        "(or `uv run --no-sync python scripts/git_diff_guard.py [diff args]`) so output stays bounded."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
