from __future__ import annotations

import json
from pathlib import Path


def test_codex_hooks_manifest_includes_apply_patch_edit_hooks() -> None:
    """The repo-local Codex hooks must cover apply_patch for both edit phases."""
    manifest = json.loads(Path(".codex/hooks.json").read_text())
    hooks = manifest["hooks"]

    pretool_matchers = {entry["matcher"] for entry in hooks["PreToolUse"]}
    posttool_matchers = {entry["matcher"] for entry in hooks["PostToolUse"]}

    assert "Edit|Write|MultiEdit|apply_patch" in pretool_matchers
    assert "Edit|Write|MultiEdit|apply_patch" in posttool_matchers
