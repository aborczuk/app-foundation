"""Integration tests for check-prerequisites shell-wrapper/Python parity contract."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".specify"
    / "scripts"
    / "bash"
    / "check-prerequisites.sh"
)


def _run_check_prereq(repo_dir: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT_PATH), *args],
        cwd=repo_dir,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _init_git_repo(repo_dir: Path, branch: str) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
    subprocess.run(["git", "checkout", "-b", branch], cwd=repo_dir, check=True, capture_output=True)


def test_check_prerequisites_json_include_tasks_contract(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _init_git_repo(repo, "123-feature-branch")

    feature_dir = repo / "specs" / "123-feature-branch"
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (feature_dir / "tasks.md").write_text("- [ ] T001 sample\n", encoding="utf-8")
    (feature_dir / "research.md").write_text("# Research\n", encoding="utf-8")
    (feature_dir / "quickstart.md").write_text("# Quickstart\n", encoding="utf-8")

    result = _run_check_prereq(repo, "--json", "--include-tasks")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["FEATURE_DIR"] == str(feature_dir)
    assert "research.md" in payload["AVAILABLE_DOCS"]
    assert "quickstart.md" in payload["AVAILABLE_DOCS"]
    assert "tasks.md" in payload["AVAILABLE_DOCS"]


def test_check_prerequisites_require_tasks_fails_when_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _init_git_repo(repo, "124-feature-branch")

    feature_dir = repo / "specs" / "124-feature-branch"
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")

    result = _run_check_prereq(repo, "--json", "--require-tasks")

    assert result.returncode == 1
    assert "tasks.md not found" in result.stderr


def test_check_prerequisites_paths_only_json_skips_validation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _init_git_repo(repo, "125-feature-branch")
    (repo / "specs" / "125-feature-branch").mkdir(parents=True, exist_ok=True)

    result = _run_check_prereq(repo, "--json", "--paths-only")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["REPO_ROOT"] == str(repo)
    assert payload["BRANCH"] == "125-feature-branch"
    assert payload["FEATURE_DIR"] == str(repo / "specs" / "125-feature-branch")
    assert payload["TASKS"] == str(repo / "specs" / "125-feature-branch" / "tasks.md")


def test_check_prerequisites_rejects_non_feature_git_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    result = _run_check_prereq(repo, "--json")

    assert result.returncode == 1
    assert "Not on a feature branch" in result.stderr
