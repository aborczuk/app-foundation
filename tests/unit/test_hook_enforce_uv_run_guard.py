"""Unit tests for the uv run enforcement pre-tool hook."""

from __future__ import annotations

import json
import subprocess
import sys


def _run_hook(command: str) -> str:
    """Run the uv run enforcement hook with a synthetic command payload."""
    payload = {"tool_input": {"command": command}}
    result = subprocess.run(
        [sys.executable, "scripts/hook_enforce_uv_run_guard.py"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_direct_uv_run_is_denied() -> None:
    """Direct uv run invocation should be denied."""
    stdout = _run_hook("uv run --no-sync python -m pytest tests/unit/test_x.py")

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "Direct uv run calls are denied" in decision["permissionDecisionReason"]
    assert "uv_cache_dir.sh" in decision["permissionDecisionReason"]


def test_absolute_uv_run_is_denied() -> None:
    """Absolute-path uv run invocation should also be denied."""
    stdout = _run_hook("/opt/homebrew/bin/uv run --no-sync python -m pytest tests/unit/test_x.py")

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"


def test_uv_cache_helper_command_is_allowed() -> None:
    """Commands that source the cache helper should pass through."""
    stdout = _run_hook(
        "source scripts/uv_cache_dir.sh && uv run --no-sync python scripts/pytest_guard.py run -- "
        "tests/unit/test_x.py"
    )

    assert stdout == ""


def test_inline_cache_override_is_allowed() -> None:
    """Inline UV_CACHE_DIR overrides should pass through."""
    stdout = _run_hook("UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync python -m pytest tests/unit/test_x.py")

    assert stdout == ""
