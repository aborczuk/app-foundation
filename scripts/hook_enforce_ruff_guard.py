#!/usr/bin/env python3
"""PreToolUse hook: enforce guarded Ruff execution through scripts/ruff_guard.py."""

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


def _contains_ruff_invocation(tokens: list[str]) -> bool:
    """Return whether tokens include a direct Ruff invocation."""
    for index, token in enumerate(tokens):
        if Path(token).name == "ruff":
            return True
        if token == "-m" and index + 1 < len(tokens) and tokens[index + 1] == "ruff":
            return True
    return False


def _uses_ruff_guard(tokens: list[str]) -> bool:
    """Return whether command tokens already route through ruff_guard.py."""
    return any(Path(token).name == "ruff_guard.py" for token in tokens)


def main() -> int:
    """Deny direct Ruff calls and require deterministic wrapper usage."""
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

    if not _contains_ruff_invocation(tokens):
        return 0
    if _uses_ruff_guard(tokens):
        return 0

    _emit_deny(
        "Direct ruff calls are denied. Use `edit_validate` for normal workflow, or "
        "`uv run --no-sync python scripts/ruff_guard.py <python-paths>` for targeted lint "
        "so non-Python inputs are blocked and failure output stays bounded."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
