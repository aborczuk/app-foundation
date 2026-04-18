"""Smoke tests for the speckit solution command doc structure."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_read_markdown_module():
    """Load the repo markdown helper as a module for a deterministic smoke test."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "read_markdown.py"
    spec = importlib.util.spec_from_file_location("read_markdown", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_speckit_solution_doc_exposes_compact_and_expanded_headings() -> None:
    """Keep the solution command aligned to the compact/expanded markdown pattern."""
    read_markdown = _load_read_markdown_module()
    doc_path = Path(__file__).resolve().parents[2] / ".claude" / "commands" / "speckit.solution.md"

    assert (
        read_markdown.read_markdown_section(str(doc_path), "Compact Contract (Load First)")
        == 0
    )
    assert (
        read_markdown.read_markdown_section(
            str(doc_path), "Expanded Guidance (Load On Demand)"
        )
        == 0
    )
