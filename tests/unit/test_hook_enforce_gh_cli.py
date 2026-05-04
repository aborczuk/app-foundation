"""Unit tests for the GitHub CLI enforcement pre-tool hook."""

from __future__ import annotations

import json
import subprocess
import sys


def _run_hook(command: str) -> str:
    """Run the gh enforcement hook with a synthetic command payload."""
    payload = {"tool_input": {"command": command}}
    result = subprocess.run(
        [sys.executable, "scripts/hook_enforce_gh_cli.py"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_direct_gh_run_view_is_denied() -> None:
    """Direct gh run view invocation should be denied."""
    stdout = _run_hook("gh run view 123 --log-failed")

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "github_guard.py" in decision["permissionDecisionReason"]


def test_github_guard_wrapper_is_allowed() -> None:
    """github_guard should be treated as a safe wrapper."""
    stdout = _run_hook("python scripts/github_guard.py run -- gh run view 123 --log-failed")
    assert stdout == ""


def test_non_gh_command_is_allowed() -> None:
    """Non-gh commands should pass through."""
    stdout = _run_hook("python scripts/ruff_guard.py scripts/read_code.py")
    assert stdout == ""
