#!/usr/bin/env python3
"""Deterministic format validation for speckit tasks.md artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

PHASE_HEADER_RE = re.compile(r"^\s*##\s+Phase\s+\d+:\s+(?P<title>.+?)\s*$")
TASK_PREFIX_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s*T\d{3}(?:[a-c])?\b")
TASKISH_LINE_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s+(?P<token>T\S+)")
TASK_LINE_RE = re.compile(
    r"^\s*-\s*\[(?P<checked>[xX ])\]\s+"
    r"(?P<task_id>T\d{3}(?:[a-c])?)"
    r"(?:\s+\[(?P<parallel>P)\])?"
    r"(?:\s+\[(?P<human>H)\])?"
    r"(?:\s+\[(?P<story>US\d+)\])?"
    r"\s+(?P<description>.+?)\s*$"
)


@dataclass(frozen=True)
class TaskLine:
    """Parsed representation for one task line."""

    line_no: int
    raw: str
    task_id: str
    marker_parallel: bool
    marker_human: bool
    story_label: str | None
    description: str


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    validate = subparsers.add_parser(
        "validate-format",
        help="Validate tasks.md checklist format and phase/story label consistency.",
    )
    validate.add_argument("--tasks-file", required=True)
    validate.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _phase_type(phase_title: str) -> str:
    """Classify phase title into one of four coarse categories."""
    title = phase_title.lower()
    if "user story" in title:
        return "story"
    if "setup" in title:
        return "setup"
    if "foundational" in title:
        return "foundational"
    return "polish"


def _contains_path(description: str) -> bool:
    """Return true when description names a nested or repository-root file path."""
    return bool(
        "/" in description
        or "\\" in description
        or re.search(r"(?<![\w.-])[\w.-]+\.(?:md|py|toml|ya?ml|json)(?![\w.-])", description)
    )


def _validate(tasks_file: Path) -> tuple[int, dict[str, Any]]:
    """Validate formatting and sequencing constraints for tasks.md."""
    if not tasks_file.exists():
        return (
            2,
            {
                "mode": "validate_format",
                "ok": False,
                "tasks_file": str(tasks_file),
                "reasons": ["missing_tasks_file"],
                "errors": [],
            },
        )

    phase_title = ""
    phase_kind = ""
    errors: list[dict[str, Any]] = []
    parsed_tasks: list[TaskLine] = []

    for line_no, raw in enumerate(tasks_file.read_text(encoding="utf-8").splitlines(), start=1):
        phase_match = PHASE_HEADER_RE.match(raw)
        if phase_match:
            phase_title = phase_match.group("title").strip()
            phase_kind = _phase_type(phase_title)
            continue

        taskish_match = TASKISH_LINE_RE.match(raw)
        if taskish_match and not TASK_LINE_RE.match(raw):
            errors.append(
                {
                    "line": line_no,
                    "code": "invalid_task_line",
                    "message": (
                        "Task-like checklist line must use canonical `TNNN` format with valid markers "
                        "and description ordering."
                    ),
                }
            )
            continue

        if not TASK_PREFIX_RE.match(raw):
            continue

        match = TASK_LINE_RE.match(raw)
        if not match:
            errors.append(
                {
                    "line": line_no,
                    "code": "invalid_task_format",
                    "message": "Task line does not match required checklist format.",
                }
            )
            continue

        description = match.group("description")
        task = TaskLine(
            line_no=line_no,
            raw=raw,
            task_id=match.group("task_id"),
            marker_parallel=match.group("parallel") == "P",
            marker_human=match.group("human") == "H",
            story_label=match.group("story"),
            description=description,
        )
        parsed_tasks.append(task)

        if task.marker_parallel and task.marker_human:
            errors.append(
                {
                    "line": line_no,
                    "code": "conflicting_markers",
                    "message": "Task cannot have both [P] and [H].",
                }
            )

        if phase_kind == "story" and task.story_label is None:
            errors.append(
                {
                    "line": line_no,
                    "code": "missing_story_label",
                    "message": "Story phase task must include [USn] label.",
                }
            )

        if not _contains_path(task.description):
            errors.append(
                {
                    "line": line_no,
                    "code": "missing_file_path",
                    "message": "Task description should include an explicit file path.",
                }
            )

    seen_ids: set[str] = set()
    duplicate_ids: list[str] = []
    task_groups: list[list[TaskLine]] = []
    for task in parsed_tasks:
        if task.task_id in seen_ids:
            duplicate_ids.append(task.task_id)
        seen_ids.add(task.task_id)

    if duplicate_ids:
        errors.append(
            {
                "line": None,
                "code": "duplicate_task_ids",
                "message": f"Duplicate task IDs: {', '.join(sorted(set(duplicate_ids)))}",
            }
        )

    for task in parsed_tasks:
        number = int(task.task_id[1:4])
        if not task_groups or int(task_groups[-1][0].task_id[1:4]) != number:
            task_groups.append([task])
        else:
            task_groups[-1].append(task)

    if task_groups:
        expected_number = int(task_groups[0][0].task_id[1:4])
        for group in task_groups:
            number = int(group[0].task_id[1:4])
            suffixes = [task.task_id[4:] for task in group]
            valid_split = suffixes in ([""], ["a", "b"], ["a", "b", "c"])
            if number != expected_number or not valid_split:
                errors.append(
                    {
                        "line": None,
                        "code": "non_sequential_task_ids",
                        "message": "Task IDs must be sequential, with split tasks ordered as a/b or a/b/c.",
                    }
                )
                break
            expected_number += 1

    payload: dict[str, Any] = {
        "mode": "validate_format",
        "tasks_file": str(tasks_file),
        "task_count": len(parsed_tasks),
        "error_count": len(errors),
        "errors": errors,
        "ok": len(errors) == 0,
    }
    return (0 if payload["ok"] else 2, payload)


def _print_payload(payload: dict[str, Any], as_json: bool) -> None:
    """Render a compact result to stdout."""
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"ok={payload.get('ok')} task_count={payload.get('task_count')} error_count={payload.get('error_count')}")
    for err in payload.get("errors", []):
        line = err.get("line")
        line_text = f"line {line}" if line is not None else "global"
        print(f"{line_text}: {err.get('code')} - {err.get('message')}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run requested tasks gate check and return process exit code."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.subcommand != "validate-format":
        return 2
    exit_code, payload = _validate(Path(args.tasks_file).resolve())
    _print_payload(payload, as_json=bool(args.json))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
