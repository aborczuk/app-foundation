"""Unit tests for consolidated edit_code validation, evidence reuse, and unskippable closeout."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import edit_code
from scripts import workflow_evidence as we


def _setup_fake_repo(tmp_path: Path, monkeypatch) -> Path:
    """Create a temporary repo layout and point edit_code.REPO_ROOT at it."""
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests" / "unit").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (tmp_path / "src" / "app.py").write_text('"""Demo."""\n\ndef add(a: int, b: int) -> int:\n    """Add."""\n    return a + b\n', encoding="utf-8")
    (tmp_path / "tests" / "unit" / "test_app.py").write_text('"""Test."""\n\ndef test_add() -> None:\n    """Test add."""\n    assert True\n', encoding="utf-8")
    monkeypatch.setattr(edit_code, "REPO_ROOT", tmp_path)
    edit_code._reset_runtime_caches()
    return tmp_path


def test_sync_parser_forbids_skip_ruff_and_skip_pyright() -> None:
    """Closeout sync MUST NOT expose --skip-ruff or --skip-pyright bypass flags."""
    parser = edit_code._build_parser()
    base = ["sync", "--paths", "src/app.py", "--tests", "tests/unit/test_app.py", "--commit-message", "msg"]
    with pytest.raises(SystemExit):
        parser.parse_args([*base, "--skip-ruff"])
    with pytest.raises(SystemExit):
        parser.parse_args([*base, "--skip-pyright"])


def test_validate_then_sync_runs_each_mandatory_validator_at_most_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Unchanged validated state must reuse evidence across validate and sync."""
    repo = _setup_fake_repo(tmp_path, monkeypatch)
    labels: list[str] = []

    def fake_run_command(command: list[str], *, label: str, stdin_payload: str | None = None) -> int:
        """Record invoked command labels and return success."""
        labels.append(label)
        return 0

    monkeypatch.setattr(edit_code, "_run_command", fake_run_command)
    monkeypatch.setattr(edit_code, "_dirty_paths", lambda paths=None: {"src/app.py"})
    monkeypatch.setattr(edit_code, "_has_staged_path_changes", lambda paths: True)
    monkeypatch.setattr(edit_code, "_run_git_with_retry", lambda cmd, *, label: 0)

    rc_val = edit_code._run_validate(
        ["src/app.py"],
        ["tests/unit/test_app.py"],
        skip_ruff=False,
        skip_pyright=False,
        changed_only=False,
    )
    assert rc_val == 0
    assert labels == ["pytest_guard", "ruff_check", "pyright", "docstrings"]

    # Sync on the exact same unchanged files must NOT re-run any mandatory validator.
    rc_sync = edit_code._run_sync(
        ["src/app.py"],
        ["tests/unit/test_app.py"],
        commit_message="feat: update app",
        no_push=True,
        changed_only=False,
    )
    assert rc_sync == 0
    assert labels.count("pytest_guard") == 1
    assert labels.count("ruff_check") == 1
    assert labels.count("pyright") == 1
    assert labels.count("docstrings") == 1
    assert we.has_valid_evidence(repo, validator_id="ruff", paths=["src/app.py"], selectors=["src/app.py"])


