"""Unit tests for read_markdown helper concurrency guards."""

from __future__ import annotations

import fcntl
import importlib.util
import sys
from pathlib import Path


def _load_module(module_name: str, script_name: str):
    """Load a helper script module from the scripts directory for unit tests."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec for {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


read_markdown = _load_module("read_markdown_guards", "read_markdown.py")


def test_read_markdown_section_fails_when_lock_is_held(monkeypatch, tmp_path: Path, capsys) -> None:
    """read_markdown_section should fail fast when a concurrent file lock is present."""
    target = tmp_path / "doc.md"
    target.write_text("# Heading\nbody\n", encoding="utf-8")

    refresh_calls = {"count": 0}

    def fake_refresh(_file: Path) -> bool:
        refresh_calls["count"] += 1
        return True

    monkeypatch.setattr(read_markdown, "_refresh_indexes_for_read", fake_refresh)
    monkeypatch.setattr(read_markdown, "_vector_markdown_line_num", lambda *_args, **_kwargs: 1)

    lock_path = read_markdown._markdown_lock_path(target.resolve())
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = read_markdown.read_markdown_section(str(target), "Heading")

    stderr = capsys.readouterr().err
    assert result == 1
    assert "guard blocked concurrent read" in stderr
    assert refresh_calls["count"] == 0


def test_read_markdown_headings_fails_when_lock_is_held(monkeypatch, tmp_path: Path, capsys) -> None:
    """read_markdown_headings should fail fast when a concurrent file lock is present."""
    target = tmp_path / "doc.md"
    target.write_text("# Heading\n## Child\n", encoding="utf-8")

    refresh_calls = {"count": 0}

    def fake_refresh(_file: Path) -> bool:
        refresh_calls["count"] += 1
        return True

    monkeypatch.setattr(read_markdown, "_refresh_indexes_for_read", fake_refresh)

    lock_path = read_markdown._markdown_lock_path(target.resolve())
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = read_markdown.read_markdown_headings(str(target))

    stderr = capsys.readouterr().err
    assert result == 1
    assert "guard blocked concurrent read" in stderr
    assert refresh_calls["count"] == 0


def test_reserve_markdown_budget_blocks_when_cap_is_exceeded(monkeypatch, tmp_path: Path, capsys) -> None:
    """Session budget reservations should fail once cumulative usage exceeds the configured cap."""
    monkeypatch.setenv(read_markdown.READ_MARKDOWN_LOCK_DIR_ENV, str(tmp_path / "locks"))
    monkeypatch.setenv(read_markdown.READ_MARKDOWN_SESSION_ID_ENV, "unit-session")
    monkeypatch.setenv(read_markdown.READ_MARKDOWN_STEP_BUDGET_ENV, "3")
    monkeypatch.setenv(read_markdown.READ_MARKDOWN_BUDGET_RESET_SECONDS_ENV, "120")

    assert read_markdown._reserve_markdown_budget(2) is True
    assert read_markdown._reserve_markdown_budget(2) is False
    stderr = capsys.readouterr().err
    assert "budget exceeded" in stderr


def test_read_markdown_headings_fails_when_budget_is_exceeded(monkeypatch, tmp_path: Path, capsys) -> None:
    """read_markdown_headings should stop before output when session budget would be exceeded."""
    target = tmp_path / "doc.md"
    target.write_text("# One\n## Two\n### Three\n", encoding="utf-8")
    monkeypatch.setattr(read_markdown, "_refresh_indexes_for_read", lambda _file: True)
    monkeypatch.setenv(read_markdown.READ_MARKDOWN_LOCK_DIR_ENV, str(tmp_path / "locks"))
    monkeypatch.setenv(read_markdown.READ_MARKDOWN_SESSION_ID_ENV, "budget-headings")
    monkeypatch.setenv(read_markdown.READ_MARKDOWN_STEP_BUDGET_ENV, "2")
    monkeypatch.setenv(read_markdown.READ_MARKDOWN_BUDGET_RESET_SECONDS_ENV, "120")

    result = read_markdown.read_markdown_headings(str(target))

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert "budget exceeded" in captured.err
