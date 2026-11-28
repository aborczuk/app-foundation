"""Unit tests for evidence-aware Git pre-commit and post-commit fallback safeguards."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts import git_post_commit_refresh, git_pre_commit_lint
from scripts import workflow_evidence as we


def _setup_repo(tmp_path: Path, monkeypatch) -> Path:
    """Create a minimal repo layout and point git hook scripts at it."""
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    target = tmp_path / "src" / "demo.py"
    target.write_text('"""Demo."""\n\nX = 1\n', encoding="utf-8")
    monkeypatch.setattr(git_pre_commit_lint, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(git_post_commit_refresh, "REPO_ROOT", tmp_path)
    return tmp_path


def test_pre_commit_skips_ruff_only_when_exact_evidence_matches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Pre-commit lint must skip ruff on exact matching evidence and run it otherwise."""
    repo = _setup_repo(tmp_path, monkeypatch)
    target = repo / "src" / "demo.py"
    monkeypatch.setattr(git_pre_commit_lint, "_staged_paths", lambda: [target])

    ruff_calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        """Record ruff_guard invocations."""
        ruff_calls.append(list(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(git_pre_commit_lint.subprocess, "run", fake_run)

    # 1. Direct commit without evidence -> runs ruff_guard.
    assert git_pre_commit_lint.run_pre_commit_lint() == 0
    assert len(ruff_calls) == 1

    # 2. Exact matching governed evidence -> skips duplicate ruff_guard.
    we.record_validation_evidence(repo, validator_id="ruff", paths=["src/demo.py"], selectors=["src/demo.py"])
    assert git_pre_commit_lint.run_pre_commit_lint() == 0
    assert len(ruff_calls) == 1

    # 3. File modified after evidence -> mismatched evidence forces ruff_guard to run.
    target.write_text('"""Demo."""\n\nX = 2\n', encoding="utf-8")
    assert git_pre_commit_lint.run_pre_commit_lint() == 0
    assert len(ruff_calls) == 2

    # 4. Corrupt evidence file -> fails closed and runs ruff_guard.
    evidence_file = we.workflow_state_dir(repo) / "evidence.json"
    evidence_file.write_text("{not-json", encoding="utf-8")
    assert git_pre_commit_lint.run_pre_commit_lint() == 0
    assert len(ruff_calls) == 3


def test_post_commit_skips_refresh_only_when_exact_evidence_matches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Post-commit refresh must skip hook_refresh_indexes only on exact verified evidence."""
    repo = _setup_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(git_post_commit_refresh, "_changed_paths_for_head", lambda: ["src/demo.py"])

    refresh_calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        """Record hook_refresh_indexes invocations."""
        refresh_calls.append(list(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(git_post_commit_refresh.subprocess, "run", fake_run)

    # 1. Direct commit without evidence -> runs refresh.
    assert git_post_commit_refresh.main() == 0
    assert len(refresh_calls) == 1

    # 2. Exact matching refresh evidence -> skips duplicate refresh.
    we.record_validation_evidence(repo, validator_id="refresh", paths=["src/demo.py"], selectors=["src/demo.py"])
    assert git_post_commit_refresh.main() == 0
    assert len(refresh_calls) == 1

    # 3. Content changed after evidence -> runs refresh.
    (repo / "src" / "demo.py").write_text('"""Demo."""\n\nX = 99\n', encoding="utf-8")
    assert git_post_commit_refresh.main() == 0
    assert len(refresh_calls) == 2
