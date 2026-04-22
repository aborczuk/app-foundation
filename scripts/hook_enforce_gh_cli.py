#!/usr/bin/env python3
"""PreToolUse hook: enforce low-payload GitHub CLI usage patterns."""

from __future__ import annotations

import json
import shlex
import sys
from typing import Sequence

SAFE_WRAPPER_MARKERS = (
    "scripts/gh_safe_pr_info.sh",
    "scripts/gh_safe_pr_files.sh",
)

HEAVY_PR_VIEW_FIELDS = {
    "files",
    "commits",
    "reviews",
    "latestReviews",
}


def _emit_deny(reason: str) -> None:
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


def _tokenize(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _contains_safe_wrapper(command: str) -> bool:
    return any(marker in command for marker in SAFE_WRAPPER_MARKERS)


def _gh_args(tokens: Sequence[str]) -> tuple[str, ...]:
    try:
        gh_idx = next(i for i, tok in enumerate(tokens) if tok == "gh" or tok.endswith("/gh"))
    except StopIteration:
        return ()
    return tuple(tokens[gh_idx + 1 :])


def _extract_json_fields(tokens: Sequence[str]) -> set[str]:
    fields: set[str] = set()
    for idx, token in enumerate(tokens):
        if token == "--json" and idx + 1 < len(tokens):
            raw = tokens[idx + 1]
            fields.update(part.strip() for part in raw.split(",") if part.strip())
        elif token.startswith("--json="):
            raw = token.split("=", 1)[1]
            fields.update(part.strip() for part in raw.split(",") if part.strip())
    return fields


def _is_write_api_call(tokens: Sequence[str]) -> bool:
    for idx, token in enumerate(tokens):
        if token == "-X" and idx + 1 < len(tokens):
            return tokens[idx + 1].upper() in {"POST", "PATCH", "PUT", "DELETE"}
        if token.startswith("-X") and len(token) > 2:
            return token[2:].upper() in {"POST", "PATCH", "PUT", "DELETE"}
        if token.startswith("--method="):
            return token.split("=", 1)[1].upper() in {"POST", "PATCH", "PUT", "DELETE"}
    return False


def main() -> int:
    """Deny high-payload direct `gh` commands unless safe wrappers are used."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    command = payload.get("tool_input", {}).get("command", "").strip()
    if not command or "gh" not in command:
        return 0

    if _contains_safe_wrapper(command):
        return 0

    tokens = _tokenize(command)
    gh_args = _gh_args(tokens)
    if not gh_args:
        return 0

    primary = gh_args[0]
    secondary = gh_args[1] if len(gh_args) > 1 else ""

    if primary in {"version", "--version"}:
        return 0
    if primary == "auth" and secondary == "status":
        return 0

    if primary == "pr" and secondary == "diff":
        _emit_deny(
            "Direct `gh pr diff` is blocked due to high token payload risk. "
            "Use `scripts/gh_safe_pr_files.sh <repo> <pr_number>` plus targeted file patch retrieval."
        )
        return 0

    if primary == "search" and secondary == "code":
        _emit_deny(
            "Direct `gh search code` is blocked in this repo. "
            "Use codegraph-first local discovery for repo code reads, or approved scoped wrappers."
        )
        return 0

    if primary == "api":
        if _is_write_api_call(tokens):
            return 0
        _emit_deny(
            "Direct read-style `gh api` calls are blocked to prevent oversized responses. "
            "Use `scripts/gh_safe_pr_info.sh <repo> <pr_number>` or `scripts/gh_safe_pr_files.sh <repo> <pr_number>`."
        )
        return 0

    if primary == "pr" and secondary == "view":
        fields = _extract_json_fields(tokens)
        if not fields:
            _emit_deny(
                "Direct `gh pr view` without an explicit --json field list is blocked. "
                "Use `scripts/gh_safe_pr_info.sh <repo> <pr_number>`."
            )
            return 0
        if fields & HEAVY_PR_VIEW_FIELDS:
            _emit_deny(
                "High-payload `gh pr view --json` fields requested "
                f"({', '.join(sorted(fields & HEAVY_PR_VIEW_FIELDS))}). "
                "Use `scripts/gh_safe_pr_files.sh <repo> <pr_number>` for file listings."
            )
            return 0
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
