"""Smoke tests for the speckit implement command doc orchestration contract."""

from __future__ import annotations

from pathlib import Path


def test_speckit_implement_doc_requires_persistent_builder_qa_subagents() -> None:
    """Keep implement aligned to persistent builder/QA subagent orchestration."""
    doc_path = Path(__file__).resolve().parents[2] / ".claude" / "commands" / "speckit.implement.md"
    doc_text = doc_path.read_text(encoding="utf-8")

    assert "persistent `spawn_agent` subagents" in doc_text
    assert "`/speckit.implement` itself is the orchestrator" in doc_text
    assert "Do not use `fork_context: true`" in doc_text
    assert "gpt-5.4-mini" in doc_text
    assert "The orchestrator agent is the mediator." in doc_text
    assert "Do not send the full implement command doc as the builder subagent prompt." in doc_text
    assert "The builder subagent should receive the selected task entry plus feature context as the default implementation packet." in doc_text
    assert "The QA subagent may use `.claude/commands/speckit.qa.md` as its standing review contract" in doc_text
    assert "scripts/speckit_offline_qa_handoff.py" in doc_text
    assert "scripts/speckit_closeout_task.py" in doc_text
    assert "QA payload minimum fields" in doc_text
    assert "QA result minimum fields" in doc_text
    assert "extract a compact decision summary once" in doc_text
    assert "invalid or empty builder/QA completion" in doc_text
