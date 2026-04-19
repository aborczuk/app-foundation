"""Parity contracts for migrated SpecKit shell wrappers and Python entrypoints."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
FEATURE_NAME = "022-codegraph-hardening"
FEATURE_DIR = Path("specs") / FEATURE_NAME

SHELL_ENV = {"PATH": "/usr/bin:/bin"}


def _copy_tree(src: Path, dest: Path) -> None:
    shutil.copytree(src, dest)


def _bootstrap_workspace(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)

    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "-b", FEATURE_NAME], cwd=repo_root, check=True, capture_output=True, text=True)

    (repo_root / ".specify").mkdir(parents=True, exist_ok=True)
    _copy_tree(REPO_ROOT / ".specify" / "scripts", repo_root / ".specify" / "scripts")
    _copy_tree(REPO_ROOT / ".specify" / "templates", repo_root / ".specify" / "templates")
    _copy_tree(REPO_ROOT / "scripts", repo_root / "scripts")

    feature_dir = repo_root / FEATURE_DIR
    (feature_dir / "contracts").mkdir(parents=True, exist_ok=True)
    (feature_dir / "research.md").write_text("# Research\n", encoding="utf-8")
    (feature_dir / "data-model.md").write_text("# Data Model\n", encoding="utf-8")
    (feature_dir / "quickstart.md").write_text("# Quickstart\n", encoding="utf-8")
    (feature_dir / "tasks.md").write_text("- [ ] T001 Smoke task\n", encoding="utf-8")
    (feature_dir / "contracts" / "contract.md").write_text("# Contract\n", encoding="utf-8")

    return repo_root


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _bootstrap_create_feature_workspace(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)

    _git(repo_root, "init")
    _git(repo_root, "checkout", "-b", "main")
    _git(repo_root, "config", "user.name", "Specify Test User")
    _git(repo_root, "config", "user.email", "specify@example.com")

    (repo_root / ".specify").mkdir(parents=True, exist_ok=True)
    _copy_tree(REPO_ROOT / ".specify" / "scripts", repo_root / ".specify" / "scripts")
    _copy_tree(REPO_ROOT / ".specify" / "templates", repo_root / ".specify" / "templates")
    _copy_tree(REPO_ROOT / "scripts", repo_root / "scripts")
    (repo_root / "README.md").write_text("# Temp workspace\n", encoding="utf-8")
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "bootstrap workspace")
    return repo_root


def _attach_origin_main(repo_root: Path, remote_root: Path) -> None:
    remote_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare"], cwd=remote_root, check=True, capture_output=True, text=True)
    _git(repo_root, "remote", "add", "origin", str(remote_root))
    _git(repo_root, "push", "-u", "origin", "main")


def _run_shell(repo_root: Path, script_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script_path), *args],
        cwd=repo_root,
        env={**os.environ, **SHELL_ENV},
        check=False,
        capture_output=True,
        text=True,
    )


def _run_python(repo_root: Path, script_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script_path), *args],
        cwd=repo_root,
        env={**os.environ, **SHELL_ENV},
        check=False,
        capture_output=True,
        text=True,
    )


def _run_shell_source(repo_root: Path, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", command],
        cwd=repo_root,
        env={**os.environ, **SHELL_ENV},
        check=False,
        capture_output=True,
        text=True,
    )


def _normalize_text(text: str, repo_root: Path) -> str:
    return text.replace(str(repo_root), "<REPO_ROOT>")


def _normalize_value(value: object, repo_root: Path) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_value(item, repo_root) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item, repo_root) for item in value]
    if isinstance(value, str):
        return value.replace(str(repo_root), "<REPO_ROOT>")
    return value


def _assert_parity(
    shell_result: subprocess.CompletedProcess[str],
    shell_repo: Path,
    python_result: subprocess.CompletedProcess[str],
    python_repo: Path,
) -> None:
    assert shell_result.returncode == python_result.returncode, (
        f"exit code mismatch\nshell={shell_result.returncode}\npython={python_result.returncode}\n"
        f"shell stderr={shell_result.stderr}\npython stderr={python_result.stderr}"
    )
    assert _normalize_text(shell_result.stdout, shell_repo) == _normalize_text(python_result.stdout, python_repo), (
        f"stdout mismatch\nshell={shell_result.stdout}\npython={python_result.stdout}"
    )
    assert _normalize_text(shell_result.stderr, shell_repo) == _normalize_text(python_result.stderr, python_repo), (
        f"stderr mismatch\nshell={shell_result.stderr}\npython={python_result.stderr}"
    )


def test_check_prerequisites_json_parity(tmp_path: Path) -> None:
    shell_repo = _bootstrap_workspace(tmp_path / "shell")
    python_repo = _bootstrap_workspace(tmp_path / "python")

    for repo_root in (shell_repo, python_repo):
        (repo_root / FEATURE_DIR / "plan.md").write_text("# Plan\n", encoding="utf-8")

    shell_result = _run_shell(
        shell_repo,
        shell_repo / ".specify" / "scripts" / "bash" / "check-prerequisites.sh",
        "--json",
        "--require-tasks",
        "--include-tasks",
    )
    python_result = _run_python(
        python_repo,
        python_repo / ".specify" / "scripts" / "python" / "check_prerequisites.py",
        "--json",
        "--require-tasks",
        "--include-tasks",
    )

    _assert_parity(shell_result, shell_repo, python_result, python_repo)
    assert shell_result.returncode == 0

    shell_payload = _normalize_value(json.loads(shell_result.stdout), shell_repo)
    python_payload = _normalize_value(json.loads(python_result.stdout), python_repo)
    assert shell_payload == python_payload
    assert shell_payload["FEATURE_DIR"] == "<REPO_ROOT>/specs/022-codegraph-hardening"
    assert shell_payload["AVAILABLE_DOCS"] == [
        "research.md",
        "data-model.md",
        "contracts/",
        "quickstart.md",
        "tasks.md",
    ]


def test_check_prerequisites_missing_plan_parity(tmp_path: Path) -> None:
    shell_repo = _bootstrap_workspace(tmp_path / "shell")
    python_repo = _bootstrap_workspace(tmp_path / "python")

    shell_result = _run_shell(
        shell_repo,
        shell_repo / ".specify" / "scripts" / "bash" / "check-prerequisites.sh",
        "--json",
        "--require-tasks",
    )
    python_result = _run_python(
        python_repo,
        python_repo / ".specify" / "scripts" / "python" / "check_prerequisites.py",
        "--json",
        "--require-tasks",
    )

    _assert_parity(shell_result, shell_repo, python_result, python_repo)
    assert shell_result.returncode == 1
    assert "plan.md not found" in _normalize_text(shell_result.stderr, shell_repo)


def test_check_prerequisites_missing_tasks_parity(tmp_path: Path) -> None:
    shell_repo = _bootstrap_workspace(tmp_path / "shell")
    python_repo = _bootstrap_workspace(tmp_path / "python")

    for repo_root in (shell_repo, python_repo):
        (repo_root / FEATURE_DIR / "plan.md").write_text("# Plan\n", encoding="utf-8")
        (repo_root / FEATURE_DIR / "tasks.md").unlink()

    shell_result = _run_shell(
        shell_repo,
        shell_repo / ".specify" / "scripts" / "bash" / "check-prerequisites.sh",
        "--json",
        "--require-tasks",
    )
    python_result = _run_python(
        python_repo,
        python_repo / ".specify" / "scripts" / "python" / "check_prerequisites.py",
        "--json",
        "--require-tasks",
    )

    _assert_parity(shell_result, shell_repo, python_result, python_repo)
    assert shell_result.returncode == 1
    assert "tasks.md not found" in _normalize_text(shell_result.stderr, shell_repo)


def test_setup_plan_parity(tmp_path: Path) -> None:
    shell_repo = _bootstrap_workspace(tmp_path / "shell")
    python_repo = _bootstrap_workspace(tmp_path / "python")

    shell_result = _run_shell(
        shell_repo,
        shell_repo / ".specify" / "scripts" / "bash" / "setup-plan.sh",
        "--json",
    )
    python_result = _run_python(
        python_repo,
        python_repo / ".specify" / "scripts" / "python" / "setup_plan.py",
        "--json",
    )

    _assert_parity(shell_result, shell_repo, python_result, python_repo)
    assert shell_result.returncode == 0
    assert (shell_repo / FEATURE_DIR / "plan.md").read_text(encoding="utf-8") == (
        python_repo / FEATURE_DIR / "plan.md"
    ).read_text(encoding="utf-8")


def test_setup_plan_branch_validation_parity(tmp_path: Path) -> None:
    shell_repo = _bootstrap_workspace(tmp_path / "shell")
    python_repo = _bootstrap_workspace(tmp_path / "python")

    shell_env = {**os.environ, **SHELL_ENV, "SPECIFY_FEATURE": "main"}
    python_env = {**os.environ, **SHELL_ENV, "SPECIFY_FEATURE": "main"}

    shell_result = subprocess.run(
        ["bash", str(shell_repo / ".specify" / "scripts" / "bash" / "setup-plan.sh"), "--json"],
        cwd=shell_repo,
        env=shell_env,
        check=False,
        capture_output=True,
        text=True,
    )
    python_result = subprocess.run(
        [sys.executable, str(python_repo / ".specify" / "scripts" / "python" / "setup_plan.py"), "--json"],
        cwd=python_repo,
        env=python_env,
        check=False,
        capture_output=True,
        text=True,
    )

    _assert_parity(shell_result, shell_repo, python_result, python_repo)
    assert shell_result.returncode == 1
    assert "feature" in _normalize_text(shell_result.stderr, shell_repo).lower()


def test_create_new_feature_blocks_dirty_main_parity(tmp_path: Path) -> None:
    shell_repo = _bootstrap_create_feature_workspace(tmp_path / "shell")
    python_repo = _bootstrap_create_feature_workspace(tmp_path / "python")

    for repo_root in (shell_repo, python_repo):
        (repo_root / "LOCAL_DIRTY.md").write_text("dirty main change\n", encoding="utf-8")

    shell_result = _run_shell(
        shell_repo,
        shell_repo / ".specify" / "scripts" / "bash" / "create-new-feature.sh",
        "--json",
        "--short-name",
        "bootstrap-parity",
        "--base",
        "main",
        "Enforce clean main preflight",
    )
    python_result = _run_python(
        python_repo,
        python_repo / ".specify" / "scripts" / "python" / "create_new_feature.py",
        "--json",
        "--short-name",
        "bootstrap-parity",
        "--base",
        "main",
        "Enforce clean main preflight",
    )

    _assert_parity(shell_result, shell_repo, python_result, python_repo)
    assert shell_result.returncode == 1
    assert "Local 'main' has uncommitted changes." in _normalize_text(shell_result.stderr, shell_repo)


def test_create_new_feature_blocks_dirty_non_main_before_switch_parity(tmp_path: Path) -> None:
    shell_repo = _bootstrap_create_feature_workspace(tmp_path / "shell")
    python_repo = _bootstrap_create_feature_workspace(tmp_path / "python")

    for repo_root in (shell_repo, python_repo):
        _git(repo_root, "checkout", "-b", "scratch")
        (repo_root / "SCRATCH_DIRTY.md").write_text("dirty feature branch change\n", encoding="utf-8")

    shell_result = _run_shell(
        shell_repo,
        shell_repo / ".specify" / "scripts" / "bash" / "create-new-feature.sh",
        "--json",
        "--short-name",
        "bootstrap-parity",
        "--base",
        "main",
        "Enforce branch-off-main preflight",
    )
    python_result = _run_python(
        python_repo,
        python_repo / ".specify" / "scripts" / "python" / "create_new_feature.py",
        "--json",
        "--short-name",
        "bootstrap-parity",
        "--base",
        "main",
        "Enforce branch-off-main preflight",
    )

    _assert_parity(shell_result, shell_repo, python_result, python_repo)
    assert shell_result.returncode == 1
    assert "with uncommitted changes." in _normalize_text(shell_result.stderr, shell_repo)
    assert "To branch off main" in _normalize_text(shell_result.stderr, shell_repo)


def test_create_new_feature_blocks_unpushed_main_parity(tmp_path: Path) -> None:
    shell_repo = _bootstrap_create_feature_workspace(tmp_path / "shell")
    python_repo = _bootstrap_create_feature_workspace(tmp_path / "python")

    _attach_origin_main(shell_repo, tmp_path / "shell-remote.git")
    _attach_origin_main(python_repo, tmp_path / "python-remote.git")

    for repo_root in (shell_repo, python_repo):
        (repo_root / "LOCAL_AHEAD.md").write_text("ahead commit\n", encoding="utf-8")
        _git(repo_root, "add", "LOCAL_AHEAD.md")
        _git(repo_root, "commit", "-m", "local ahead of origin/main")

    shell_result = _run_shell(
        shell_repo,
        shell_repo / ".specify" / "scripts" / "bash" / "create-new-feature.sh",
        "--json",
        "--short-name",
        "bootstrap-parity",
        "--base",
        "main",
        "Enforce pushed main preflight",
    )
    python_result = _run_python(
        python_repo,
        python_repo / ".specify" / "scripts" / "python" / "create_new_feature.py",
        "--json",
        "--short-name",
        "bootstrap-parity",
        "--base",
        "main",
        "Enforce pushed main preflight",
    )

    _assert_parity(shell_result, shell_repo, python_result, python_repo)
    assert shell_result.returncode == 1
    assert "not pushed to origin/main" in _normalize_text(shell_result.stderr, shell_repo)


def test_update_agent_context_parity(tmp_path: Path) -> None:
    shell_repo = _bootstrap_workspace(tmp_path / "shell")
    python_repo = _bootstrap_workspace(tmp_path / "python")

    plan_text = """# Plan

