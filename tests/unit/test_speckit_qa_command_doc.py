"""Smoke tests for the speckit QA command doc orchestration contract."""

from __future__ import annotations

from pathlib import Path


def test_speckit_qa_doc_describes_subagent_role_without_closeout_ownership() -> None:
    """Keep QA aligned to the implement-session reviewer role."""
    doc_path = Path(__file__).resolve().parents[2] / ".claude" / "commands" / "speckit.qa.md"
    doc_text = doc_path.read_text(encoding="utf-8")

    assert "persistent implement-session QA subagent" in doc_text
    assert "PASS/FIX_REQUIRED verdict for the orchestrator" in doc_text
    assert "scripts/speckit_offline_qa_handoff.py" in doc_text
    assert "scripts/speckit_closeout_task.py" in doc_text
    assert "Do not append ledger events, close tasks, or emit phase-completion events." in doc_text
