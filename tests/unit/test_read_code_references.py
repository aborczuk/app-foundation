"""Unit tests for graph-backed read-code references output."""

from __future__ import annotations

import builtins
import importlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

read_code: Any = importlib.import_module("scripts.read_code")


def _load_read_code_without_direct_codegraphcontext(
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    """Import a fresh read_code module while blocking direct codegraphcontext imports."""
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "read_code.py"
    original_import = builtins.__import__

    def blocked_import(name: str, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[override]
        if name == "codegraphcontext" or name.startswith("codegraphcontext."):
            raise ImportError("blocked direct codegraphcontext import")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    spec = importlib.util.spec_from_file_location("scripts.read_code_lazy_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def _make_match(
    *,
    unit_id: str,
    symbol_name: str,
    symbol_type: str,
    line_num: int = 1,
    line_end: int = 1,
    body: str = "",
) -> Any:
    """Build a compact vector match for references tests."""
    return read_code._VectorMatch(
        unit_id=unit_id,
        symbol_name=symbol_name,
        qualified_name=f"sample.{symbol_name}",
        line_num=line_num,
        line_end=line_end,
        raw_score=1.0,
        metadata_score=1.0,
        confidence=100,
        exact_symbol_match=True,
        symbol_type=symbol_type,
        has_body=bool(body),
        has_docstring=False,
        line_span=max(1, line_end - line_num + 1),
        body=body,
        preview=symbol_name,
        signature=symbol_name,
    )


def _configure_reference_mode(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    resolution: Any,
    *,
    exact_record: dict[str, object] | None = None,
    callers: list[dict[str, object]] | None = None,
    callees: list[dict[str, object]] | None = None,
    variable_terms: list[str] | None = None,
    variable_records: list[dict[str, object]] | None = None,
    usage_terms: list[str] | None = None,
    content_records: list[dict[str, object]] | None = None,
    callers_total: int | None = None,
    callees_total: int | None = None,
) -> None:
    """Patch references mode queries with deterministic fixtures."""
    monkeypatch.setattr(module, "_refresh_indexes_for_read", lambda *_: True)
    monkeypatch.setattr(module, "codegraph_supports_file", lambda *_: True)
    monkeypatch.setattr(module, "codegraph_refresh_if_needed", lambda *_: True)
    monkeypatch.setattr(module, "_resolve_graph_target", lambda *_: resolution)
    monkeypatch.setattr(module, "_reference_exact_node_records", lambda *_: ([exact_record] if exact_record else [], None))

    def _mock_callers(*args: Any, **kwargs: Any) -> tuple[list[dict[str, object]], str | None]:
        """Mock that respects pagination parameters."""
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", 80)
        records = callers or []
        return (records[offset : offset + limit], None)

    def _mock_callees(*args: Any, **kwargs: Any) -> tuple[list[dict[str, object]], str | None]:
        """Mock that respects pagination parameters."""
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", 80)
        records = callees or []
        return (records[offset : offset + limit], None)

    monkeypatch.setattr(module, "_reference_direct_callers", _mock_callers)
    monkeypatch.setattr(module, "_reference_direct_callees", _mock_callees)
    monkeypatch.setattr(
        module,
        "_reference_direct_callers_total",
        lambda *_: (len(callers or []) if callers_total is None else callers_total, None),
    )
    monkeypatch.setattr(
        module,
        "_reference_direct_callees_total",
        lambda *_: (len(callees or []) if callees_total is None else callees_total, None),
    )
    monkeypatch.setattr(module, "_reference_variable_terms", lambda *args, **kwargs: list(variable_terms or []))
    monkeypatch.setattr(module, "_reference_variable_records", lambda *args, **kwargs: (list(variable_records or []), None))
    monkeypatch.setattr(module, "_reference_usage_terms", lambda *args, **kwargs: list(usage_terms or []))
    monkeypatch.setattr(module, "_reference_content_records", lambda *args, **kwargs: (list(content_records or []), None))


def test_reference_command_falls_back_from_non_vector_uid(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Graph-style UIDs should not be emitted as read targets."""
    record = {
        "kind": ["Function"],
        "uid": "read_code_read/Users/example/scripts/read_code.py2337",
        "name": "main",
        "path": "scripts/read_code.py",
        "line_number": 10,
        "end_line": 10,
    }

    hits = read_code._reference_records_to_hits(
        "callers",
        [record],
        display_path="scripts/read_code.py",
        fallback_kind="function",
    )
    capsys.readouterr()

    assert len(hits) == 1
    assert hits[0].command == "read scripts/read_code.py main"
    assert "read_code_read/Users/example/scripts/read_code.py2337" not in hits[0].command


def test_reference_command_uses_hit_path_when_available(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reference commands should use the hit record path, not the target path."""
    record = {
        "kind": ["Function"],
        "uid": "function:caller",
        "name": "caller",
        "path": "tests/test_read_code.py",
        "line_number": 12,
        "end_line": 14,
    }

    hits = read_code._reference_records_to_hits(
        "callers",
        [record],
        display_path="scripts/read_code.py",
        fallback_kind="function",
    )
    capsys.readouterr()

    assert len(hits) == 1
    assert hits[0].location == "tests/test_read_code.py:12-14"
    assert hits[0].command == "read tests/test_read_code.py function:caller"


def test_read_code_modes_import_and_run_without_direct_codegraphcontext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Read, outline, and source-window entrypoints should not need direct codegraph imports."""
    fresh = _load_read_code_without_direct_codegraphcontext(monkeypatch)
    code_file = tmp_path / "sample.py"
    code_file.write_text("def read_code_read():\n    return 1\n", encoding="utf-8")

    vector_match = fresh._VectorMatch(
        unit_id="function:read_code_read",
        symbol_name="read_code_read",
        qualified_name="sample.read_code_read",
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
        preview="read_code_read",
        signature="def read_code_read():",
    )
    resolution = fresh._ReadResolution(match=vector_match, method="exact_symbol_name")
    context_resolution = SimpleNamespace(
        vector_candidates=[],
        vector_match=vector_match,
        strict_status=None,
        line_num=1,
    )
    outline_symbol = {
        "symbol_name": "read_code_read",
        "symbol_type": "function",
        "line_start": 1,
        "line_end": 2,
        "signature": "def read_code_read():",
        "qualified_name": "sample.read_code_read",
        "body": "def read_code_read():\n    return 1\n",
        "docstring": "",
    }

    monkeypatch.setattr(fresh, "_refresh_indexes_for_read", lambda *_: True)
    monkeypatch.setattr(fresh, "_consume_vector_runtime_note", lambda: "")
    monkeypatch.setattr(fresh, "_vector_list_code_symbols", lambda *_: [outline_symbol])
    monkeypatch.setattr(fresh, "_resolve_exact_indexed_candidate", lambda *_: resolution)
    monkeypatch.setattr(fresh, "_resolve_pattern_anchor", lambda *_args, **_kwargs: context_resolution)
    monkeypatch.setattr(fresh, "_render_resolution_extras", lambda *args, **kwargs: None)

    outline_result = fresh.read_code_outline([str(code_file)])
    outline_out = capsys.readouterr()
    assert outline_result == 0
    assert "# outline path=" in outline_out.out

    read_result = fresh.read_code_read([str(code_file), "function:read_code_read"])
    read_out = capsys.readouterr()
    assert read_result == 0
    assert "# read file=" in read_out.out

    context_result = fresh.read_code_context([str(code_file), "read_code_read"])
    context_out = capsys.readouterr()
    assert context_result == 0
    assert "def read_code_read():" in context_out.out

    window_result = fresh.read_code_window([str(code_file), "1", "2", "read_code_read"])
    window_out = capsys.readouterr()
    assert window_result == 0
    assert "def read_code_read():" in window_out.out
    assert "return 1" in window_out.out


def test_read_code_references_target_row_uses_unit_id_and_labeled_graph_uid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The references target row should prefer the vector id and label any graph uid explicitly."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def read_code_read():\n    return 1\n", encoding="utf-8")

    target = _make_match(
        unit_id="function:read_code_read",
        symbol_name="read_code_read",
        symbol_type="function",
        line_num=1,
        line_end=2,
        body="def read_code_read():\n    return 1\n",
    )
    resolution = read_code._ReadResolution(match=target, method="exact_symbol_name")
    exact_record = {
        "kind": ["Function"],
        "uid": "graph-123",
        "name": "read_code_read",
        "path": str(code_file),
        "line_number": 1,
        "end_line": 2,
    }

    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda *_: True)
    monkeypatch.setattr(read_code, "codegraph_supports_file", lambda *_: True)
    monkeypatch.setattr(read_code, "codegraph_refresh_if_needed", lambda *_: True)
    monkeypatch.setattr(read_code, "_resolve_graph_target", lambda *_: resolution)
    monkeypatch.setattr(read_code, "_reference_exact_node_records", lambda *_: ([exact_record], None))
    monkeypatch.setattr(read_code, "_reference_direct_callers", lambda *args, **kwargs: ([], None))
    monkeypatch.setattr(read_code, "_reference_direct_callees", lambda *args, **kwargs: ([], None))
    monkeypatch.setattr(read_code, "_reference_variable_terms", lambda *args, **kwargs: [])
    monkeypatch.setattr(read_code, "_reference_variable_records", lambda *args, **kwargs: ([], None))
    monkeypatch.setattr(read_code, "_reference_usage_terms", lambda *args, **kwargs: ["read_code_read"])
    monkeypatch.setattr(read_code, "_reference_content_records", lambda *args, **kwargs: ([], None))

    result = read_code.read_code_references([str(code_file), "read_code_read", "--kind=default", "--max=1"])
    captured = capsys.readouterr()

    assert result == 0
    assert "# target" in captured.out
    assert "id\tgraph_uid\tname\tkind\tlines\tresolution_method\tlocation" in captured.out
    assert "function:read_code_read\tgraph-123\tread_code_read\tfunction\t1-2\texact_symbol_name\t" in captured.out


def test_read_code_references_truncated_only_checks_visible_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Hidden sections should not force truncated=true when they are filtered out."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def read_code_read():\n    return 1\n", encoding="utf-8")

    target = _make_match(
        unit_id="function:read_code_read",
        symbol_name="read_code_read",
        symbol_type="function",
        line_num=1,
        line_end=2,
        body="def read_code_read():\n    return 1\n",
    )
    resolution = read_code._ReadResolution(match=target, method="exact_symbol_name")
    exact_record = {
        "kind": ["Function"],
        "uid": "function:read_code_read",
        "name": "read_code_read",
        "path": str(code_file),
        "line_number": 1,
        "end_line": 2,
    }
    caller_record = {
        "kind": ["Function"],
        "uid": "function:caller",
        "name": "caller",
        "path": "tests/test_usage.py",
        "line_number": 10,
        "end_line": 11,
    }
    read_record = {
        "kind": ["Function"],
        "uid": "function:reader",
        "name": "reader",
        "path": "src/other.py",
        "line_number": 20,
        "end_line": 22,
        "source": "def reader():\n    read_code_read()\n    read_code_read()\n",
    }

    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda *_: True)
    monkeypatch.setattr(read_code, "codegraph_supports_file", lambda *_: True)
    monkeypatch.setattr(read_code, "codegraph_refresh_if_needed", lambda *_: True)
    monkeypatch.setattr(read_code, "_resolve_graph_target", lambda *_: resolution)
    monkeypatch.setattr(read_code, "_reference_exact_node_records", lambda *_: ([exact_record], None))
    monkeypatch.setattr(read_code, "_reference_direct_callers", lambda *args, **kwargs: ([caller_record], None))
    monkeypatch.setattr(read_code, "_reference_direct_callers_total", lambda *_: (1, None))
    monkeypatch.setattr(read_code, "_reference_direct_callees", lambda *args, **kwargs: ([], None))
    monkeypatch.setattr(read_code, "_reference_variable_terms", lambda *args, **kwargs: [])
    monkeypatch.setattr(read_code, "_reference_variable_records", lambda *args, **kwargs: ([], None))
    monkeypatch.setattr(read_code, "_reference_usage_terms", lambda *args, **kwargs: ["read_code_read"])
    monkeypatch.setattr(read_code, "_reference_content_records", lambda *args, **kwargs: ([read_record], None))

    result = read_code.read_code_references([str(code_file), "read_code_read", "--kind=callers", "--max=1"])
    captured = capsys.readouterr()

    assert result == 0
    assert "# callers returned=1 total=1" in captured.out
    assert "read tests/test_usage.py function:caller" in captured.out
    assert "# reads returned=" not in captured.out
    assert "reads=2" in captured.out
    assert "truncated=false" in captured.out


def test_read_code_references_accepts_ambiguous_mentions_kind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ambiguous mentions should be a valid explicit references kind."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def read_code_read():\n    return 1\n", encoding="utf-8")

    target = _make_match(
        unit_id="function:read_code_read",
        symbol_name="read_code_read",
        symbol_type="function",
        line_num=1,
        line_end=2,
        body="def read_code_read():\n    return 1\n",
    )
    resolution = read_code._ReadResolution(match=target, method="exact_symbol_name")
    exact_record = {
        "kind": ["Function"],
        "uid": "graph-123",
        "name": "read_code_read",
        "path": str(code_file),
        "line_number": 1,
        "end_line": 2,
    }

    _configure_reference_mode(monkeypatch, read_code, resolution, exact_record=exact_record, usage_terms=[])

    result = read_code.read_code_references(
        [str(code_file), "read_code_read", "--kind=ambiguous_mentions", "--max=1"]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert "kind=ambiguous_mentions" in captured.out
    assert "offset=0" in captured.out
    assert "returned=0" in captured.out
    assert "total=0" in captured.out
    assert "# ambiguous_mentions returned=0 total=0" in captured.out


def test_read_code_references_rejects_unknown_kind_with_updated_allowlist(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Invalid kinds should mention the expanded allowlist."""
    result = read_code.read_code_references(["scripts/read_code.py", "read_code_read", "--kind=bogus"])
    captured = capsys.readouterr()

    assert result == 1
    assert "ambiguous_mentions" in captured.err
    assert "ERROR: --kind must be one of default|callers|callees|reads|writes|variables|tests|ambiguous_mentions|all" in captured.err


def test_read_code_references_pages_callers_by_offset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Explicit caller pagination should page only the callers section."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def read_code_read():\n    return 1\n", encoding="utf-8")

    target = _make_match(
        unit_id="function:read_code_read",
        symbol_name="read_code_read",
        symbol_type="function",
        line_num=1,
        line_end=2,
        body="def read_code_read():\n    return 1\n",
    )
    resolution = read_code._ReadResolution(match=target, method="exact_symbol_name")
    exact_record = {
        "kind": ["Function"],
        "uid": "graph-123",
        "name": "read_code_read",
        "path": str(code_file),
        "line_number": 1,
        "end_line": 2,
    }
    all_caller_records = [
        {
            "kind": ["Function"],
            "uid": "function:caller_a",
            "name": "caller_a",
            "path": "tests/test_usage.py",
            "line_number": 10,
            "end_line": 11,
        },
        {
            "kind": ["Function"],
            "uid": "function:caller_b",
            "name": "caller_b",
            "path": "src/other.py",
            "line_number": 20,
            "end_line": 21,
        },
        {
            "kind": ["Function"],
            "uid": "function:caller_c",
            "name": "caller_c",
            "path": "src/more.py",
            "line_number": 30,
            "end_line": 31,
        },
    ]

    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda *_: True)
    monkeypatch.setattr(read_code, "codegraph_supports_file", lambda *_: True)
    monkeypatch.setattr(read_code, "codegraph_refresh_if_needed", lambda *_: True)
    monkeypatch.setattr(read_code, "_resolve_graph_target", lambda *_: resolution)
    monkeypatch.setattr(read_code, "_reference_exact_node_records", lambda *_: ([exact_record], None))

    def _mock_callers(file_path: Path, target: Any, depth: int, offset: int = 0, limit: int = 80) -> tuple[list[dict[str, object]], str | None]:
        """Mock that respects pagination parameters."""
        return (all_caller_records[offset : offset + limit], None)

    monkeypatch.setattr(read_code, "_reference_direct_callers", _mock_callers)
    monkeypatch.setattr(read_code, "_reference_direct_callees", lambda *args, **kwargs: ([], None))
    monkeypatch.setattr(read_code, "_reference_direct_callers_total", lambda *_: (5, None))
    monkeypatch.setattr(read_code, "_reference_direct_callees_total", lambda *_: (0, None))
    monkeypatch.setattr(read_code, "_reference_variable_terms", lambda *args, **kwargs: [])
    monkeypatch.setattr(read_code, "_reference_variable_records", lambda *args, **kwargs: ([], None))
    monkeypatch.setattr(read_code, "_reference_usage_terms", lambda *args, **kwargs: [])
    monkeypatch.setattr(read_code, "_reference_content_records", lambda *args, **kwargs: ([], None))

    first_result = read_code.read_code_references(
        [str(code_file), "read_code_read", "--kind=callers", "--max=2", "--offset=0"]
    )
    first = capsys.readouterr()
    second_result = read_code.read_code_references(
        [str(code_file), "read_code_read", "--kind=callers", "--max=2", "--offset=2"]
    )
    second = capsys.readouterr()

    assert first_result == 0
    assert "# callers returned=2 total=5" in first.out
    assert "offset=0" in first.out
    assert "returned=2" in first.out
    assert "total=5" in first.out
    assert "truncated=true" in first.out
    assert "next_offset=2" in first.out
    assert "command=read tests/test_usage.py function:caller_a" in first.out
    assert "command=read src/other.py function:caller_b" in first.out

    assert second_result == 0
    assert "# callers returned=1 total=5" in second.out
    assert "offset=2" in second.out
    assert "returned=1" in second.out
    assert "total=5" in second.out
    assert "truncated=true" in second.out
    assert "next_offset=3" in second.out
    assert "command=read src/more.py function:caller_c" in second.out
    assert "command=read tests/test_usage.py function:caller_a" not in second.out


@pytest.mark.parametrize(
    ("kind", "depth", "expected_total"),
    [
        ("callers", 1, 5),
        ("callers", 2, 7),
        ("callees", 1, 4),
        ("callees", 2, 6),
    ],
)
def test_read_code_references_uses_true_totals_for_graph_native_sections(
    kind: str,
    depth: int,
    expected_total: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Graph-native explicit sections should honor count-query totals at both supported depths."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def read_code_read():\n    return 1\n", encoding="utf-8")

    target = _make_match(
        unit_id="function:read_code_read",
        symbol_name="read_code_read",
        symbol_type="function",
        line_num=1,
        line_end=2,
        body="def read_code_read():\n    return 1\n",
    )
    resolution = read_code._ReadResolution(match=target, method="exact_symbol_name")
    exact_record = {
        "kind": ["Function"],
        "uid": "graph-123",
        "name": "read_code_read",
        "path": str(code_file),
        "line_number": 1,
        "end_line": 2,
    }
    graph_records = [
        {
            "kind": ["Function"],
            "uid": f"function:{kind}_a",
            "name": f"{kind}_a",
            "path": "tests/test_usage.py",
            "line_number": 10,
            "end_line": 11,
        },
        {
            "kind": ["Function"],
            "uid": f"function:{kind}_b",
            "name": f"{kind}_b",
            "path": "src/other.py",
            "line_number": 20,
            "end_line": 21,
        },
    ]
    count_depths: list[int] = []

    _configure_reference_mode(
        monkeypatch,
        read_code,
        resolution,
        exact_record=exact_record,
        callers=graph_records if kind == "callers" else [],
        callees=graph_records if kind == "callees" else [],
        usage_terms=[],
    )

    def _count_total(*args: Any) -> tuple[int | None, str | None]:
        count_depths.append(int(args[2]))
        return expected_total, None

    if kind == "callers":
        monkeypatch.setattr(read_code, "_reference_direct_callers_total", _count_total)
    else:
        monkeypatch.setattr(read_code, "_reference_direct_callees_total", _count_total)

    result = read_code.read_code_references(
        [str(code_file), "read_code_read", f"--kind={kind}", f"--depth={depth}", "--max=1", "--offset=0"]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert count_depths == [depth]
    assert f"# {kind} returned=1 total={expected_total}" in captured.out
    assert "offset=0" in captured.out
    assert "returned=1" in captured.out
    assert f"total={expected_total}" in captured.out
    assert "truncated=true" in captured.out
    assert "next_offset=1" in captured.out


def test_read_code_references_fails_when_graph_native_count_query_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Count-query failures should abort callers instead of using bounded totals."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def read_code_read():\n    return 1\n", encoding="utf-8")

    target = _make_match(
        unit_id="function:read_code_read",
        symbol_name="read_code_read",
        symbol_type="function",
        line_num=1,
        line_end=2,
        body="def read_code_read():\n    return 1\n",
    )
    resolution = read_code._ReadResolution(match=target, method="exact_symbol_name")
    exact_record = {
        "kind": ["Function"],
        "uid": "graph-123",
        "name": "read_code_read",
        "path": str(code_file),
        "line_number": 1,
        "end_line": 2,
    }
    caller_records = [
        {
            "kind": ["Function"],
            "uid": "function:caller_a",
            "name": "caller_a",
            "path": "tests/test_usage.py",
            "line_number": 10,
            "end_line": 11,
        }
    ]

    _configure_reference_mode(
        monkeypatch,
        read_code,
        resolution,
        exact_record=exact_record,
        callers=caller_records,
        usage_terms=[],
    )
    monkeypatch.setattr(read_code, "_reference_direct_callers_total", lambda *_: (None, "boom"))

    result = read_code.read_code_references([str(code_file), "read_code_read", "--kind=callers", "--max=1"])
    captured = capsys.readouterr()

    assert result == 1
    assert "ERROR: references callers count query failed: boom" in captured.err


def test_read_code_references_pages_reads_by_offset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Explicit read pagination should page only the reads section."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def read_code_read():\n    return 1\n", encoding="utf-8")

    target = _make_match(
        unit_id="function:read_code_read",
        symbol_name="read_code_read",
        symbol_type="function",
        line_num=1,
        line_end=2,
        body="def read_code_read():\n    return 1\n",
    )
    resolution = read_code._ReadResolution(match=target, method="exact_symbol_name")
    exact_record = {
        "kind": ["Function"],
        "uid": "graph-123",
        "name": "read_code_read",
        "path": str(code_file),
        "line_number": 1,
        "end_line": 2,
    }
    read_record = {
        "kind": ["Function"],
        "uid": "function:reader",
        "name": "reader",
        "path": "src/other.py",
        "line_number": 20,
        "end_line": 22,
        "source": "def reader():\n    read_code_read()\n    read_code_read()\n",
    }

    _configure_reference_mode(
        monkeypatch,
        read_code,
        resolution,
        exact_record=exact_record,
        usage_terms=["read_code_read"],
        content_records=[read_record],
    )

    result = read_code.read_code_references([str(code_file), "read_code_read", "--kind=reads", "--max=1", "--offset=1"])
    captured = capsys.readouterr()

    assert result == 0
    assert "# reads returned=1 total=2" in captured.out
    assert "offset=1" in captured.out
    assert "returned=1" in captured.out
    assert "total=2" in captured.out
    assert "truncated=false" in captured.out
    assert "next_offset=" not in captured.out
    assert "src/other.py:22-22 function:reader" in captured.out
    assert "src/other.py:21-21 function:reader" not in captured.out


