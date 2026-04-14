"""Integration tests for the codegraph doctor and health contract."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from src.mcp_codebase.health import classify_graph_health


def _seed_repo(
    root: Path,
    *,
    source_mtime: float,
    db_mtime: float,
) -> None:
    source = root / "src" / "module.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")

    db = root / ".codegraphcontext" / "db" / "kuzudb"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("snapshot\n", encoding="utf-8")

    os.utime(source, (source_mtime, source_mtime))
    os.utime(db, (db_mtime, db_mtime))


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
    )
    payload = json.loads(proc.stdout)
    return proc.returncode, payload, proc.stderr


def test_doctor_cli_matches_shared_classifier_on_fresh_checkout(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    now = time.time()
    project_root = tmp_path / "fresh"
    _seed_repo(project_root, source_mtime=now - 120, db_mtime=now - 30)

    exit_code, payload, _stderr = _run_doctor(repo, project_root)
    expected = classify_graph_health(project_root).to_dict()

    assert exit_code == 0
    assert payload["status"] == expected["status"]
    assert payload["recovery_hint"]["id"] == expected["recovery_hint"]["id"]
    assert payload["recovery_hint"]["command"] == expected["recovery_hint"]["command"]


def test_doctor_cli_matches_shared_classifier_on_stale_checkout(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    now = time.time()
    project_root = tmp_path / "stale"
    _seed_repo(project_root, source_mtime=now - 5, db_mtime=now - 120)

    exit_code, payload, _stderr = _run_doctor(repo, project_root)
    expected = classify_graph_health(project_root).to_dict()

    assert exit_code != 0
    assert payload["status"] == "stale"
    assert payload["status"] == expected["status"]
    assert payload["recovery_hint"]["id"] == expected["recovery_hint"]["id"]
