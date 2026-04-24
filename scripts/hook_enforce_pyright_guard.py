#!/usr/bin/env python3
"""PreToolUse hook: enforce deterministic Pyright execution through edit workflow."""

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


def _contains_pyright_invocation(tokens: list[str]) -> bool:
    """Return whether tokens include a direct Pyright invocation."""
    for index, token in enumerate(tokens):
        if Path(token).name == "pyright":
            return True
        if token == "-m" and index + 1 < len(tokens) and tokens[index + 1] == "pyright":
            return True
    return False


def _uses_edit_workflow(tokens: list[str]) -> bool:
    """Return whether command tokens are already using deterministic edit workflow scripts."""
    return any(Path(token).name == "edit_code.py" for token in tokens)


def main() -> int:
    """Deny direct Pyright calls and require edit workflow routing."""
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

    if not _contains_pyright_invocation(tokens):
        return 0
    if _uses_edit_workflow(tokens):
        return 0

    _emit_deny(
        "Direct pyright calls are denied. Use `edit_validate --paths <paths> --tests <pytest selectors>` "
        "(or `edit_sync` for full validation+refresh+sync) so type checks run in deterministic sequence."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
