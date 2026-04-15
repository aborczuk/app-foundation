#!/usr/bin/env python3
"""Canonical task closeout path for Speckit task-ledger workflows.

This script appends the closeout evidence in ledger-first order, marks the task
closed in tasks.md, and returns a compact machine-readable result so implement
can continue silently or hard-stop at the user-story boundary.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, NoReturn


TASK_LINE_RE = re.compile(r"^(?P<prefix>\s*-\s*)\[(?P<mark>[ XH])\]\s*(?P<task>T\d+)(?P<rest>\b.*)$")


@dataclass(frozen=True)
class CloseoutResult:
    ok: bool
    feature_id: str
    task_id: str
    commit_sha: str
    qa_run_id: str
    next_action: str
    next_task_id: str | None
    checkpoint_phase: str | None

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok,
                "feature_id": self.feature_id,
                "task_id": self.task_id,
                "commit_sha": self.commit_sha,
                "qa_run_id": self.qa_run_id,
                "next_action": self.next_action,
                "next_task_id": self.next_task_id,
                "checkpoint_phase": self.checkpoint_phase,
            },
            sort_keys=True,
        )


def _fail(message: str) -> NoReturn:
    raise SystemExit(message)


def _ledger_script() -> Path:
    return Path(__file__).resolve().with_name("task_ledger.py")


def _append_event(
    *,
    ledger_file: Path,
    feature_id: str,
    task_id: str,
    event: str,
    actor: str,
    commit_sha: str | None = None,
    qa_run_id: str | None = None,
    details: str | None = None,
) -> None:
    cmd = [
        sys.executable,
        str(_ledger_script()),
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
        actor,
    ]
    if commit_sha:
        cmd.extend(["--commit-sha", commit_sha])
    if qa_run_id:
        cmd.extend(["--qa-run-id", qa_run_id])
    if details:
        cmd.extend(["--details", details])
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        _fail(result.stderr.strip() or result.stdout.strip() or f"failed to append {event}")


def _validate_ledger(ledger_file: Path) -> None:
    cmd = [
        sys.executable,
        str(_ledger_script()),
        "validate",
        "--file",
        str(ledger_file),
    ]
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        _fail(result.stderr.strip() or result.stdout.strip() or "ledger validation failed")


def _task_lines(tasks_path: Path) -> list[str]:
    return tasks_path.read_text(encoding="utf-8").splitlines()


def _find_task_line(lines: list[str], task_id: str) -> int:
    for idx, line in enumerate(lines):
        match = TASK_LINE_RE.match(line)
        if match and match.group("task") == task_id:
            return idx
    _fail(f"task {task_id} not found in tasks.md")


def _phase_bounds(lines: list[str], task_idx: int) -> tuple[int, int, str]:
    start = 0
    for idx in range(task_idx, -1, -1):
        if lines[idx].startswith("## "):
            start = idx
            break
    else:
        _fail("could not determine phase heading for task")

    end = len(lines)
    for idx in range(task_idx + 1, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break
    return start, end, lines[start]


def _rewrite_task_line(line: str, task_id: str) -> str:
    match = TASK_LINE_RE.match(line)
    if not match or match.group("task") != task_id:
        return line
    return f'{match.group("prefix")}[X] {match.group("task")}{match.group("rest")}'


def _phase_next_task(lines: list[str], start: int, end: int, closed_task_id: str) -> str | None:
    found_closed = False
    for line in lines[start + 1 : end]:
        match = TASK_LINE_RE.match(line)
        if not match:
            continue
        task_id = match.group("task")
        mark = match.group("mark")
        if task_id == closed_task_id:
            found_closed = True
            continue
        if found_closed and mark != "X":
            return task_id
    return None


def _phase_has_open_tasks(lines: list[str], start: int, end: int, closed_task_id: str) -> bool:
    for line in lines[start + 1 : end]:
        match = TASK_LINE_RE.match(line)
        if not match:
            continue
        if match.group("task") == closed_task_id:
            continue
        if match.group("mark") != "X":
            return True
    return False


def _closeout(
    *,
    feature_id: str,
    task_id: str,
    tasks_file: Path,
    ledger_file: Path,
    commit_sha: str,
    qa_run_id: str,
    actor: str,
) -> CloseoutResult:
    lines = _task_lines(tasks_file)
    task_idx = _find_task_line(lines, task_id)
    start, end, phase_heading = _phase_bounds(lines, task_idx)
    if "Checkpoint" not in "".join(lines[start:end]):
        _fail("phase checkpoint missing from tasks.md")

    if not _phase_has_open_tasks(lines, start, end, task_id):
        checkpoint_phase = phase_heading.lstrip("# ").strip()
        next_action = "checkpoint"
        next_task_id = None
    else:
        checkpoint_phase = None
        next_action = "continue"
        next_task_id = _phase_next_task(lines, start, end, task_id)

    _append_event(
        ledger_file=ledger_file,
        feature_id=feature_id,
        task_id=task_id,
        event="tests_passed",
        actor=actor,
        details="closeout path recorded task test evidence",
    )
    _append_event(
        ledger_file=ledger_file,
        feature_id=feature_id,
        task_id=task_id,
        event="commit_created",
        actor=actor,
        commit_sha=commit_sha,
    )
    _append_event(
        ledger_file=ledger_file,
        feature_id=feature_id,
        task_id=task_id,
        event="offline_qa_started",
        actor=actor,
    )
    _append_event(
        ledger_file=ledger_file,
        feature_id=feature_id,
        task_id=task_id,
        event="offline_qa_passed",
        actor=actor,
        qa_run_id=qa_run_id,
        details="closeout path recorded offline QA pass",
    )
    _append_event(
        ledger_file=ledger_file,
        feature_id=feature_id,
        task_id=task_id,
        event="task_closed",
        actor=actor,
        details="canonical closeout path completed",
    )
    _validate_ledger(ledger_file)

    updated = list(lines)
    updated[task_idx] = _rewrite_task_line(updated[task_idx], task_id)
    tasks_file.write_text("\n".join(updated) + "\n", encoding="utf-8")

    return CloseoutResult(
        ok=True,
        feature_id=feature_id,
        task_id=task_id,
        commit_sha=commit_sha,
        qa_run_id=qa_run_id,
        next_action=next_action,
        next_task_id=next_task_id,
        checkpoint_phase=checkpoint_phase,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Canonical Speckit task closeout path.")
    parser.add_argument("--feature-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--tasks-file", required=True)
    parser.add_argument("--ledger-file", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--qa-run-id", required=True)
    parser.add_argument("--actor", default="codex")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    result = _closeout(
        feature_id=args.feature_id,
        task_id=args.task_id,
        tasks_file=Path(args.tasks_file),
        ledger_file=Path(args.ledger_file),
        commit_sha=args.commit_sha,
        qa_run_id=args.qa_run_id,
        actor=args.actor,
    )
    print(result.to_json() if args.json else result.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
