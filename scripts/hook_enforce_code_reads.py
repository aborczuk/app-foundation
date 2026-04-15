#!/usr/bin/env python3
"""PreToolUse hook: deny broad reads of large code/doc files unless read-code helper is used."""

from __future__ import annotations

import json
import re
import shlex
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

TEXT_EXTENSIONS = {
    ".md",
    ".markdown",
    ".rst",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
}

LINE_THRESHOLD = 200
MAX_HELPER_LINES = 80


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

    suffix = path.suffix.lower()
    if suffix not in CODE_EXTENSIONS and suffix not in TEXT_EXTENSIONS:
        return False

    try:
        line_count = sum(1 for _ in path.open("r", encoding="utf-8", errors="ignore"))
    except OSError:
        return False

    return line_count > LINE_THRESHOLD


def _extract_read_code_policy(command: str) -> tuple[str, str, int, bool] | None:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None

    helper_idx = -1
    helper_mode = ""
    for idx, token in enumerate(tokens):
        if token in {"read_code_context", "read_code_window"}:
            helper_idx = idx
            helper_mode = "context" if token == "read_code_context" else "window"
            break
        if token.endswith("read-code.sh"):
            helper_idx = idx
            helper_mode = ""
            break
    if helper_idx == -1:
        return None

    if helper_mode:
        mode = helper_mode
        args = tokens[helper_idx + 1 :]
    else:
        if helper_idx + 1 >= len(tokens):
            return None
        mode = tokens[helper_idx + 1]
        args = tokens[helper_idx + 2 :]
    if mode not in {"context", "window"}:
        return None
    if len(args) < 2:
        return None

    path_text = args[0]
    allow_fallback = "--allow-fallback" in args
    requested_lines = 60

    if mode == "context":
        tail = args[2:]
        for token in tail:
            if token.isdigit():
                requested_lines = int(token)
                break
    else:
        tail = args[2:]
        for token in tail:
            if token.isdigit():
                requested_lines = int(token)
                break

    return mode, path_text, requested_lines, allow_fallback


def main() -> int:
    """Evaluate command payload and deny risky broad reads of large code files."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    command = payload.get("tool_input", {}).get("command", "").strip()
    if not command:
        return 0

    helper_policy = _extract_read_code_policy(command)
    if helper_policy is not None:
        _, target_path, requested_lines, allow_fallback = helper_policy
        if _is_large_code_file(target_path):
            if requested_lines > MAX_HELPER_LINES:
                _emit_deny(
                    f"read-code helper line windows over {MAX_HELPER_LINES} are denied for large files. "
                    "Use a smaller bounded window."
                )
                return 0
            if allow_fallback:
                _emit_deny(
                    "read-code --allow-fallback is denied for large code/doc files. "
                    "Use strict symbol resolution or narrow the symbol first."
                )
                return 0
        return 0

    if "SPECKIT_HUD_DIRECT_READ=1" in command and "read-code.sh" in command:
        return 0

    risky_read_tokens = ("cat ", "nl -ba ", "sed -n", "awk ", "head ", "tail ", "less ", "more ")
    if not any(token in command for token in risky_read_tokens):
        return 0

    for candidate in _extract_candidate_paths(command):
        if _is_large_code_file(candidate):
            _emit_deny(
                "Large code/doc-file reads must use scripts/read-code.sh "
                "(read_code_context/read_code_window) with codegraph discovery first, "
                "or approved HUD direct-read fast-path."
            )
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
