"""Unit tests for local graph health classification."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from src.mcp_codebase import health as health_module
from src.mcp_codebase.health import (
    GraphAccessMode,
    GraphHealthStatus,
    classify_graph_health,
)


def _seed_repo(
    root: Path,
    *,
    source_mtime: float,
    db_mtime: float,
    lock_marker: str | None = None,
    readable: bool = True,
) -> Path:
    source = root / "src" / "module.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")

    db = root / ".codegraphcontext" / "db" / "kuzudb"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("snapshot\n", encoding="utf-8")

    os.utime(source, (source_mtime, source_mtime))
    os.utime(db, (db_mtime, db_mtime))

    if lock_marker is not None:
        marker = root / lock_marker
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("locked\n", encoding="utf-8")

    if not readable:
        db.chmod(0o000)

    return db


def test_classify_graph_health_returns_healthy_for_fresh_index(tmp_path: Path) -> None:
    now = time.time()
    db = _seed_repo(
        tmp_path,
        source_mtime=now - 120,
        db_mtime=now - 30,
    )

    result = classify_graph_health(tmp_path)

    assert result.status is GraphHealthStatus.HEALTHY
    assert result.access_mode is GraphAccessMode.READ_ONLY
    assert result.recovery_hint.id == "continue"
    assert "current" in result.detail.lower()
    assert result.latency_ms >= 0
    assert db.exists()


def test_classify_graph_health_returns_stale_when_sources_are_newer(tmp_path: Path) -> None:
    now = time.time()
    _seed_repo(
        tmp_path,
        source_mtime=now - 5,
        db_mtime=now - 120,
    )

    result = classify_graph_health(tmp_path)

    assert result.status is GraphHealthStatus.STALE
    assert result.access_mode is GraphAccessMode.READ_ONLY
    assert result.recovery_hint.id == "refresh-scoped-index"
    assert "changed after the indexed snapshot" in result.detail
    assert "safe_index" in result.recovery_hint.command


def test_classify_graph_health_returns_locked_for_lock_marker(tmp_path: Path) -> None:
    now = time.time()
    _seed_repo(
        tmp_path,
        source_mtime=now - 120,
        db_mtime=now - 30,
        lock_marker=".codegraphcontext/db/kuzudb.lock",
    )

    result = classify_graph_health(tmp_path)

    assert result.status is GraphHealthStatus.LOCKED
    assert result.access_mode is GraphAccessMode.READ_ONLY
    assert result.recovery_hint.id == "retry-after-close"
    assert "lock marker" in result.detail


def test_classify_graph_health_returns_unavailable_for_unreadable_db(tmp_path: Path) -> None:
    now = time.time()
    db = _seed_repo(
        tmp_path,
        source_mtime=now - 120,
        db_mtime=now - 30,
        readable=False,
    )

    try:
        result = classify_graph_health(tmp_path)
    finally:
        db.chmod(0o644)

    assert result.status is GraphHealthStatus.UNAVAILABLE
    assert result.access_mode is GraphAccessMode.READ_ONLY
    assert result.recovery_hint.id == "fallback-to-files"
    assert "not readable" in result.detail


def test_classify_graph_health_returns_memory_pressure_hint(tmp_path: Path) -> None:
    error_file = tmp_path / ".codegraphcontext" / "last-index-error.txt"
    error_file.parent.mkdir(parents=True, exist_ok=True)
    error_file.write_text(
        "type=memory-pressure\nexit_code=137\ndetail=buffer pool exhausted while indexing\n",
        encoding="utf-8",
    )

    result = classify_graph_health(tmp_path)

    assert result.status is GraphHealthStatus.UNAVAILABLE
    assert result.access_mode is GraphAccessMode.READ_ONLY
    assert result.recovery_hint.id == "fail-fast-memory-pressure"
    assert "memory pressure" in result.detail.lower()


def test_classify_graph_health_ignores_git_edit_drift_for_fresh_snapshot(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    source = tmp_path / "src" / "module.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    db = tmp_path / ".codegraphcontext" / "db" / "kuzudb"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("snapshot\n", encoding="utf-8")
    marker = tmp_path / ".codegraphcontext" / "last-edit-signature.txt"
    marker.write_text("", encoding="utf-8")

    now = time.time()
    os.utime(source, (now - 120, now - 120))
    os.utime(db, (now - 30, now - 30))

    result = classify_graph_health(tmp_path)

    assert result.status is GraphHealthStatus.HEALTHY
    assert result.access_mode is GraphAccessMode.READ_ONLY
    assert result.recovery_hint.id == "continue"
    assert "current with tracked source files" in result.detail


def test_current_edit_signature_ignores_codegraphcontext_on_leading_space_status(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        health_module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=" M .codegraphcontext/last-edit-signature.txt\n",
            stderr="",
        ),
    )

    signature = health_module._current_edit_signature(tmp_path)

    assert signature == ""


def test_read_cached_edit_signature_strips_trailing_newline(tmp_path: Path) -> None:
    marker = tmp_path / ".codegraphcontext" / "last-edit-signature.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(" M src/module.py\n", encoding="utf-8")

    cached = health_module._read_cached_edit_signature(tmp_path)

    assert cached == " M src/module.py"


def test_classify_graph_health_stays_read_only_while_owner_marker_exists(tmp_path: Path) -> None:
    now = time.time()
    owner_pid_file = tmp_path / ".codegraphcontext" / "db" / "kuzudb.owner.pid"
    _seed_repo(
        tmp_path,
        source_mtime=now - 120,
        db_mtime=now - 30,
        lock_marker=".codegraphcontext/db/kuzudb.lock",
    )
    owner_pid_file.parent.mkdir(parents=True, exist_ok=True)
    owner_pid_file.write_text("12345\n", encoding="utf-8")

    start = time.monotonic()
    result = classify_graph_health(tmp_path)
    elapsed = time.monotonic() - start

    assert elapsed < 0.5
    assert result.status is GraphHealthStatus.LOCKED
    assert result.access_mode is GraphAccessMode.READ_ONLY
    assert owner_pid_file.exists()
