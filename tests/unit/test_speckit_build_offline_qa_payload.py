"""Unit tests for scripts/speckit_build_offline_qa_payload.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module(module_name: str, script_name: str):
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


speckit_build_offline_qa_payload = _load_script_module(
    "speckit_build_offline_qa_payload", "speckit_build_offline_qa_payload.py"
)


def test_default_quality_guards_are_stable() -> None:
    assert speckit_build_offline_qa_payload.DEFAULT_QUALITY_GUARDS == [
        "Domain 13",
        "Domain 14",
        "Domain 17",
    ]


def test_changed_files_from_head_prefers_workspace_changes(tmp_path: Path) -> None:
    """Workspace edits should drive payload changed_files before a task commit exists."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    import subprocess

    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "codex@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Codex"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    tracked = repo_root / "tracked.txt"
    tracked.write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    tracked.write_text("base\nworkspace change\n", encoding="utf-8")
    untracked = repo_root / "untracked.txt"
    untracked.write_text("new file\n", encoding="utf-8")

    changed_files = speckit_build_offline_qa_payload._changed_files_from_head(repo_root)

    assert changed_files == ["tracked.txt", "untracked.txt"]
