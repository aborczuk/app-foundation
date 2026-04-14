"""Integration tests for codegraph recovery and rebuild behavior."""

from __future__ import annotations

import json
import os
import subprocess
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
) -> tuple[Path, Path]:
    source = root / "src" / "module.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")

    db = root / ".codegraphcontext" / "db" / "kuzudb"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("snapshot\n", encoding="utf-8")

    config = root / ".codegraphcontext" / "config.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("database: kuzudb\n", encoding="utf-8")

    os.utime(source, (source_mtime, source_mtime))
    os.utime(db, (db_mtime, db_mtime))

    if lock_marker is not None:
        marker = root / lock_marker
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("locked\n", encoding="utf-8")

    if not readable:
        db.chmod(0o000)

    return source, db


def _run_doctor(repo: Path, project_root: Path) -> tuple[int, dict[str, object], str]:
    proc = subprocess.run(
        [
            "bash",
            "scripts/cgc_doctor.sh",
            "--json",
            "--project-root",
            str(project_root),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = json.loads(proc.stdout)
    return proc.returncode, payload, proc.stderr


def test_lock_and_query_failure_modes(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    now = time.time()
    project_root = tmp_path / "recovery-matrix"

    _, db = _seed_repo(
        project_root,
        source_mtime=now - 120,
        db_mtime=now - 30,
    )
    exit_code, payload, _stderr = _run_doctor(repo, project_root)
    expected = classify_graph_health(project_root).to_dict()

    assert exit_code == 0
    assert payload["status"] == GraphHealthStatus.HEALTHY.value
    assert payload["status"] == expected["status"]
    assert payload["recovery_hint"]["id"] == "continue"

    source, _ = _seed_repo(
        project_root,
        source_mtime=now - 5,
        db_mtime=now - 120,
    )
    exit_code, payload, _stderr = _run_doctor(repo, project_root)
    expected = classify_graph_health(project_root).to_dict()

    assert exit_code != 0
    assert payload["status"] == GraphHealthStatus.STALE.value
    assert payload["status"] == expected["status"]
    assert payload["recovery_hint"]["id"] == "refresh-scoped-index"
    assert "cgc_safe_index.sh" in payload["recovery_hint"]["command"]
    assert "working tree changed" in payload["detail"]

    _seed_repo(
        project_root,
        source_mtime=now - 120,
        db_mtime=now - 30,
        lock_marker=".codegraphcontext/db/kuzudb.lock",
    )
    exit_code, payload, _stderr = _run_doctor(repo, project_root)
    expected = classify_graph_health(project_root).to_dict()

    assert exit_code != 0
    assert payload["status"] == GraphHealthStatus.LOCKED.value
    assert payload["status"] == expected["status"]
    assert payload["recovery_hint"]["id"] == "retry-after-close"
    assert "lock marker" in payload["detail"]

    lock_marker = project_root / ".codegraphcontext" / "db" / "kuzudb.lock"
    if lock_marker.exists():
        lock_marker.unlink()

    _, db = _seed_repo(
        project_root,
        source_mtime=now - 120,
        db_mtime=now - 30,
        readable=False,
    )
    try:
        exit_code, payload, _stderr = _run_doctor(repo, project_root)
        expected = classify_graph_health(project_root).to_dict()
    finally:
        db.chmod(0o644)

    assert exit_code != 0
    assert payload["status"] == GraphHealthStatus.UNAVAILABLE.value
    assert payload["status"] == expected["status"]
    assert payload["recovery_hint"]["id"] == "fallback-to-files"
    assert "readable" in payload["detail"]
    assert "read-code.sh" in payload["recovery_hint"]["command"]
    assert source.exists()


def test_local_edit_invalidates_then_refresh_restores_health(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    now = time.time()
    project_root = tmp_path / "refresh-cycle"
    source, db = _seed_repo(
        project_root,
        source_mtime=now - 120,
        db_mtime=now - 30,
    )

    exit_code, payload, _stderr = _run_doctor(repo, project_root)
    assert exit_code == 0
    assert payload["status"] == GraphHealthStatus.HEALTHY.value

    source.write_text("VALUE = 2\n", encoding="utf-8")
    os.utime(source, (now + 5, now + 5))

    exit_code, payload, _stderr = _run_doctor(repo, project_root)
    expected = classify_graph_health(project_root).to_dict()

    assert exit_code != 0
    assert payload["status"] == GraphHealthStatus.STALE.value
    assert payload["status"] == expected["status"]
    assert payload["recovery_hint"]["id"] == "refresh-scoped-index"
    assert "working tree changed after the indexed snapshot" in payload["detail"]

    os.utime(db, (now + 10, now + 10))

    exit_code, payload, _stderr = _run_doctor(repo, project_root)
    expected = classify_graph_health(project_root).to_dict()

    assert exit_code == 0
    assert payload["status"] == GraphHealthStatus.HEALTHY.value
    assert payload["status"] == expected["status"]
    assert payload["recovery_hint"]["id"] == "continue"
    assert "current" in payload["detail"].lower()
