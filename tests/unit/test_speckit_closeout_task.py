"""Tests for the canonical Speckit task closeout script."""

# isort: skip_file
from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import subprocess
import sys


SCRIPT = Path("scripts/speckit_closeout_task.py")
LEDGER = Path("scripts/task_ledger.py")


def _load_closeout_module():
    """Load the closeout script as an importable test module."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / "speckit_closeout_task.py"
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location("speckit_closeout_task", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _append_ledger_event(
    ledger_file: Path,
    *,
    feature_id: str,
    task_id: str,
    event: str,
    commit_sha: str | None = None,
    qa_run_id: str | None = None,
) -> None:
    cmd = [
        sys.executable,
        str(LEDGER),
        "append",
        "--file",
        str(ledger_file),
        "--feature-id",
        feature_id,
        "--task-id",
        task_id,
        "--event",
        event,
        "--actor",
        "codex",
    ]
    if commit_sha:
        cmd.extend(["--commit-sha", commit_sha])
    if qa_run_id:
        cmd.extend(["--qa-run-id", qa_run_id])
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _run_closeout(
    *,
    feature_id: str,
    task_id: str,
    tasks_file: Path,
    ledger_file: Path,
    commit_sha: str | None,
    qa_run_id: str,
    qa_result_file: Path | None = None,
) -> dict[str, object]:
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--feature-id",
        feature_id,
        "--task-id",
        task_id,
        "--tasks-file",
        str(tasks_file),
        "--ledger-file",
        str(ledger_file),
        "--qa-run-id",
        qa_run_id,
        "--json",
    ]
    if commit_sha:
        cmd.extend(["--commit-sha", commit_sha])
    if qa_result_file is not None:
        cmd.extend(["--qa-result-file", str(qa_result_file)])
    result = subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout.strip())


def _write_tasks_file(path: Path, *, phase_two_task_open: bool = True) -> None:
    phase_two_line = "- [ ] T003 Third task" if phase_two_task_open else "- [X] T003 Third task"
    path.write_text(
        "\n".join(
            [
                "# Tasks: Example Feature",
                "",
                "## Phase 1: Story One",
                "",
                "- [ ] T001 First task",
                "- [ ] T002 Second task",
                "",
                "**Story boundary**: Story one hard-stops at the end of the phase.",
                "",
                "## Phase 2: Story Two",
                "",
                phase_two_line,
                "",
                "**Story boundary**: Story two hard-stops at the end of the phase.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_closeout_script_continues_when_phase_has_more_tasks(tmp_path: Path) -> None:
    tasks_file = tmp_path / "tasks.md"
    ledger_file = tmp_path / "ledger.jsonl"
    qa_result_file = tmp_path / "qa-result.json"
    _write_tasks_file(tasks_file, phase_two_task_open=True)
    qa_result_file.write_text(json.dumps({"verdict": "PASS", "findings": []}), encoding="utf-8")

    _append_ledger_event(ledger_file, feature_id="000", task_id="T001", event="task_started")
    _append_ledger_event(ledger_file, feature_id="000", task_id="T001", event="discovery_completed")

    payload = _run_closeout(
        feature_id="000",
        task_id="T001",
        tasks_file=tasks_file,
        ledger_file=ledger_file,
        commit_sha="abc1234",
        qa_run_id="qa-1",
        qa_result_file=qa_result_file,
    )

    assert payload["ok"] is True
    assert payload["next_action"] == "continue"
    assert payload["next_task_id"] == "T002"
    assert "- [X] T001 First task" in tasks_file.read_text(encoding="utf-8")


def test_closeout_script_stops_when_phase_is_complete(tmp_path: Path) -> None:
    tasks_file = tmp_path / "tasks.md"
    ledger_file = tmp_path / "ledger.jsonl"
    qa_result_file = tmp_path / "qa-result.json"
    _write_tasks_file(tasks_file, phase_two_task_open=False)
    qa_result_file.write_text(json.dumps({"verdict": "PASS", "findings": []}), encoding="utf-8")

    _append_ledger_event(ledger_file, feature_id="000", task_id="T003", event="task_started")
    _append_ledger_event(ledger_file, feature_id="000", task_id="T003", event="discovery_completed")

    payload = _run_closeout(
        feature_id="000",
        task_id="T003",
        tasks_file=tasks_file,
        ledger_file=ledger_file,
        commit_sha="def5678",
        qa_run_id="qa-2",
        qa_result_file=qa_result_file,
    )

    assert payload["ok"] is True
    assert payload["next_action"] == "continue"
    assert payload["next_task_id"] is None
    assert "- [X] T003 Third task" in tasks_file.read_text(encoding="utf-8")


def test_closeout_script_passes_without_commit_sha(tmp_path: Path) -> None:
    tasks_file = tmp_path / "tasks.md"
    ledger_file = tmp_path / "ledger.jsonl"
    qa_result_file = tmp_path / "qa-result.json"
    _write_tasks_file(tasks_file, phase_two_task_open=True)
    qa_result_file.write_text(json.dumps({"verdict": "PASS", "findings": []}), encoding="utf-8")

    _append_ledger_event(ledger_file, feature_id="000", task_id="T001", event="task_started")
    _append_ledger_event(ledger_file, feature_id="000", task_id="T001", event="discovery_completed")

    payload = _run_closeout(
        feature_id="000",
        task_id="T001",
        tasks_file=tasks_file,
        ledger_file=ledger_file,
        commit_sha=None,
        qa_run_id="qa-optional-commit",
        qa_result_file=qa_result_file,
    )

    assert payload["ok"] is True
    assert payload["commit_sha"] is None
    ledger_events = [json.loads(line) for line in ledger_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    task_events = [event["event"] for event in ledger_events if event["feature_id"] == "000" and event["task_id"] == "T001"]
    assert "offline_qa_started" in task_events
    assert "offline_qa_passed" in task_events
    assert "commit_created" not in task_events


def test_closeout_reflects_mapped_clickup_task_done(tmp_path: Path) -> None:
    closeout_module = _load_closeout_module()
    tasks_file = tmp_path / "tasks.md"
    ledger_file = tmp_path / "ledger.jsonl"
    manifest_path = tmp_path / "clickup-manifest.json"
    qa_result_file = tmp_path / "qa-result.json"
    _write_tasks_file(tasks_file, phase_two_task_open=True)
    qa_result_file.write_text(json.dumps({"verdict": "PASS", "findings": []}), encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "version": "1",
                "workspace_id": "workspace-1",
                "space_id": "space-1",
                "folders": {},
                "lists": {},
                "tasks": {},
                "subtasks": {},
                "feature_projection_meta": {},
                "task_projection_meta": {
                    "000:T001": {
                        "task_id": "T001",
                        "subtask_id": "clickup-subtask-1",
                    }
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    _append_ledger_event(ledger_file, feature_id="000", task_id="T001", event="task_started")
    _append_ledger_event(ledger_file, feature_id="000", task_id="T001", event="discovery_completed")
    result = closeout_module.closeout_task(
        feature_id="000",
        task_id="T001",
        tasks_file=tasks_file,
        ledger_file=ledger_file,
        commit_sha="abc1234",
        qa_run_id="qa-done",
        qa_result_path=qa_result_file,
        actor="codex",
        manifest_path=manifest_path,
    )
    payload = json.loads(result.to_json())

    assert payload["ok"] is True
    assert payload["clickup_sync_status"] == "pending_agent_update"
    assert payload["clickup_desired_status"] == "done"
    assert payload["clickup_task_id"] == "clickup-subtask-1"
    assert payload["clickup_sync_reason"] is None


def test_closeout_skips_clickup_agent_followthrough_when_manifest_mapping_is_missing(tmp_path: Path) -> None:
    closeout_module = _load_closeout_module()
    tasks_file = tmp_path / "tasks.md"
    ledger_file = tmp_path / "ledger.jsonl"
    manifest_path = tmp_path / "clickup-manifest.json"
    qa_result_file = tmp_path / "qa-result.json"
    _write_tasks_file(tasks_file, phase_two_task_open=True)
    qa_result_file.write_text(json.dumps({"verdict": "PASS", "findings": []}), encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "version": "1",
                "workspace_id": "workspace-1",
                "space_id": "space-1",
                "folders": {},
                "lists": {},
                "tasks": {},
                "subtasks": {},
                "feature_projection_meta": {},
                "task_projection_meta": {},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    _append_ledger_event(ledger_file, feature_id="000", task_id="T001", event="task_started")
    _append_ledger_event(ledger_file, feature_id="000", task_id="T001", event="discovery_completed")

    class _FailingReporter:
        async def mark_task_done(self, task_id: str) -> dict[str, object]:
            raise RuntimeError(f"temporary failure for {task_id}")

    result = closeout_module.closeout_task(
        feature_id="000",
        task_id="T001",
        tasks_file=tasks_file,
        ledger_file=ledger_file,
        commit_sha="abc1234",
        qa_run_id="qa-done",
        qa_result_path=qa_result_file,
        actor="codex",
        manifest_path=manifest_path,
    )
    payload = json.loads(result.to_json())

    assert payload["ok"] is True
    assert payload["clickup_sync_status"] == "skipped"
    assert payload["clickup_task_id"] is None
    assert payload["clickup_desired_status"] is None
    assert "clickup_task_mapping_missing" in str(payload["clickup_sync_reason"])
    assert "- [X] T001 First task" in tasks_file.read_text(encoding="utf-8")


def test_closeout_docs_point_to_canonical_script() -> None:
    closeout_doc = Path(".claude/commands/speckit.closeout.md").read_text(encoding="utf-8")
    claude_doc = Path("CLAUDE.md").read_text(encoding="utf-8")

    assert "scripts/speckit_closeout_task.py" in closeout_doc
    assert "/speckit.checkpoint" not in closeout_doc
    assert "next_task_id=None" in closeout_doc
    assert "AGENTS.md" in claude_doc
