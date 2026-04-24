"""Unit tests for the Pyright enforcement pre-tool hook."""

from __future__ import annotations

import json
import subprocess
import sys


def _run_hook(command: str) -> str:
    """Run the Pyright enforcement hook with a synthetic command payload."""
    payload = {"tool_input": {"command": command}}
    result = subprocess.run(
        [sys.executable, "scripts/hook_enforce_pyright_guard.py"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_direct_pyright_is_denied() -> None:
    """Direct CLI Pyright invocation should be denied."""
    stdout = _run_hook("pyright scripts/read_code.py")

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "Direct pyright calls are denied" in decision["permissionDecisionReason"]
    assert "edit_validate" in decision["permissionDecisionReason"]


def test_uv_run_pyright_is_denied() -> None:
    """uv-run Pyright invocation should be denied."""
    stdout = _run_hook("uv run --no-sync pyright scripts/read_code.py")

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"


def test_python_module_pyright_is_denied() -> None:
    """python -m pyright invocation should be denied."""
    stdout = _run_hook("uv run --no-sync python -m pyright scripts/read_code.py")

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"


def test_non_pyright_command_is_allowed() -> None:
    """Non-pyright command should pass through."""
    stdout = _run_hook("uv run --no-sync python scripts/ruff_guard.py scripts/read_code.py")
    assert stdout == ""
