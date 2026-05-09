from __future__ import annotations

import json
import subprocess
import sys
from typing import Any


def _run_hook(payload: dict[str, Any]) -> str:
    """Run the pretool dispatcher and return its stdout payload."""
    result = subprocess.run(
        [sys.executable, "scripts/hook_pretool_dispatch.py"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_denies_apply_patch_delete_file_marker() -> None:
    """The dispatcher should hard-block apply_patch delete-file payloads."""
    stdout = _run_hook(
        {
            "tool_name": "apply_patch",
            "tool_input": {
                "patch": "*** Begin Patch\n*** Delete File: /tmp/example.txt\n*** End Patch\n",
            },
        }
    )

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "`*** Delete File:`" in decision["permissionDecisionReason"]


def test_allows_non_delete_apply_patch_payload() -> None:
    """The dispatcher should not block apply_patch payloads without delete-file markers."""
    stdout = _run_hook(
        {
            "tool_name": "apply_patch",
            "tool_input": {
                "patch": "*** Begin Patch\n*** Update File: /tmp/example.txt\n@@\n-old\n+new\n*** End Patch\n",
            },
        }
    )

    assert stdout == ""
