"""Unit tests for read-code shortlist and bounded body helper behavior."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


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


def _configure_search_cache_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    session_id: str = "session-1",
    signature: str = "",
) -> tuple[Path, Path]:
    """Pin scratchpad and history storage to temp files for one test session."""
    scratchpad_path = tmp_path / "search-scratchpad.json"
    metadata_log_path = tmp_path / "search-history.jsonl"
    monkeypatch.setattr(read_code, "_read_code_session_id", lambda: session_id)
    monkeypatch.setattr(read_code, "codegraph_current_edit_signature", lambda *_args, **_kwargs: signature)
    monkeypatch.setattr(read_code, "_read_code_search_scratchpad_path", lambda _session_id: scratchpad_path)
    monkeypatch.setattr(read_code, "_read_code_search_metadata_log_path", lambda: metadata_log_path)
    return scratchpad_path, metadata_log_path


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


def test_vector_anchor_rank_downranks_test_files_for_regular_context() -> None:
    """Regular discovery should prefer implementation files over test files."""
    implementation = read_code._VectorMatch(
        unit_id="function:impl",
        symbol_name="impl",
        qualified_name="impl",
        line_num=1,
        line_end=1,
        raw_score=0.90,
        cosine_similarity=90,
        file_path=Path("/repo/src/module.py"),
    )
    test_candidate = read_code._VectorMatch(
        unit_id="function:test",
        symbol_name="test",
        qualified_name="test",
        line_num=2,
        line_end=2,
        raw_score=0.90,
        cosine_similarity=90,
        file_path=Path("/repo/tests/test_module.py"),
    )

    assert read_code._vector_anchor_rank(implementation) > read_code._vector_anchor_rank(test_candidate)


def test_query_semantic_anchor_candidate_keeps_tests_first_for_explicit_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit test-targeted requests should keep test candidates competitive."""
    test_candidate = read_code._VectorMatch(
        unit_id="function:test",
        symbol_name="test",
        qualified_name="test",
        line_num=2,
        line_end=2,
        raw_score=0.90,
        cosine_similarity=90,
        file_path=Path("/repo/tests/test_module.py"),
    )
    implementation = read_code._VectorMatch(
        unit_id="function:impl",
        symbol_name="impl",
        qualified_name="impl",
        line_num=1,
        line_end=1,
        raw_score=0.90,
        cosine_similarity=90,
        file_path=Path("/repo/src/module.py"),
    )
    seen_allow_test_files: list[bool] = []

    def _fake_vector_find_candidates(
        file_path: Path | None,
        raw_pattern: str,
        normalized_pattern: str,
        scope: str,
        *,
        allow_test_files: bool = False,
    ) -> list[read_code._VectorMatch]:
        seen_allow_test_files.append(allow_test_files)
        return [test_candidate, implementation]

    monkeypatch.setattr(read_code, "_semantic_anchor_candidate_scopes", lambda _request_scope, _content_type: ("code",))
    monkeypatch.setattr(read_code, "_vector_find_candidates", _fake_vector_find_candidates)

    vector_candidates, vector_match, ok = read_code._query_semantic_anchor_candidate(
        Path("/repo/tests/test_module.py"),
        "test query",
        "test query",
        candidate_index=0,
        show_shortlist_hint=False,
        content_type=None,
    )

    assert ok is True
    assert vector_match == test_candidate
    assert vector_candidates[0] == test_candidate
    assert seen_allow_test_files == [True]


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

    def fake_resolve_pattern_anchor_with_scratchpad(
        parsed: read_code._ContextArgs,
        *,
        request_scope: read_code._ContextQueryScope,
        normalized_pattern: str,
    ) -> tuple[read_code._AnchorResolution, bool, str]:
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
        return (
            read_code._AnchorResolution(
                vector_candidates=[vector_match],
                vector_match=vector_match,
                strict_status=0,
                line_num=10,
            ),
            False,
            "",
        )

    monkeypatch.setattr(read_code, "_parse_context_args", fake_parse_context_args)
    monkeypatch.setattr(read_code, "_classify_context_query_scope", fake_classify_context_query_scope)
    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", fake_refresh_indexes_for_read)
    monkeypatch.setattr(
        read_code,
        "_resolve_pattern_anchor_with_scratchpad",
        fake_resolve_pattern_anchor_with_scratchpad,
    )
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
    ) -> tuple[list[read_code._VectorMatch], read_code._VectorMatch | None, bool, read_code._RerankDebugInfo | None]:
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
        return [vector_match], vector_match, True, None

    monkeypatch.setattr(read_code, "_query_semantic_anchor_candidate_with_debug", fake_query_semantic_anchor_candidate)
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


