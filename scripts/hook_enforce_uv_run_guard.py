#!/usr/bin/env python3
"""PreToolUse hook: enforce uv run routing through the cache helper."""

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


def _contains_uv_run_invocation(tokens: list[str]) -> bool:
    """Return whether tokens include a direct uv run invocation."""
    for index, token in enumerate(tokens):
        if Path(token).name == "uv" and index + 1 < len(tokens) and tokens[index + 1] == "run":
            return True
    return False


def _uses_uv_cache_helper(tokens: list[str]) -> bool:
    """Return whether the command already routes through the cache helper."""
    return any(Path(token).name == "uv_cache_dir.sh" for token in tokens)


def _uses_inline_cache_override(tokens: list[str]) -> bool:
    """Return whether the command sets UV_CACHE_DIR inline."""
    return any(token.startswith("UV_CACHE_DIR=") for token in tokens)


def main() -> int:
    """Deny direct uv run calls unless cache routing is explicit."""
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

    if not _contains_uv_run_invocation(tokens):
        return 0
    if _uses_uv_cache_helper(tokens) or _uses_inline_cache_override(tokens):
        return 0

    _emit_deny(
        "Direct uv run calls are denied. Source `scripts/uv_cache_dir.sh` first so uv's cache "
        "stays inside the repository, then run uv."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