**Language/Version**: Python 3.12
**Primary Dependencies**: pytest
**Storage**: sqlite
**Project Type**: cli
"""
    for repo_root in (shell_repo, python_repo):
        (repo_root / FEATURE_DIR / "plan.md").write_text(plan_text, encoding="utf-8")

    shell_result = _run_shell(
        shell_repo,
        shell_repo / ".specify" / "scripts" / "bash" / "update-agent-context.sh",
        "claude",
    )
    python_result = _run_python(
        python_repo,
        python_repo / ".specify" / "scripts" / "python" / "update_agent_context.py",
        "claude",
    )

    _assert_parity(shell_result, shell_repo, python_result, python_repo)
    assert shell_result.returncode == 0
    assert (shell_repo / "CLAUDE.md").read_text(encoding="utf-8") == (python_repo / "CLAUDE.md").read_text(
        encoding="utf-8"
    )


def test_read_markdown_parity(tmp_path: Path) -> None:
    shell_repo = _bootstrap_workspace(tmp_path / "shell")
    python_repo = _bootstrap_workspace(tmp_path / "python")

    markdown_text = """# Notes

## Phase 9: Add-to-Backlog - Python Orchestration Migration

We compare prefix matching here.
"""
    for repo_root in (shell_repo, python_repo):
        (repo_root / "docs").mkdir(parents=True, exist_ok=True)
        (repo_root / "docs" / "notes.md").write_text(markdown_text, encoding="utf-8")

    shell_result = _run_shell(
        shell_repo,
        shell_repo / "scripts" / "read-markdown.sh",
        "docs/notes.md",
        "Phase 9",
    )
    python_result = _run_python(
        python_repo,
        python_repo / "scripts" / "read_markdown.py",
        "docs/notes.md",
        "Phase 9",
    )

    _assert_parity(shell_result, shell_repo, python_result, python_repo)
    assert shell_result.returncode == 0
    assert "Phase 9: Add-to-Backlog - Python Orchestration Migration" in _normalize_text(
        shell_result.stdout, shell_repo
    )


def test_read_code_parity(tmp_path: Path) -> None:
    shell_repo = _bootstrap_workspace(tmp_path / "shell")
    python_repo = _bootstrap_workspace(tmp_path / "python")

    code_text = """def sample_fn():
    return "ok"


