"""Unit tests for scripts/speckit_codex_handoff_runner.py."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def _load_script_module(module_name: str, script_name: str):
    """Load a script module from the repo's scripts directory."""
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


speckit_codex_handoff_runner = _load_script_module(
    "speckit_codex_handoff_runner",
    "speckit_codex_handoff_runner.py",
)


def test_run_codex_handoff_commits_changes(tmp_path: Path, monkeypatch) -> None:
    """Codex handoff should commit the task edits and report the commit SHA."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)

    def fake_run_codex_exec(prompt, repo_root_param):  # noqa: ANN001
        target = repo_root_param / "specs" / "023-deterministic-phase-orchestration" / "implementation.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("implemented\n", encoding="utf-8")
        return 0, "codex stdout", "codex stderr", "Implementation complete"

    monkeypatch.setattr(speckit_codex_handoff_runner, "_run_codex_exec", fake_run_codex_exec)

    result = speckit_codex_handoff_runner.run_codex_handoff(
        {
            "feature_id": "023",
            "phase": "implement",
            "correlation_id": "run-test:speckit.implement",
            "handoff": {
                "feature_dir": str(repo_root / "specs" / "023-deterministic-phase-orchestration"),
                "task_id": "T001",
                "task_attempt": 1,
                "task_action": "started",
                "output_template_path": str(
                    repo_root / "specs" / "023-deterministic-phase-orchestration" / "implementation.md"
                ),
                "completion_marker": "## Summary",
            },
        },
        repo_root=repo_root,
    )

    assert result["ok"] is True
    assert result["commit_sha"]
    assert result["artifact_path"].endswith("implementation.md")
    assert result["completion_marker"] == "## Summary"
    assert result["summary"] == "Implementation complete"
    assert result["changed_files"] == ["specs/023-deterministic-phase-orchestration/implementation.md"]


def test_run_codex_handoff_accepts_flat_payload(tmp_path: Path, monkeypatch) -> None:
    """Codex handoff should accept the flat implement-step payload shape."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)

    def fake_run_codex_exec(prompt, repo_root_param):  # noqa: ANN001
        target = repo_root_param / "specs" / "023-deterministic-phase-orchestration" / "implementation.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("implemented\n", encoding="utf-8")
        return 0, "codex stdout", "codex stderr", "Implementation complete"

    monkeypatch.setattr(speckit_codex_handoff_runner, "_run_codex_exec", fake_run_codex_exec)

    result = speckit_codex_handoff_runner.run_codex_handoff(
        {
            "feature_id": "023",
            "phase": "implement",
            "correlation_id": "run-test:speckit.implement.flat",
            "feature_dir": str(repo_root / "specs" / "023-deterministic-phase-orchestration"),
            "repo_root": str(repo_root),
            "task_id": "T001",
            "task_attempt": 1,
            "task_action": "started",
            "task_registered": True,
            "task_parallel": False,
        },
        repo_root=repo_root,
    )

    assert result["ok"] is True
    assert result["commit_sha"]
    assert result["summary"] == "Implementation complete"
    assert result["changed_files"] == ["specs/023-deterministic-phase-orchestration/implementation.md"]
