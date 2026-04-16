"""Shadow comparison helpers for temporary rollout parity checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from difflib import unified_diff
from typing import Any


def _normalize_text(text: str, replacements: Sequence[tuple[str, str]]) -> str:
    normalized = text
    for old, new in replacements:
        normalized = normalized.replace(old, new)
    return normalized


def _diff_text(label: str, legacy_text: str, modern_text: str) -> str:
    if legacy_text == modern_text:
        return ""
    diff_lines = unified_diff(
        legacy_text.splitlines(),
        modern_text.splitlines(),
        fromfile=f"legacy:{label}",
        tofile=f"python:{label}",
        lineterm="",
    )
    return "\n".join(diff_lines)


def compare_outputs(
    legacy: Mapping[str, Any],
    modern: Mapping[str, Any],
    *,
    normalize_replacements: Sequence[tuple[str, str]] = (),
) -> dict[str, Any]:
    """Compare legacy and modern outputs and return a shadow parity report.

    The report is intentionally text-centric so temporary rollout modes can emit
    human-readable diffs while still returning a structured failure contract.
    """
    legacy_stdout = _normalize_text(str(legacy.get("stdout", "")), normalize_replacements)
    modern_stdout = _normalize_text(str(modern.get("stdout", "")), normalize_replacements)
    legacy_stderr = _normalize_text(str(legacy.get("stderr", "")), normalize_replacements)
    modern_stderr = _normalize_text(str(modern.get("stderr", "")), normalize_replacements)

    legacy_exit_code = int(legacy.get("exit_code", 0))
    modern_exit_code = int(modern.get("exit_code", 0))

    stdout_match = legacy_stdout == modern_stdout
    stderr_match = legacy_stderr == modern_stderr
    exit_code_match = legacy_exit_code == modern_exit_code

    stdout_diff = _diff_text("stdout", legacy_stdout, modern_stdout)
    stderr_diff = _diff_text("stderr", legacy_stderr, modern_stderr)

    differences: list[dict[str, Any]] = []
    if not stdout_match:
        differences.append({"channel": "stdout", "diff": stdout_diff})
    if not stderr_match:
        differences.append({"channel": "stderr", "diff": stderr_diff})
    if not exit_code_match:
        differences.append(
            {
                "channel": "exit_code",
                "legacy": legacy_exit_code,
                "modern": modern_exit_code,
            }
        )

    return {
        "ok": stdout_match and stderr_match and exit_code_match,
        "stdout_match": stdout_match,
        "stderr_match": stderr_match,
        "exit_code_match": exit_code_match,
        "differences": differences,
        "legacy": {
            "stdout": legacy_stdout,
            "stderr": legacy_stderr,
            "exit_code": legacy_exit_code,
        },
        "modern": {
            "stdout": modern_stdout,
            "stderr": modern_stderr,
            "exit_code": modern_exit_code,
        },
    }
