"""Live-backend verification for vector edit fingerprinting, read_code.py, and slug normalization."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import scripts.read_code_health as read_code_health

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_cmd(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a live subprocess command without mocking or stubbing."""
    return subprocess.run(
        command,
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )


def test_live_edit_refresh_commit_and_post_edit_fingerprint_cycle(tmp_path: Path) -> None:
    """Exercise real git commits and real content-fingerprint persistence end to end."""
    repo = tmp_path / "live_repo"
    repo.mkdir()
    assert _run_cmd(["git", "init"], cwd=repo).returncode == 0
    assert _run_cmd(["git", "config", "user.name", "Live Tester"], cwd=repo).returncode == 0
    assert _run_cmd(["git", "config", "user.email", "live@example.com"], cwd=repo).returncode == 0

    module = repo / "service.py"
    module.write_text("def version() -> int:\n    return 1\n", encoding="utf-8")
    assert _run_cmd(["git", "add", "service.py"], cwd=repo).returncode == 0
    assert _run_cmd(["git", "commit", "-m", "initial"], cwd=repo).returncode == 0

    # Edit and persist refreshed content fingerprint
    module.write_text("def version() -> int:\n    return 2\n", encoding="utf-8")
    refreshed_sig = read_code_health.codegraph_current_edit_signature(repo)
    read_code_health._persist_vector_edit_signature(refreshed_sig, repo)
    assert read_code_health.vector_index_probe(repo).status == "healthy"

    # Commit unchanged refreshed content -> fingerprint and health must remain unchanged
    assert _run_cmd(["git", "add", "service.py"], cwd=repo).returncode == 0
    assert _run_cmd(["git", "commit", "-m", "commit refreshed file"], cwd=repo).returncode == 0
    assert read_code_health.codegraph_current_edit_signature(repo) == refreshed_sig
    post_commit_probe = read_code_health.vector_index_probe(repo)
    assert post_commit_probe.status == "healthy"
    assert post_commit_probe.stale_drift_paths == ()

    # Subsequent real edit -> must deterministically report stale on service.py
    module.write_text("def version() -> int:\n    return 3\n", encoding="utf-8")
    post_edit_probe = read_code_health.vector_index_probe(repo)
    assert post_edit_probe.status == "stale"
    assert "service.py" in post_edit_probe.stale_drift_paths


def test_live_read_code_window_and_deterministic_repo_fingerprint() -> None:
    """Run live scripts/read_code.py window and verify repo fingerprint determinism."""
    first_sig = read_code_health.codegraph_current_edit_signature(REPO_ROOT)
    second_sig = read_code_health.codegraph_current_edit_signature(REPO_ROOT)
    assert first_sig
    assert first_sig == second_sig
    assert "scripts/pipeline_ledger.py:" in first_sig

    proc = _run_cmd(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "read_code.py"),
            "window",
            "scripts/pipeline_ledger.py",
            "1",
            "25",
        ],
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Append-only pipeline ledger tooling" in proc.stdout


def test_live_driver_and_ledger_accept_full_feature_slug() -> None:
    """Verify live CLI subprocesses accept NNN-slug against the real append-only ledger."""
    gate_proc = _run_cmd(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "pipeline_ledger.py"),
            "assert-phase-complete",
            "--feature-id",
            "059-workflow-state-consistency",
            "--event",
            "analysis_completed",
        ],
        cwd=REPO_ROOT,
    )
    assert gate_proc.returncode == 0, gate_proc.stderr
    assert "Phase gate PASSED: analysis_completed found for feature 059" in gate_proc.stdout

    driver_proc = _run_cmd(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "pipeline_driver.py"),
            "--feature-id",
            "059-workflow-state-consistency",
            "--dry-run",
            "--json",
        ],
        cwd=REPO_ROOT,
    )
    assert driver_proc.returncode == 0, driver_proc.stderr
    json_line = [line for line in driver_proc.stdout.splitlines() if line.startswith("{")][-1]
    payload = json.loads(json_line)
    assert payload["phase_state"]["ledger_feature_id"] == "059"
    assert payload["phase_state"]["ledger_event_count"] >= 4
    assert payload["phase_state"]["approved_plan"] is True
