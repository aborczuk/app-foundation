"""Unit tests for on-demand discovery freshness enforcement on authoritative reads."""

from __future__ import annotations

from pathlib import Path

from scripts import hook_refresh_indexes, read_code, read_code_health
from scripts import workflow_evidence as we


def _setup_repo(tmp_path: Path, monkeypatch) -> Path:
    """Create a minimal repo layout and bind read_code_health/hook_refresh_indexes to it."""
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    target = tmp_path / "src" / "service.py"
    target.write_text('"""Service."""\n\ndef run() -> int:\n    """Run."""\n    return 1\n', encoding="utf-8")
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code_health, "_is_repo_local_path", lambda path: True)
    monkeypatch.setattr(read_code_health, "_ensure_codegraph_session_available", lambda path: None)
    monkeypatch.setattr(read_code_health, "codegraph_current_edit_signature", lambda root=None: "sig-current")
    return tmp_path


def test_authoritative_read_refreshes_stale_scope_and_marks_current(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """An authoritative read hitting a stale scope must refresh once and mark it current."""
    repo = _setup_repo(tmp_path, monkeypatch)
    target = repo / "src" / "service.py"
    we.mark_paths_stale(repo, ["src/service.py"])

    refresh_calls: list[Path] = []
    monkeypatch.setattr(read_code_health, "_read_request_trusts_vector_cache", lambda *a, **kw: True)
    monkeypatch.setattr(
        read_code_health,
        "vector_refresh_by_state",
        lambda path, **kw: refresh_calls.append(path) or True,
    )

    assert read_code_health._refresh_indexes_for_read(target) is True
    assert len(refresh_calls) == 1
    freshness = we.load_freshness_state(repo)
    assert freshness.get_status("vector", "src") == "current"
    assert freshness.get_entry("vector", "src").edit_signature == "sig-current"


def test_repeated_authoritative_read_on_current_state_triggers_zero_refreshes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Repeated authoritative reads on clean current state must trigger zero duplicate refreshes."""
    repo = _setup_repo(tmp_path, monkeypatch)
    target = repo / "src" / "service.py"
    we.mark_scope_current(repo, backend="vector", scope="src", edit_signature="sig-current")
    we.mark_scope_current(repo, backend="codegraph", scope="src", edit_signature="sig-current")

    refresh_calls: list[Path] = []
    monkeypatch.setattr(read_code_health, "_read_request_trusts_vector_cache", lambda *a, **kw: True)
    monkeypatch.setattr(
        read_code_health,
        "vector_refresh_by_state",
        lambda path, **kw: refresh_calls.append(path) or True,
    )

    assert read_code_health._refresh_indexes_for_read(target) is True
    assert read_code_health._refresh_indexes_for_read(target) is True
    assert refresh_calls == []


def test_authoritative_read_fails_closed_with_stderr_when_stale_refresh_fails(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """When refreshing a stale scope fails, authoritative read must fail closed and mark unverifiable."""
    repo = _setup_repo(tmp_path, monkeypatch)
    target = repo / "src" / "service.py"
    we.mark_paths_stale(repo, ["src/service.py"])

    monkeypatch.setattr(read_code_health, "_read_request_trusts_vector_cache", lambda *a, **kw: True)
    monkeypatch.setattr(read_code_health, "vector_refresh_by_state", lambda path, **kw: False)
    monkeypatch.setattr(read_code_health, "_consume_vector_runtime_note", lambda: "vector refresh stderr detail")

    assert read_code_health._refresh_indexes_for_read(target) is False
    captured = capsys.readouterr()
    assert "vector refresh stderr detail" in captured.err
    freshness = we.load_freshness_state(repo)
    assert freshness.get_status("vector", "src") == "unverifiable"
    assert "vector refresh stderr detail" in freshness.get_entry("vector", "src").last_error


def test_window_read_never_triggers_index_refresh(tmp_path: Path, monkeypatch, capsys) -> None:
    """Direct read_code.py window reads must bypass index refresh even when scopes are stale."""
    target = tmp_path / "sample.py"
    target.write_text("line1\nline2\nline3\n", encoding="utf-8")

    monkeypatch.setattr(
        read_code,
        "_refresh_indexes_for_read",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("window read must not trigger index refresh")),
    )

    rc = read_code.read_code_window([str(target), "1", "2"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "line1" in captured.out
    assert "line2" in captured.out


def test_hook_refresh_indexes_updates_freshness_state_on_success_and_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """hook_refresh_indexes must mark scopes current on success and unverifiable on failure."""
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    target = tmp_path / "src" / "mod.py"
    target.write_text("X = 1\n", encoding="utf-8")
    we.mark_paths_stale(tmp_path, ["src/mod.py"])

    monkeypatch.setattr(hook_refresh_indexes, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(hook_refresh_indexes, "_collect_changed_paths", lambda payload: [target])
    monkeypatch.setattr(hook_refresh_indexes, "_refresh_codegraph", lambda paths: [])
    monkeypatch.setattr(hook_refresh_indexes, "_refresh_vector", lambda paths: [])
    monkeypatch.setattr(hook_refresh_indexes, "_record_refresh_side_effects", lambda **kw: None)

    failures = hook_refresh_indexes.run_refresh_request({"tool_input": {"paths": [str(target)]}})
    assert failures == []
    freshness = we.load_freshness_state(tmp_path)
    assert freshness.get_status("codegraph", "src") == "current"
    assert freshness.get_status("vector", "src") == "current"

    # Now simulate a codegraph refresh failure -> scope must become unverifiable.
    monkeypatch.setattr(hook_refresh_indexes, "_refresh_codegraph", lambda paths: ["cgc index failed: permission denied"])
    failures = hook_refresh_indexes.run_refresh_request({"tool_input": {"paths": [str(target)]}})
    assert failures == ["cgc index failed: permission denied"]
    failed = we.load_freshness_state(tmp_path)
    assert failed.get_status("codegraph", "src") == "unverifiable"
    assert "permission denied" in failed.get_entry("codegraph", "src").last_error


def test_broad_repo_root_read_refreshes_all_stale_vector_scopes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Broad context reads at REPO_ROOT must refresh stale vector scopes and mark them current."""
    repo = _setup_repo(tmp_path, monkeypatch)
    we.mark_paths_stale(repo, ["src/service.py"])
    refresh_calls: list[Path] = []

    monkeypatch.setattr(read_code_health, "_read_request_trusts_vector_cache", lambda *a, **kw: True)
    monkeypatch.setattr(
        read_code_health,
        "vector_refresh_by_state",
        lambda path, **kw: refresh_calls.append(path) or True,
    )

    assert read_code_health._refresh_indexes_for_read(repo) is True
    assert len(refresh_calls) == 1
    assert we.stale_scopes_for_backend(repo, "vector") == []


def test_ensure_codegraph_fresh_for_read_refreshes_stale_skips_clean_and_fails_closed(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """Codegraph freshness gate for find/analyze must refresh stale scopes, skip clean, and fail closed."""
    import subprocess

    repo = _setup_repo(tmp_path, monkeypatch)
    we.mark_paths_stale(repo, ["src/service.py"])
    calls: list[list[str]] = []

    def ok_run(cmd, **kwargs):
        """Simulate successful scoped cgc_safe_index.py run."""
        calls.append(list(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(read_code_health.subprocess, "run", ok_run)
    assert read_code_health.ensure_codegraph_fresh_for_read(repo) is True
    assert len(calls) == 1
    assert we.stale_scopes_for_backend(repo, "codegraph") == []

    # Second call on clean state triggers zero refreshes.
    assert read_code_health.ensure_codegraph_fresh_for_read(repo) is True
    assert len(calls) == 1

    # Simulate stale scope with failing refresh -> fail closed with stderr and unverifiable status.
    we.mark_paths_stale(repo, ["src/service.py"])

    def fail_run(cmd, **kwargs):
        """Simulate failing scoped cgc_safe_index.py run with stderr."""
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="cgc db locked")

    monkeypatch.setattr(read_code_health.subprocess, "run", fail_run)
    assert read_code_health.ensure_codegraph_fresh_for_read(repo) is False
    assert "cgc db locked" in capsys.readouterr().err
    assert we.load_freshness_state(repo).get_status("codegraph", "src") == "unverifiable"


def test_read_code_find_and_analyze_fail_closed_when_codegraph_freshness_fails(
    monkeypatch,
) -> None:
    """read_code_find and read_code_analyze must abort without invoking cgc if freshness fails."""
    monkeypatch.setattr(read_code, "codegraph_current_edit_signature", lambda: "sig-test")
    monkeypatch.setattr(read_code, "ensure_codegraph_fresh_for_read", lambda: False)
    monkeypatch.setattr(read_code, "_load_cached_search_entry", lambda *a, **kw: None)
    monkeypatch.setattr(
        read_code.subprocess,
        "run",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("cgc must not run on failed freshness")),
    )

    assert read_code.read_code_find(["name", "sample"]) == 1
    assert read_code.read_code_analyze(["callers", "sample"]) == 1
