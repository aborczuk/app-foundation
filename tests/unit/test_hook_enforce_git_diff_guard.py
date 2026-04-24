from __future__ import annotations

import json
import subprocess
import sys


def _run_hook(command: str) -> str:
    """Run the git diff enforcement hook with a synthetic command payload."""
    payload = {"tool_input": {"command": command}}
    result = subprocess.run(
        [sys.executable, "scripts/hook_enforce_git_diff_guard.py"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_direct_git_diff_is_denied() -> None:
    """Direct git diff invocation should be denied."""
    stdout = _run_hook("git diff -- scripts/read_code.py")

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "Direct git diff calls are denied" in decision["permissionDecisionReason"]
    assert "git_diff_guard.py" in decision["permissionDecisionReason"]


def test_git_c_diff_is_denied() -> None:
    """`git -C <repo> diff` should also be denied."""
    stdout = _run_hook("git -C /Users/andreborczuk/app-foundation diff -- scripts/read_code.py")

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"


def test_guarded_diff_command_is_allowed() -> None:
    """git_diff_guard routing should pass through."""
    stdout = _run_hook("uv run --no-sync python scripts/git_diff_guard.py --stat scripts/read_code.py")
    assert stdout == ""
