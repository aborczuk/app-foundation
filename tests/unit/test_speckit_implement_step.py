"""Unit tests for the deterministic speckit implement step."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_script_module(module_name: str, script_filename: str) -> ModuleType:
    """Load a repository script as an importable module for tests."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_filename
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


speckit_implement_step = _load_script_module(
    "speckit_implement_step",
    "speckit_implement_step.py",
)


def _write_tasks_file(path: Path) -> None:
    """Write a minimal valid tasks file for implement-step tests."""
    path.write_text(
        "\n".join(
            [
                "## Implement",
                "- [ ] T001 Say hooray! — ./README.md",
                "- [ ] T002 Keep going — ./README.md",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_registered_tasks_ledger(path: Path) -> None:
    """Seed a ledger with two registered tasks and no execution history."""
    path.parent.mkdir(parents=True, exist_ok=True)
    events = [
        {
            "timestamp_utc": "2026-04-29T00:00:00Z",
            "feature_id": "023",
            "task_id": "T001",
            "attempt": 1,
            "event": "task_registered",
            "actor": "codex",
        },
        {
            "timestamp_utc": "2026-04-29T00:01:00Z",
            "feature_id": "023",
            "task_id": "T002",
            "attempt": 1,
            "event": "task_registered",
            "actor": "codex",
        },
    ]
    path.write_text("\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n", encoding="utf-8")


class _FakeCloseoutResult:
    """Minimal closeout result stub used to exercise the implement flow."""

    def __init__(self, *, task_id: str, commit_sha: str, qa_run_id: str) -> None:
        self.ok = True
        self.qa_verdict = "PASS"
        self.next_action = "complete"
        self.next_task_id = None
        self._payload = {
            "ok": True,
            "task_id": task_id,
            "commit_sha": commit_sha,
            "qa_run_id": qa_run_id,
            "qa_verdict": "PASS",
            "next_action": "complete",
            "next_task_id": None,
        }

    def to_json(self) -> str:
        """Serialize the closeout stub in the shape the runner expects."""
        return json.dumps(self._payload, sort_keys=True)


def test_main_blocks_when_feature_not_found(tmp_path: Path, capsys) -> None:
    """Missing feature directories should fail before any task work begins."""
    exit_code = speckit_implement_step.main(
        [
            "--repo-root",
            str(tmp_path),
            "--feature-id",
            "023",
            "--correlation-id",
            "run-test:speckit.implement",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["ok"] is False
    assert payload["exit_code"] == 1
    assert payload["gate"] == "implement_execution"
    assert payload["reasons"] == ["feature_not_found"]
    assert isinstance(payload["debug_path"], str) and payload["debug_path"]
    assert Path(payload["debug_path"]).exists()


def test_main_consumes_registered_tasks_and_runs_local_handoff(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """Implement should take the next registered task and route it through the local runner."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True)
    _write_tasks_file(feature_dir / "tasks.md")
    _write_registered_tasks_ledger(repo_root / ".speckit" / "task-ledger.jsonl")

    monkeypatch.setenv("SPECKIT_AGENT_ID", "codex")
    monkeypatch.setattr(
        speckit_implement_step,
        "_resolve_feature_dir",
        lambda _repo_root, _feature_id: feature_dir,
    )
    monkeypatch.setattr(
        speckit_implement_step,
        "_ensure_implement_branch",
        lambda *args, **kwargs: {
            "branch_name": feature_dir.name,
            "current_branch": "023-deterministic-phase-orchestration",
            "branch_exists": True,
            "status": "already_checked_out",
        },
    )
    monkeypatch.setattr(
        speckit_implement_step,
        "_run_offline_qa_handoff",
        lambda *, feature_id, task_id, attempt: {
            "mode": "offline_qa_handoff",
            "feature_id": feature_id,
            "task_id": task_id,
            "attempt": attempt,
            "payload_file": str(
                repo_root / ".speckit" / "offline-qa" / f"{feature_id}_{task_id}_attempt_{attempt}.handoff.json"
            ),
            "result_file": str(
                repo_root / ".speckit" / "offline-qa" / f"{feature_id}_{task_id}_attempt_{attempt}.result.json"
            ),
            "reasons": [],
            "ok": True,
            "result_verdict": "PASS",
            "qa_run_id": f"qa-{feature_id}-{task_id}-attempt-{attempt}",
        },
    )
    monkeypatch.setattr(
        speckit_implement_step,
        "_closeout_task",
        lambda **kwargs: _FakeCloseoutResult(
            task_id=kwargs["task_id"],
            commit_sha=kwargs["commit_sha"],
            qa_run_id=kwargs["qa_run_id"],
        ),
    )
    monkeypatch.setattr(
        speckit_implement_step,
        "_update_implementation_docs",
        lambda **kwargs: {
            "entry_id": kwargs["correlation_id"],
            "updated": True,
            "commit_sha": kwargs["commit_sha"],
        },
    )

    observed: dict[str, Any] = {"handoff_inputs": [], "commands": []}

    def fake_run_command(command, *, cwd, timeout_seconds, input_payload=None):  # noqa: ANN001
        command_text = " ".join(str(part) for part in command)
        observed.setdefault("commands", []).append(list(command))
        if "speckit_gate_status.py" in command_text:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout=json.dumps({"ok": True}),
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        if "speckit_implement_gate.py" in command_text:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout=json.dumps({"ok": True, "reasons": []}),
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
                )
        if "speckit_codex_handoff_runner.py" in command_text:
            observed["handoff_inputs"].append(json.loads(input_payload or "{}"))
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "exit_code": 0,
                        "correlation_id": "run-test:speckit.implement",
                        "feature_id": "023",
                        "phase": "implement",
                        "task_id": "T001",
                        "task_attempt": 1,
                        "task_action": "started",
                        "artifact_path": "",
                        "completion_marker": "",
                        "runner": "codex-local",
                        "handoff_execution": "codex_exec",
                        "session_mode": "fresh",
                        "reasons": [],
                        "error_code": None,
                        "debug_path": None,
                        "commit_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                        "summary": "Implementation complete",
                        "changed_files": ["README.md"],
                        "stdout_tail": [],
                        "stderr_tail": [],
                        "handoff": {
                            "task_id": "T001",
                            "task_attempt": 1,
                            "task_action": "started",
                        },
                    }
                ),
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        raise AssertionError(f"unexpected command: {command_text}")

    monkeypatch.setattr(speckit_implement_step, "_run_command", fake_run_command)

    exit_code = speckit_implement_step.main(
        [
            "--repo-root",
            str(repo_root),
            "--feature-id",
            "023",
            "--correlation-id",
            "run-test:speckit.implement",
            "--phase",
            "implement",
            "--phase-type",
            "story",
            "--next-phase",
            "closed",
            "--require-handoff",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["ok"] is True
    assert payload["exit_code"] == 0
    assert payload["next_phase"] == "closed"
    assert isinstance(payload["debug_path"], str) and payload["debug_path"]

    debug_payload = json.loads(Path(payload["debug_path"]).read_text(encoding="utf-8"))
    stage_names = [stage["name"] for stage in debug_payload["stages"]]
    assert stage_names == [
        "resolve_feature_dir",
        "gate_status",
        "branch_setup",
        "task_queue",
        "llm_handoff_round_1",
        "commit_resolution_round_1",
        "offline_qa_handoff_round_1",
        "closeout",
        "docs_update",
        "task_gate",
    ]
    statuses = {stage["name"]: stage["status"] for stage in debug_payload["stages"]}
    assert statuses["task_queue"] == "pass"
    assert statuses["llm_handoff_round_1"] == "pass"
    assert statuses["closeout"] == "pass"
    assert statuses["docs_update"] == "pass"

    handoff_inputs = observed["handoff_inputs"]
    assert len(handoff_inputs) == 1
    handoff_input = handoff_inputs[0]
    assert isinstance(handoff_input, dict)
    assert handoff_input["task_id"] == "T001"
    assert handoff_input["repo_root"] == str(repo_root)
    assert handoff_input["feature_dir"] == str(feature_dir)
    assert handoff_input["resume_session"] is False
    assert handoff_input["retry_index"] == 0

    ledger_events = [
        json.loads(line)
        for line in (repo_root / ".speckit" / "task-ledger.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    started_events = [
        event
        for event in ledger_events
        if event["feature_id"] == "023" and event["task_id"] == "T001" and event["event"] == "task_started"
    ]
    assert started_events


def test_main_retries_after_qa_failure_with_same_session(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """Implement should resume the same Codex session after a QA failure."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True)
    _write_tasks_file(feature_dir / "tasks.md")
    _write_registered_tasks_ledger(repo_root / ".speckit" / "task-ledger.jsonl")

    monkeypatch.setenv("SPECKIT_AGENT_ID", "codex")
    monkeypatch.setattr(
        speckit_implement_step,
        "_resolve_feature_dir",
        lambda _repo_root, _feature_id: feature_dir,
    )
    monkeypatch.setattr(
        speckit_implement_step,
        "_ensure_implement_branch",
        lambda *args, **kwargs: {
            "branch_name": feature_dir.name,
            "current_branch": "023-deterministic-phase-orchestration",
            "branch_exists": True,
            "status": "already_checked_out",
        },
    )

    qa_rounds = iter(
        [
            {
                "mode": "offline_qa_handoff",
                "feature_id": "023",
                "task_id": "T001",
                "attempt": 1,
                "payload_file": str(
                    repo_root / ".speckit" / "offline-qa" / "023_T001_attempt_1.handoff.json"
                ),
                "result_file": str(
                    repo_root / ".speckit" / "offline-qa" / "023_T001_attempt_1.result.json"
                ),
                "reasons": [],
                "ok": True,
                "result_verdict": "FAIL",
                "qa_run_id": "qa-023-T001-attempt-1",
            },
            {
                "mode": "offline_qa_handoff",
                "feature_id": "023",
                "task_id": "T001",
                "attempt": 1,
                "payload_file": str(
                    repo_root / ".speckit" / "offline-qa" / "023_T001_attempt_1.handoff.json"
                ),
                "result_file": str(
                    repo_root / ".speckit" / "offline-qa" / "023_T001_attempt_1.result.json"
                ),
                "reasons": [],
                "ok": True,
                "result_verdict": "PASS",
                "qa_run_id": "qa-023-T001-attempt-2",
            },
        ]
    )
    monkeypatch.setattr(
        speckit_implement_step,
        "_run_offline_qa_handoff",
        lambda *, feature_id, task_id, attempt: next(qa_rounds),
    )

    closeout_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        speckit_implement_step,
        "_closeout_task",
        lambda **kwargs: closeout_calls.append(kwargs) or _FakeCloseoutResult(
            task_id=kwargs["task_id"],
            commit_sha=kwargs["commit_sha"],
            qa_run_id=kwargs["qa_run_id"],
        ),
    )
    monkeypatch.setattr(
        speckit_implement_step,
        "_update_implementation_docs",
        lambda **kwargs: {
            "entry_id": kwargs["correlation_id"],
            "updated": True,
            "commit_sha": kwargs["commit_sha"],
        },
    )

    observed: dict[str, Any] = {"handoff_inputs": [], "commands": []}

    def fake_run_command(command, *, cwd, timeout_seconds, input_payload=None):  # noqa: ANN001
        command_text = " ".join(str(part) for part in command)
        observed.setdefault("commands", []).append(list(command))
        if "speckit_gate_status.py" in command_text:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout=json.dumps({"ok": True}),
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        if "speckit_implement_gate.py" in command_text:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout=json.dumps({"ok": True, "reasons": []}),
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        if "speckit_codex_handoff_runner.py" in command_text:
            observed["handoff_inputs"].append(json.loads(input_payload or "{}"))
            handoff_inputs = observed["handoff_inputs"]
            round_index = len(handoff_inputs)
            commit_sha = "1111111111111111111111111111111111111111" if round_index == 1 else "2222222222222222222222222222222222222222"
            summary = "Implementation complete" if round_index == 1 else "Implementation revised after QA"
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "exit_code": 0,
                        "correlation_id": "run-test:speckit.implement",
                        "feature_id": "023",
                        "phase": "implement",
                        "task_id": "T001",
                        "task_attempt": 1,
                        "task_action": "started",
                        "artifact_path": "",
                        "completion_marker": "",
                        "runner": "codex-local",
                        "handoff_execution": "codex_exec",
                        "session_mode": "resume" if round_index > 1 else "fresh",
                        "reasons": [],
                        "error_code": None,
                        "debug_path": None,
                        "commit_sha": commit_sha,
                        "summary": summary,
                        "changed_files": ["README.md"],
                        "stdout_tail": [],
                        "stderr_tail": [],
                        "handoff": {
                            "task_id": "T001",
                            "task_attempt": 1,
                            "task_action": "started",
                        },
                    }
                ),
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        raise AssertionError(f"unexpected command: {command_text}")

    monkeypatch.setattr(speckit_implement_step, "_run_command", fake_run_command)

    exit_code = speckit_implement_step.main(
        [
            "--repo-root",
            str(repo_root),
            "--feature-id",
            "023",
            "--correlation-id",
            "run-test:speckit.implement",
            "--phase",
            "implement",
            "--phase-type",
            "story",
            "--next-phase",
            "closed",
            "--require-handoff",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["ok"] is True
    debug_payload = json.loads(Path(payload["debug_path"]).read_text(encoding="utf-8"))
    stage_names = [stage["name"] for stage in debug_payload["stages"]]
    assert stage_names == [
        "resolve_feature_dir",
        "gate_status",
        "branch_setup",
        "task_queue",
        "llm_handoff_round_1",
        "commit_resolution_round_1",
        "offline_qa_handoff_round_1",
        "llm_handoff_round_2",
        "commit_resolution_round_2",
        "offline_qa_handoff_round_2",
        "closeout",
        "docs_update",
        "task_gate",
    ]
    handoff_inputs = observed["handoff_inputs"]
    assert len(handoff_inputs) == 2
    first_handoff = handoff_inputs[0]
    second_handoff = handoff_inputs[1]
    assert first_handoff["resume_session"] is False
    assert first_handoff["retry_index"] == 0
    assert second_handoff["resume_session"] is True
    assert second_handoff["retry_index"] == 1
    assert second_handoff["qa_feedback"]["qa_run_id"] == "qa-023-T001-attempt-1"
    assert second_handoff["qa_feedback"]["result_verdict"] == "FAIL"
    assert closeout_calls and closeout_calls[0]["commit_sha"] == "2222222222222222222222222222222222222222"
