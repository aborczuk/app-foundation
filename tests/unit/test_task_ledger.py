"""Unit tests for per-agent task ledger start gates."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "task_ledger.py"


def _event(task_id: str, event: str, actor: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "timestamp_utc": "2026-04-03T00:00:00Z",
        "feature_id": "015",
        "task_id": task_id,
        "attempt": 1,
        "event": event,
        "actor": actor,
    }
    payload.update(extra)
    return payload


def _write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    lines = [json.dumps(event, sort_keys=True) for event in events]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_tasks(path: Path, body: str) -> None:
    path.write_text(body.strip() + "\n", encoding="utf-8")


def _assert_can_start(ledger: Path, tasks: Path, task_id: str, actor: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "assert-can-start",
            "--file",
            str(ledger),
            "--tasks-file",
            str(tasks),
            "--feature-id",
            "015",
            "--task-id",
            task_id,
            "--actor",
            actor,
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_assert_can_start_blocks_same_actor_from_second_open_task(tmp_path: Path) -> None:
    """Test the expected behavior."""
    ledger = tmp_path / "task-ledger.jsonl"
    tasks = tmp_path / "tasks.md"
    _write_tasks(
        tasks,
        """
        - [ ] T001 [P] first parallel task
        - [ ] T002 [P] second parallel task
        """,
    )
    _write_jsonl(
        ledger,
        [
            _event("T001", "task_started", "agent-a"),
        ],
    )

    proc = _assert_can_start(ledger, tasks, "T002", "agent-a")
    assert proc.returncode == 1
    assert "already has open task T001" in proc.stderr


def test_assert_can_start_allows_parallel_task_for_different_actor(tmp_path: Path) -> None:
    """Test the expected behavior."""
    ledger = tmp_path / "task-ledger.jsonl"
    tasks = tmp_path / "tasks.md"
    _write_tasks(
        tasks,
        """
        - [ ] T001 [P] first parallel task
        - [ ] T002 [P] second parallel task
        """,
    )
    _write_jsonl(
        ledger,
        [
            _event("T001", "task_started", "agent-a"),
        ],
    )

    proc = _assert_can_start(ledger, tasks, "T002", "agent-b")
    assert proc.returncode == 0
    assert "Start gate passed" in proc.stdout


def test_assert_can_start_blocks_non_parallel_task_until_all_prior_closed(tmp_path: Path) -> None:
    """Test the expected behavior."""
    ledger = tmp_path / "task-ledger.jsonl"
    tasks = tmp_path / "tasks.md"
    _write_tasks(
        tasks,
        """
        - [ ] T001 [P] first parallel task
        - [ ] T002 [P] second parallel task
        - [ ] T003 non parallel task
        """,
    )
    _write_jsonl(
        ledger,
        [
            _event("T001", "task_started", "agent-a"),
            _event("T001", "tests_passed", "agent-a"),
            _event("T001", "commit_created", "agent-a", commit_sha="abc1234"),
            _event("T001", "offline_qa_started", "agent-a"),
            _event("T001", "offline_qa_passed", "agent-a", qa_run_id="qa-001"),
            _event("T001", "task_closed", "agent-a", qa_run_id="qa-001"),
            _event("T002", "task_started", "agent-b"),
        ],
    )

    proc = _assert_can_start(ledger, tasks, "T003", "agent-c")
    assert proc.returncode == 1
    assert "prior task T002 is not closed" in proc.stderr


def test_assert_can_start_allows_non_parallel_task_after_all_prior_closed(tmp_path: Path) -> None:
    """Test the expected behavior."""
    ledger = tmp_path / "task-ledger.jsonl"
    tasks = tmp_path / "tasks.md"
    _write_tasks(
        tasks,
        """
        - [ ] T001 [P] first parallel task
        - [ ] T002 [P] second parallel task
        - [ ] T003 non parallel task
        """,
    )
    _write_jsonl(
        ledger,
        [
            _event("T001", "task_started", "agent-a"),
            _event("T001", "tests_passed", "agent-a"),
            _event("T001", "commit_created", "agent-a", commit_sha="abc1234"),
            _event("T001", "offline_qa_started", "agent-a"),
            _event("T001", "offline_qa_passed", "agent-a", qa_run_id="qa-001"),
            _event("T001", "task_closed", "agent-a", qa_run_id="qa-001"),
            _event("T002", "task_started", "agent-b"),
            _event("T002", "tests_passed", "agent-b"),
            _event("T002", "commit_created", "agent-b", commit_sha="def5678"),
            _event("T002", "offline_qa_started", "agent-b"),
            _event("T002", "offline_qa_passed", "agent-b", qa_run_id="qa-002"),
            _event("T002", "task_closed", "agent-b", qa_run_id="qa-002"),
        ],
    )

    proc = _assert_can_start(ledger, tasks, "T003", "agent-c")
    assert proc.returncode == 0
    assert "Start gate passed" in proc.stdout
