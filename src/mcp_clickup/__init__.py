"""Shared domain models for the speckit ClickUp sync module."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Task:
    """Single implementation task parsed from tasks.md."""

    id: str
    title: str
    workflow_type: str = "build_spec"
    context_ref: str = ""
    execution_policy: str = "manual-test"


@dataclass(frozen=True)
class TaskGroup:
    """Group of implementation tasks under a tasks.md heading."""

    feature_num: str
    title: str
    tasks: list[Task] = field(default_factory=list)


@dataclass(frozen=True)
class SpecArtifact:
    """Parsed feature spec metadata plus optional grouped tasks."""

    feature_num: str
    short_name: str
    title: str
    spec_dir: Path
    is_phase_spec: bool
    parent_num: str | None
    has_tasks: bool
    task_groups: list[TaskGroup] = field(default_factory=list)


@dataclass
class SyncManifest:
    """Persisted mapping from canonical speckit keys to ClickUp IDs."""

    version: str
    workspace_id: str
    space_id: str
    folders: dict[str, str] = field(default_factory=dict)
    lists: dict[str, str] = field(default_factory=dict)
    tasks: dict[str, str] = field(default_factory=dict)
    subtasks: dict[str, str] = field(default_factory=dict)


@dataclass
class SyncReport:
    """Bootstrap reconciliation/create summary payload."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    drift_items: list[str] = field(default_factory=list)
    aborted: bool = False
    abort_reason: str | None = None


@dataclass
class ListStatus:
    """Grouped status counts and drift for a single phase list."""

    feature_num: str
    list_name: str
    done: int = 0
    in_progress: int = 0
    blocked: int = 0
    not_started: int = 0
    drift: list[str] = field(default_factory=list)


@dataclass
class StatusSummary:
    """Read-only status summary grouped by feature list."""

    by_list: dict[str, ListStatus] = field(default_factory=dict)


__all__ = [
    "ListStatus",
    "SpecArtifact",
    "StatusSummary",
    "SyncManifest",
    "SyncReport",
    "Task",
    "TaskGroup",
]
