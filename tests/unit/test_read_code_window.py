"""Unit tests for the read_code window disablement contract."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_read_code_module():
    """Load scripts/read_code.py as a module for direct parser tests."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / "read_code.py"
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location("read_code", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_window_args_uses_start_and_end_lines(tmp_path: Path) -> None:
    """Window argument parsing remains stable for any internal callers."""
    read_code = _load_read_code_module()
    target = tmp_path / "sample.py"
    target.write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")

    parsed = read_code._parse_window_args([str(target), "2", "4", "--hud-symbol", "--allow-fallback", "needle"])

    assert parsed is not None
    assert parsed.file_path == target
    assert parsed.start_line == 2
    assert parsed.end_line == 4
    assert parsed.use_hud_fast_path is True
    assert parsed.allow_fallback is True
    assert parsed.pattern == "needle"


def test_parse_window_args_rejects_ranges_over_the_maximum(tmp_path: Path) -> None:
    """Reject ranges that exceed the configured 80-line cap."""
    read_code = _load_read_code_module()
    target = tmp_path / "sample.py"
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")

    assert read_code._parse_window_args([str(target), "1", str(read_code.READ_CODE_MAX_LINES + 1)]) is None


def test_read_code_window_is_disabled(tmp_path: Path, capsys) -> None:
    """Window mode should fail closed and force semantic-first discovery."""
    read_code = _load_read_code_module()
    target = tmp_path / "sample.py"
    target.write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")

    rc = read_code.read_code_window([str(target), "2", "4"])
    stderr = capsys.readouterr().err

    assert rc == 1
    assert "window mode is disabled" in stderr
