#!/usr/bin/env python3
"""Regenerate missing/template HUD artifacts from tasks.md deterministically."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

TASK_LINE_RE = re.compile(
    r"^\s*-\s*\[(?P<checked>[xX ])\]\s+"
    r"(?P<task_id>T\d{3})"
    r"(?:\s+\[(?P<parallel>P)\])?"
    r"(?:\s+\[(?P<human>H)\])?"
    r"(?:\s+\[(?P<story>US\d+)\])?"
    r"\s+(?P<description>.+?)\s*$"
)
HEADING_RE = re.compile(r"^\s{0,3}(?P<hashes>#{2,3})\s+(?P<title>.+?)\s*$")
TASK_REF_RE = re.compile(r"`([^`]+:[^`]+)`")
FEATURE_ID_RE = re.compile(r"^(?P<id>\d{3})[-_].+$")


@dataclass(frozen=True)
class TaskRecord:
    """Parsed task metadata needed for HUD rendering."""

    task_id: str
    description: str
    heading: str
    is_human: bool


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-dir", required=True, help="Feature directory containing tasks.md.")
    parser.add_argument("--dry-run", action="store_true", help="Report planned changes without writing files.")
    parser.add_argument(
        "--task-id",
        action="append",
        default=[],
        help="Limit rewrite to specific task id(s). Repeat for multiple values.",
    )
    parser.add_argument(
        "--rewrite-existing",
        action="store_true",
        help="Rewrite existing HUDs even when they are not templates.",
    )
    return parser.parse_args(argv)


def _feature_id_from_dir(feature_dir: Path) -> str:
    """Extract a 3-digit feature id from the feature directory name."""
    match = FEATURE_ID_RE.match(feature_dir.name)
    if match:
        return match.group("id")
    return "000"


def _extract_summary_and_ref(description: str) -> tuple[str, str]:
    """Split a task description into summary text and file:symbol reference."""
    for separator in (" — ", " - "):
        if separator in description:
            summary, tail = description.rsplit(separator, 1)
            tail = tail.strip()
            if tail.startswith("`") and tail.endswith("`"):
                return summary.strip(), tail.strip("`")

    inline = TASK_REF_RE.search(description)
    if inline:
        ref = inline.group(1)
        summary = description.replace(inline.group(0), "").strip(" -")
        return summary, ref

    return description.strip(), "[resolve from tasks.md annotation]"


def _normalize_story_goal(heading: str) -> str:
    """Normalize heading text into a concise story-goal line."""
    cleaned = heading.replace("MVP", "").strip()
    cleaned = re.sub(r"^Delta\s+", "", cleaned)
    return cleaned


def _security_review_for_path(file_path: str) -> str:
    """Return a deterministic security note based on path scope."""
    if file_path.startswith(("tests/", "specs/", ".claude/")):
        return "N/A - test/doc scope only, no external secret/material handling."
    return (
        "Pending implement-phase security review; no external secret/material "
        "handling expected for this task scope."
    )


def _is_template_hud(content: str) -> bool:
    """Return true when a HUD appears to be scaffold-template content."""
    markers = (
        "[from tasks.md annotation, resolved by codegraph]",
        "[name of external system]",
        "[For 3+ point tasks",
        "[NOT runnable code",
        "Story Goal**: [from tasks.md phase header]",
    )
    return any(marker in content for marker in markers)


def _render_code_hud(*, feature_id: str, task: TaskRecord) -> str:
    """Render a code-task HUD from parsed task metadata."""
    summary, ref = _extract_summary_and_ref(task.description)
    file_path = ref.split(":", 1)[0] if ":" in ref else ref
    story_goal = _normalize_story_goal(task.heading)
    security_note = _security_review_for_path(file_path)
    return f"""---
feature_id: "{feature_id}"
task_id: "{task.task_id}"
---

# HUD: {task.task_id} - {summary}

## Working Memory

**File:Symbol**: `{ref}`
**Callers**: Resolve during implement discovery via codegraph caller query for this symbol.
**Reuse path**: Reuse existing behavior in `{file_path}` and extend deterministically for this task.

## Solution Sketch

