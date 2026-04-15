"""Tests for the canonical Speckit task closeout script."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/speckit_closeout_task.py")
LEDGER = Path("scripts/task_ledger.py")


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
    commit_sha: str,
    qa_run_id: str,
) -> dict[str, object]:
    result = subprocess.run(
        [
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
            "--commit-sha",
            commit_sha,
            "--qa-run-id",
            qa_run_id,
            "--json",
        ],
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
                "**Checkpoint**: Story one hard-stops after checkpoint validation.",
                "",
                "## Phase 2: Story Two",
                "",
                phase_two_line,
                "",
                "**Checkpoint**: Story two hard-stops after checkpoint validation.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_closeout_script_continues_when_phase_has_more_tasks(tmp_path: Path) -> None:
    tasks_file = tmp_path / "tasks.md"
    ledger_file = tmp_path / "ledger.jsonl"
    _write_tasks_file(tasks_file, phase_two_task_open=True)

    _append_ledger_event(ledger_file, feature_id="000", task_id="T001", event="task_started")
    _append_ledger_event(ledger_file, feature_id="000", task_id="T001", event="discovery_completed")

    payload = _run_closeout(
        feature_id="000",
        task_id="T001",
        tasks_file=tasks_file,
        ledger_file=ledger_file,
        commit_sha="abc1234",
        qa_run_id="qa-1",
    )

    assert payload["ok"] is True
    assert payload["next_action"] == "continue"
    assert payload["next_task_id"] == "T002"
    assert payload["checkpoint_phase"] is None
    assert "- [X] T001 First task" in tasks_file.read_text(encoding="utf-8")


def test_closeout_script_hard_stops_when_phase_is_complete(tmp_path: Path) -> None:
    tasks_file = tmp_path / "tasks.md"
    ledger_file = tmp_path / "ledger.jsonl"
    _write_tasks_file(tasks_file, phase_two_task_open=False)

    _append_ledger_event(ledger_file, feature_id="000", task_id="T003", event="task_started")
    _append_ledger_event(ledger_file, feature_id="000", task_id="T003", event="discovery_completed")

    payload = _run_closeout(
        feature_id="000",
        task_id="T003",
        tasks_file=tasks_file,
        ledger_file=ledger_file,
        commit_sha="def5678",
        qa_run_id="qa-2",
    )

    assert payload["ok"] is True
    assert payload["next_action"] == "checkpoint"
    assert payload["next_task_id"] is None
    assert payload["checkpoint_phase"] == "Phase 2: Story Two"
    assert "- [X] T003 Third task" in tasks_file.read_text(encoding="utf-8")


def test_closeout_docs_point_to_canonical_script() -> None:
    closeout_doc = Path(".claude/commands/speckit.closeout.md").read_text(encoding="utf-8")
    claude_doc = Path("CLAUDE.md").read_text(encoding="utf-8")

    assert "scripts/speckit_closeout_task.py" in closeout_doc
    assert "/speckit.checkpoint [phase]" in closeout_doc
    assert "/speckit.closeout" in claude_doc
