#!/usr/bin/env python3
"""PreToolUse hook: enforce guarded pytest execution through pytest_guard.py."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path


def _emit_deny(reason: str) -> None:
    """Emit a deny decision payload for the hook runtime."""
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


def _contains_pytest_invocation(tokens: list[str]) -> bool:
    """Return whether a bash command token list invokes pytest directly."""
    for index, token in enumerate(tokens):
        if token == "pytest":
            return True
        if token == "-m" and index + 1 < len(tokens) and tokens[index + 1] == "pytest":
            return True
    return False


def _uses_pytest_guard(tokens: list[str]) -> bool:
    """Return whether command tokens already route through pytest_guard.py."""
    return any(Path(token).name == "pytest_guard.py" for token in tokens)


def main() -> int:
    """Deny direct pytest calls and require pytest_guard wrapper usage."""
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

    if not _contains_pytest_invocation(tokens):
        return 0
    if _uses_pytest_guard(tokens):
        return 0

    _emit_deny(
        "Direct pytest calls are denied. Use `edit_validate --paths <paths> --tests <pytest selectors>` "
        "for normal workflow, or "
        "`uv run --no-sync python scripts/pytest_guard.py run -- <pytest args>` "
        "(for example `uv run --no-sync python scripts/pytest_guard.py run -- tests/unit/test_x.py -k case_name`) "
        "so output remains compact and full logs are persisted to file."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
