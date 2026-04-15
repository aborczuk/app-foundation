"""Docs contract tests for the Speckit checkpoint handoff flow."""

from __future__ import annotations

from pathlib import Path


def test_implement_doc_requires_github_sync_and_compact_status() -> None:
    text = Path(".claude/commands/speckit.implement.md").read_text(encoding="utf-8")

    assert "GitHub sync handoff" in text
    assert "/speckit.checkpoint Phase [N]" in text
    assert "compact status line" in text
    assert "do not emit a prose summary" in text.lower()


def test_checkpoint_doc_requires_compact_stop_at_story_boundary() -> None:
    text = Path(".claude/commands/speckit.checkpoint.md").read_text(encoding="utf-8")

    assert "compact PASS status" in text
    assert "do not auto-start the next story" in text.lower()
    assert "do not narrate a summary" in text.lower()
