"""Artifact parsing pipeline for speckit ClickUp sync."""

from __future__ import annotations

import re
from pathlib import Path

from src.mcp_clickup import SpecArtifact, Task, TaskGroup

_SPEC_DIR_RE = re.compile(r"^(?P<num>\d{3})-(?P<name>.+)$")
_PARENT_RE = re.compile(r"\*\*Parent Spec\*\*:\s*(\d{3})")
_TITLE_RE = re.compile(r"^#\s+Feature Specification:\s*(.+)$", re.MULTILINE)
_GROUP_RE = re.compile(r"^##\s+(.+)$")
_TASK_RE = re.compile(r"^-\s+\[[ xX]\]\s+(T\d+)\s+(.+)$")


def _parse_spec_title(spec_text: str) -> str:
    match = _TITLE_RE.search(spec_text)
    if match:
        return match.group(1).strip()
    return "Untitled"


def _parse_parent_num(spec_text: str) -> str | None:
    match = _PARENT_RE.search(spec_text)
    if match:
        return match.group(1)
    return None


def parse_task_groups(tasks_md_path: Path, feature_num: str) -> list[TaskGroup]:
    """Parse grouped tasks from a tasks.md file."""
    text = tasks_md_path.read_text(encoding="utf-8")

    groups: list[TaskGroup] = []
    current_title: str | None = None
    current_tasks: list[Task] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        group_match = _GROUP_RE.match(line)
        if group_match:
            if current_title is not None:
                groups.append(TaskGroup(feature_num=feature_num, title=current_title, tasks=current_tasks))
            current_title = group_match.group(1).strip()
            current_tasks = []
            continue

        task_match = _TASK_RE.match(line)
        if task_match and current_title is not None:
            task_id = task_match.group(1)
            task_title = task_match.group(2).strip()
            current_tasks.append(Task(id=task_id, title=task_title))

    if current_title is not None:
        groups.append(TaskGroup(feature_num=feature_num, title=current_title, tasks=current_tasks))

    return groups


def discover_spec_artifacts(specs_root: Path) -> list[SpecArtifact]:
    """Discover feature directories and parse spec/task artifacts."""
    artifacts: list[SpecArtifact] = []

    for child in sorted(specs_root.iterdir()):
        if not child.is_dir():
            continue
        match = _SPEC_DIR_RE.match(child.name)
        if not match:
            continue

        feature_num = match.group("num")
        short_name = match.group("name")
        spec_md = child / "spec.md"
        if not spec_md.exists():
            continue

        spec_text = spec_md.read_text(encoding="utf-8")
        parent_num = _parse_parent_num(spec_text)
        is_phase_spec = parent_num is not None

        tasks_md = child / "tasks.md"
        has_tasks = tasks_md.exists()
        task_groups = parse_task_groups(tasks_md, feature_num) if has_tasks else []

        artifacts.append(
            SpecArtifact(
                feature_num=feature_num,
                short_name=short_name,
                title=_parse_spec_title(spec_text),
                spec_dir=child,
                is_phase_spec=is_phase_spec,
                parent_num=parent_num,
                has_tasks=has_tasks,
                task_groups=task_groups,
            )
        )

    return artifacts
