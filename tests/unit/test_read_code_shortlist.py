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


def test_context_scope_classifier_marks_scoped_requests() -> None:
    """Exact-symbol and file-local requests should classify as scoped."""
    symbol_scope = read_code._classify_context_query_scope(
        read_code._ContextArgs(
            file_path=None,
            pattern="def read_code_context(",
            context=60,
            allow_fallback=False,
            show_shortlist=False,
            inline_body=False,
            candidate_index=0,
            content_type=None,
        )
    )
    file_scope = read_code._classify_context_query_scope(
        read_code._ContextArgs(
            file_path=Path("/tmp/example.py"),
            pattern="how does this work",
            context=60,
            allow_fallback=False,
            show_shortlist=False,
            inline_body=False,
            candidate_index=0,
            content_type=None,
        )
    )

    assert symbol_scope.is_scoped
    assert file_scope.is_scoped


def test_context_scope_classifier_marks_broad_prompts() -> None:
    """Broad natural-language prompts should remain broad."""
    broad_scope = read_code._classify_context_query_scope(
        read_code._ContextArgs(
            file_path=None,
            pattern="how does this work",
            context=60,
            allow_fallback=False,
            show_shortlist=False,
            inline_body=False,
            candidate_index=0,
            content_type=None,
        )
    )

    assert not broad_scope.is_scoped


def test_read_code_context_classifies_before_refresh_and_resolution(monkeypatch) -> None:
    """The scope classifier should run before preflight and anchor resolution."""
    calls: list[str] = []

    def fake_parse_context_args(argv: list[str]) -> read_code._ContextArgs | None:
        calls.append("parse")
        return read_code._ContextArgs(
            file_path=Path("/tmp/example.py"),
            pattern="def sample(",
            context=60,
            allow_fallback=False,
            show_shortlist=False,
            inline_body=False,
            candidate_index=0,
            content_type=None,
        )

    def fake_classify_context_query_scope(parsed: read_code._ContextArgs) -> read_code._ContextQueryScope:
        calls.append("classify")
        return read_code._ContextQueryScope(is_scoped=True, reason="file-path supplied")

    def fake_refresh_indexes_for_read(preflight_path: Path, *, verbose: bool = False) -> bool:
        calls.append("refresh")
        return True

    def fake_resolve_pattern_anchor(
        file_path: Path | None,
        pattern: str,
        normalized_pattern: str,
        *,
        candidate_index: int,
        allow_fallback: bool,
        show_shortlist_hint: bool,
        content_type: str | None,
        request_scope: read_code._ContextQueryScope | None = None,
    ) -> read_code._AnchorResolution:
        calls.append("resolve")
        vector_match = read_code._VectorMatch(
            unit_id="function:sample",
            symbol_name="sample",
            qualified_name="sample",
            line_num=10,
            line_end=12,
            raw_score=0.9,
            cosine_similarity=90,
            file_path=Path("/tmp/example.py"),
        )
        return read_code._AnchorResolution(
            vector_candidates=[vector_match],
            vector_match=vector_match,
            strict_status=0,
            line_num=10,
        )

    monkeypatch.setattr(read_code, "_parse_context_args", fake_parse_context_args)
    monkeypatch.setattr(read_code, "_classify_context_query_scope", fake_classify_context_query_scope)
    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", fake_refresh_indexes_for_read)
    monkeypatch.setattr(read_code, "_resolve_pattern_anchor", fake_resolve_pattern_anchor)
    monkeypatch.setattr(read_code, "_render_compact_match", lambda *args, **kwargs: None)
    monkeypatch.setattr(read_code, "_render_resolution_extras", lambda *args, **kwargs: None)
    monkeypatch.setattr(read_code, "_render_numbered_window", lambda *args, **kwargs: None)

    assert read_code.read_code_context(["sample"]) == 0
    assert calls == ["parse", "classify", "refresh", "resolve"]
