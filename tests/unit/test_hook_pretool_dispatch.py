from __future__ import annotations

import io
import json
import subprocess
import sys
from typing import Any

from scripts import hook_pretool_dispatch


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


def _run_hook_in_process(
    payload: dict[str, Any],
    monkeypatch,
    capsys,
    branch_reason: str | None = "feature branch required",
) -> str:
    """Run the dispatcher with monkeypatched guard seams for deterministic tests."""
    monkeypatch.setattr(hook_pretool_dispatch, "_branch_guard", lambda: branch_reason)
    monkeypatch.setattr(hook_pretool_dispatch, "_load_guard_main", lambda script_name: None)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert hook_pretool_dispatch.main() == 0
    return capsys.readouterr().out.strip()


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


def test_denies_apply_patch_payload_on_non_feature_branch(monkeypatch, capsys) -> None:
    """The dispatcher should treat apply_patch as a direct edit event."""
    stdout = _run_hook_in_process(
        {
            "tool_name": "apply_patch",
            "tool_input": {
                "patch": "*** Begin Patch\n*** Update File: /tmp/example.txt\n@@\n-old\n+new\n*** End Patch\n",
            },
        },
        monkeypatch,
        capsys,
    )

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "feature branch" in decision["permissionDecisionReason"]


def test_denies_multiedit_payload_on_non_feature_branch(monkeypatch, capsys) -> None:
    """The dispatcher should treat MultiEdit as a direct edit event."""
    stdout = _run_hook_in_process(
        {
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": "src/example.py",
                "content": "x = 1\n",
            },
        },
        monkeypatch,
        capsys,
    )

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "feature branch" in decision["permissionDecisionReason"]


def test_denies_git_grep_with_repo_specific_guidance() -> None:
    """The dispatcher should give explicit repo guidance for git grep usage."""
    stdout = _run_hook(
        {
            "tool_name": "exec_command",
            "tool_input": {
                "command": "git grep -n needle origin/main -- src/file.py",
            },
        }
    )

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    reason = decision["permissionDecisionReason"]
    assert "git grep" in reason
    assert "scripts/read_code.py context" in reason
    assert "scripts/github_guard.py run -- gh" in reason


def test_denies_rg_with_repo_reader_guidance() -> None:
    """The dispatcher should point plain rg usage to the repo readers."""
    stdout = _run_hook(
        {
            "tool_name": "exec_command",
            "tool_input": {
                "command": "rg needle src",
            },
        }
    )

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    reason = decision["permissionDecisionReason"]
    assert "grep/rg" in reason
    assert "scripts/read_code.py context" in reason


def test_denies_cmd_shaped_payload_with_repo_reader_guidance() -> None:
    """The dispatcher should normalize exec payloads that use `cmd` instead of `command`."""
    stdout = _run_hook(
        {
            "tool_name": "exec_command",
            "tool_input": {
                "cmd": "rg needle src",
            },
        }
    )

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    reason = decision["permissionDecisionReason"]
    assert "grep/rg" in reason
    assert "scripts/read_code.py context" in reason


def test_apply_patch_cmd_payload_is_not_treated_as_shell_command(monkeypatch, capsys) -> None:
    """Edit payload fields named cmd should not be routed through shell-read guards."""
    read_token = "ta" + "il"
    doc_path = "docs/governance/" + "read-code-stdio-worker.md"
    stdout = _run_hook_in_process(
        {
            "tool_name": "apply_patch",
            "tool_input": {
                "cmd": (
                    "*** Begin Patch\n"
                    "*** Update File: docs/governance/example.md\n"
                    "@@\n"
                    f"+{read_token} -n 80 {doc_path}\n"
                    "*** End Patch\n"
                )
            },
        },
        monkeypatch,
        capsys,
        branch_reason=None,
    )

    assert stdout == ""