def test_resolve_pattern_anchor_skips_codegraph_discovery_for_trusted_broad_reads(monkeypatch) -> None:
    """Trusted broad reads should stay on the mixed retrieval path."""
    request_scope = read_code._ContextQueryScope(is_scoped=False, reason="broad prompt")
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
    calls: list[str] = []

    monkeypatch.setattr(
        read_code,
        "_query_semantic_anchor_candidate_with_debug",
        lambda *args, **kwargs: ([vector_match], None, True, None),
    )
    monkeypatch.setattr(read_code, "evaluate_read_vector_trust", lambda *args, **kwargs: True)
    monkeypatch.setattr(read_code, "codegraph_supports_file", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        read_code,
        "codegraph_discover_or_fail",
        lambda *args, **kwargs: calls.append("discover") or (_ for _ in ()).throw(
            AssertionError("codegraph discovery should be skipped")
        ),
    )
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
    assert resolution.vector_candidates == [vector_match]
    assert resolution.vector_match is None
    assert calls == []


def test_resolve_pattern_anchor_keeps_satisfactory_broad_results_without_recovery(monkeypatch) -> None:
    """Satisfactory broad reads should not escalate when fallback is allowed."""
    request_scope = read_code._ContextQueryScope(is_scoped=False, reason="broad prompt")
    vector_match = read_code._VectorMatch(
        unit_id="function:sample",
        symbol_name="sample",
        qualified_name="sample",
        line_num=10,
        line_end=12,
        raw_score=0.95,
        cosine_similarity=95,
        file_path=Path("/tmp/example.py"),
    )
    calls: list[str] = []

    monkeypatch.setattr(
        read_code,
        "_query_semantic_anchor_candidate_with_debug",
        lambda *args, **kwargs: ([vector_match], vector_match, True, None),
    )
    monkeypatch.setattr(read_code, "evaluate_read_vector_trust", lambda *args, **kwargs: True)
    monkeypatch.setattr(read_code, "codegraph_supports_file", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        read_code,
        "codegraph_discover_or_fail",
        lambda *args, **kwargs: calls.append("discover") or True,
    )
    monkeypatch.setattr(read_code, "_emit_vector_fallback_notice", lambda *args, **kwargs: calls.append("notice"))

    resolution = read_code._resolve_pattern_anchor(
        Path("/tmp/example.py"),
        "sample",
        "sample",
        candidate_index=0,
        allow_fallback=True,
        show_shortlist_hint=False,
        content_type=None,
        request_scope=request_scope,
    )

    assert resolution is not None
    assert resolution.vector_candidates == [vector_match]
    assert resolution.vector_match == vector_match
    assert resolution.line_num == 10
    assert calls == ["notice"]