def helper():
    return sample_fn()
"""
    for repo_root in (shell_repo, python_repo):
        (repo_root / "src").mkdir(parents=True, exist_ok=True)
        (repo_root / "src" / "sample.py").write_text(code_text, encoding="utf-8")

    shell_result = _run_shell(
        shell_repo,
        shell_repo / "scripts" / "read-code.sh",
        "context",
        "src/sample.py",
        "sample_fn",
        "2",
        "--allow-fallback",
    )
    python_result = _run_python(
        python_repo,
        python_repo / "scripts" / "read_code.py",
        "context",
        "src/sample.py",
        "sample_fn",
        "2",
        "--allow-fallback",
    )

    _assert_parity(shell_result, shell_repo, python_result, python_repo)
    assert shell_result.returncode == 0
    assert "sample_fn" in _normalize_text(shell_result.stdout, shell_repo)


def test_read_helper_missing_targets_parity(tmp_path: Path) -> None:
    shell_repo = _bootstrap_workspace(tmp_path / "shell")
    python_repo = _bootstrap_workspace(tmp_path / "python")

    for repo_root in (shell_repo, python_repo):
        (repo_root / "docs").mkdir(parents=True, exist_ok=True)
        (repo_root / "docs" / "notes.md").write_text("# Notes\n\n## Present\n", encoding="utf-8")
        (repo_root / "src").mkdir(parents=True, exist_ok=True)
        (repo_root / "src" / "sample.py").write_text("def present():\n    return 1\n", encoding="utf-8")

    markdown_shell = _run_shell(
        shell_repo,
        shell_repo / "scripts" / "read-markdown.sh",
        "docs/notes.md",
        "Missing Section",
    )
    markdown_python = _run_python(
        python_repo,
        python_repo / "scripts" / "read_markdown.py",
        "docs/notes.md",
        "Missing Section",
    )
    _assert_parity(markdown_shell, shell_repo, markdown_python, python_repo)
    assert markdown_shell.returncode == 1
    assert "Section '## Missing Section' not found" in _normalize_text(markdown_shell.stderr, shell_repo)

    code_shell = _run_shell(
        shell_repo,
        shell_repo / "scripts" / "read-code.sh",
        "context",
        "src/sample.py",
        "missing_symbol",
        "2",
        "--allow-fallback",
    )
    code_python = _run_python(
        python_repo,
        python_repo / "scripts" / "read_code.py",
        "context",
        "src/sample.py",
        "missing_symbol",
        "2",
        "--allow-fallback",
    )
    _assert_parity(code_shell, shell_repo, code_python, python_repo)
    assert code_shell.returncode == 1
    normalized_code_stderr = _normalize_text(code_shell.stderr, shell_repo)
    assert "uv is required for codegraph discovery" in normalized_code_stderr or "Strict symbol resolution failed" in normalized_code_stderr


def test_read_markdown_wrapper_source_compatibility(tmp_path: Path) -> None:
    repo_root = _bootstrap_workspace(tmp_path / "repo")
    (repo_root / "docs").mkdir(parents=True, exist_ok=True)
    (repo_root / "docs" / "notes.md").write_text(
        """# Notes

## Phase 9: Add-to-Backlog - Python Orchestration Migration

Wrapper source compatibility check.
""",
        encoding="utf-8",
    )

    result = _run_shell_source(
        repo_root,
        "source scripts/read-markdown.sh && read_markdown_section docs/notes.md 'Phase 9'",
    )

    assert result.returncode == 0, result.stderr
    assert "Phase 9: Add-to-Backlog - Python Orchestration Migration" in result.stdout


def test_read_code_wrapper_source_compatibility(tmp_path: Path) -> None:
    repo_root = _bootstrap_workspace(tmp_path / "repo")
    (repo_root / "src").mkdir(parents=True, exist_ok=True)
    (repo_root / "src" / "sample.py").write_text(
        """def sample_fn():
    return "ok"
""",
        encoding="utf-8",
    )

    result = _run_shell_source(
        repo_root,
        "source scripts/read-code.sh && read_code_context src/sample.py sample_fn 2 --allow-fallback",
    )

    assert result.returncode == 0, result.stderr
    assert "sample_fn" in result.stdout
