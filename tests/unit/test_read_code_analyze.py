"""Unit tests for read_code analyze shortlist behavior."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def _load_read_code_module():
    """Load scripts/read_code.py as a module for direct parser tests."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / "read_code.py"
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location("read_code_analyze", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_analyze_args_supports_candidate_stepping() -> None:
    """Analyze mode should accept shortlist stepping flags without forwarding them to cgc."""
    read_code = _load_read_code_module()

    parsed = read_code._parse_analyze_args(
        ["callers", "read_code_find", "--show-shortlist", "--next-candidate", "--candidate-index", "1"]
    )

    assert parsed is not None
    assert parsed.command == "callers"
    assert parsed.forwarded_args == ["read_code_find"]
    assert parsed.show_shortlist is True
    assert parsed.candidate_index == 1


def test_parse_cgc_analyze_output_filters_non_repo_matches(tmp_path: Path, monkeypatch) -> None:
    """Only repo-local analyze rows with Location should survive parsing."""
    read_code = _load_read_code_module()
    monkeypatch.setattr(read_code, "REPO_ROOT", tmp_path)
    repo_file = tmp_path / "scripts" / "read_code.py"
    repo_file.parent.mkdir(parents=True)
    repo_file.write_text("", encoding="utf-8")
    raw_output = "\n".join(
        [
            "Functions that call 'read_code_find':",
            "╭─────────────────┬───────────────────────────────────────────────┬────────────╮",
            "│ Caller Function │ Location                                      │ Call Type  │",
            "├─────────────────┼───────────────────────────────────────────────┼────────────┤",
            f"│ main            │ {repo_file}:10                                │ 📝 Project │",
            "│ other           │ /outside/repo/site.py:9                      │ 📝 Project │",
            "╰─────────────────┴───────────────────────────────────────────────┴────────────╯",
        ]
    )

    matches = read_code._parse_cgc_analyze_output(raw_output)

    assert len(matches) == 1
    assert matches[0].columns["Caller Function"] == "main"
    assert matches[0].location == f"{repo_file}:10"


def test_read_code_analyze_returns_compact_first_match(tmp_path: Path, monkeypatch, capsys) -> None:
    """Analyze mode should render one compact repo-local row instead of the full raw table."""
    read_code = _load_read_code_module()
    monkeypatch.setattr(read_code, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code, "init_codegraph_env", lambda: None)
    repo_file = tmp_path / "scripts" / "read_code.py"
    repo_file.parent.mkdir(parents=True)
    repo_file.write_text("", encoding="utf-8")
    raw_output = "\n".join(
        [
            "Functions that call 'read_code_find':",
            "╭─────────────────┬───────────────────────────────────────────────┬────────────╮",
            "│ Caller Function │ Location                                      │ Call Type  │",
            "├─────────────────┼───────────────────────────────────────────────┼────────────┤",
            f"│ main            │ {repo_file}:10                                │ 📝 Project │",
            f"│ second          │ {repo_file}:20                                │ 📝 Project │",
            "╰─────────────────┴───────────────────────────────────────────────┴────────────╯",
        ]
    )
    monkeypatch.setattr(
        read_code.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout="", stderr=raw_output),
    )

    rc = read_code.read_code_analyze(["callers", "read_code_find"])
    output = capsys.readouterr().out

    assert rc == 0
    assert "analyze_command: callers" in output
    assert "caller_function: main" in output
    assert "match_index: 0/1" in output
    assert "Functions that call" not in output


def test_read_code_analyze_falls_back_to_raw_output_without_table(monkeypatch, capsys) -> None:
    """Non-table analyze output should still pass through unchanged."""
    read_code = _load_read_code_module()
    monkeypatch.setattr(read_code, "init_codegraph_env", lambda: None)
    monkeypatch.setattr(
        read_code.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout="No dependency information found", stderr=""),
    )

    rc = read_code.read_code_analyze(["deps", "scripts.read_code"])
    output = capsys.readouterr().out

    assert rc == 0
    assert "No dependency information found" in output