def test_content_config_and_selector_changes_invalidate_validation_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Changing content, config, lockfile, or test selector must force re-validation."""
    repo = _setup_fake_repo(tmp_path, monkeypatch)
    labels: list[str] = []

    monkeypatch.setattr(
        edit_code,
        "_run_command",
        lambda command, *, label, stdin_payload=None: labels.append(label) or 0,
    )

    assert edit_code._run_validate(
        ["src/app.py"],
        ["tests/unit/test_app.py"],
        skip_ruff=False,
        skip_pyright=False,
        changed_only=False,
    ) == 0
    assert len(labels) == 4

    # Change test selector -> pytest must re-run, ruff/pyright/docstrings stay cached.
    labels.clear()
    assert edit_code._run_validate(
        ["src/app.py"],
        ["tests/unit/test_other.py"],
        skip_ruff=False,
        skip_pyright=False,
        changed_only=False,
    ) == 0
    assert labels == ["pytest_guard"]

    # Change file content -> all 4 mandatory validators must re-run.
    (repo / "src" / "app.py").write_text('"""Demo."""\n\ndef add(a: int, b: int) -> int:\n    """Add."""\n    return a + b + 1\n', encoding="utf-8")
    labels.clear()
    assert edit_code._run_validate(
        ["src/app.py"],
        ["tests/unit/test_other.py"],
        skip_ruff=False,
        skip_pyright=False,
        changed_only=False,
    ) == 0
    assert labels == ["pytest_guard", "ruff_check", "pyright", "docstrings"]

    # Change pyproject.toml -> all 4 must re-run.
    (repo / "pyproject.toml").write_text("[tool.ruff]\nline-length = 120\n", encoding="utf-8")
    labels.clear()
    assert edit_code._run_validate(
        ["src/app.py"],
        ["tests/unit/test_other.py"],
        skip_ruff=False,
        skip_pyright=False,
        changed_only=False,
    ) == 0
    assert labels == ["pytest_guard", "ruff_check", "pyright", "docstrings"]


@pytest.mark.parametrize("failing_label", ["pytest_guard", "ruff_check", "pyright", "docstrings", "refresh_indexes"])
def test_sync_rejects_closeout_when_any_mandatory_check_or_refresh_fails(
    tmp_path: Path,
    monkeypatch,
    failing_label: str,
) -> None:
    """Closeout sync must fail closed and never commit when any validator or refresh fails."""
    repo = _setup_fake_repo(tmp_path, monkeypatch)
    we.mark_paths_stale(repo, ["src/app.py"])
    git_calls: list[list[str]] = []

    def fake_run_command(command: list[str], *, label: str, stdin_payload: str | None = None) -> int:
        """Fail on the parametrized check label."""
        return 1 if label == failing_label else 0

    monkeypatch.setattr(edit_code, "_run_command", fake_run_command)
    monkeypatch.setattr(edit_code, "_dirty_paths", lambda paths=None: {"src/app.py"})
    monkeypatch.setattr(edit_code, "_run_git_with_retry", lambda cmd, *, label: git_calls.append(cmd) or 0)

    rc = edit_code._run_sync(
        ["src/app.py"],
        ["tests/unit/test_app.py"],
        commit_message="feat: should not commit",
        no_push=True,
        changed_only=False,
    )
    assert rc == 1
    assert git_calls == []


def test_sync_refreshes_stale_discovery_and_emits_commit_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Sync must refresh stale scopes, mark them current, persist commit evidence, and clear changed paths."""
    repo = _setup_fake_repo(tmp_path, monkeypatch)
    we.record_changed_paths(repo, ["src/app.py"])
    we.mark_paths_stale(repo, ["src/app.py"])
    labels: list[str] = []

    monkeypatch.setattr(
        edit_code,
        "_run_command",
        lambda command, *, label, stdin_payload=None: labels.append(label) or 0,
    )
    monkeypatch.setattr(edit_code, "_dirty_paths", lambda paths=None: {"src/app.py"})
    monkeypatch.setattr(edit_code, "_has_staged_path_changes", lambda paths: True)
    monkeypatch.setattr(edit_code, "_run_git_with_retry", lambda cmd, *, label: 0)

    rc = edit_code._run_sync(
        ["src/app.py"],
        ["tests/unit/test_app.py"],
        commit_message="feat: clean sync",
        no_push=True,
        changed_only=False,
    )
    assert rc == 0
    assert "refresh_indexes" in labels
    assert we.has_valid_evidence(repo, validator_id="refresh", paths=["src/app.py"], selectors=["src/app.py"])
    assert we.load_freshness_state(repo).get_status("codegraph", "src") == "current"
    assert we.load_changed_paths(repo) == []
