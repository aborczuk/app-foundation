"""Unit tests for shared workflow evidence, freshness state, and repo-local tool env."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_workflow_evidence() -> Any:
    """Import scripts.workflow_evidence fresh for test assertions."""
    return importlib.import_module("scripts.workflow_evidence")


def _init_sample_repo(tmp_path: Path) -> Path:
    """Create a minimal repo layout with config and source files for evidence tests."""
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "specs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (tmp_path / "src" / "sample.py").write_text("def greet() -> str:\n    return 'hi'\n", encoding="utf-8")
    (tmp_path / "scripts" / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    return tmp_path


def test_record_changed_paths_persists_normalized_unique_paths_atomically(tmp_path: Path) -> None:
    """Changed-path tracking must normalize, deduplicate, and persist repo-local paths."""
    we = _load_workflow_evidence()
    repo = _init_sample_repo(tmp_path)

    recorded = we.record_changed_paths(
        repo,
        [repo / "src" / "sample.py", "src/sample.py", "scripts/helper.py"],
    )
    assert recorded == ["scripts/helper.py", "src/sample.py"]
    assert we.load_changed_paths(repo) == ["scripts/helper.py", "src/sample.py"]

    state_file = we.workflow_state_dir(repo) / "changed_paths.json"
    assert state_file.is_file()
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload["paths"] == ["scripts/helper.py", "src/sample.py"]

    we.clear_changed_paths(repo)
    assert we.load_changed_paths(repo) == []


def test_evidence_digest_invalidates_on_content_config_lockfile_python_and_selector_changes(
    tmp_path: Path,
) -> None:
    """Validation evidence digest must change whenever any binding input drifts."""
    we = _load_workflow_evidence()
    repo = _init_sample_repo(tmp_path)
    touched = ["src/sample.py"]
    selectors = ["tests/unit/test_sample.py"]

    baseline = we.compute_evidence_digest(
        repo,
        validator_id="pytest",
        paths=touched,
        selectors=selectors,
        python_minor="3.12",
    )
    same = we.compute_evidence_digest(
        repo,
        validator_id="pytest",
        paths=["src/sample.py"],
        selectors=["tests/unit/test_sample.py"],
        python_minor="3.12",
    )
    assert baseline == same

    # Different validator_id invalidates.
    assert (
        we.compute_evidence_digest(
            repo,
            validator_id="ruff",
            paths=touched,
            selectors=selectors,
            python_minor="3.12",
        )
        != baseline
    )

    # Different selector invalidates.
    assert (
        we.compute_evidence_digest(
            repo,
            validator_id="pytest",
            paths=touched,
            selectors=["tests/unit/test_other.py"],
            python_minor="3.12",
        )
        != baseline
    )

    # Different Python minor version invalidates.
    assert (
        we.compute_evidence_digest(
            repo,
            validator_id="pytest",
            paths=touched,
            selectors=selectors,
            python_minor="3.13",
        )
        != baseline
    )

    # Content change invalidates.
    (repo / "src" / "sample.py").write_text("def greet() -> str:\n    return 'bye'\n", encoding="utf-8")
    after_content = we.compute_evidence_digest(
        repo,
        validator_id="pytest",
        paths=touched,
        selectors=selectors,
        python_minor="3.12",
    )
    assert after_content != baseline

    # Config change invalidates.
    (repo / "pyproject.toml").write_text("[tool.ruff]\nline-length = 120\n", encoding="utf-8")
    after_config = we.compute_evidence_digest(
        repo,
        validator_id="pytest",
        paths=touched,
        selectors=selectors,
        python_minor="3.12",
    )
    assert after_config != after_content

    # Lockfile change invalidates.
    (repo / "uv.lock").write_text("version = 2\n", encoding="utf-8")
    after_lock = we.compute_evidence_digest(
        repo,
        validator_id="pytest",
        paths=touched,
        selectors=selectors,
        python_minor="3.12",
    )
    assert after_lock != after_config


def test_validation_evidence_record_and_verify_roundtrip(tmp_path: Path) -> None:
    """Persisted validation evidence must verify on unchanged state and fail after edits."""
    we = _load_workflow_evidence()
    repo = _init_sample_repo(tmp_path)
    touched = ["src/sample.py"]

    record = we.record_validation_evidence(
        repo,
        validator_id="ruff",
        paths=touched,
        selectors=touched,
    )
    assert record.validator_id == "ruff"
    assert we.has_valid_evidence(repo, validator_id="ruff", paths=touched, selectors=touched) is True

    # Editing the file invalidates the stored evidence.
    (repo / "src" / "sample.py").write_text("x = 2\n", encoding="utf-8")
    assert we.has_valid_evidence(repo, validator_id="ruff", paths=touched, selectors=touched) is False


def test_freshness_state_transitions_per_backend_and_scope(tmp_path: Path) -> None:
    """Freshness tracking must support stale, current, and unverifiable per backend and scope."""
    we = _load_workflow_evidence()
    repo = _init_sample_repo(tmp_path)

    we.mark_paths_stale(repo, ["src/sample.py", "specs/060/spec.md"])
    state = we.load_freshness_state(repo)
    assert state.get_status("codegraph", "src") == "stale"
    assert state.get_status("vector", "src") == "stale"
    assert state.get_status("vector", "specs") == "stale"
    assert we.stale_scopes_for_backend(repo, "codegraph") == ["src"]

    we.mark_scope_current(repo, backend="codegraph", scope="src", edit_signature="sig-1")
    updated = we.load_freshness_state(repo)
    assert updated.get_status("codegraph", "src") == "current"
    assert updated.get_entry("codegraph", "src").edit_signature == "sig-1"
    assert we.stale_scopes_for_backend(repo, "codegraph") == []

    we.mark_scope_unverifiable(repo, backend="vector", scope="src", error="index lock timeout")
    failed = we.load_freshness_state(repo)
    assert failed.get_status("vector", "src") == "unverifiable"
    assert "index lock timeout" in failed.get_entry("vector", "src").last_error


def test_repo_local_tool_env_isolates_home_and_xdg_inside_repo(tmp_path: Path) -> None:
    """repo_local_tool_env must route HOME, XDG_*, UV, Semble, and CGC into repo .codegraphcontext."""
    we = _load_workflow_evidence()
    repo = _init_sample_repo(tmp_path)
    base_env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/Users/outside-user",
        "XDG_CONFIG_HOME": "/Users/outside-user/.config",
        "XDG_CACHE_HOME": "/Users/outside-user/.cache",
        "XDG_DATA_HOME": "/Users/outside-user/.local/share",
    }

    isolated = we.repo_local_tool_env(repo, base_env=base_env)
    cgc_root = (repo / ".codegraphcontext").resolve()

    for key in (
        "HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "CODEGRAPH_CONTEXT_DIR",
        "CODEGRAPH_DB_DIR",
        "KUZUDB_PATH",
        "FALKORDB_PATH",
        "FALKORDB_SOCKET_PATH",
        "UV_CACHE_DIR",
        "SEMBLE_CACHE_LOCATION",
    ):
        value = Path(isolated[key]).resolve()
        assert str(value).startswith(str(cgc_root)), f"{key}={value} escaped {cgc_root}"
        assert "/Users/outside-user" not in str(value)

    assert Path(isolated["HOME"]).is_dir()
    assert Path(isolated["XDG_CONFIG_HOME"]).is_dir()
    assert Path(isolated["XDG_CACHE_HOME"]).is_dir()
    assert Path(isolated["XDG_DATA_HOME"]).is_dir()


def test_corrupt_state_files_fail_closed_without_crashing(tmp_path: Path) -> None:
    """Corrupt JSON evidence files must be treated as missing/unverifiable rather than valid."""
    we = _load_workflow_evidence()
    repo = _init_sample_repo(tmp_path)
    state_dir = we.workflow_state_dir(repo)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "evidence.json").write_text("{corrupt json", encoding="utf-8")

    assert (
        we.has_valid_evidence(repo, validator_id="ruff", paths=["src/sample.py"], selectors=["src/sample.py"])
        is False
    )


def test_deleted_file_is_hashed_deterministically(tmp_path: Path) -> None:
    """Deleted paths in a change set must produce a stable digest without raising FileNotFoundError."""
    we = _load_workflow_evidence()
    repo = _init_sample_repo(tmp_path)
    missing = ["src/deleted_file.py"]

    d1 = we.compute_evidence_digest(repo, validator_id="ruff", paths=missing, selectors=missing)
    d2 = we.compute_evidence_digest(repo, validator_id="ruff", paths=missing, selectors=missing)
    assert d1 == d2
    assert isinstance(d1, str) and len(d1) == 64


@pytest.mark.parametrize("bad_path", ["../outside.py", "/tmp/outside.py"])
def test_record_changed_paths_ignores_paths_outside_repo(tmp_path: Path, bad_path: str) -> None:
    """Paths outside the repository root must be ignored by changed-path tracking."""
    we = _load_workflow_evidence()
    repo = _init_sample_repo(tmp_path)

    recorded = we.record_changed_paths(repo, [bad_path, "src/sample.py"])
    assert recorded == ["src/sample.py"]
