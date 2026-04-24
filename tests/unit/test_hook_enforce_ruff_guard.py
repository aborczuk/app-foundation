"""Unit tests for the Ruff enforcement pre-tool hook."""

from __future__ import annotations

import json
import subprocess
import sys


def _run_hook(command: str) -> str:
    """Run the Ruff enforcement hook with a synthetic command payload."""
    payload = {"tool_input": {"command": command}}
    result = subprocess.run(
        [sys.executable, "scripts/hook_enforce_ruff_guard.py"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_direct_ruff_is_denied() -> None:
    """Direct CLI Ruff invocation should be denied."""
    stdout = _run_hook("ruff check scripts/read_code.py")

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "Direct ruff calls are denied" in decision["permissionDecisionReason"]
    assert "edit_validate" in decision["permissionDecisionReason"]


def test_uv_run_ruff_is_denied() -> None:
    """uv-run Ruff invocation should be denied."""
    stdout = _run_hook("uv run --no-sync ruff check scripts/read_code.py")

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"


def test_python_module_ruff_is_denied() -> None:
    """python -m ruff invocation should be denied."""
    stdout = _run_hook("uv run --no-sync python -m ruff check scripts/read_code.py")

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"


def test_ruff_guard_command_is_allowed() -> None:
    """Guarded Ruff wrapper invocation should pass through."""
    stdout = _run_hook("uv run --no-sync python scripts/ruff_guard.py scripts/read_code.py")

    assert stdout == ""
