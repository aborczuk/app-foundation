from __future__ import annotations

import io
import json
import sys
from typing import Any

from scripts import hook_pretool_dispatch


def _run_hook(payload: dict[str, Any], monkeypatch, capsys) -> str:
    """Run the pretool dispatcher in-process and return its stdout payload."""
    monkeypatch.setattr(hook_pretool_dispatch, "_branch_guard", lambda: "feature branch required")
    monkeypatch.setattr(hook_pretool_dispatch, "_worktree_guard", lambda command: None)
    monkeypatch.setattr(hook_pretool_dispatch, "_grep_guard", lambda command: None)
    monkeypatch.setattr(hook_pretool_dispatch, "_load_guard_main", lambda script_name: None)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert hook_pretool_dispatch.main() == 0
    return capsys.readouterr().out.strip()


def test_allows_new_spec_markdown_payload_on_non_feature_branch(monkeypatch, capsys) -> None:
    """The dispatcher should allow new spec Markdown files before they exist on disk."""
    stdout = _run_hook(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "specs/999-example/spec.md",
                "content": "# Example\n",
            },
        },
        monkeypatch,
        capsys,
    )

    assert stdout == ""


def test_allows_governance_markdown_payload_on_non_feature_branch(monkeypatch, capsys) -> None:
    """The dispatcher should allow governance Markdown edits outside feature branches."""
    stdout = _run_hook(
        {
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": "docs/governance/example.md",
                "content": "# Governance\n",
            },
        },
        monkeypatch,
        capsys,
    )

    assert stdout == ""


def test_denies_non_exempt_markdown_payload_on_non_feature_branch(monkeypatch, capsys) -> None:
    """The dispatcher should keep branch guards for Markdown outside the exempt folders."""
    stdout = _run_hook(
        {
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": "docs/notes/example.md",
                "content": "# Notes\n",
            },
        },
        monkeypatch,
        capsys,
    )

    assert stdout
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "feature branch" in decision["permissionDecisionReason"]
