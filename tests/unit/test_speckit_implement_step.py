"""Unit tests for the deterministic speckit implement step."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


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


def _write_tasks_file(path: Path, *, task_lines: list[str] | None = None) -> None:
    """Write a minimal valid tasks file for implement-step tests."""
    path.write_text(
        "\n".join(
            task_lines
            or [
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


def _task_event(
    event: str,
    *,
    task_id: str,
    actor: str = "codex",
    timestamp_utc: str = "2026-04-29T00:00:00Z",
    verification_method: str | None = None,
) -> dict[str, object]:
    """Build a minimal task-ledger event payload for selector tests."""
    payload: dict[str, object] = {
        "timestamp_utc": timestamp_utc,
        "feature_id": "023",
        "task_id": task_id,
        "attempt": 1,
        "event": event,
        "actor": actor,
    }
    if verification_method is not None:
        payload["verification_method"] = verification_method
    return payload


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


def test_select_next_registered_task_skips_other_actor_for_parallel_work(tmp_path: Path) -> None:
    """A second actor should claim the next startable parallel task instead of blocking."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True)
    _write_tasks_file(
        feature_dir / "tasks.md",
        task_lines=[
            "## Implement",
            "- [ ] T001 Setup — ./README.md",
            "- [ ] T002 [P] Parallel one — ./README.md",
            "- [ ] T003 [P] Parallel two — ./README.md",
        ],
    )
    ledger_path = repo_root / ".speckit" / "task-ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    events = [
        _task_event("task_registered", task_id="T001"),
        _task_event("task_registered", task_id="T002"),
        _task_event("task_registered", task_id="T003"),
        _task_event("task_started", task_id="T001"),
        _task_event("human_action_verified", task_id="T001", verification_method="manual-review"),
        _task_event("task_closed", task_id="T001"),
        _task_event("task_started", task_id="T002", actor="agent-a"),
    ]
    ledger_path.write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
        encoding="utf-8",
    )

    summary = speckit_implement_step._select_next_registered_task(
        repo_root=repo_root,
        feature_dir=feature_dir,
        feature_id="023",
        actor="agent-b",
        correlation_id="run-test:speckit.implement",
    )

    assert summary["next_task_id"] == "T003"
    assert summary["task_action"] == "started"
    assert summary["task_parallel"] is True
    assert summary["task_owner_actor"] == "agent-b"


def test_resolve_explicit_task_start_gate_reports_eligibility_without_mutation(tmp_path: Path) -> None:
    """Explicit task gate helper should expose startability without starting the task."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True)
    _write_tasks_file(
        feature_dir / "tasks.md",
        task_lines=[
            "## Implement",
            "- [ ] T001 Setup — ./README.md",
            "- [ ] T002 [P] Parallel one — ./README.md",
        ],
    )
    ledger_path = repo_root / ".speckit" / "task-ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        "\n".join(
            json.dumps(event, sort_keys=True)
            for event in [
                _task_event("task_registered", task_id="T001"),
                _task_event("task_registered", task_id="T002"),
                _task_event("task_started", task_id="T001"),
                _task_event("human_action_verified", task_id="T001", verification_method="manual-review"),
                _task_event("task_closed", task_id="T001"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = speckit_implement_step._resolve_explicit_task_start_gate(
        repo_root=repo_root,
        feature_dir=feature_dir,
        feature_id="023",
        task_id="T002",
        actor="agent-b",
    )

    assert summary["task_id"] == "T002"
    assert summary["blocking_reason"] is None
    assert summary["task_started"] is False
    assert summary["parallel"] is True
    assert Path(summary["ledger_path"]) == ledger_path


def test_resolve_explicit_task_start_gate_reports_blocking_reason_without_mutation(
    tmp_path: Path,
) -> None:
    """Explicit task gate helper should reject blocked work without mutating the ledger."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True)
    _write_tasks_file(
        feature_dir / "tasks.md",
        task_lines=[
            "## Implement",
            "- [ ] T001 Setup — ./README.md",
            "- [ ] T002 [P] Parallel one — ./README.md",
        ],
    )
    ledger_path = repo_root / ".speckit" / "task-ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    before = (
        "\n".join(
            json.dumps(event, sort_keys=True)
            for event in [
                _task_event("task_registered", task_id="T001"),
                _task_event("task_registered", task_id="T002"),
                _task_event("task_started", task_id="T001"),
            ]
        )
        + "\n"
    )
    ledger_path.write_text(before, encoding="utf-8")

    summary = speckit_implement_step._resolve_explicit_task_start_gate(
        repo_root=repo_root,
        feature_dir=feature_dir,
        feature_id="023",
        task_id="T002",
        actor="agent-b",
    )

    assert summary["task_id"] == "T002"
    assert summary["blocking_reason"] == "Cannot start T002; prior task T001 is not closed in the ledger"
    assert summary["task_started"] is False
    assert summary["parallel"] is False
    assert ledger_path.read_text(encoding="utf-8") == before


