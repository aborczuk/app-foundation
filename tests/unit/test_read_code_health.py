"""Unit tests for deterministic content-based vector edit fingerprinting."""

from __future__ import annotations

import subprocess
from pathlib import Path

import scripts.read_code_health as read_code_health
import src.mcp_codebase.health as codebase_health


def _git(repo: Path, *args: str) -> None:
    """Run a git command inside a temporary repository."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"


def _init_temp_repo(tmp_path: Path) -> Path:
    """Create a minimal git repository with one tracked Python file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    src_file = repo / "app.py"
    src_file.write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_vector_fingerprint_stays_stable_across_edit_refresh_and_commit(tmp_path: Path) -> None:
    """Committing already-refreshed file content must not trigger false-positive staleness."""
    repo = _init_temp_repo(tmp_path)
    src_file = repo / "app.py"
    src_file.write_text("VALUE = 2\n", encoding="utf-8")

    sig_after_edit = read_code_health.codegraph_current_edit_signature(repo)
    read_code_health._persist_vector_edit_signature(sig_after_edit, repo)

    probe_before_commit = read_code_health.vector_index_probe(repo)
    assert probe_before_commit.status == "healthy"

    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "update value")

    sig_after_commit = read_code_health.codegraph_current_edit_signature(repo)
    assert sig_after_commit == sig_after_edit

    probe_after_commit = read_code_health.vector_index_probe(repo)
    assert probe_after_commit.status == "healthy"
    assert probe_after_commit.stale_drift_paths == ()


def test_vector_fingerprint_detects_real_post_refresh_edit(tmp_path: Path) -> None:
    """A genuine file edit after refresh must report bounded drift on the modified path."""
    repo = _init_temp_repo(tmp_path)
    sig_initial = read_code_health.codegraph_current_edit_signature(repo)
    read_code_health._persist_vector_edit_signature(sig_initial, repo)

    (repo / "app.py").write_text("VALUE = 99\n", encoding="utf-8")
    probe = read_code_health.vector_index_probe(repo)

    assert probe.status == "stale"
    assert "app.py" in probe.stale_drift_paths


def test_vector_fingerprint_ignores_runtime_noise_directories(tmp_path: Path) -> None:
    """Edits inside ignored runtime directories must not alter the edit fingerprint."""
    repo = _init_temp_repo(tmp_path)
    sig_before = read_code_health.codegraph_current_edit_signature(repo)

    for rel in (
        ".speckit/runtime.log",
        ".codegraphcontext/cache.json",
        "logs/debug.txt",
        "shadow-runs/run.json",
    ):
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("noise\n", encoding="utf-8")

    sig_after = read_code_health.codegraph_current_edit_signature(repo)
    assert sig_after == sig_before


def test_mcp_codebase_health_edit_drift_matches_commit_invariant(tmp_path: Path) -> None:
    """src/mcp_codebase/health.py must also treat committed refreshed content as non-drifted."""
    repo = _init_temp_repo(tmp_path)
    (repo / "app.py").write_text("VALUE = 3\n", encoding="utf-8")

    sig_after_edit = codebase_health._current_edit_signature(repo)
    marker = repo / codebase_health._LAST_EDIT_SIGNATURE_FILE
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(sig_after_edit, encoding="utf-8")

    assert codebase_health._read_edit_drift(repo) is None

    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "commit refreshed edit")

    assert codebase_health._current_edit_signature(repo) == sig_after_edit
    assert codebase_health._read_edit_drift(repo) is None

    (repo / "app.py").write_text("VALUE = 4\n", encoding="utf-8")
    drift = codebase_health._read_edit_drift(repo)
    assert drift is not None
    assert drift[0] == codebase_health.GraphHealthStatus.STALE
