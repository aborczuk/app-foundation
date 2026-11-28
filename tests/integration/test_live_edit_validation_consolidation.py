"""Live-backend integration tests for consolidated edit validation, freshness, and isolation."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from scripts import edit_code, git_pre_commit_lint, hook_posttool_edit_validation, read_code_health
from scripts import workflow_evidence as we

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command inside an isolated temporary repository."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_live_inconsistent_multi_file_edit_edit_code_evidence_and_git_hook_fallback(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """Live E2E: inconsistent edits -> restore -> edit_code evidence reuse -> git hook fallback."""
    assert _run_git(tmp_path, "init").returncode == 0
    assert _run_git(tmp_path, "config", "user.email", "test@example.com").returncode == 0
    assert _run_git(tmp_path, "config", "user.name", "Test User").returncode == 0

    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")

    # Symlink repo scripts and .venv so edit_code and git_pre_commit_lint run real repo guards.
    (tmp_path / "scripts").symlink_to(REPO_ROOT / "scripts", target_is_directory=True)
    if (REPO_ROOT / ".venv").is_dir():
        (tmp_path / ".venv").symlink_to(REPO_ROOT / ".venv", target_is_directory=True)

    alpha = tmp_path / "src" / "alpha.py"
    beta = tmp_path / "src" / "beta.py"
    test_file = tmp_path / "tests" / "test_alpha.py"

    # 1. Temporarily inconsistent multi-file intermediate edit: zero validator failures.
    alpha.write_text('"""Alpha."""\n\nfrom beta import compute\n\ndef run() -> int:\n    """Run."""\n    return compute(2)\n', encoding="utf-8")
    beta.write_text("def broken(:\n", encoding="utf-8")

    monkeypatch.setattr(hook_posttool_edit_validation, "ROOT", tmp_path)
    assert (
        hook_posttool_edit_validation.run_posttool_request(
            {"tool_input": {"paths": [str(alpha), str(beta)]}}
        )
        == []
    )
    assert we.load_changed_paths(tmp_path) == ["src/alpha.py", "src/beta.py"]
    assert we.load_freshness_state(tmp_path).get_status("codegraph", "src") == "stale"

    # 2. Direct commit without evidence on broken file -> pre-commit fallback runs real ruff and rejects.
    assert _run_git(tmp_path, "add", "src/alpha.py", "src/beta.py").returncode == 0
    monkeypatch.setattr(git_pre_commit_lint, "REPO_ROOT", tmp_path)
    assert git_pre_commit_lint.run_pre_commit_lint() != 0

    # 3. Restore consistency and run real edit_code._run_validate twice -> second run reuses evidence.
    alpha.write_text(
        '"""Alpha."""\n\nfrom __future__ import annotations\n\n\ndef run(value: int) -> int:\n    """Return value."""\n    return value\n',
        encoding="utf-8",
    )
    beta.write_text(
        '"""Beta."""\n\nfrom __future__ import annotations\n\n\ndef compute(x: int) -> int:\n    """Double x."""\n    return x * 2\n',
        encoding="utf-8",
    )
    test_file.write_text(
        '"""Alpha test."""\n\n\ndef test_smoke() -> None:\n    """Pass smoke check."""\n    assert True\n',
        encoding="utf-8",
    )
    assert _run_git(tmp_path, "add", "src/alpha.py", "src/beta.py", "tests/test_alpha.py").returncode == 0

    monkeypatch.setattr(edit_code, "REPO_ROOT", tmp_path)
    edit_code._reset_runtime_caches()
    invoked: list[str] = []
    real_run_command = edit_code._run_command

    def tracking_run_command(command: list[str], *, label: str, stdin_payload: str | None = None) -> int:
        """Record real validator executions through edit_code."""
        invoked.append(label)
        return real_run_command(command, label=label, stdin_payload=stdin_payload)

    monkeypatch.setattr(edit_code, "_run_command", tracking_run_command)

    rc1 = edit_code._run_validate(
        ["src/alpha.py", "src/beta.py", "tests/test_alpha.py"],
        [str(test_file)],
        skip_ruff=False,
        skip_pyright=False,
        changed_only=False,
    )
    assert rc1 == 0
    assert invoked == ["pytest_guard", "ruff_check", "pyright", "docstrings"]

    # Second validate on unchanged state must skip every mandatory validator.
    invoked.clear()
    rc2 = edit_code._run_validate(
        ["src/alpha.py", "src/beta.py", "tests/test_alpha.py"],
        [str(test_file)],
        skip_ruff=False,
        skip_pyright=False,
        changed_only=False,
    )
    assert rc2 == 0
    assert invoked == []

    # 4. Pre-commit with exact matching evidence from edit_code skips duplicate ruff.
    capsys.readouterr()
    assert git_pre_commit_lint.run_pre_commit_lint() == 0
    assert "skipping duplicate lint" in capsys.readouterr().out

    # 5. Mutate staged file with a lint error -> mismatched evidence triggers real ruff fallback failure.
    beta.write_text("import unused_mod\n", encoding="utf-8")
    assert _run_git(tmp_path, "add", "src/beta.py").returncode == 0
    assert git_pre_commit_lint.run_pre_commit_lint() != 0


def test_live_on_demand_codegraph_freshness_and_clean_repeat_read() -> None:
    """Live on-demand freshness: stale codegraph scope refreshes once, clean repeat triggers zero refreshes."""
    we.mark_paths_stale(REPO_ROOT, ["scripts/workflow_evidence.py"])
    assert "scripts" in we.stale_scopes_for_backend(REPO_ROOT, "codegraph")

    # First authoritative freshness check runs real cgc_safe_index.py for stale 'scripts' scope.
    assert read_code_health.ensure_codegraph_fresh_for_read(REPO_ROOT) is True
    assert "scripts" not in we.stale_scopes_for_backend(REPO_ROOT, "codegraph")

    # Clean repeat triggers zero refreshes.
    assert read_code_health.ensure_codegraph_fresh_for_read(REPO_ROOT) is True


def test_live_bootstrap_session_healthy_skip_and_restricted_home_isolation(tmp_path: Path) -> None:
    """Live bootstrap_session must succeed under a read-only HOME with zero ~/.codegraphcontext writes."""
    restricted_home = tmp_path / "readonly-home"
    restricted_home.mkdir(parents=True, exist_ok=True)
    restricted_home.chmod(stat.S_IRUSR | stat.S_IXUSR)

    env = os.environ.copy()
    env["HOME"] = str(restricted_home)
    env["XDG_CONFIG_HOME"] = str(restricted_home / ".config")
    env["XDG_CACHE_HOME"] = str(restricted_home / ".cache")
    env["XDG_DATA_HOME"] = str(restricted_home / ".local" / "share")

    try:
        proc1 = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "bootstrap_session.py"), "--json"],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc1.returncode == 0, proc1.stderr or proc1.stdout
        payload1 = json.loads(proc1.stdout.strip().splitlines()[-1])
        assert payload1["bootstrap_ok"] is True
        assert payload1["failed_scopes"] == []
        assert not (restricted_home / ".codegraphcontext").exists()

        # Second invocation on healthy snapshot must skip all scope indexing.
        proc2 = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "bootstrap_session.py"), "--json"],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc2.returncode == 0, proc2.stderr or proc2.stdout
        payload2 = json.loads(proc2.stdout.strip().splitlines()[-1])
        assert payload2["bootstrap_ok"] is True
        assert payload2["warmed_scopes"] == []
        assert payload2["codegraph_before"] == "healthy"
    finally:
        restricted_home.chmod(stat.S_IRWXU)
