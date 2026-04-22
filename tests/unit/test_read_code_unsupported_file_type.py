"""Regression tests for read-code file types handled without codegraph discovery."""

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


def _fake_vector_match(line_num: int) -> object:
    return read_code._VectorMatch(
        line_num=line_num,
        raw_score=0.9,
        metadata_score=8.0,
        exact_symbol_match=True,
        symbol_type="yaml_section",
        has_body=True,
        has_docstring=True,
        line_span=4,
    )


def test_yaml_read_uses_vector_anchor_without_codegraph_warning(tmp_path: Path, monkeypatch, capsys) -> None:
    target = tmp_path / "command-manifest.yaml"
    target.write_text("header\nanchor line\ntrailing\n", encoding="utf-8")

    calls: list[str] = []

    def fake_vector_find_line_num(file_path: Path, raw_pattern: str, normalized_pattern: str, scope: str):
        calls.append("vector")
        if len(calls) == 1:
            return None
        return _fake_vector_match(2)

    monkeypatch.setattr(read_code, "codegraph_supports_file", lambda file_path: False)
    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda file_path: True)
    monkeypatch.setattr(
        read_code,
        "codegraph_discover_or_fail",
        lambda pattern, scope_path=None: (_ for _ in ()).throw(AssertionError("codegraph should not run")),
    )
    monkeypatch.setattr(read_code, "_vector_find_line_num", fake_vector_find_line_num)
    monkeypatch.setattr(read_code, "_resolve_line_num_strict", lambda *args, **kwargs: (1, None))

    exit_code = read_code.read_code_context([str(target), "anchor line", "2"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert calls == ["vector", "vector"]
    assert "unsupported file type for codegraph discovery" not in captured.err


def test_shell_read_uses_vector_anchor_without_codegraph_warning(tmp_path: Path, monkeypatch, capsys) -> None:
    target = tmp_path / "read-code.sh"
    target.write_text("header\nanchor line\ntrailing\n", encoding="utf-8")

    calls: list[str] = []

    def fake_vector_find_line_num(file_path: Path, raw_pattern: str, normalized_pattern: str, scope: str):
        calls.append("vector")
        if len(calls) == 1:
            return None
        return _fake_vector_match(2)

    monkeypatch.setattr(read_code, "codegraph_supports_file", lambda file_path: False)
    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda file_path: True)
    monkeypatch.setattr(
        read_code,
        "codegraph_discover_or_fail",
        lambda pattern, scope_path=None: (_ for _ in ()).throw(AssertionError("codegraph should not run")),
    )
    monkeypatch.setattr(read_code, "_vector_find_line_num", fake_vector_find_line_num)
    monkeypatch.setattr(read_code, "_resolve_line_num_strict", lambda *args, **kwargs: (1, None))

    exit_code = read_code.read_code_context([str(target), "anchor line", "2"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert calls == ["vector", "vector"]
    assert "unsupported file type for codegraph discovery" not in captured.err
