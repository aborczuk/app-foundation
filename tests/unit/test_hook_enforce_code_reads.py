from __future__ import annotations

import json
import os
import subprocess
import sys


def _run_hook(command: str, *, max_lines: str | None = None) -> str:
    """Run the code-read hook and return its stdout payload."""
    payload = {"tool_input": {"command": command}}
    env = os.environ.copy()
    if max_lines is not None:
        env["SPECKIT_READ_CODE_MAX_LINES"] = max_lines
    result = subprocess.run(
        [sys.executable, "scripts/hook_enforce_code_reads.py"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    return result.stdout.strip()


def test_read_code_window_limit_comes_from_env_var() -> None:
    """The hook should derive its deny message from the configured helper limit."""
    stdout = _run_hook(
        "uv run python scripts/read_code.py window scripts/read_code.py 1 13",
        max_lines="12",
    )

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "over 12 are denied" in decision["permissionDecisionReason"]


def test_read_code_window_limit_uses_bounded_span_not_end_line() -> None:
    """A later window under the limit should not be denied just because the end line is large."""
    stdout = _run_hook(
        "uv run python scripts/read_code.py window scripts/read_code.py 81 119",
        max_lines="80",
    )

    assert stdout == ""


def test_read_code_window_limit_denies_actual_span_over_limit() -> None:
    """The hook should deny windows whose computed span exceeds the configured limit."""
    stdout = _run_hook(
        "uv run python scripts/read_code.py window scripts/read_code.py 81 161",
        max_lines="80",
    )

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "over 80 are denied" in decision["permissionDecisionReason"]
