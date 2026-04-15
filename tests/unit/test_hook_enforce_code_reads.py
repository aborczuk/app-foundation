"""Tests for the large read enforcement hook."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_hook(command: str) -> str:
    payload = {"tool_input": {"command": command}}
    result = subprocess.run(
        [sys.executable, "scripts/hook_enforce_code_reads.py"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_large_markdown_sed_reads_are_denied(tmp_path: Path) -> None:
    large_doc = tmp_path / "docs" / "guide.md"
    large_doc.parent.mkdir(parents=True, exist_ok=True)
    large_doc.write_text("line\n" * 250, encoding="utf-8")

    stdout = _run_hook(f"sed -n '1,220p' {large_doc}")

    assert stdout
    data = json.loads(stdout)
    decision = data["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "read-code.sh" in decision["permissionDecisionReason"]


def test_small_markdown_sed_reads_are_allowed(tmp_path: Path) -> None:
    small_doc = tmp_path / "docs" / "guide.md"
    small_doc.parent.mkdir(parents=True, exist_ok=True)
    small_doc.write_text("line\n" * 10, encoding="utf-8")

    stdout = _run_hook(f"sed -n '1,10p' {small_doc}")

    assert stdout == ""


def test_settings_prioritize_code_doc_read_hook() -> None:
    settings = json.loads(Path(".claude/settings.json").read_text(encoding="utf-8"))
    bash_hooks = settings["hooks"]["PreToolUse"][0]["hooks"]

    assert bash_hooks[0]["command"] == "python3 scripts/hook_enforce_code_reads.py"
    assert "code/doc" in bash_hooks[0]["statusMessage"]
