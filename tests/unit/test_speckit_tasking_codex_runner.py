"""Unit tests for the Codex-backed tasking runner."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module(module_name: str, script_name: str):
    """Load a script module from the repo's scripts directory."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tasking_runner = _load_script_module(
    "speckit_tasking_codex_runner", "speckit_tasking_codex_runner.py"
)


def test_tasking_runner_estimate_mode_success(tmp_path: Path, monkeypatch) -> None:
    """Estimate mode should persist and reuse the same Codex session."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "023-tasking"
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "tasks.md").write_text("- [ ] T001 sample task\n", encoding="utf-8")
    (feature_dir / "estimates.md").write_text("T001 | 3\n", encoding="utf-8")

    calls: list[str | None] = []

    def fake_run(prompt: str, repo_root: Path, session_id: str | None = None):
        calls.append(session_id)
        return tasking_runner.CommandResult(
            exit_code=0,
            stdout="codex stdout",
            stderr="",
            last_message="estimate summary",
        )

    monkeypatch.setattr(
        tasking_runner,
        "_run_codex_exec",
        fake_run,
    )
    monkeypatch.setattr(
        tasking_runner,
        "_status_paths",
        lambda repo_root, feature_dir: ["specs/023-tasking/estimates.md"],
    )
    monkeypatch.setattr(
        tasking_runner,
        "_discover_latest_session_record",
        lambda codex_home: {
            "session_id": "estimate-session-123",
            "thread_name": "estimate-thread",
            "updated_at": "2026-04-30T22:00:00Z",
        },
    )

    args = tasking_runner._build_parser().parse_args(
        ["--mode", "estimate", "--feature-dir", str(feature_dir), "--json"]
    )

    first_payload = tasking_runner.run_tasking_codex(args, repo_root=repo_root)
    second_payload = tasking_runner.run_tasking_codex(args, repo_root=repo_root)

    assert first_payload["ok"] is True
    assert first_payload["session_mode"] == "fresh"
    assert first_payload["session_id"] == "estimate-session-123"
    assert first_payload["artifact_path"] == str(feature_dir / "estimates.md")
    assert first_payload["changed_files"] == ["specs/023-tasking/estimates.md"]
    session_state_path = Path(first_payload["session_state_path"])
    assert session_state_path.exists()
    assert '"session_id": "estimate-session-123"' in session_state_path.read_text(encoding="utf-8")

    assert second_payload["ok"] is True
    assert second_payload["session_mode"] == "resume"
    assert second_payload["session_id"] == "estimate-session-123"
    assert second_payload["session_state_path"] == first_payload["session_state_path"]
    assert calls == [None, "estimate-session-123"]
    runner_log_path = Path(second_payload["runner_log_path"])
    assert runner_log_path.exists()
    log_text = runner_log_path.read_text(encoding="utf-8")
    assert '"session_mode": "resume"' in log_text
    assert '"session_id": "estimate-session-123"' in log_text


def test_tasking_runner_breakdown_mode_failure(tmp_path: Path, monkeypatch) -> None:
    """Breakdown mode should persist the session even when Codex fails."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "023-tasking"
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "tasks.md").write_text("- [ ] T001 sample task\n", encoding="utf-8")
    (feature_dir / "estimates.md").write_text("T001 | 8\n", encoding="utf-8")

    calls: list[str | None] = []

    def fake_run(prompt: str, repo_root: Path, session_id: str | None = None):
        calls.append(session_id)
        return tasking_runner.CommandResult(
            exit_code=1,
            stdout="codex stdout",
            stderr="codex stderr",
            last_message="breakdown summary",
        )

    monkeypatch.setattr(
        tasking_runner,
        "_run_codex_exec",
        fake_run,
    )
    monkeypatch.setattr(
        tasking_runner,
        "_discover_latest_session_record",
        lambda codex_home: {
            "session_id": "breakdown-session-456",
            "thread_name": "breakdown-thread",
            "updated_at": "2026-04-30T22:00:00Z",
        },
    )

    args = tasking_runner._build_parser().parse_args(
        ["--mode", "breakdown", "--feature-dir", str(feature_dir), "--json"]
    )

    first_payload = tasking_runner.run_tasking_codex(args, repo_root=repo_root)
    second_payload = tasking_runner.run_tasking_codex(args, repo_root=repo_root)

    assert first_payload["ok"] is False
    assert first_payload["session_mode"] == "fresh"
    assert first_payload["session_id"] == "breakdown-session-456"
    assert "codex_exec_failed" in first_payload["reasons"]
    assert first_payload["artifact_path"] == str(feature_dir / "tasks.md")
    session_state_path = Path(first_payload["session_state_path"])
    assert session_state_path.exists()
    assert '"session_id": "breakdown-session-456"' in session_state_path.read_text(encoding="utf-8")

    assert second_payload["ok"] is False
    assert second_payload["session_mode"] == "resume"
    assert second_payload["session_id"] == "breakdown-session-456"
    assert second_payload["session_state_path"] == first_payload["session_state_path"]
    assert calls == [None, "breakdown-session-456"]
    runner_log_path = Path(second_payload["runner_log_path"])
    assert runner_log_path.exists()
    log_text = runner_log_path.read_text(encoding="utf-8")
    assert '"session_mode": "resume"' in log_text
    assert '"session_id": "breakdown-session-456"' in log_text


def test_tasking_runner_clears_both_session_states(tmp_path: Path) -> None:
    """Cleanup should remove both warm-session state files for the feature."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "023-tasking"
    feature_dir.mkdir(parents=True, exist_ok=True)
    estimate_state = repo_root / ".speckit" / "runtime" / "tasking" / "sessions" / "estimate" / "specs__023-tasking.json"
    breakdown_state = repo_root / ".speckit" / "runtime" / "tasking" / "sessions" / "breakdown" / "specs__023-tasking.json"
    estimate_state.parent.mkdir(parents=True, exist_ok=True)
    breakdown_state.parent.mkdir(parents=True, exist_ok=True)
    estimate_state.write_text("{\"session_id\": \"estimate-session-123\"}\n", encoding="utf-8")
    breakdown_state.write_text("{\"session_id\": \"breakdown-session-456\"}\n", encoding="utf-8")

    removed_paths = tasking_runner.clear_tasking_session_state(repo_root, feature_dir)

    assert removed_paths == [str(estimate_state), str(breakdown_state)]
    assert not estimate_state.exists()
    assert not breakdown_state.exists()