def test_start_explicit_task_request_starts_eligible_task(tmp_path: Path) -> None:
    """Explicit start requests should append a task_started event for eligible work."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True)
    _write_tasks_file(
        feature_dir / "tasks.md",
        task_lines=[
            "## Implement",
            "- [ ] T001 Setup — ./README.md",
            "- [ ] T002 [P] Parallel one — ./README.md",
        ],
    )
    ledger_path = repo_root / ".speckit" / "task-ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        "\n".join(
            json.dumps(event, sort_keys=True)
            for event in [
                _task_event("task_registered", task_id="T001"),
                _task_event("task_registered", task_id="T002"),
                _task_event("task_started", task_id="T001"),
                _task_event("human_action_verified", task_id="T001", verification_method="manual-review"),
                _task_event("task_closed", task_id="T001"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = speckit_implement_step._start_explicit_task_request(
        repo_root=repo_root,
        feature_dir=feature_dir,
        feature_id="023",
        task_id="T002",
        actor="agent-b",
        correlation_id="clickup:CU-2",
    )

    assert summary["task_id"] == "T002"
    assert summary["task_action"] == "started"
    assert summary["task_started"] is True
    assert summary["task_owner_actor"] == "agent-b"


def test_start_explicit_task_request_resumes_same_actor_task_without_new_event(tmp_path: Path) -> None:
    """Explicit start requests should resume an already-started task for the same actor."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True)
    _write_tasks_file(
        feature_dir / "tasks.md",
        task_lines=[
            "## Implement",
            "- [ ] T001 Setup — ./README.md",
        ],
    )
    ledger_path = repo_root / ".speckit" / "task-ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    before = (
        "\n".join(
            json.dumps(event, sort_keys=True)
            for event in [
                _task_event("task_registered", task_id="T001", actor="agent-b"),
                _task_event("task_started", task_id="T001", actor="agent-b"),
            ]
        )
        + "\n"
    )
    ledger_path.write_text(before, encoding="utf-8")

    summary = speckit_implement_step._start_explicit_task_request(
        repo_root=repo_root,
        feature_dir=feature_dir,
        feature_id="023",
        task_id="T001",
        actor="agent-b",
        correlation_id="clickup:CU-1",
    )

    assert summary["task_action"] == "resumed"
    assert summary["task_started"] is True
    assert ledger_path.read_text(encoding="utf-8") == before


def test_main_blocks_when_feature_not_found(tmp_path: Path, monkeypatch, capsys) -> None:
    """Missing feature directories should fail before any task work begins."""
    bootstrap_calls: list[Path] = []
    # Inject the bootstrap hook first so the failure path still proves startup ran.
    monkeypatch.setattr(
        speckit_implement_step,
        "bootstrap_session",
        lambda repo_root: bootstrap_calls.append(Path(repo_root)) or {"bootstrap_ok": True},
    )

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
    assert bootstrap_calls == [tmp_path.resolve()]


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
                        "runner_log_path": str(
                            repo_root
                            / ".speckit"
                            / "runtime"
                            / "implement"
                            / "runner"
                            / "run-test_speckit.implement__T001__attempt-1__retry-0.json"
                        ),
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


