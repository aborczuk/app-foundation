"""Integration tests for update-agent-context shell-wrapper/Python parity contract."""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".specify"
    / "scripts"
    / "bash"
    / "update-agent-context.sh"
)


def _run_update_agent_context(
    repo_dir: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
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
    subprocess.run(
        ["git", "checkout", "-b", branch],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )


def _seed_feature_layout(repo: Path, branch: str) -> None:
    feature_dir = repo / "specs" / branch
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "plan.md").write_text(
        "\n".join(
            [
                "# Plan",
                "",
                "**Language/Version**: Python 3.12",
                "**Primary Dependencies**: FastAPI",
                "**Storage**: SQLite",
                "**Project Type**: web app",
                "",
            ]
        ),
        encoding="utf-8",
    )

    template_dir = repo / ".specify" / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "agent-file-template.md").write_text(
        "\n".join(
            [
                "# [PROJECT NAME] Development Guidelines",
                "",
                "Auto-generated from all feature plans. Last updated: [DATE]",
                "",
                "## Active Technologies",
                "",
                "[EXTRACTED FROM ALL PLAN.MD FILES]",
                "",
                "## Project Structure",
                "",
                "```text",
                "[ACTUAL STRUCTURE FROM PLANS]",
                "```",
                "",
                "## Commands",
                "",
                "[ONLY COMMANDS FOR ACTIVE TECHNOLOGIES]",
                "",
                "## Code Style",
                "",
                "[LANGUAGE-SPECIFIC, ONLY FOR LANGUAGES IN USE]",
                "",
                "## Recent Changes",
                "",
                "[LAST 3 FEATURES AND WHAT THEY ADDED]",
                "",
                "<!-- MANUAL ADDITIONS START -->",
                "<!-- MANUAL ADDITIONS END -->",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_update_agent_context_creates_codex_file_from_template(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    branch = "126-feature-branch"
    _init_git_repo(repo, branch)
    _seed_feature_layout(repo, branch)

    result = _run_update_agent_context(repo, "codex")

    assert result.returncode == 0, result.stderr
    agents_file = repo / "AGENTS.md"
    assert agents_file.is_file()
    content = agents_file.read_text(encoding="utf-8")
    assert "# repo Development Guidelines" in content
    assert "- Python 3.12 + FastAPI (126-feature-branch)" in content
    assert "- 126-feature-branch: Added Python 3.12 + FastAPI" in content
    assert "backend/" in content
    assert "frontend/" in content
    assert "cd src && pytest && ruff check ." in content
    assert "Python 3.12: Follow standard conventions" in content


def test_update_agent_context_updates_existing_sections_and_preserves_manual(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    branch = "127-feature-branch"
    _init_git_repo(repo, branch)
    _seed_feature_layout(repo, branch)

    agents_file = repo / "AGENTS.md"
    agents_file.write_text(
        "\n".join(
            [
                "# repo Development Guidelines",
                "",
                "Auto-generated from all feature plans. Last updated: 2025-01-01",
                "",
                "## Active Technologies",
                "- Existing Tech (001-existing)",
                "",
                "## Recent Changes",
                "- 001-existing: Added Existing Tech",
                "- 000-older: Added Legacy",
                "- 999-oldest: Added Deprecated",
                "",
                "<!-- MANUAL ADDITIONS START -->",
                "Keep this line",
                "<!-- MANUAL ADDITIONS END -->",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _run_update_agent_context(repo, "codex")

    assert result.returncode == 0, result.stderr
    updated = agents_file.read_text(encoding="utf-8")
    assert "Keep this line" in updated
    assert "- Python 3.12 + FastAPI (127-feature-branch)" in updated
    assert "- SQLite (127-feature-branch)" in updated
    # Preserve legacy shell behavior: when Active Technologies is followed by a blank
    # line, the existing script does not inject a new Recent Changes entry.
    assert "- 127-feature-branch: Added Python 3.12 + FastAPI" not in updated
    assert "- 001-existing: Added Existing Tech" in updated
    assert "- 000-older: Added Legacy" in updated
    assert "- 999-oldest: Added Deprecated" in updated
