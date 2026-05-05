"""Unit tests for scripts/speckit_codex_handoff_runner.py."""

from __future__ import annotations

import importlib.util
import json
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

    def fake_run_codex_exec(prompt, repo_root_param, *, resume_session=False):  # noqa: ANN001
        target = repo_root_param / "specs" / "023-deterministic-phase-orchestration" / "implementation.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("implemented\n", encoding="utf-8")
        assert resume_session is False
        assert "Implement the next registered task" in prompt
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
    assert result["session_mode"] == "fresh"
    runner_log_path = Path(result["runner_log_path"])
    assert runner_log_path.is_file()
    runner_log = json.loads(runner_log_path.read_text(encoding="utf-8"))
    assert runner_log["prompt"].startswith("You are the local Codex action runner")
    assert runner_log["codex_stdout"] == "codex stdout"
    assert runner_log["codex_stderr"] == "codex stderr"
    assert runner_log["result"]["ok"] is True
    assert runner_log["result"]["commit_sha"] == result["commit_sha"]


def test_run_codex_handoff_accepts_flat_payload(tmp_path: Path, monkeypatch) -> None:
    """Codex handoff should accept the flat implement-step payload shape."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)

    def fake_run_codex_exec(prompt, repo_root_param, *, resume_session=False):  # noqa: ANN001
        target = repo_root_param / "specs" / "023-deterministic-phase-orchestration" / "implementation.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("implemented\n", encoding="utf-8")
        assert resume_session is False
        assert "Handoff payload:" in prompt
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
    assert result["session_mode"] == "fresh"


def test_run_codex_handoff_includes_explicit_instructions(tmp_path: Path, monkeypatch) -> None:
    """Codex handoff should surface explicit instructions in the action prompt."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)

    captured: dict[str, object] = {}

    def fake_run_codex_exec(prompt, repo_root_param, *, resume_session=False):  # noqa: ANN001
        captured["prompt"] = prompt
        captured["resume_session"] = resume_session
        target = repo_root_param / "specs" / "023-deterministic-phase-orchestration" / "sketch.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("sketched\n", encoding="utf-8")
        return 0, "codex stdout", "codex stderr", "Sketch complete"

    monkeypatch.setattr(speckit_codex_handoff_runner, "_run_codex_exec", fake_run_codex_exec)

    result = speckit_codex_handoff_runner.run_codex_handoff(
        {
            "feature_id": "023",
            "phase": "sketch",
            "correlation_id": "run-test:speckit.solution.sketch",
            "handoff": {
                "feature_dir": str(repo_root / "specs" / "023-deterministic-phase-orchestration"),
                "task_id": "",
                "task_attempt": 1,
                "task_action": "sketch",
                "output_template_path": str(
                    repo_root / "specs" / "023-deterministic-phase-orchestration" / "sketch.md"
                ),
                "completion_marker": "## Sketch Completion Summary",
                "instructions": "Write a sketch-first solution summary.",
            },
        },
        repo_root=repo_root,
    )

    assert result["ok"] is True
    assert captured["resume_session"] is False
    assert "Requested instructions:" in str(captured["prompt"])
    assert "Write a sketch-first solution summary." in str(captured["prompt"])
    assert result["changed_files"] == ["specs/023-deterministic-phase-orchestration/sketch.md"]


