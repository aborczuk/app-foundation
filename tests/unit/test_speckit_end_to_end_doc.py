"""Smoke tests for the speckit end-to-end governance doc."""

from __future__ import annotations

from pathlib import Path


def test_end_to_end_doc_marks_implement_as_command_agent_owned_generative() -> None:
    """Keep governance docs aligned to the implement orchestration boundary."""
    doc_path = Path(__file__).resolve().parents[2] / "docs" / "governance" / "speckit-end-to-end.md"
    doc_text = doc_path.read_text(encoding="utf-8")

    assert "`/speckit.implement` is a generative command-agent-owned orchestration step." in doc_text
    assert "The `/speckit.implement` command agent itself orchestrates the persistent builder and QA subagents." in doc_text
    assert "`scripts/speckit_implement_step.py` and `scripts/speckit_codex_handoff_runner.py` are not the orchestration authority for `implement`." in doc_text
    assert "agent-owned Composio follow-through happens after canonical repo closeout" in doc_text
