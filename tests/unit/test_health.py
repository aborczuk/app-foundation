"""Unit tests for local graph health classification."""

from __future__ import annotations

import os
import time
from pathlib import Path

from src.mcp_codebase.health import GraphHealthStatus, classify_graph_health


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
    assert result.recovery_hint.id == "fail-fast-memory-pressure"
    assert "memory pressure" in result.detail.lower()
