"""Unit tests for the non-blocking PostToolUse edit-tracking and staleness hook."""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

from scripts import hook_posttool_edit_validation as hook
from scripts import workflow_evidence as we


def test_run_posttool_request_tracks_changed_paths_and_marks_stale_without_validators_or_refresh(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Intermediate multi-file Python edits must track paths and mark stale with zero validators/refresh."""
    src_dir = tmp_path / "src"
    scripts_dir = tmp_path / "scripts"
    src_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    broken_a = src_dir / "module_a.py"
    broken_b = scripts_dir / "module_b.py"
    # Intentionally inconsistent / invalid Python to prove intermediate edits are never blocked.
    broken_a.write_text("from missing_symbol import broken\ndef f(:\n", encoding="utf-8")
    broken_b.write_text("import nonexistent_dep\n", encoding="utf-8")

    monkeypatch.setattr(hook, "ROOT", tmp_path)
    subprocess_calls: list[list[str]] = []

    def forbid_subprocess(command, **kwargs):
        """Fail if PostToolUse attempts to spawn any validator or refresh subprocess."""
        subprocess_calls.append(list(command))
        raise AssertionError(f"PostToolUse must not invoke subprocess: {command}")

    monkeypatch.setattr(subprocess, "run", forbid_subprocess)
    assert not hasattr(hook, "hook_refresh_indexes")

    payload = {"tool_input": {"paths": [str(broken_a), str(broken_b)]}}
    assert hook.run_posttool_request(payload) == []
    assert subprocess_calls == []
    assert we.load_changed_paths(tmp_path) == ["scripts/module_b.py", "src/module_a.py"]

    freshness = we.load_freshness_state(tmp_path)
    assert freshness.get_status("codegraph", "src") == "stale"
    assert freshness.get_status("codegraph", "scripts") == "stale"
    assert freshness.get_status("vector", "src") == "stale"
    assert freshness.get_status("vector", "scripts") == "stale"


def test_run_posttool_request_marks_non_python_docs_stale_without_validators_or_refresh(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Non-Python spec/doc edits should track paths and mark vector scope stale without refresh."""
    specs_dir = tmp_path / "specs" / "060-demo"
    specs_dir.mkdir(parents=True, exist_ok=True)
    doc = specs_dir / "spec.md"
    doc.write_text("# Spec\n", encoding="utf-8")

    monkeypatch.setattr(hook, "ROOT", tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: (_ for _ in ()).throw(AssertionError(f"Unexpected subprocess: {command}")),
    )

    payload = {"tool_input": {"file_path": str(doc)}}
    assert hook.run_posttool_request(payload) == []
    assert we.load_changed_paths(tmp_path) == ["specs/060-demo/spec.md"]

    freshness = we.load_freshness_state(tmp_path)
    assert freshness.get_status("vector", "specs") == "stale"
    assert freshness.get_status("codegraph", "specs") == "current"


def test_run_posttool_request_ignores_paths_outside_repo(monkeypatch, tmp_path: Path) -> None:
    """Paths outside the repository root should be ignored safely without mutating state."""
    monkeypatch.setattr(hook, "ROOT", tmp_path)
    payload = {"tool_input": {"file_path": "/tmp/outside-repo-file.py"}}

    assert hook.run_posttool_request(payload) == []
    assert we.load_changed_paths(tmp_path) == []


def test_main_emits_failures_and_exits_non_zero(monkeypatch, capsys) -> None:
    """CLI mode should surface hook failures on stderr."""
    monkeypatch.setattr(hook, "run_posttool_request", lambda payload: ["tracking failed: disk error"])
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO('{"tool_input":{"file_path":"scripts/sample.py"}}'))

    assert hook.main() == 1
    captured = capsys.readouterr()
    assert "ERROR: tracking failed: disk error" in captured.err


def test_settings_route_edit_hooks_through_unified_script() -> None:
    """Codex settings should use the unified post-edit hook entrypoint."""
    settings = Path(".claude/settings.json").read_text(encoding="utf-8")

    assert '"command": "python3 scripts/hook_posttool_edit_validation.py"' in settings


def test_repo_local_codex_hooks_register_guard_entrypoints() -> None:
    """Repo-local Codex hooks should own session, pre-tool, and post-tool registration."""
    hooks = Path(".codex/hooks.json").read_text(encoding="utf-8")

    assert '"SessionStart"' in hooks
    assert '"matcher": "startup|resume"' in hooks
    assert '"PreToolUse"' in hooks
    assert '"matcher": "Bash"' in hooks
    assert '"command": "python3 /Users/andreborczuk/app-foundation/scripts/hook_pretool_dispatch.py"' in hooks
    assert '"PostToolUse"' in hooks
    assert '"matcher": "Edit|Write|MultiEdit|apply_patch"' in hooks
    assert '"command": "python3 /Users/andreborczuk/app-foundation/scripts/hook_posttool_edit_validation.py"' in hooks