**Modify**: `{ref}` to satisfy this task contract from `tasks.md`.
**Create**: none (introduce net-new helpers only if reuse proves insufficient during implementation).
**Reuse**: Existing contracts and helpers already present in the target module/test harness.
**Composition**: {summary}
**Failing test assertion**: Current behavior does not deterministically satisfy this task contract.
**Domains touched**: deterministic orchestration plus module-local behavior for `{file_path}`.

## Test Specification

Assert task `{task.task_id}` deterministically validates: {summary}.

## Security Review

{security_note}

## Functional Goal

**Story Goal**: {story_goal}
**Acceptance Criteria**: {summary} is implemented at `{ref}` and verified by deterministic PASS/FAIL checks.

## Quality Guards

- Preserve deterministic behavior and explicit failure reasons.
- Prevent side effects outside declared artifact/event boundaries.
- Keep required domain baselines (10, 13, 14, 17) where applicable to this seam.

## Process Checklist

- [ ] discovery_completed
- [ ] lld_recorded  <- [include only for 3+ point tasks]
- [ ] quality_guards_passed
- [ ] functional_goal_achieved
- [ ] tests_passed
"""


def _render_human_hud(*, feature_id: str, task: TaskRecord, tasks_file: Path) -> str:
    """Render a runbook HUD from parsed human-task metadata."""
    summary, ref = _extract_summary_and_ref(task.description)
    file_path = ref.split(":", 1)[0] if ":" in ref else ref
    story_goal = _normalize_story_goal(task.heading)
    return f"""---
feature_id: "{feature_id}"
task_id: "{task.task_id}"
---

# HUD: {task.task_id} [H] - {summary}

## Runbook

**System**: `{file_path}`
**Steps**:
1. Execute the operator procedure for: {summary}
2. Capture deterministic evidence in the referenced runbook notes and confirm expected/blocked outcomes.

**Verification command**: `uv run python scripts/speckit_tasks_gate.py validate-format --tasks-file {tasks_file} --json`

## Functional Goal

**Story Goal**: {story_goal}
**Blocks**: Pipeline progress beyond this step until verification evidence is recorded.

## Process Checklist

- [ ] human_action_started
- [ ] human_action_verified
- [ ] task_closed
"""


def _iter_tasks(tasks_file: Path) -> Iterable[TaskRecord]:
    """Yield parsed task records from tasks.md with nearest heading context."""
    current_heading = "Phase"
    for raw in tasks_file.read_text(encoding="utf-8").splitlines():
        heading_match = HEADING_RE.match(raw)
        if heading_match:
            current_heading = heading_match.group("title").strip()
            continue

        task_match = TASK_LINE_RE.match(raw)
        if not task_match:
            continue

        yield TaskRecord(
            task_id=task_match.group("task_id"),
            description=task_match.group("description").strip(),
            heading=current_heading,
            is_human=task_match.group("human") == "H",
        )


def main(argv: list[str] | None = None) -> int:
    """Regenerate required HUDs for tasks that are missing or still templates."""
    args = _parse_args(argv or sys.argv[1:])
    feature_dir = Path(args.feature_dir)
    tasks_file = feature_dir / "tasks.md"
    hud_dir = feature_dir / "huds"
    feature_id = _feature_id_from_dir(feature_dir)
    task_filter = set(args.task_id)

    if not tasks_file.exists():
        print(f"ERROR: tasks file not found: {tasks_file}", file=sys.stderr)
        return 2

    if not hud_dir.exists() and not args.dry_run:
        hud_dir.mkdir(parents=True, exist_ok=True)

    updated: list[str] = []
    for task in _iter_tasks(tasks_file):
        if task_filter and task.task_id not in task_filter:
            continue
        hud_path = hud_dir / f"{task.task_id}.md"
        existed = hud_path.exists()
        if existed:
            existing = hud_path.read_text(encoding="utf-8")
            if not args.rewrite_existing and not _is_template_hud(existing):
                continue

        content = (
            _render_human_hud(feature_id=feature_id, task=task, tasks_file=tasks_file)
            if task.is_human
            else _render_code_hud(feature_id=feature_id, task=task)
        )
        action = "rewritten" if existed else "created"
        updated.append(f"{task.task_id}:{action}")
        if not args.dry_run:
            hud_path.write_text(content, encoding="utf-8")

    print(f"updated={len(updated)}")
    for item in updated:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
