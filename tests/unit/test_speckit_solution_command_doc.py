"""Smoke tests for the speckit solution command doc structure."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_read_markdown_module():
    """Load the repo markdown helper as a module for a deterministic smoke test."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "read_markdown.py"
    spec = importlib.util.spec_from_file_location("read_markdown", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_speckit_solution_doc_exposes_compact_and_expanded_headings() -> None:
    """Keep the solution command aligned to the compact/expanded markdown pattern."""
    read_markdown = _load_read_markdown_module()
    doc_path = Path(__file__).resolve().parents[2] / ".claude" / "commands" / "speckit.solution.md"

    compact_section = read_markdown.read_markdown_section(
        str(doc_path), "Compact Contract (Load First)"
    )
    expanded_section = read_markdown.read_markdown_section(
        str(doc_path), "Expanded Guidance (Load On Demand)"
    )

    assert compact_section
    assert expanded_section
    assert any("## Compact Contract (Load First)" in line for line in compact_section)
    assert any("## Expanded Guidance (Load On Demand)" in line for line in expanded_section)


def test_speckit_solution_doc_consumes_plan_design_slices() -> None:
    """The solution doc should consume plan slices instead of sketch artifacts."""
    doc_path = Path(__file__).resolve().parents[2] / ".claude" / "commands" / "speckit.solution.md"
    doc_text = doc_path.read_text(encoding="utf-8")

    assert "Do not generate `sketch.md`" in doc_text
    assert "plan.md` design slices" in doc_text
    assert "routing.json" in doc_text
    assert "speckit_remake_huds.py prepare" in doc_text
    assert "Do not call `scripts/speckit_codex_handoff_runner.py`" in doc_text
    assert "Do not call `/speckit.tasking`" in doc_text
    assert "Auto-invoke `/speckit.sketch`" not in doc_text
    assert "Auto-invoke `/speckit.tasking`" not in doc_text
    assert "Auto-invoke `/speckit.solutionreview`" not in doc_text
    assert "Auto-invoke `/speckit.analyze`" not in doc_text