def test_main_keeps_the_codex_session_warm_across_multiple_tasks(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """Implement should reuse one Codex session until the task gate is empty."""
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
    def fake_offline_qa_handoff(*, feature_id, task_id, attempt):  # noqa: ANN001
        result_path = repo_root / ".speckit" / "offline-qa" / f"{feature_id}_{task_id}_attempt_{attempt}.result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps({"verdict": "PASS", "findings": []}, sort_keys=True), encoding="utf-8")
        return {
            "mode": "offline_qa_handoff",
            "feature_id": feature_id,
            "task_id": task_id,
            "attempt": attempt,
            "payload_file": str(result_path.with_suffix(".handoff.json")),
            "result_file": str(result_path),
            "reasons": [],
            "ok": True,
            "result_verdict": "PASS",
            "qa_run_id": f"qa-{feature_id}-{task_id}-attempt-{attempt}",
        }

    monkeypatch.setattr(speckit_implement_step, "_run_offline_qa_handoff", fake_offline_qa_handoff)

    closeout_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        speckit_implement_step,
        "_closeout_task",
        lambda **kwargs: closeout_calls.append(kwargs)
        or speckit_implement_step.speckit_closeout_task.closeout_task(
            feature_id=kwargs["feature_id"],
            task_id=kwargs["task_id"],
            tasks_file=kwargs["tasks_file"],
            ledger_file=kwargs["ledger_path"],
            commit_sha=kwargs["commit_sha"],
            qa_run_id=kwargs["qa_run_id"],
            qa_result_path=kwargs["qa_result_path"],
            actor=kwargs["actor"],
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
    task_gate_rounds = iter(
        [
            {
                "ok": True,
                "mode": "task_gate",
                "feature_id": "023",
                "open_task_ids": ["T002"],
                "closed_task_ids": ["T001"],
                "continuation_task_id": "T002",
                "implementation_completed_state": "continue_open_tasks",
                "reasons": [],
            },
            {
                "ok": True,
                "mode": "task_gate",
                "feature_id": "023",
                "open_task_ids": [],
                "closed_task_ids": ["T001", "T002"],
                "continuation_task_id": None,
                "implementation_completed_state": "emitted",
                "reasons": [],
            },
        ]
    )

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
                stdout=json.dumps(next(task_gate_rounds)),
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        if "speckit_codex_handoff_runner.py" in command_text:
            observed["handoff_inputs"].append(json.loads(input_payload or "{}"))
            handoff_inputs = observed["handoff_inputs"]
            round_index = len(handoff_inputs)
            task_id = str(handoff_inputs[-1]["task_id"])
            commit_sha = "1111111111111111111111111111111111111111" if round_index == 1 else "2222222222222222222222222222222222222222"
            summary = "Implementation complete" if round_index == 1 else "Implementation continued in the warm session"
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "exit_code": 0,
                        "correlation_id": "run-test:speckit.implement",
                        "feature_id": "023",
                        "phase": "implement",
                        "task_id": task_id,
                        "task_attempt": 1,
                        "task_action": "started",
                        "artifact_path": "",
                        "completion_marker": "",
                        "runner": "codex-local",
                        "handoff_execution": "codex_exec",
                        "session_mode": "fresh" if round_index == 1 else "resume",
                        "reasons": [],
                        "error_code": None,
                        "debug_path": None,
                        "commit_sha": commit_sha,
                        "summary": summary,
                        "changed_files": ["README.md"],
                        "stdout_tail": [],
                        "stderr_tail": [],
                        "runner_log_path": str(
                            repo_root
                            / ".speckit"
                            / "runtime"
                            / "implement"
                            / "runner"
                            / f"run-test_speckit.implement__{task_id}__attempt-1__retry-{round_index - 1}.json"
                        ),
                        "handoff": {
                            "task_id": task_id,
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
    assert stage_names.count("task_queue") == 2
    assert stage_names.count("llm_handoff_round_1") == 2
    assert stage_names.count("closeout") == 2
    assert stage_names.count("task_gate") == 2

    handoff_inputs = observed["handoff_inputs"]
    assert len(handoff_inputs) == 2
    assert handoff_inputs[0]["task_id"] == "T001"
    assert handoff_inputs[0]["resume_session"] is False
    assert handoff_inputs[1]["task_id"] == "T002"
    assert handoff_inputs[1]["resume_session"] is True
    assert handoff_inputs[1]["retry_index"] == 0

    assert len(closeout_calls) == 2
    assert closeout_calls[0]["task_id"] == "T001"
    assert closeout_calls[1]["task_id"] == "T002"


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
                        "runner_log_path": str(
                            repo_root
                            / ".speckit"
                            / "runtime"
                            / "implement"
                            / "runner"
                            / f"run-test_speckit.implement__T001__attempt-1__retry-{round_index - 1}.json"
                        ),
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
    handoff_stage = next(stage for stage in debug_payload["stages"] if stage["name"] == "llm_handoff_round_1")
    assert handoff_stage["details"]["runner_log_path"]
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

def test_ensure_implement_branch_creates_branch_from_main(monkeypatch, tmp_path: Path) -> None:
    """Implement should create the feature branch from local main when needed."""
    repo_root = tmp_path
    feature_dir = repo_root / "specs" / "023-demo-branch"
    feature_dir.mkdir(parents=True)
    calls: list[list[str]] = []

    def fake_run_command(command, *, cwd, timeout_seconds, input_payload=None):
        del cwd, input_payload
        calls.append([str(part) for part in command])
        if command == ["git", "branch", "--show-current"]:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout="main\n",
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        if command == ["git", "branch", "--list", feature_dir.name]:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout="",
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        if command == ["git", "switch", "-c", feature_dir.name]:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout=f"Switched to a new branch '{feature_dir.name}'\n",
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(speckit_implement_step, "_run_command", fake_run_command)

    details = speckit_implement_step._ensure_implement_branch(repo_root, feature_dir, timeout_seconds=30)

    assert details["branch_name"] == feature_dir.name
    assert details["status"] == "created"
    assert calls == [
        ["git", "branch", "--show-current"],
        ["git", "branch", "--list", feature_dir.name],
        ["git", "switch", "-c", feature_dir.name],
    ]


def test_ensure_implement_branch_requires_main(monkeypatch, tmp_path: Path) -> None:
    """Implement should refuse to create a new branch off a non-main checkout."""
    repo_root = tmp_path
    feature_dir = repo_root / "specs" / "023-demo-branch"
    feature_dir.mkdir(parents=True)
    calls: list[list[str]] = []

    def fake_run_command(command, *, cwd, timeout_seconds, input_payload=None):
        del cwd, input_payload
        calls.append([str(part) for part in command])
        if command == ["git", "branch", "--show-current"]:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout="scratch\n",
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        if command == ["git", "branch", "--list", feature_dir.name]:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout="",
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(speckit_implement_step, "_run_command", fake_run_command)

    with pytest.raises(ValueError, match="implement_branch_requires_main"):
        speckit_implement_step._ensure_implement_branch(repo_root, feature_dir, timeout_seconds=30)

    assert calls == [
        ["git", "branch", "--show-current"],
        ["git", "branch", "--list", feature_dir.name],
    ]