@pytest.mark.parametrize(
    ("initial_candidates", "initial_match"),
    [
        ([], None),
        (
            [
                read_code._VectorMatch(
                    unit_id="function:weak",
                    symbol_name="weak",
                    qualified_name="weak",
                    line_num=10,
                    line_end=12,
                    raw_score=0.7,
                    cosine_similarity=70,
                    file_path=Path("/tmp/example.py"),
                )
            ],
            read_code._VectorMatch(
                unit_id="function:weak",
                symbol_name="weak",
                qualified_name="weak",
                line_num=10,
                line_end=12,
                raw_score=0.7,
                cosine_similarity=70,
                file_path=Path("/tmp/example.py"),
            ),
        ),
        (
            [
                read_code._VectorMatch(
                    unit_id="function:top",
                    symbol_name="top",
                    qualified_name="top",
                    line_num=10,
                    line_end=12,
                    raw_score=0.9,
                    cosine_similarity=90,
                    file_path=Path("/tmp/example.py"),
                ),
                read_code._VectorMatch(
                    unit_id="function:runner_up",
                    symbol_name="runner_up",
                    qualified_name="runner_up",
                    line_num=12,
                    line_end=14,
                    raw_score=0.88,
                    cosine_similarity=88,
                    file_path=Path("/tmp/example.py"),
                ),
            ],
            read_code._VectorMatch(
                unit_id="function:top",
                symbol_name="top",
                qualified_name="top",
                line_num=10,
                line_end=12,
                raw_score=0.9,
                cosine_similarity=90,
                file_path=Path("/tmp/example.py"),
            ),
        ),
    ],
)
def test_resolve_pattern_anchor_recovers_from_bad_broad_outcomes_when_fallback_allowed(
    monkeypatch,
    initial_candidates,
    initial_match,
) -> None:
    """Broad reads should recover only from explicit bad outcomes when fallback is allowed."""
    request_scope = read_code._ContextQueryScope(is_scoped=False, reason="broad prompt")
    refresh_match = read_code._VectorMatch(
        unit_id="function:refreshed",
        symbol_name="refreshed",
        qualified_name="refreshed",
        line_num=20,
        line_end=22,
        raw_score=0.98,
        cosine_similarity=98,
        file_path=Path("/tmp/example.py"),
    )
    calls: list[str] = []
    responses = [
        (initial_candidates, initial_match, True, None),
        ([refresh_match], refresh_match, True, None),
    ]

    def fake_query_semantic_anchor_candidate(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(read_code, "_query_semantic_anchor_candidate_with_debug", fake_query_semantic_anchor_candidate)
    monkeypatch.setattr(read_code, "evaluate_read_vector_trust", lambda *args, **kwargs: True)
    monkeypatch.setattr(read_code, "codegraph_supports_file", lambda *args, **kwargs: True)
    monkeypatch.setattr(read_code, "_emit_vector_fallback_notice", lambda *args, **kwargs: calls.append("notice"))
    monkeypatch.setattr(
        read_code,
        "codegraph_discover_or_fail",
        lambda *args, **kwargs: calls.append("discover") or True,
    )

    resolution = read_code._resolve_pattern_anchor(
        Path("/tmp/example.py"),
        "sample",
        "sample",
        candidate_index=0,
        allow_fallback=True,
        show_shortlist_hint=False,
        content_type=None,
        request_scope=request_scope,
    )

    assert resolution is not None
    assert resolution.vector_candidates == [refresh_match]
    assert resolution.vector_match == refresh_match
    assert resolution.line_num == 20
    assert calls == ["notice", "discover"]


def test_emit_vector_fallback_notice_surfaces_trust_escalation_note(monkeypatch, capsys) -> None:
    """Escalation notes should read as explicit trust warnings."""
    monkeypatch.setattr(
        read_code,
        "_consume_vector_runtime_note",
        lambda: "vector trust invalidated: stale drift overlaps requested scope",
    )

    read_code._emit_vector_fallback_notice(
        file_path=Path("/tmp/example.py"),
        pattern="sample",
        vector_match=None,
        resolved_line=None,
    )

    captured = capsys.readouterr()
    assert "Vector trust escalated" in captured.err
    assert "stale drift overlaps requested scope" in captured.err


def test_resolve_pattern_anchor_recovers_from_stale_broad_reads_when_fallback_allowed(monkeypatch) -> None:
    """Stale broad reads should recover through codegraph when fallback is allowed."""
    request_scope = read_code._ContextQueryScope(is_scoped=False, reason="broad prompt")
    initial_match = read_code._VectorMatch(
        unit_id="function:sample",
        symbol_name="sample",
        qualified_name="sample",
        line_num=10,
        line_end=12,
        raw_score=0.95,
        cosine_similarity=95,
        file_path=Path("/tmp/example.py"),
    )
    refresh_match = read_code._VectorMatch(
        unit_id="function:refreshed",
        symbol_name="refreshed",
        qualified_name="refreshed",
        line_num=22,
        line_end=24,
        raw_score=0.99,
        cosine_similarity=99,
        file_path=Path("/tmp/example.py"),
    )
    calls: list[str] = []
    responses = [
        ([initial_match], initial_match, True, None),
        ([refresh_match], refresh_match, True, None),
    ]

    monkeypatch.setattr(read_code, "_query_semantic_anchor_candidate_with_debug", lambda *args, **kwargs: responses.pop(0))
    monkeypatch.setattr(read_code, "evaluate_read_vector_trust", lambda *args, **kwargs: True)
    monkeypatch.setattr(read_code, "_broad_read_trusts_vector_cache", lambda *args, **kwargs: False)
    monkeypatch.setattr(read_code, "codegraph_supports_file", lambda *args, **kwargs: True)
    monkeypatch.setattr(read_code, "_emit_vector_fallback_notice", lambda *args, **kwargs: calls.append("notice"))
    monkeypatch.setattr(
        read_code,
        "codegraph_discover_or_fail",
        lambda *args, **kwargs: calls.append("discover") or True,
    )

    resolution = read_code._resolve_pattern_anchor(
        Path("/tmp/example.py"),
        "sample",
        "sample",
        candidate_index=0,
        allow_fallback=True,
        show_shortlist_hint=False,
        content_type=None,
        request_scope=request_scope,
    )

    assert resolution is not None
    assert resolution.vector_candidates == [refresh_match]
    assert resolution.vector_match == refresh_match
    assert resolution.line_num == 22
    assert calls == ["notice", "discover"]


def test_query_semantic_anchor_candidate_skips_markdown_for_scoped_code_requests(monkeypatch) -> None:
    """Scoped code requests should only query code candidates."""
    scopes: list[str] = []
    request_scope = read_code._ContextQueryScope(is_scoped=True, reason="file-path supplied")

    def fake_vector_find_candidates(file_path, pattern, normalized_pattern, scope, **kwargs):
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

    def fake_vector_find_candidates(file_path, pattern, normalized_pattern, scope, **kwargs):
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


def test_resolve_pattern_anchor_uses_daemon_rerank_scores_when_available(monkeypatch) -> None:
    """Context ranking should reorder the shortlist when the daemon-backed reranker returns scores."""
    request_scope = read_code._ContextQueryScope(is_scoped=True, reason="file-path supplied")
    initial = [
        read_code._VectorMatch(
            unit_id="function:first",
            symbol_name="first",
            qualified_name="first",
            line_num=10,
            line_end=12,
            raw_score=0.9,
            cosine_similarity=90,
            body="def first():\n    return 'first'\n",
            file_path=Path("/tmp/example.py"),
        ),
        read_code._VectorMatch(
            unit_id="function:second",
            symbol_name="second",
            qualified_name="second",
            line_num=20,
            line_end=22,
            raw_score=0.8,
            cosine_similarity=80,
            body="def second():\n    return 'second'\n",
            file_path=Path("/tmp/example.py"),
        ),
    ]

    monkeypatch.setattr(read_code, "_vector_find_candidates", lambda *args, **kwargs: initial)
    monkeypatch.setattr(
        read_code,
        "_load_read_code_reranker",
        lambda: type(
            "Backend",
            (),
            {
                "model_name": "BAAI/bge-reranker-v2-m3",
                "score_pairs": lambda self, query, passages: ([0.1, 0.95], "daemon"),
            },
        )(),
    )

    resolution = read_code._resolve_pattern_anchor(
        Path("/tmp/example.py"),
        "top",
        "top",
        candidate_index=0,
        allow_fallback=False,
        show_shortlist_hint=False,
        content_type="code",
        request_scope=request_scope,
    )

    assert resolution is not None
    assert [candidate.symbol_name for candidate in resolution.vector_candidates] == ["second", "first"]
    assert resolution.vector_match is not None
    assert resolution.vector_match.symbol_name == "second"
    assert resolution.rerank_source == "daemon"
    assert resolution.rerank_debug is not None
    assert resolution.rerank_debug.changed is True


def test_rerank_semantic_candidates_scores_only_visible_shortlist_window(monkeypatch) -> None:
    """The daemon should only score the user-visible shortlist window, not the full retrieval set."""
    captured_passages: list[str] = []
    candidates = [
        read_code._VectorMatch(
            unit_id=f"function:item_{index}",
            symbol_name=f"item_{index}",
            qualified_name=f"item_{index}",
            line_num=index,
            line_end=index,
            raw_score=1.0 - (index * 0.01),
            cosine_similarity=100 - index,
            body=f"def item_{index}():\n    return {index}\n",
            file_path=Path("/tmp/example.py"),
        )
        for index in range(read_code.READ_CODE_SEMANTIC_RETRIEVAL_LIMIT)
    ]

    class _Backend:
        model_name = "BAAI/bge-reranker-v2-m3"

        def score_pairs(self, query: str, passages: list[str]) -> tuple[list[float], str]:
            del query
            captured_passages.extend(passages)
            return ([0.0] * (len(passages) - 1)) + [1.0], "daemon"

    monkeypatch.setattr(read_code, "_load_read_code_reranker", lambda: _Backend())

    result = read_code._rerank_semantic_candidates(
        "target",
        candidates,
        allow_test_files=False,
    )

    assert len(captured_passages) == read_code.READ_CODE_RERANK_WINDOW_LIMIT
    assert result.source == "daemon"
    assert result.candidates[0].symbol_name == f"item_{read_code.READ_CODE_RERANK_WINDOW_LIMIT - 1}"
    assert result.candidates[read_code.READ_CODE_RERANK_WINDOW_LIMIT].symbol_name == f"item_{read_code.READ_CODE_RERANK_WINDOW_LIMIT}"


def test_read_code_context_rerank_debug_is_opt_in(
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Rerank diagnostics should stay hidden unless the opt-in flag is present."""
    vector_match = read_code._VectorMatch(
        unit_id="function:sample",
        symbol_name="sample",
        qualified_name="sample",
        line_num=10,
        line_end=12,
        raw_score=0.9,
        cosine_similarity=91,
        file_path=Path("/tmp/example.py"),
    )
    resolution = read_code._AnchorResolution(
        vector_candidates=[vector_match],
        vector_match=vector_match,
        strict_status=0,
        line_num=10,
        rerank_debug=read_code._RerankDebugInfo(
            status="applied",
            model_name="BAAI/bge-reranker-v2-m3",
            candidate_count=2,
            changed=True,
            before_symbols=("sample", "other"),
            after_symbols=("other", "sample"),
        ),
        rerank_source="daemon",
    )

    monkeypatch.setattr(
        read_code,
        "_refresh_indexes_for_read",
        lambda preflight_path, *, verbose=False, request_is_scoped=None: True,
    )
    monkeypatch.setattr(
        read_code,
        "_resolve_pattern_anchor_with_scratchpad",
        lambda parsed, *, request_scope, normalized_pattern: (resolution, False, "clean"),
    )
    monkeypatch.setattr(read_code, "_render_compact_match", lambda *args, **kwargs: None)
    monkeypatch.setattr(read_code, "_render_resolution_extras", lambda *args, **kwargs: None)
    monkeypatch.setattr(read_code, "_append_search_metadata_event", lambda **kwargs: None)

    assert read_code.read_code_context(["sample"]) == 0
    hidden = capsys.readouterr()
    assert "rerank_status:" not in hidden.out

    assert read_code.read_code_context(["sample", "--show-rerank"]) == 0
    shown = capsys.readouterr()
    assert "rerank_status: applied" in shown.out
    assert "result_source: daemon" in shown.out


def test_vector_anchor_rank_penalizes_test_files_for_regular_context(monkeypatch) -> None:
    """Regular discovery should prefer implementation files over test files."""
    implementation = Path("/tmp/example.py")
    test_file = Path("/tmp/tests/test_example.py")

    impl_rank = read_code._vector_anchor_rank(
        read_code._VectorMatch(
            unit_id="function:impl",
            symbol_name="impl",
            qualified_name="impl",
            line_num=10,
            line_end=12,
            raw_score=0.9,
            cosine_similarity=90,
            file_path=implementation,
        ),
    )
    test_rank = read_code._vector_anchor_rank(
        read_code._VectorMatch(
            unit_id="function:test",
            symbol_name="test",
            qualified_name="test",
            line_num=10,
            line_end=12,
            raw_score=0.9,
            cosine_similarity=90,
            file_path=test_file,
        ),
    )

    assert impl_rank > test_rank


def test_vector_anchor_rank_preserves_test_files_for_explicit_test_targeting(monkeypatch) -> None:
    """Explicit test targeting should not down-rank test files."""
    test_file = Path("/tmp/tests/test_example.py")
    impl_rank = read_code._vector_anchor_rank(
        read_code._VectorMatch(
            unit_id="function:impl",
            symbol_name="impl",
            qualified_name="impl",
            line_num=10,
            line_end=12,
            raw_score=0.9,
            cosine_similarity=90,
            file_path=Path("/tmp/example.py"),
        ),
        allow_test_files=True,
    )
    test_rank = read_code._vector_anchor_rank(
        read_code._VectorMatch(
            unit_id="function:test",
            symbol_name="test",
            qualified_name="test",
            line_num=10,
            line_end=12,
            raw_score=0.9,
            cosine_similarity=90,
            file_path=test_file,
        ),
        allow_test_files=True,
    )

    assert impl_rank == test_rank


def test_vector_query_candidates_prefers_implementation_files_by_default(monkeypatch) -> None:
    """Ordinary candidate selection should prefer implementation files over tests."""
    test_match = read_code._VectorMatch(
        unit_id="function:test",
        symbol_name="test",
        qualified_name="test",
        line_num=10,
        line_end=12,
        raw_score=0.9,
        cosine_similarity=90,
        file_path=Path("/tmp/tests/test_example.py"),
    )
    impl_match = read_code._VectorMatch(
        unit_id="function:impl",
        symbol_name="impl",
        qualified_name="impl",
        line_num=10,
        line_end=12,
        raw_score=0.9,
        cosine_similarity=90,
        file_path=Path("/tmp/example.py"),
    )

    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)
    monkeypatch.setattr(
        read_code,
        "_run_command_capture",
        lambda *args, **kwargs: read_code.subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=read_code.json.dumps(
                [
                    {"kind": "test", "file_path": "/tmp/tests/test_example.py", "line_start": 10, "score": 0.9},
                    {"kind": "impl", "file_path": "/tmp/example.py", "line_start": 10, "score": 0.9},
                ]
            ),
            stderr="",
        ),
    )
    monkeypatch.setattr(
        read_code,
        "_vector_match_for_item",
        lambda item, query, normalized_query: test_match if item["kind"] == "test" else impl_match,
    )

    candidates = read_code._vector_query_candidates(
        None,
        "impl",
        "impl",
        "code",
        allow_test_files=False,
    )

    assert candidates
    assert candidates[0].file_path == Path("/tmp/example.py")


def test_vector_query_candidates_preserves_test_files_for_explicit_test_targeting(monkeypatch) -> None:
    """Explicit test-targeted discovery should keep test candidates eligible."""
    test_match = read_code._VectorMatch(
        unit_id="function:test",
        symbol_name="test",
        qualified_name="test",
        line_num=10,
        line_end=12,
        raw_score=0.9,
        cosine_similarity=90,
        file_path=Path("/tmp/tests/test_example.py"),
    )
    impl_match = read_code._VectorMatch(
        unit_id="function:impl",
        symbol_name="impl",
        qualified_name="impl",
        line_num=10,
        line_end=12,
        raw_score=0.9,
        cosine_similarity=90,
        file_path=Path("/tmp/example.py"),
    )

    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)
    monkeypatch.setattr(
        read_code,
        "_run_command_capture",
        lambda *args, **kwargs: read_code.subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=read_code.json.dumps(
                [
                    {"kind": "test", "file_path": "/tmp/tests/test_example.py", "line_start": 10, "score": 0.9},
                    {"kind": "impl", "file_path": "/tmp/example.py", "line_start": 10, "score": 0.9},
                ]
            ),
            stderr="",
        ),
    )
    monkeypatch.setattr(
        read_code,
        "_vector_match_for_item",
        lambda item, query, normalized_query: test_match if item["kind"] == "test" else impl_match,
    )

    candidates = read_code._vector_query_candidates(
        None,
        "test",
        "test",
        "code",
        allow_test_files=True,
    )

    assert candidates
    assert candidates[0].file_path == Path("/tmp/tests/test_example.py")


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


def test_read_code_context_keeps_inline_body_window_for_code_results(monkeypatch, tmp_path: Path) -> None:
    """Code inline-body rendering should keep the same window bounds."""
    code_file = tmp_path / "example.py"
    code_file.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
    calls: dict[str, object] = {}
    _configure_search_cache_paths(monkeypatch, tmp_path, signature="clean")

    monkeypatch.setattr(
        read_code,
        "_refresh_indexes_for_read",
        lambda preflight_path, *, verbose=False, request_is_scoped=None: True,
    )
    monkeypatch.setattr(
        read_code,
        "_resolve_pattern_anchor",
        lambda *args, **kwargs: read_code._AnchorResolution(
            vector_candidates=[
                read_code._VectorMatch(
                    unit_id="function:sample",
                    symbol_name="sample",
                    qualified_name="sample",
                    line_num=3,
                    line_end=3,
                    raw_score=1.0,
                    cosine_similarity=100,
                    file_path=code_file,
                )
            ],
            vector_match=read_code._VectorMatch(
                unit_id="function:sample",
                symbol_name="sample",
                qualified_name="sample",
                line_num=3,
                line_end=3,
                raw_score=1.0,
                cosine_similarity=100,
                file_path=code_file,
            ),
            strict_status=0,
            line_num=3,
        ),
    )
    monkeypatch.setattr(read_code, "_render_compact_match", lambda *args, **kwargs: None)
    monkeypatch.setattr(read_code, "_render_resolution_extras", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        read_code,
        "_render_numbered_window",
        lambda file_path, start, end: calls.update({"file_path": file_path, "start": start, "end": end}),
    )

    assert read_code.read_code_context([str(code_file), "sample"]) == 0
    assert read_code.read_code_context([str(code_file), "sample", "--inline-body"]) == 0
    assert calls == {"file_path": code_file, "start": 1, "end": 57}


def test_read_code_context_keeps_inline_body_window_for_markdown_results(monkeypatch, tmp_path: Path) -> None:
    """Markdown inline-body rendering should keep the same section window."""
    markdown_file = tmp_path / "example.md"
    markdown_file.write_text("# Title\n\n## Section\nbody\n", encoding="utf-8")
    calls: dict[str, object] = {}
    _configure_search_cache_paths(monkeypatch, tmp_path, signature="clean")

    monkeypatch.setattr(
        read_code,
        "_refresh_indexes_for_read",
        lambda preflight_path, *, verbose=False, request_is_scoped=None: True,
    )
    monkeypatch.setattr(
        read_code,
        "_resolve_pattern_anchor",
        lambda *args, **kwargs: read_code._AnchorResolution(
            vector_candidates=[
                read_code._VectorMatch(
                    unit_id="markdown",
                    symbol_name="Section",
                    qualified_name=f"{markdown_file}:Section",
                    line_num=3,
                    line_end=3,
                    raw_score=1.0,
                    cosine_similarity=100,
                    file_path=markdown_file,
                    signature="## Section",
                    docstring="",
                )
            ],
            vector_match=read_code._VectorMatch(
                unit_id="markdown",
                symbol_name="Section",
                qualified_name=f"{markdown_file}:Section",
                line_num=3,
                line_end=3,
                raw_score=1.0,
                cosine_similarity=100,
                file_path=markdown_file,
                signature="## Section",
                docstring="",
            ),
            strict_status=0,
            line_num=3,
        ),
    )
    monkeypatch.setattr(read_code, "_render_compact_match", lambda *args, **kwargs: None)
    monkeypatch.setattr(read_code, "_render_resolution_extras", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        read_code,
        "_render_numbered_window",
        lambda file_path, start, end: calls.update({"file_path": file_path, "start": start, "end": end}),
    )

    assert read_code.read_code_context([str(markdown_file), "Section"]) == 0
    assert read_code.read_code_context([str(markdown_file), "Section", "--inline-body"]) == 0
    assert calls == {"file_path": markdown_file, "start": 3, "end": 4}


def test_read_code_context_keeps_markdown_selection_for_broad_prompt(monkeypatch, tmp_path: Path) -> None:
    """Broad prompts should still be able to surface markdown matches."""
    markdown_file = tmp_path / "example.md"
    markdown_file.write_text("# Title\n\n## Section\nbody\n", encoding="utf-8")
    calls: dict[str, object] = {}
    _configure_search_cache_paths(monkeypatch, tmp_path, signature="clean")
    markdown_match = read_code._VectorMatch(
        unit_id="markdown",
        symbol_name="Section",
        qualified_name=f"{markdown_file}:Section",
        line_num=3,
        line_end=3,
        raw_score=1.0,
        cosine_similarity=100,
        file_path=markdown_file,
        signature="## Section",
        docstring="",
    )

    monkeypatch.setattr(
        read_code,
        "_refresh_indexes_for_read",
        lambda preflight_path, *, verbose=False, request_is_scoped=None: calls.setdefault(
            "request_is_scoped", request_is_scoped
        )
        or True,
    )
    monkeypatch.setattr(
        read_code,
        "_resolve_pattern_anchor",
        lambda *args, **kwargs: read_code._AnchorResolution(
            vector_candidates=[markdown_match],
            vector_match=markdown_match,
            strict_status=0,
            line_num=3,
        ),
    )
    monkeypatch.setattr(read_code, "_render_compact_match", lambda *args, **kwargs: None)
    monkeypatch.setattr(read_code, "_render_resolution_extras", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        read_code,
        "_render_numbered_window",
        lambda file_path, start, end: calls.update({"file_path": file_path, "start": start, "end": end}),
    )

    assert read_code.read_code_context(["how does markdown selection work"]) == 0
    assert read_code.read_code_context(["how does markdown selection work", "--inline-body"]) == 0
    assert calls["request_is_scoped"] is False
    assert calls["file_path"] == markdown_file
    assert calls["start"] == 3
    assert calls["end"] == 4


def test_read_code_context_rejects_inline_body_on_first_read(
    monkeypatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Inline body should be blocked until the exact query has been selected in-session once."""
    code_file = tmp_path / "example.py"
    code_file.write_text("print('hi')\n", encoding="utf-8")
    _configure_search_cache_paths(monkeypatch, tmp_path, signature="clean")
    refresh_calls = {"count": 0}

    def _unexpected_refresh(*_args, **_kwargs) -> bool:
        refresh_calls["count"] += 1
        return True

    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", _unexpected_refresh)
    monkeypatch.setattr(
        read_code,
        "_resolve_pattern_anchor",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not resolve on first inline-body read")),
    )

    assert read_code.read_code_context([str(code_file), "sample", "--inline-body"]) == 1
    captured = capsys.readouterr()
    assert "--inline-body requires a prior context read" in captured.err
    assert refresh_calls["count"] == 0


def test_read_code_context_reuses_scratchpad_for_next_candidate(monkeypatch, tmp_path: Path) -> None:
    """Context stepping should reuse the first shortlist instead of rerunning search."""
    _, metadata_log_path = _configure_search_cache_paths(monkeypatch, tmp_path, signature="clean")
    selected: list[str] = []
    resolver_calls = {"count": 0}
    request_scope = read_code._ContextQueryScope(is_scoped=True, reason="test scope")
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
            unit_id="function:follow_up",
            symbol_name="follow_up",
            qualified_name="follow_up",
            line_num=20,
            line_end=22,
            raw_score=0.85,
            cosine_similarity=89,
            file_path=Path("/tmp/example.py"),
        ),
    ]

    def fake_resolve_pattern_anchor(*_args, **_kwargs):
        resolver_calls["count"] += 1
        return read_code._AnchorResolution(
            vector_candidates=candidates,
            vector_match=candidates[0],
            strict_status=0,
            line_num=candidates[0].line_num,
        )

    monkeypatch.setattr(read_code, "_classify_context_query_scope", lambda _parsed: request_scope)
    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(read_code, "_resolve_pattern_anchor", fake_resolve_pattern_anchor)
    monkeypatch.setattr(
        read_code,
        "_render_compact_match",
        lambda vector_match, **_kwargs: selected.append(vector_match.symbol_name),
    )
    monkeypatch.setattr(read_code, "_render_resolution_extras", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(read_code, "_render_read_context_inline_body", lambda *_args, **_kwargs: None)

    assert read_code.read_code_context(["sample"]) == 0
    assert read_code.read_code_context(["sample", "--next-candidate"]) == 0

    assert resolver_calls["count"] == 1
    assert selected == ["top", "follow_up"]
    metadata_events = read_code._load_search_metadata_events()
    assert len(metadata_events) == 2
    assert metadata_events[0]["cache_hit"] is False
    assert metadata_events[1]["cache_hit"] is True
    assert metadata_log_path.is_file()


def test_read_code_find_reuses_scratchpad_for_next_candidate(
    monkeypatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Find stepping should reuse parsed matches from the session scratchpad."""
    _configure_search_cache_paths(monkeypatch, tmp_path, signature="clean")
    run_calls = {"count": 0}
    matches = [
        read_code._FindMatch(
            name="sample",
            symbol_type="function",
            location="scripts/example.py:10",
            path=Path("scripts/example.py"),
            line_num=10,
        ),
        read_code._FindMatch(
            name="sample_follow_up",
            symbol_type="function",
            location="scripts/example.py:20",
            path=Path("scripts/example.py"),
            line_num=20,
        ),
    ]

    def fake_run(*_args, **_kwargs):
        run_calls["count"] += 1
        return read_code.subprocess.CompletedProcess(args=["uv"], returncode=0, stdout="ignored", stderr="")

    monkeypatch.setattr(read_code, "init_codegraph_env", lambda: None)
    monkeypatch.setattr(read_code.subprocess, "run", fake_run)
    monkeypatch.setattr(read_code, "_parse_cgc_find_output", lambda _raw_output: matches)

    assert read_code.read_code_find(["name", "sample"]) == 0
    first = capsys.readouterr()
    assert "match_index: 0/1" in first.out
    assert "location: scripts/example.py:10" in first.out

    assert read_code.read_code_find(["name", "sample", "--next-candidate"]) == 0
    second = capsys.readouterr()
    assert "match_index: 1/1" in second.out
    assert "location: scripts/example.py:20" in second.out
    assert run_calls["count"] == 1


def test_read_code_analyze_reuses_scratchpad_for_next_candidate(
    monkeypatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Analyze stepping should reuse parsed matches from the session scratchpad."""
    _configure_search_cache_paths(monkeypatch, tmp_path, signature="clean")
    run_calls = {"count": 0}
    matches = [
        read_code._AnalyzeMatch(
            columns={"caller": "top"},
            location="scripts/example.py:10",
            path=Path("scripts/example.py"),
            line_num=10,
        ),
        read_code._AnalyzeMatch(
            columns={"caller": "follow_up"},
            location="scripts/example.py:20",
            path=Path("scripts/example.py"),
            line_num=20,
        ),
    ]

    def fake_run(*_args, **_kwargs):
        run_calls["count"] += 1
        return read_code.subprocess.CompletedProcess(args=["uv"], returncode=0, stdout="ignored", stderr="")

    monkeypatch.setattr(read_code, "init_codegraph_env", lambda: None)
    monkeypatch.setattr(read_code.subprocess, "run", fake_run)
    monkeypatch.setattr(read_code, "_parse_cgc_analyze_output", lambda _raw_output: matches)

    assert read_code.read_code_analyze(["callers", "sample"]) == 0
    first = capsys.readouterr()
    assert "match_index: 0/1" in first.out
    assert "caller: top" in first.out

    assert read_code.read_code_analyze(["callers", "sample", "--next-candidate"]) == 0
    second = capsys.readouterr()
    assert "match_index: 1/1" in second.out
    assert "caller: follow_up" in second.out
    assert run_calls["count"] == 1


def test_search_scratchpad_invalidates_on_signature_mismatch_and_ttl(monkeypatch, tmp_path: Path) -> None:
    """Scratchpad reuse should stop when the repo signature or entry freshness changes."""
    scratchpad_path, _ = _configure_search_cache_paths(monkeypatch, tmp_path, signature="clean")
    session_id = "session-ttl"
    query_payload = {"command": "find", "query": "sample"}
    cache_key = read_code._search_cache_key("find", query_payload)

    read_code._store_search_scratchpad_entry(
        session_id,
        cache_key,
        command="find",
        query_payload=query_payload,
        signature="clean",
        matches_payload=[
            {
                "name": "sample",
                "symbol_type": "function",
                "location": "scripts/example.py:10",
                "path": "scripts/example.py",
                "line_num": 10,
            }
        ],
    )

    assert read_code._load_cached_search_entry(session_id, cache_key, signature="other") is None
    assert read_code._load_cached_search_entry(session_id, cache_key, signature="clean") is not None

    payload = json.loads(scratchpad_path.read_text(encoding="utf-8"))
    payload["entries"][cache_key]["cached_at"] = 1.0
    scratchpad_path.write_text(json.dumps(payload), encoding="utf-8")

    assert read_code._load_cached_search_entry(session_id, cache_key, signature="clean") is None


def test_read_code_history_renders_recent_and_stats(
    monkeypatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """History views should render compact recent events and aggregate cache stats."""
    _, metadata_log_path = _configure_search_cache_paths(monkeypatch, tmp_path, signature="clean")

    read_code._append_search_metadata_event(
        command="context",
        subcommand=None,
        query="sample",
        query_shape="scoped",
        file_path=Path("scripts/example.py"),
        hit_count=2,
        selected_candidate_index=0,
        cache_hit=False,
        result_source="backend",
        elapsed_ms=15.5,
        signature="clean",
    )
    read_code._append_search_metadata_event(
        command="find",
        subcommand="name",
        query="sample",
        query_shape="name",
        file_path=None,
        hit_count=2,
        selected_candidate_index=1,
        cache_hit=True,
        result_source="scratchpad",
        elapsed_ms=3.0,
        signature="clean",
    )

    assert read_code.read_code_history(["recent", "5"]) == 0
    recent = capsys.readouterr()
    assert "history_command: recent" in recent.out
    assert "context" in recent.out
    assert "find:name" in recent.out

    assert read_code.read_code_history(["stats"]) == 0
    stats = capsys.readouterr()
    assert "history_command: stats" in stats.out
    assert "cache_hit_rate:" in stats.out
    assert "context\tscoped" in stats.out
    assert "find\tname" in stats.out
    assert metadata_log_path.is_file()
