from __future__ import annotations

# ruff: noqa: I001

import json
import subprocess
import sys
from pathlib import Path
from typing import cast


REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / "scripts" / "hook_enforce_code_reads.py"


def _run_hook(command: str) -> str:
    payload = {"tool_input": {"command": command}}
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _hook_decision(stdout: str) -> dict[str, object]:
    assert stdout
    return cast(dict[str, object], json.loads(stdout)["hookSpecificOutput"])


def test_legacy_read_code_symbols_invocation_is_denied() -> None:
    stdout = _run_hook("source scripts/read-code.sh; read_code_symbols scripts/read_code.py")
    decision = _hook_decision(stdout)

    assert decision["permissionDecision"] == "deny"
    assert "read_code_debug.py" in str(decision["permissionDecisionReason"])


def test_legacy_symbols_mode_is_denied() -> None:
    stdout = _run_hook("uv run --no-sync python scripts/read_code.py symbols scripts/read_code.py")
    decision = _hook_decision(stdout)

    assert decision["permissionDecision"] == "deny"


def test_debug_entrypoint_is_allowed() -> None:
    stdout = _run_hook("uv run --no-sync python scripts/read_code_debug.py scripts/read_code.py")

    assert stdout == ""
