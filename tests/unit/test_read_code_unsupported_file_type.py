"""Regression tests for unsupported read-code file types."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module(module_name: str, script_name: str):
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


read_code = _load_module("read_code", "read_code.py")


def test_unsupported_file_type_can_still_use_vector_anchor(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "notes.md"
    target.write_text("header\nanchor line\ntrailing\n", encoding="utf-8")

    calls: list[str] = []

    def fake_vector_find_line_num(file_path: Path, raw_pattern: str, normalized_pattern: str, scope: str):
        calls.append("vector")
        if len(calls) == 1:
            return None
        return read_code._VectorMatch(
            line_num=2,
            raw_score=0.9,
            metadata_score=8.0,
            exact_symbol_match=True,
            symbol_type="function",
            has_body=True,
            has_docstring=True,
            line_span=4,
        )

    monkeypatch.setattr(read_code, "codegraph_supports_file", lambda file_path: False)
    monkeypatch.setattr(
        read_code,
        "codegraph_discover_or_fail",
        lambda pattern, scope_path=None: (_ for _ in ()).throw(AssertionError("codegraph should not run")),
    )
    monkeypatch.setattr(read_code, "_vector_find_line_num", fake_vector_find_line_num)
    monkeypatch.setattr(read_code, "_resolve_line_num_strict", lambda *args, **kwargs: (1, None))

    exit_code = read_code.read_code_context([str(target), "anchor line", "2"])

    assert exit_code == 0
    assert calls == ["vector", "vector"]
