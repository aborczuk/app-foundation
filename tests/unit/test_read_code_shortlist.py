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
            unit_id="function:top",
            symbol_name="top",
            qualified_name="top",
            line_num=10,
            line_end=13,
            raw_score=0.95,
            cosine_similarity=100,
            symbol_type="function",
            has_body=True,
            has_docstring=True,
            body="def top():\n    return 1",
            preview="def top():",
            signature="def top():",
            file_path=Path(),
            docstring="",
        ),
        read_code._VectorMatch(
            unit_id="function:follow_up",
            symbol_name="follow_up",
            qualified_name="follow_up",
            line_num=30,
            line_end=32,
            raw_score=0.75,
            cosine_similarity=81,
            symbol_type="function",
            has_body=True,
            has_docstring=False,
            body="def follow_up():\n    return 2",
            preview="def follow_up():",
            signature="def follow_up():",
            file_path=Path(),
            docstring="",
        ),
    ]

    assert read_code.candidate_body_helper(candidates, 1) == "def follow_up():\n    return 2"
    assert read_code.candidate_body_helper(candidates, 5) is None


def test_vector_anchor_rank_prefers_higher_similarity() -> None:
    """Higher cosine similarity should sort ahead of weaker matches."""
    higher = read_code._VectorMatch(
        unit_id="function:higher",
        symbol_name="higher",
        qualified_name="higher",
        line_num=1,
        line_end=1,
        raw_score=0.99,
        cosine_similarity=99,
    )
    lower = read_code._VectorMatch(
        unit_id="function:lower",
        symbol_name="lower",
        qualified_name="lower",
        line_num=2,
        line_end=2,
        raw_score=0.45,
        cosine_similarity=45,
    )

    assert read_code._vector_anchor_rank(higher) > read_code._vector_anchor_rank(lower)