def test_run_codex_handoff_resumes_session_with_feedback(tmp_path: Path, monkeypatch) -> None:
    """Codex handoff should resume the prior session and include QA feedback."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)

    captured: dict[str, object] = {}

    def fake_run_codex_exec(prompt, repo_root_param, *, resume_session=False):  # noqa: ANN001
        captured["prompt"] = prompt
        captured["resume_session"] = resume_session
        target = repo_root_param / "specs" / "023-deterministic-phase-orchestration" / "implementation.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("revised after qa\n", encoding="utf-8")
        return 0, "codex stdout", "codex stderr", "Implementation revised"

    monkeypatch.setattr(speckit_codex_handoff_runner, "_run_codex_exec", fake_run_codex_exec)

    result = speckit_codex_handoff_runner.run_codex_handoff(
        {
            "feature_id": "023",
            "phase": "implement",
            "correlation_id": "run-test:speckit.implement.retry",
            "handoff": {
                "feature_dir": str(repo_root / "specs" / "023-deterministic-phase-orchestration"),
                "task_id": "T001",
                "task_attempt": 2,
                "task_action": "resumed",
                "output_template_path": str(
                    repo_root / "specs" / "023-deterministic-phase-orchestration" / "implementation.md"
                ),
                "completion_marker": "## Summary",
                "resume_session": True,
                "retry_index": 1,
                "qa_feedback": {
                    "qa_run_id": "qa-023-T001-attempt-1",
                    "result_verdict": "FAIL",
                    "reasons": ["missing_readme_update"],
                },
            },
        },
        repo_root=repo_root,
    )

    assert result["ok"] is True
    assert result["session_mode"] == "resume"
    assert captured["resume_session"] is True
    assert "QA feedback:" in str(captured["prompt"])
    assert "missing_readme_update" in str(captured["prompt"])
    runner_log = json.loads(Path(result["runner_log_path"]).read_text(encoding="utf-8"))
    assert runner_log["qa_feedback"]["reasons"] == ["missing_readme_update"]


def test_run_codex_handoff_writes_log_artifact_on_codex_failure(tmp_path: Path, monkeypatch) -> None:
    """Codex handoff should persist a full log even when Codex exits unsuccessfully."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)

    def fake_run_codex_exec(prompt, repo_root_param, *, resume_session=False):  # noqa: ANN001
        del prompt, repo_root_param, resume_session
        return 1, "codex stdout failure", "codex stderr failure", "Last attempt before failure"

    monkeypatch.setattr(speckit_codex_handoff_runner, "_run_codex_exec", fake_run_codex_exec)

    result = speckit_codex_handoff_runner.run_codex_handoff(
        {
            "feature_id": "023",
            "phase": "implement",
            "correlation_id": "run-test:speckit.implement.failure",
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

    assert result["ok"] is False
    assert result["error_code"] == "codex_exec_failed"
    runner_log_path = Path(result["runner_log_path"])
    assert runner_log_path.is_file()
    runner_log = json.loads(runner_log_path.read_text(encoding="utf-8"))
    assert runner_log["codex_exit_code"] == 1
    assert runner_log["codex_stdout"] == "codex stdout failure"
    assert runner_log["codex_stderr"] == "codex stderr failure"
    assert runner_log["result"]["error_code"] == "codex_exec_failed"


def test_run_codex_exec_seeds_a_private_codex_home(tmp_path: Path, monkeypatch) -> None:
    """Codex exec should run against a writable private CODEX_HOME."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source_home = tmp_path / "codex-home"
    source_home.mkdir()
    (source_home / "auth.json").write_text("{\"token\": \"test\"}\n", encoding="utf-8")
    (source_home / "config.toml").write_text("[default]\n", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(source_home))
    monkeypatch.setattr(speckit_codex_handoff_runner.shutil, "which", lambda name: "/usr/bin/codex")

    captured: dict[str, object] = {}

    def fake_run(command, *, cwd, input, text, capture_output, check, env):  # noqa: ANN001
        del input, text, capture_output, check
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = dict(env)
        codex_home = Path(env["CODEX_HOME"])
        assert codex_home != source_home
        assert codex_home.is_dir()
        assert (codex_home / "auth.json").is_file()
        assert (codex_home / "config.toml").is_file()
        return subprocess.CompletedProcess(command, 0, stdout="codex stdout", stderr="codex stderr")

    monkeypatch.setattr(speckit_codex_handoff_runner.subprocess, "run", fake_run)

    exit_code, stdout, stderr, last_message = speckit_codex_handoff_runner._run_codex_exec(
        "prompt",
        repo_root,
    )

    assert exit_code == 0
    assert stdout == "codex stdout"
    assert stderr == "codex stderr"
    assert last_message == ""
    assert captured["command"][0] == "/usr/bin/codex"
    assert captured["cwd"] == repo_root
    assert captured["env"]["CODEX_HOME"] != str(source_home)
