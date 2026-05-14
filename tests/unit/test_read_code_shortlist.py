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
    refresh_kwargs: dict[str, object] = {}
    resolve_kwargs: dict[str, object] = {}

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

    def fake_refresh_indexes_for_read(
        preflight_path: Path,
        *,
        verbose: bool = False,
        request_is_scoped: bool | None = None,
    ) -> bool:
        calls.append("refresh")
        refresh_kwargs["preflight_path"] = preflight_path
        refresh_kwargs["verbose"] = verbose
        refresh_kwargs["request_is_scoped"] = request_is_scoped
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
        resolve_kwargs["request_scope"] = request_scope
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
    assert refresh_kwargs == {
        "preflight_path": Path("/tmp/example.py"),
        "verbose": False,
        "request_is_scoped": True,
    }
    assert resolve_kwargs["request_scope"] == read_code._ContextQueryScope(
        is_scoped=True,
        reason="file-path supplied",
    )


def test_resolve_pattern_anchor_forwards_request_scope_to_semantic_query(monkeypatch) -> None:
    """The anchor resolver should route request scope into semantic candidate lookup."""
    captured: dict[str, object] = {}
    request_scope = read_code._ContextQueryScope(is_scoped=True, reason="file-path supplied")

    def fake_query_semantic_anchor_candidate(
        file_path: Path | None,
        pattern: str,
        normalized_pattern: str,
        *,
        candidate_index: int,
        show_shortlist_hint: bool,
        content_type: str | None,
        request_scope: read_code._ContextQueryScope | None = None,
    ) -> tuple[list[read_code._VectorMatch], read_code._VectorMatch | None, bool]:
        captured["request_scope"] = request_scope
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
        return [vector_match], vector_match, True

    monkeypatch.setattr(read_code, "_query_semantic_anchor_candidate", fake_query_semantic_anchor_candidate)
    monkeypatch.setattr(read_code, "_emit_vector_fallback_notice", lambda *args, **kwargs: None)

    resolution = read_code._resolve_pattern_anchor(
        Path("/tmp/example.py"),
        "sample",
        "sample",
        candidate_index=0,
        allow_fallback=False,
        show_shortlist_hint=False,
        content_type=None,
        request_scope=request_scope,
    )

    assert resolution is not None
    assert captured["request_scope"] == request_scope


def test_query_semantic_anchor_candidate_skips_markdown_for_scoped_code_requests(monkeypatch) -> None:
    """Scoped code requests should only query code candidates."""
    scopes: list[str] = []
    request_scope = read_code._ContextQueryScope(is_scoped=True, reason="file-path supplied")

    def fake_vector_find_candidates(file_path, pattern, normalized_pattern, scope):
        scopes.append(scope)
        return [
            read_code._VectorMatch(
                unit_id=f"{scope}:top",
                symbol_name="top",
                qualified_name="top",
                line_num=10,
                line_end=12,
                raw_score=0.9,
                cosine_similarity=90,
                file_path=Path("/tmp/example.py"),
            )
        ]

    monkeypatch.setattr(read_code, "_vector_find_candidates", fake_vector_find_candidates)

    candidates, selected, ok = read_code._query_semantic_anchor_candidate(
        Path("/tmp/example.py"),
        "top",
        "top",
        candidate_index=0,
        show_shortlist_hint=False,
        content_type="code",
        request_scope=request_scope,
    )

    assert ok is True
    assert scopes == ["code"]
    assert len(candidates) == 1
    assert selected is not None
    assert selected.symbol_name == "top"


