"""Unit tests for read-code shortlist and bounded body helper behavior."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module(module_name: str, script_name: str):
    """Load a scripts module directly from the repo for unit testing."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


read_code = _load_module("read_code_shortlist", "read_code.py")


def test_candidate_body_helper_returns_bounded_follow_up_body() -> None:
    """A later shortlist candidate body should be retrievable without widening scope."""
    candidates = [
        read_code._VectorMatch(
            line_num=10,
            raw_score=0.95,
            metadata_score=18.0,
            confidence=100,
            exact_symbol_match=True,
            symbol_type="function",
            has_body=True,
            has_docstring=True,
            line_span=4,
            body="def top():\n    return 1",
            preview="def top():",
            signature="def top():",
        ),
        read_code._VectorMatch(
            line_num=30,
            raw_score=0.75,
            metadata_score=11.0,
            confidence=81,
            exact_symbol_match=False,
            symbol_type="function",
            has_body=True,
            has_docstring=False,
            line_span=3,
            body="def follow_up():\n    return 2",
            preview="def follow_up():",
            signature="def follow_up():",
        ),
    ]

    assert read_code.candidate_body_helper(candidates, 1) == "def follow_up():\n    return 2"
    assert read_code.candidate_body_helper(candidates, 5) is None


def test_candidate_confidence_scores_high_confident_symbol_above_body_threshold() -> None:
    """High-confidence symbol matches should clear the body-first cutoff."""
    confidence = read_code._candidate_confidence(
        1.0,
        18.5,
        exact_symbol_match=True,
        has_body=True,
        has_docstring=True,
        line_span=0,
    )

    assert confidence >= 90
