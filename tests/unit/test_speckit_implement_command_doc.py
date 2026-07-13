"""Smoke tests for the speckit implement command doc orchestration contract."""

from __future__ import annotations

from pathlib import Path


def test_speckit_implement_doc_requires_root_plus_persistent_qa_subagent() -> None:
    """Keep implement aligned to root-owned implementation plus persistent QA."""
    doc_path = Path(__file__).resolve().parents[2] / ".claude" / "commands" / "speckit.implement.md"
    doc_text = doc_path.read_text(encoding="utf-8")

    assert "persistent QA subagent review" in doc_text
    assert "root-owned task implementation" in doc_text
    assert "Do not use `fork_context: true`" in doc_text
    assert "gpt-5.4-mini" in doc_text
    assert "The root agent is both implementer and orchestrator." in doc_text
    assert "Spawn exactly one persistent subagent" in doc_text
    assert "implement the next task from `tasks.md`" in doc_text
    assert "The QA subagent may use `.claude/commands/speckit.qa.md` as its standing review contract" in doc_text
    assert "scripts/speckit_offline_qa_handoff.py" in doc_text
    assert "scripts/speckit_closeout_task.py" in doc_text
    assert "clickup_sync_status=pending_agent_update" in doc_text
    assert "connected Composio ClickUp tools" in doc_text
    assert "keep repo closeout authoritative" in doc_text
    assert "QA payload minimum fields" in doc_text
    assert "QA result minimum fields" in doc_text
    assert "extract a compact decision summary once" in doc_text
    assert "invalid or empty QA completion" in doc_text
