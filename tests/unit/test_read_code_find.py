"""Unit tests for read_code find shortlist behavior."""

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
    spec = importlib.util.spec_from_file_location("read_code_find", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_find_args_supports_candidate_stepping() -> None:
    """Find mode should accept shortlist stepping flags without forwarding them to cgc."""
    read_code = _load_read_code_module()

    parsed = read_code._parse_find_args(
        ["content", "next-candidate", "--show-shortlist", "--next-candidate", "--candidate-index", "1"]
    )

    assert parsed is not None
    assert parsed.command == "content"
    assert parsed.forwarded_args == ["next-candidate"]
    assert parsed.show_shortlist is True
    assert parsed.candidate_index == 1


def test_parse_cgc_find_output_filters_non_repo_matches(tmp_path: Path, monkeypatch) -> None:
    """Only repo-local matches should survive parsing, including wrapped locations."""
    read_code = _load_read_code_module()
    monkeypatch.setattr(read_code, "REPO_ROOT", tmp_path)
    repo_file = tmp_path / "scripts" / "read_code.py"
    repo_file.parent.mkdir(parents=True)
    repo_file.write_text("", encoding="utf-8")
    raw_output = "\n".join(
        [
            "Found 2 content match(es) for 'needle':",
            "╭─────────────────────┬──────────┬─────────────────────────────────────────────╮",
            "│ Name                │ Type     │ Location                                    │",
            "├─────────────────────┼──────────┼─────────────────────────────────────────────┤",
            f"│ read_code_find      │ function │ {repo_file}:1017                            │",
            "│ external_symbol     │ function │ /outside/repo/site.py:9                    │",
            "╰─────────────────────┴──────────┴─────────────────────────────────────────────╯",
        ]
    )

    matches = read_code._parse_cgc_find_output(raw_output)

    assert len(matches) == 1
    assert matches[0].name == "read_code_find"
    assert matches[0].location == f"{repo_file}:1017"


def test_read_code_find_returns_compact_first_match(tmp_path: Path, monkeypatch, capsys) -> None:
    """Find mode should render one compact repo-local match instead of the full raw table."""
    read_code = _load_read_code_module()
    monkeypatch.setattr(read_code, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code, "init_codegraph_env", lambda: None)
    repo_file = tmp_path / "scripts" / "read_code.py"
    repo_file.parent.mkdir(parents=True)
    repo_file.write_text("", encoding="utf-8")
    raw_output = "\n".join(
        [
            "Found 2 content match(es) for 'needle':",
            "╭─────────────────────┬──────────┬─────────────────────────────────────────────╮",
            "│ Name                │ Type     │ Location                                    │",
            "├─────────────────────┼──────────┼─────────────────────────────────────────────┤",
            f"│ first_symbol        │ function │ {repo_file}:10                              │",
            f"│ second_symbol       │ function │ {repo_file}:20                              │",
            "╰─────────────────────┴──────────┴─────────────────────────────────────────────╯",
        ]
    )
    monkeypatch.setattr(
        read_code.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout="", stderr=raw_output),
    )

    rc = read_code.read_code_find(["content", "needle"])
    output = capsys.readouterr().out

    assert rc == 0
    assert "name: first_symbol" in output
    assert "match_index: 0/1" in output
    assert "--next-candidate for the next ranked match" in output
    assert "Found 2 content match(es)" not in output


def test_read_code_find_next_candidate_steps_to_second_match(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Find mode should step through ranked matches with --next-candidate."""
    read_code = _load_read_code_module()
    monkeypatch.setattr(read_code, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code, "init_codegraph_env", lambda: None)
    repo_file = tmp_path / "scripts" / "read_code.py"
    repo_file.parent.mkdir(parents=True)
    repo_file.write_text("", encoding="utf-8")
    raw_output = "\n".join(
        [
            "Found 2 content match(es) for 'needle':",
            "╭─────────────────────┬──────────┬─────────────────────────────────────────────╮",
            "│ Name                │ Type     │ Location                                    │",
            "├─────────────────────┼──────────┼─────────────────────────────────────────────┤",
            f"│ first_symbol        │ function │ {repo_file}:10                              │",
            f"│ second_symbol       │ function │ {repo_file}:20                              │",
            "╰─────────────────────┴──────────┴─────────────────────────────────────────────╯",
        ]
    )
    monkeypatch.setattr(
        read_code.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout="", stderr=raw_output),
    )

    rc = read_code.read_code_find(["content", "needle", "--next-candidate"])
    output = capsys.readouterr().out

    assert rc == 0
    assert "name: second_symbol" in output
    assert "match_index: 1/1" in output
