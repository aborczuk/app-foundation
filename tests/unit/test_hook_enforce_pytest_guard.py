"""Tests for the pytest guard PreToolUse hook."""

from __future__ import annotations

import json
import subprocess
import sys


def _run_hook(command: str) -> str:
    payload = {"tool_input": {"command": command}}
    result = subprocess.run(
        [sys.executable, "scripts/hook_enforce_pytest_guard.py"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_direct_pytest_is_denied() -> None:
    stdout = _run_hook("pytest tests/unit/test_hook_enforce_code_reads.py -q")

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "Direct pytest calls are denied" in decision["permissionDecisionReason"]
    assert "pytest_guard.py run" in decision["permissionDecisionReason"]


def test_python_module_pytest_is_denied() -> None:
    stdout = _run_hook("uv run --no-sync python -m pytest tests/unit/test_hook_enforce_code_reads.py")

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"


def test_pytest_guard_command_is_allowed() -> None:
    stdout = _run_hook(
        "uv run --no-sync python scripts/pytest_guard.py run -- tests/unit/test_hook_enforce_code_reads.py"
    )

    assert stdout == ""