def test_query_semantic_anchor_candidate_keeps_markdown_for_broad_requests(monkeypatch) -> None:
    """Broad requests should still query both code and markdown candidates."""
    scopes: list[str] = []

    def fake_vector_find_candidates(file_path, pattern, normalized_pattern, scope):
        scopes.append(scope)
        return [
            read_code._VectorMatch(
                unit_id=f"{scope}:top",
                symbol_name="top",
                qualified_name="top",
                line_num=10,
                line_end=12,
                raw_score=0.9,
                cosine_similarity=90,
                file_path=Path("/tmp/example.py") if scope == "code" else Path("/tmp/example.md"),
            )
        ]

    monkeypatch.setattr(read_code, "_vector_find_candidates", fake_vector_find_candidates)

    candidates, selected, ok = read_code._query_semantic_anchor_candidate(
        Path("/tmp/example.py"),
        "top",
        "top",
        candidate_index=0,
        show_shortlist_hint=False,
        content_type="code",
        request_scope=read_code._ContextQueryScope(is_scoped=False, reason="broad prompt"),
    )

    assert ok is True
    assert scopes == ["code", "markdown"]
    assert len(candidates) == 1
    assert selected is not None
    assert selected.symbol_name == "top"


def test_read_code_context_keeps_top_candidate_for_exact_symbol_scope(monkeypatch) -> None:
    """Exact-symbol reads should stay scoped and keep the same top shortlist candidate."""
    calls: dict[str, object] = {}
    candidates = [
        read_code._VectorMatch(
            unit_id="function:top",
            symbol_name="top",
            qualified_name="top",
            line_num=10,
            line_end=12,
            raw_score=0.95,
            cosine_similarity=97,
            file_path=Path("/tmp/example.py"),
        ),
        read_code._VectorMatch(
            unit_id="function:other",
            symbol_name="other",
            qualified_name="other",
            line_num=20,
            line_end=22,
            raw_score=0.45,
            cosine_similarity=40,
            file_path=Path("/tmp/example.py"),
        ),
    ]

    monkeypatch.setattr(
        read_code,
        "_refresh_indexes_for_read",
        lambda preflight_path, *, verbose=False, request_is_scoped=None: calls.setdefault(
            "request_is_scoped", request_is_scoped
        )
        or True,
    )
    monkeypatch.setattr(read_code, "_vector_find_candidates", lambda *args, **kwargs: candidates)
    monkeypatch.setattr(
        read_code,
        "_render_compact_match",
        lambda vector_match, **kwargs: calls.setdefault("selected", vector_match),
    )
    monkeypatch.setattr(read_code, "_render_resolution_extras", lambda *args, **kwargs: None)
    monkeypatch.setattr(read_code, "_render_numbered_window", lambda *args, **kwargs: None)

    assert read_code.read_code_context(["def top("]) == 0
    assert calls["request_is_scoped"] is True
    assert calls["selected"].symbol_name == "top"


def test_read_code_context_keeps_top_candidate_for_file_local_scope(monkeypatch, tmp_path: Path) -> None:
    """File-local reads should stay scoped and keep the same top shortlist candidate."""
    calls: dict[str, object] = {}
    code_file = tmp_path / "example.py"
    code_file.write_text("def top():\n    return 1\n", encoding="utf-8")
    candidates = [
        read_code._VectorMatch(
            unit_id="function:top",
            symbol_name="top",
            qualified_name="top",
            line_num=10,
            line_end=12,
            raw_score=0.95,
            cosine_similarity=97,
            file_path=code_file,
        ),
        read_code._VectorMatch(
            unit_id="function:other",
            symbol_name="other",
            qualified_name="other",
            line_num=20,
            line_end=22,
            raw_score=0.45,
            cosine_similarity=40,
            file_path=code_file,
        ),
    ]

    monkeypatch.setattr(
        read_code,
        "_refresh_indexes_for_read",
        lambda preflight_path, *, verbose=False, request_is_scoped=None: calls.setdefault(
            "request_is_scoped", request_is_scoped
        )
        or True,
    )
    monkeypatch.setattr(read_code, "_vector_find_candidates", lambda *args, **kwargs: candidates)
    monkeypatch.setattr(
        read_code,
        "_render_compact_match",
        lambda vector_match, **kwargs: calls.setdefault("selected", vector_match),
    )
    monkeypatch.setattr(read_code, "_render_resolution_extras", lambda *args, **kwargs: None)
    monkeypatch.setattr(read_code, "_render_numbered_window", lambda *args, **kwargs: None)

    assert read_code.read_code_context([str(code_file), "how does this work"]) == 0
    assert calls["request_is_scoped"] is True
    assert calls["selected"].symbol_name == "top"
