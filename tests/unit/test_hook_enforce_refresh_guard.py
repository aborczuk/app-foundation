"""Unit tests for the refresh-hook enforcement pre-tool hook."""

from __future__ import annotations

import json
import subprocess
import sys


def _run_hook(command: str) -> str:
    """Run the refresh enforcement hook with a synthetic command payload."""
    payload = {"tool_input": {"command": command}}
    result = subprocess.run(
        [sys.executable, "scripts/hook_enforce_refresh_guard.py"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_direct_refresh_hook_script_is_denied() -> None:
    """Direct hook_refresh_indexes.py invocation should be denied."""
    stdout = _run_hook("uv run --no-sync python scripts/hook_refresh_indexes.py")

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "Direct hook_refresh_indexes.py calls are denied" in decision["permissionDecisionReason"]
    assert "edit_sync" in decision["permissionDecisionReason"]


def test_absolute_refresh_hook_script_is_denied() -> None:
    """Absolute-path refresh hook invocation should also be denied."""
    stdout = _run_hook(
        '/usr/bin/python3 "/Users/andreborczuk/app-foundation/scripts/hook_refresh_indexes.py"'
    )

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"


def test_non_refresh_command_is_allowed() -> None:
    """Non-refresh command should pass through."""
    stdout = _run_hook("uv run --no-sync python scripts/pytest_guard.py run -- tests/unit/test_x.py")
    assert stdout == ""
