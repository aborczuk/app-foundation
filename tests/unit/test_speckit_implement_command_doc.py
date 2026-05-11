"""Smoke tests for the speckit implement command doc orchestration contract."""

from __future__ import annotations

from pathlib import Path


def test_speckit_implement_doc_requires_persistent_builder_qa_subagents() -> None:
    """Keep implement aligned to persistent builder/QA subagent orchestration."""
    doc_path = Path(__file__).resolve().parents[2] / ".claude" / "commands" / "speckit.implement.md"
    doc_text = doc_path.read_text(encoding="utf-8")

    assert "persistent `spawn_agent` subagents" in doc_text
    assert "`/speckit.implement` itself is the orchestrator" in doc_text
    assert "Use the command docs themselves as the subagent prompts" in doc_text
    assert "Do not use `fork_context: true`" in doc_text
    assert "gpt-5.4-mini" in doc_text
    assert "The orchestrator agent is the mediator." in doc_text
    assert "builder prompt: `.claude/commands/speckit.implement.md`" in doc_text
    assert "QA prompt: `.claude/commands/speckit.qa.md`" in doc_text
    assert "Do not route task execution through `scripts/speckit_codex_handoff_runner.py`." in doc_text
    assert "Do not delegate implement orchestration to `scripts/speckit_implement_step.py`." in doc_text
    assert "scripts/speckit_offline_qa_handoff.py" in doc_text
    assert "scripts/speckit_closeout_task.py" in doc_text
    assert "Subagents do not append ledger events, close tasks, or emit phase-completion events." in doc_text
