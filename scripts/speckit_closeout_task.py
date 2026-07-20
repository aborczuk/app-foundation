#!/usr/bin/env python3
"""Canonical task closeout path for Speckit task-ledger workflows.

This script appends the closeout evidence in ledger-first order, marks the task
closed in tasks.md, and returns a compact machine-readable result so implement
can continue silently or hard-stop at the user-story boundary.

Behavioral QA enforcement (v2):
- Reads the QA result file before appending events
- Only appends offline_qa_passed if the verdict is PASS
- Appends offline_qa_failed and blocks closeout if QA did not pass
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, NoReturn

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TASK_LINE_RE = re.compile(r"^(?P<prefix>\s*-\s*)\[(?P<mark>[ XH])\]\s*(?P<task>T\d+)(?P<rest>\b.*)$")

VERDICT_PASS = "PASS"
CLICKUP_DONE_STATUS = "done"


@dataclass(frozen=True)
class CloseoutResult:
    """Result envelope for task closeout operations."""

    ok: bool
    feature_id: str
    task_id: str
    commit_sha: str | None
    qa_run_id: str
    next_action: str
    next_task_id: str | None
    qa_verdict: str | None
    clickup_sync_status: str
    clickup_desired_status: str | None = None
    clickup_task_id: str | None = None
    clickup_sync_reason: str | None = None

    def to_json(self) -> str:
        """Serialize result to canonical JSON."""
        return json.dumps(
            {
                "ok": self.ok,
                "feature_id": self.feature_id,
                "task_id": self.task_id,
                "commit_sha": self.commit_sha,
                "qa_run_id": self.qa_run_id,
                "next_action": self.next_action,
                "next_task_id": self.next_task_id,
                "qa_verdict": self.qa_verdict,
                "clickup_sync_status": self.clickup_sync_status,
                "clickup_desired_status": self.clickup_desired_status,
                "clickup_task_id": self.clickup_task_id,
                "clickup_sync_reason": self.clickup_sync_reason,
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


def _ledger_events_for_task(ledger_file: Path, feature_id: str, task_id: str) -> list[str]:
    events: list[str] = []
    if not ledger_file.exists():
        return events
    for raw_line in ledger_file.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        event = json.loads(raw_line)
        if event.get("feature_id") == feature_id and event.get("task_id") == task_id:
            events.append(str(event.get("event", "")))
    return events


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


def _resolve_qa_result_path(
    repo_root: Path, feature_id: str, task_id: str, qa_run_id: str, explicit_path: Path | None
) -> Path | None:
    """Resolve the QA result file path from explicit arg or default pattern."""
    if explicit_path is not None:
        return explicit_path if explicit_path.exists() else None

    # Try default pattern: .speckit/offline-qa/{feature_id}_{task_id}_attempt_{N}.result.json
    qa_dir = repo_root / ".speckit" / "offline-qa"
    for attempt in range(1, 10):
        candidate = qa_dir / f"{feature_id}_{task_id}_attempt_{attempt}.result.json"
        if candidate.exists():
            return candidate

    return None


def _read_qa_verdict(result_path: Path | None) -> tuple[str | None, list[str]]:
    """Read QA result file and return verdict + findings."""
    if result_path is None:
        return None, ["QA result file not found"]
    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
        return str(data.get("verdict", "")), data.get("findings", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return None, [f"Invalid QA result file: {result_path}"]


def _default_manifest_path(repo_root: Path) -> Path:
    """Return the default ClickUp manifest path for the repository root."""
    return repo_root / ".speckit" / "clickup-manifest.json"


def _resolve_mapped_clickup_task_id(
    *,
    manifest_path: Path,
    feature_id: str,
    task_id: str,
) -> tuple[str | None, str | None]:
    """Resolve the mapped ClickUp subtask id for one repo task."""
    from src.mcp_clickup.manifest import load_manifest, task_projection_manifest_key

    if not manifest_path.exists():
        return None, "clickup_manifest_missing"
    try:
        manifest = load_manifest(manifest_path)
    except Exception as exc:  # pragma: no cover - defensive guard for malformed manifests
        return None, f"clickup_manifest_unreadable:{exc}"
    payload = manifest.task_projection_meta.get(task_projection_manifest_key(feature_id, task_id))
    if not isinstance(payload, Mapping):
        return None, "clickup_task_mapping_missing"
    subtask_id = str(payload.get("subtask_id", "")).strip()
    if not subtask_id:
        return None, "clickup_task_mapping_missing_subtask_id"
    return subtask_id, None


def _plan_clickup_closeout_reflection(
    *,
    manifest_path: Path,
    feature_id: str,
    task_id: str,
) -> tuple[str, str | None, str | None, str | None]:
    """Plan the agent-owned ClickUp done update for one successfully closed repo task."""
    clickup_task_id, resolution_reason = _resolve_mapped_clickup_task_id(
        manifest_path=manifest_path,
        feature_id=feature_id,
        task_id=task_id,
    )
    if not clickup_task_id:
        return "skipped", None, None, resolution_reason
    return "pending_agent_update", clickup_task_id, CLICKUP_DONE_STATUS, None


def _closeout(
    *,
    feature_id: str,
    task_id: str,
    tasks_file: Path,
    ledger_file: Path,
    commit_sha: str | None,
    qa_run_id: str,
    qa_result_path: Path | None,
    actor: str,
    manifest_path: Path,
) -> CloseoutResult:
    repo_root = Path(__file__).resolve().parent.parent
    lines = _task_lines(tasks_file)
    task_idx = _find_task_line(lines, task_id)
    start, end, _ = _phase_bounds(lines, task_idx)

    existing_events = _ledger_events_for_task(ledger_file, feature_id, task_id)
    existing_event_set = set(existing_events)

    next_action = "continue"
    if _phase_has_open_tasks(lines, start, end, task_id):
        next_task_id = _phase_next_task(lines, start, end, task_id)
    else:
        next_task_id = None

    # Check QA result before proceeding
    resolved_qa_path = _resolve_qa_result_path(repo_root, feature_id, task_id, qa_run_id, qa_result_path)
    qa_verdict, qa_findings = _read_qa_verdict(resolved_qa_path)

    if qa_verdict != VERDICT_PASS:
        # QA did not pass — record failure and block closeout
        if "offline_qa_started" not in existing_event_set:
            _append_event(
                ledger_file=ledger_file,
                feature_id=feature_id,
                task_id=task_id,
                event="offline_qa_started",
                actor=actor,
            )
            existing_event_set.add("offline_qa_started")

        if "offline_qa_failed" not in existing_event_set:
            _append_event(
                ledger_file=ledger_file,
                feature_id=feature_id,
                task_id=task_id,
                event="offline_qa_failed",
                actor=actor,
                qa_run_id=qa_run_id,
                details="; ".join(qa_findings) if qa_findings else "QA verdict was not PASS",
            )
            existing_event_set.add("offline_qa_failed")
        _validate_ledger(ledger_file)

        return CloseoutResult(
            ok=False,
            feature_id=feature_id,
            task_id=task_id,
            commit_sha=commit_sha,
            qa_run_id=qa_run_id,
            next_action="fix_required",
            next_task_id=None,
            qa_verdict=qa_verdict,
            clickup_sync_status="not_attempted",
        )

    # QA passed — proceed with canonical closeout
    canonical_events: list[tuple[str, dict[str, str | None]]] = [
        ("tests_passed", {"details": "closeout path recorded task test evidence"}),
        ("offline_qa_started", {}),
        ("offline_qa_passed", {"qa_run_id": qa_run_id, "details": "closeout path recorded offline QA pass"}),
        ("task_closed", {"details": "canonical closeout path completed"}),
    ]
    if commit_sha:
        canonical_events.insert(3, ("commit_created", {"commit_sha": commit_sha}))
    for event_name, extra in canonical_events:
        if event_name in existing_event_set:
            continue
        _append_event(
            ledger_file=ledger_file,
            feature_id=feature_id,
            task_id=task_id,
            event=event_name,
            actor=actor,
            commit_sha=extra.get("commit_sha"),
            qa_run_id=extra.get("qa_run_id"),
            details=extra.get("details"),
        )
        existing_event_set.add(event_name)
    _validate_ledger(ledger_file)

    updated = list(lines)
    updated[task_idx] = _rewrite_task_line(updated[task_idx], task_id)
    tasks_file.write_text("\n".join(updated) + "\n", encoding="utf-8")

    clickup_sync_status, clickup_task_id, clickup_desired_status, clickup_sync_reason = _plan_clickup_closeout_reflection(
        manifest_path=manifest_path,
        feature_id=feature_id,
        task_id=task_id,
    )

    return CloseoutResult(
        ok=True,
        feature_id=feature_id,
        task_id=task_id,
        commit_sha=commit_sha,
        qa_run_id=qa_run_id,
        next_action=next_action,
        next_task_id=next_task_id,
        qa_verdict=qa_verdict,
        clickup_sync_status=clickup_sync_status,
        clickup_desired_status=clickup_desired_status,
        clickup_task_id=clickup_task_id,
        clickup_sync_reason=clickup_sync_reason,
    )


def closeout_task(
    *,
    feature_id: str,
    task_id: str,
    tasks_file: Path,
    ledger_file: Path,
    commit_sha: str | None,
    qa_run_id: str,
    qa_result_path: Path | None,
    actor: str,
    manifest_path: Path | None = None,
) -> CloseoutResult:
    """Run canonical task closeout and return the structured result."""
    return _closeout(
        feature_id=feature_id,
        task_id=task_id,
        tasks_file=tasks_file,
        ledger_file=ledger_file,
        commit_sha=commit_sha,
        qa_run_id=qa_run_id,
        qa_result_path=qa_result_path,
        actor=actor,
        manifest_path=manifest_path or _default_manifest_path(REPO_ROOT),
    )


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser for closeout."""
    parser = argparse.ArgumentParser(description="Canonical Speckit task closeout path.")
    parser.add_argument("--feature-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--tasks-file", required=True)
    parser.add_argument("--ledger-file", required=True)
    parser.add_argument("--commit-sha")
    parser.add_argument("--qa-run-id", required=True)
    parser.add_argument("--qa-result-file", help="Path to offline QA result JSON.")
    parser.add_argument("--clickup-manifest-path", help="Path to the ClickUp sync manifest for mapped task reflection.")
    parser.add_argument("--actor", default="codex")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    """Run canonical task closeout and return exit code."""
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    qa_result_path = Path(args.qa_result_file) if args.qa_result_file else None
    result = closeout_task(
        feature_id=args.feature_id,
        task_id=args.task_id,
        tasks_file=Path(args.tasks_file),
        ledger_file=Path(args.ledger_file),
        commit_sha=str(args.commit_sha).strip() or None if args.commit_sha is not None else None,
        qa_run_id=args.qa_run_id,
        qa_result_path=qa_result_path,
        actor=args.actor,
        manifest_path=Path(args.clickup_manifest_path) if args.clickup_manifest_path else None,
    )
    print(result.to_json() if args.json else result.to_json())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
