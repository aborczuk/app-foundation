"""Unit tests for graph-backed read-code context output."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

read_code = importlib.import_module("scripts.read_code")


def test_read_code_graph_context_renders_neighborhood_without_bodies_or_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Graph context should print a capped neighborhood and follow-up reads only."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def read_code_read():\n    return 1\n", encoding="utf-8")

    target = read_code._VectorMatch(
        unit_id="function:read_code_read",
        symbol_name="read_code_read",
        qualified_name="scripts.read_code.read_code_read",
        line_num=1,
        line_end=2,
        raw_score=1.0,
        metadata_score=1.0,
        confidence=100,
        exact_symbol_match=True,
        symbol_type="function",
        has_body=True,
        has_docstring=False,
        line_span=2,
        body="def read_code_read():\n    return 1\n",
        preview="def read_code_read():",
        signature="def read_code_read() -> int:",
    )
    resolution = read_code._ReadResolution(match=target, method="exact_unit_id")
    caller = read_code._GraphEntry(
        name="main",
        kind="function",
        location=f"{code_file}:10",
        read_command=f"read {code_file} main",
    )
    callee = read_code._GraphEntry(
        name="helper",
        kind="function",
        location=f"{code_file}:20",
        read_command=f"read {code_file} helper",
    )
    test_hit = read_code._GraphEntry(
        name="test_read_code_graph_context",
        kind="function",
        location="tests/unit/test_read_code_graph_context.py:1",
        read_command="read tests/unit/test_read_code_graph_context.py test_read_code_graph_context",
    )

    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda *_: True)
    monkeypatch.setattr(read_code, "codegraph_supports_file", lambda *_: True)
    monkeypatch.setattr(read_code, "codegraph_refresh_if_needed", lambda *_: True)
    monkeypatch.setattr(read_code, "_resolve_graph_target", lambda *_: resolution)
    monkeypatch.setattr(read_code, "_collect_callers", lambda *_: ([caller], None))
    monkeypatch.setattr(read_code, "_collect_callees", lambda *_: ([callee], None))
    monkeypatch.setattr(read_code, "_collect_test_hits", lambda *_: ([test_hit], None))

    result = read_code.read_code_graph_context([str(code_file), "read_code_read"])
    captured = capsys.readouterr()

    assert result == 0
    assert "# body" not in captured.out
    assert "# references" not in captured.out
    assert "# graph_context path=" in captured.out
    assert "# target" in captured.out
    assert "# callers returned=1 total=1" in captured.out
    assert "# callees returned=1 total=1" in captured.out
    assert "# tests returned=1 total=1" in captured.out
    assert f"read {code_file} function:read_code_read" in captured.out
    assert f"read {code_file} main" in captured.out
    assert f"read {code_file} helper" in captured.out
    assert "read tests/unit/test_read_code_graph_context.py test_read_code_graph_context" in captured.out


def test_read_code_graph_context_reports_missing_graph_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Graph context should fail explicitly instead of falling back to source lines."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def read_code_read():\n    return 1\n", encoding="utf-8")

    target = read_code._VectorMatch(
        unit_id="function:read_code_read",
        symbol_name="read_code_read",
        qualified_name="scripts.read_code.read_code_read",
        line_num=1,
        line_end=2,
        raw_score=1.0,
        metadata_score=1.0,
        confidence=100,
        exact_symbol_match=True,
        symbol_type="function",
        has_body=True,
        has_docstring=False,
        line_span=2,
        body="def read_code_read():\n    return 1\n",
        preview="def read_code_read():",
        signature="def read_code_read() -> int:",
    )
    resolution = read_code._ReadResolution(match=target, method="exact_unit_id")

    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda *_: True)
    monkeypatch.setattr(read_code, "codegraph_supports_file", lambda *_: False)
    monkeypatch.setattr(read_code, "_resolve_graph_target", lambda *_: resolution)

    result = read_code.read_code_graph_context([str(code_file), "read_code_read"])
    captured = capsys.readouterr()

    assert result == 1
    assert "ERROR: graph context is not supported" in captured.err
    assert "# callers" not in captured.out
    assert "# callees" not in captured.out
    assert "# tests" not in captured.out
