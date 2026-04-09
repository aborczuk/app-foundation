#!/usr/bin/env python3
"""PreToolUse hook: deny broad reads of large code files unless read-code helper is used."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CODE_EXTENSIONS = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".kt",
    ".go",
    ".rs",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".scala",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
}

LINE_THRESHOLD = 200


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


def _extract_candidate_paths(command: str) -> list[str]:
    pattern = re.compile(r"([A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)")
    return [m.group(1) for m in pattern.finditer(command)]


def _is_large_code_file(path_text: str) -> bool:
    if any(ch in path_text for ch in ("$", "*", "?")):
        return False

    path = Path(path_text)
    if not path.is_file():
        return False

    if path.suffix.lower() not in CODE_EXTENSIONS:
        return False

    try:
        line_count = sum(1 for _ in path.open("r", encoding="utf-8", errors="ignore"))
    except OSError:
        return False

    return line_count > LINE_THRESHOLD


def main() -> int:
    """Evaluate command payload and deny risky broad reads of large code files."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    command = payload.get("tool_input", {}).get("command", "").strip()
    if not command:
        return 0

    helper_markers = (
        "read_code_context",
        "read_code_window",
        "scripts/read-code.sh",
        "read-code.sh context",
        "read-code.sh window",
    )
    if any(marker in command for marker in helper_markers):
        return 0

    risky_read_tokens = ("cat ", "nl -ba ", "sed -n", "awk ", "head ", "tail ", "less ", "more ")
    if not any(token in command for token in risky_read_tokens):
        return 0

    for candidate in _extract_candidate_paths(command):
        if _is_large_code_file(candidate):
            _emit_deny(
                "Large code-file reads must use scripts/read-code.sh "
                "(read_code_context/read_code_window) with codegraph discovery first."
            )
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
