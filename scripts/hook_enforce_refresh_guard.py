#!/usr/bin/env python3
"""PreToolUse hook: enforce refresh-index execution through deterministic edit workflow."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path


def _emit_deny(reason: str) -> None:
    """Emit a deny decision payload for the PreToolUse hook contract."""
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


def _contains_refresh_hook_invocation(tokens: list[str]) -> bool:
    """Return whether tokens include a direct hook_refresh_indexes script invocation."""
    return any(Path(token).name == "hook_refresh_indexes.py" for token in tokens)


def _uses_edit_workflow(tokens: list[str]) -> bool:
    """Return whether command tokens are already using deterministic edit workflow scripts."""
    return any(Path(token).name == "edit_code.py" for token in tokens)


def main() -> int:
    """Deny direct refresh-hook calls and require deterministic edit workflow routing."""
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

    if not _contains_refresh_hook_invocation(tokens):
        return 0
    if _uses_edit_workflow(tokens):
        return 0

    _emit_deny(
        "Direct hook_refresh_indexes.py calls are denied. Use `edit_sync` "
        "(or `edit_refresh --paths <paths>`) so refresh runs in-sequence with validation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
