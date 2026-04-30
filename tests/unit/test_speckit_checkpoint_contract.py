"""Docs contract tests for the Speckit checkpoint handoff flow."""

from __future__ import annotations

from pathlib import Path


def test_implement_doc_requires_github_sync_and_compact_status() -> None:
    text = Path(".claude/commands/speckit.implement.md").read_text(encoding="utf-8")

    assert "GitHub sync handoff" in text
    assert "/speckit.checkpoint Phase [N]" in text
    assert "compact status line" in text
    assert "do not emit a prose summary" in text.lower()
    assert "Tasking has already registered the task queue" in text
    assert "Consume the next registered task" in text
    assert "Register missing tasks" not in text


def test_tasking_doc_registers_tasks_before_implement() -> None:
    text = Path(".claude/commands/speckit.tasking.md").read_text(encoding="utf-8")

    assert "the tasking step owns `task_registered` events" in text.lower()
    assert "scripts/task_ledger.py register" in text
    assert ".speckit/task-ledger.jsonl" in text


def test_checkpoint_doc_requires_compact_stop_at_story_boundary() -> None:
    text = Path(".claude/commands/speckit.checkpoint.md").read_text(encoding="utf-8")

    assert "compact PASS status" in text
    assert "do not auto-start the next story" in text.lower()
    assert "do not narrate a summary" in text.lower()
