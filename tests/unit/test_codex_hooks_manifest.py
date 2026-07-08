from __future__ import annotations

import json
from pathlib import Path


def test_codex_hooks_manifest_includes_multiedit_edit_hooks() -> None:
    """The repo-local Codex hooks must cover MultiEdit for both edit phases."""
    manifest = json.loads(Path(".codex/hooks.json").read_text())
    hooks = manifest["hooks"]

    pretool_matchers = {entry["matcher"] for entry in hooks["PreToolUse"]}
    posttool_matchers = {entry["matcher"] for entry in hooks["PostToolUse"]}

    assert "Edit|Write|MultiEdit" in pretool_matchers
    assert "Edit|Write|MultiEdit" in posttool_matchers