def test_read_code_references_offset_only_affects_requested_kind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Offset should not affect callers/callees when requesting different kinds."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def read_code_read():\n    return 1\n", encoding="utf-8")

    target = _make_match(
        unit_id="function:read_code_read",
        symbol_name="read_code_read",
        symbol_type="function",
        line_num=1,
        line_end=2,
        body="def read_code_read():\n    return 1\n",
    )
    resolution = read_code._ReadResolution(match=target, method="exact_symbol_name")
    exact_record = {
        "kind": ["Function"],
        "uid": "graph-123",
        "name": "read_code_read",
        "path": str(code_file),
        "line_number": 1,
        "end_line": 2,
    }
    caller_records = [
        {"kind": ["Function"], "uid": "function:caller_a", "name": "caller_a", "path": "tests/test_usage.py", "line_number": 10, "end_line": 11},
        {"kind": ["Function"], "uid": "function:caller_b", "name": "caller_b", "path": "src/other.py", "line_number": 20, "end_line": 21},
    ]

    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda *_: True)
    monkeypatch.setattr(read_code, "codegraph_supports_file", lambda *_: True)
    monkeypatch.setattr(read_code, "codegraph_refresh_if_needed", lambda *_: True)
    monkeypatch.setattr(read_code, "_resolve_graph_target", lambda *_: resolution)
    monkeypatch.setattr(read_code, "_reference_exact_node_records", lambda *_: ([exact_record], None))

    captured_calls: list[tuple[int, int]] = []

    def _mock_callers_track(*args: Any, **kwargs: Any) -> tuple[list[dict[str, object]], str | None]:
        """Mock that records offset and limit parameters."""
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", 80)
        captured_calls.append(("callers", offset, limit))
        return (caller_records[offset : offset + limit], None)

    monkeypatch.setattr(read_code, "_reference_direct_callers", _mock_callers_track)
    monkeypatch.setattr(read_code, "_reference_direct_callees", lambda *args, **kwargs: ([], None))
    monkeypatch.setattr(read_code, "_reference_direct_callers_total", lambda *_: (2, None))
    monkeypatch.setattr(read_code, "_reference_direct_callees_total", lambda *_: (0, None))
    monkeypatch.setattr(read_code, "_reference_variable_terms", lambda *args, **kwargs: [])
    monkeypatch.setattr(read_code, "_reference_variable_records", lambda *args, **kwargs: ([], None))
    monkeypatch.setattr(read_code, "_reference_usage_terms", lambda *args, **kwargs: [])
    monkeypatch.setattr(read_code, "_reference_content_records", lambda *args, **kwargs: ([], None))

    result = read_code.read_code_references([str(code_file), "read_code_read", "--kind=reads", "--offset=5"])
    captured = capsys.readouterr()

    assert result == 0
    assert len(captured_calls) == 1
    assert captured_calls[0] == ("callers", 0, 80), "callers should use offset=0 when requesting --kind=reads"


@pytest.mark.parametrize(
    "kind",
    ["default", "all"],
)
def test_read_code_references_rejects_offset_for_default_and_all(
    kind: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Offset pagination should be rejected for default and all kinds."""
    result = read_code.read_code_references(["scripts/read_code.py", "read_code_read", f"--kind={kind}", "--offset=1"])
    captured = capsys.readouterr()

    assert result == 1
    assert "ERROR: --offset is currently supported only with explicit --kind sections" in captured.err


@pytest.mark.parametrize(
    "offset_token",
    ["--offset=-1", "--offset=abc"],
)
def test_read_code_references_rejects_invalid_offset_values(
    offset_token: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Offset parsing should reject negative and non-integer values."""
    result = read_code.read_code_references(["scripts/read_code.py", "read_code_read", offset_token])
    captured = capsys.readouterr()

    assert result == 1
    assert "ERROR: --offset expects a non-negative integer:" in captured.err
