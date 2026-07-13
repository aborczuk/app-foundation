"""Artifact parsing pipeline for speckit ClickUp sync."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from src.mcp_clickup import FeatureProjection, SpecArtifact, Task, TaskGroup, TaskProjection

_SPEC_DIR_RE = re.compile(r"^(?P<num>\d{3})-(?P<name>.+)$")
_PARENT_RE = re.compile(r"\*\*Parent Spec\*\*:\s*(\d{3})")
_TITLE_RE = re.compile(r"^#\s+Feature Specification:\s*(.+)$", re.MULTILINE)
_GROUP_RE = re.compile(r"^##\s+(.+)$")
_TASK_RE = re.compile(r"^-\s+\[[ xX]\]\s+(T\d+)\s+(.+)$")
_ESTIMATE_ROW_RE = re.compile(r"^\|\s*(T\d+)\s*\|\s*(\d+)\s*\|")
_TAG_PREFIX_RE = re.compile(r"^\[(?P<tag>[^\]]+)\]\s*")


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


def _repo_relative(path: Path, repo_root: Path) -> str:
    """Return a stable repo-relative path string when possible."""
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _build_artifact_links(spec_dir: Path, repo_root: Path) -> dict[str, str]:
    """Build canonical repo links for feature artifacts that already exist."""
    links: dict[str, str] = {}
    for key, filename in (
        ("spec", "spec.md"),
        ("plan", "plan.md"),
        ("tasks", "tasks.md"),
        ("estimates", "estimates.md"),
    ):
        path = spec_dir / filename
        if path.exists():
            links[key] = _repo_relative(path, repo_root)
    return links


def _feature_projection_key(artifact: SpecArtifact) -> str:
    """Return the canonical repo-owned key for one feature projection."""
    return artifact.feature_num


def _task_projection_key(feature_num: str, task_id: str) -> str:
    """Return the canonical repo-owned key for one executable task projection."""
    return f"{feature_num}:{task_id}"


def _parse_task_estimates(estimates_md_path: Path) -> dict[str, int]:
    """Parse per-task point estimates from estimates.md when present."""
    if not estimates_md_path.exists():
        return {}

    estimates: dict[str, int] = {}
    for raw_line in estimates_md_path.read_text(encoding="utf-8").splitlines():
        match = _ESTIMATE_ROW_RE.match(raw_line.strip())
        if not match:
            continue
        estimates[match.group(1)] = int(match.group(2))
    return estimates


def _extract_group_acceptance(group_lines: list[str]) -> str:
    """Extract acceptance text for all tasks in a phase using documented fallback order."""
    acceptance_heading = "### Acceptance Criteria"
    if acceptance_heading in group_lines:
        heading_idx = group_lines.index(acceptance_heading)
        acceptance_items: list[str] = []
        for raw_line in group_lines[heading_idx + 1 :]:
            stripped = raw_line.strip()
            if stripped.startswith("### ") or stripped.startswith("## "):
                break
            if stripped.startswith("- ["):
                break
            if stripped.startswith("- "):
                acceptance_items.append(stripped[2:].strip())
            elif acceptance_items and stripped:
                acceptance_items[-1] = f"{acceptance_items[-1]} {stripped}"
        if acceptance_items:
            return " ".join(acceptance_items)

    marker = "**Independent Test**:"
    for raw_line in group_lines:
        if marker in raw_line:
            return raw_line.split(marker, 1)[1].strip()

    return ""


def _parse_task_metadata(task_body: str, group_title: str) -> tuple[str, bool, str]:
    """Split a task body into normalized title plus parallel/story metadata."""
    remaining = task_body.strip()
    tags: list[str] = []
    while True:
        match = _TAG_PREFIX_RE.match(remaining)
        if not match:
            break
        tags.append(match.group("tag").strip())
        remaining = remaining[match.end() :].lstrip()

    parallel = "P" in tags
    story_label = next((tag for tag in tags if tag.upper().startswith("US")), "")
    if not story_label and "User Story" in group_title:
        story_label = group_title
    return remaining, parallel, story_label


def _build_task_group(
    *,
    feature_num: str,
    group_title: str,
    group_lines: list[str],
    task_estimates: Mapping[str, int],
    artifact_links: Mapping[str, str],
) -> TaskGroup:
    """Build one parsed task group with richer task projection metadata."""
    acceptance_criteria = _extract_group_acceptance(group_lines)
    tasks: list[Task] = []

    for raw_line in group_lines:
        task_match = _TASK_RE.match(raw_line.strip())
        if not task_match:
            continue

        task_id = task_match.group(1)
        task_title, parallel, story_label = _parse_task_metadata(task_match.group(2).strip(), group_title)
        tasks.append(
            Task(
                id=task_id,
                title=task_title,
                context_ref=str(artifact_links.get("tasks", "")),
                acceptance_criteria=acceptance_criteria,
                story_label=story_label,
                parallel=parallel,
                estimate_points=task_estimates.get(task_id),
                artifact_links=dict(artifact_links),
            )
        )

    return TaskGroup(feature_num=feature_num, title=group_title, tasks=tasks)


def parse_task_groups(
    tasks_md_path: Path,
    feature_num: str,
    *,
    task_estimates: Mapping[str, int] | None = None,
    artifact_links: Mapping[str, str] | None = None,
) -> list[TaskGroup]:
    """Parse grouped tasks from a tasks.md file into transport-neutral projections."""
    text = tasks_md_path.read_text(encoding="utf-8")

    groups: list[TaskGroup] = []
    current_title: str | None = None
    current_lines: list[str] = []
    estimates = task_estimates or {}
    links = artifact_links or {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        group_match = _GROUP_RE.match(line)
        if group_match:
            if current_title is not None:
                groups.append(
                    _build_task_group(
                        feature_num=feature_num,
                        group_title=current_title,
                        group_lines=current_lines,
                        task_estimates=estimates,
                        artifact_links=links,
                    )
                )
            current_title = group_match.group(1).strip()
            current_lines = []
            continue

        if current_title is not None:
            current_lines.append(raw_line)

    if current_title is not None:
        groups.append(
            _build_task_group(
                feature_num=feature_num,
                group_title=current_title,
                group_lines=current_lines,
                task_estimates=estimates,
                artifact_links=links,
            )
        )

    return groups


def discover_spec_artifacts(specs_root: Path) -> list[SpecArtifact]:
    """Discover feature directories and parse spec/task artifacts."""
    artifacts: list[SpecArtifact] = []
    repo_root = specs_root.parent

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
        artifact_links = _build_artifact_links(child, repo_root)

        tasks_md = child / "tasks.md"
        has_tasks = tasks_md.exists()
        estimates_md = child / "estimates.md"
        task_estimates = _parse_task_estimates(estimates_md)
        task_groups = (
            parse_task_groups(
                tasks_md,
                feature_num,
                task_estimates=task_estimates,
                artifact_links=artifact_links,
            )
            if has_tasks
            else []
        )

        artifacts.append(
            SpecArtifact(
                feature_num=feature_num,
                short_name=short_name,
                title=_parse_spec_title(spec_text),
                spec_dir=child,
                is_phase_spec=is_phase_spec,
                parent_num=parent_num,
                has_tasks=has_tasks,
                artifact_links=artifact_links,
                task_groups=task_groups,
            )
        )

    return artifacts


def build_feature_projection(artifact: SpecArtifact) -> FeatureProjection:
    """Project one parsed feature artifact into canonical feature/task sync records."""
    task_projections = [
        TaskProjection(
            feature_num=artifact.feature_num,
            feature_title=artifact.title,
            feature_short_name=artifact.short_name,
            parent_num=artifact.parent_num,
            task_id=task.id,
            task_key=_task_projection_key(artifact.feature_num, task.id),
            group_title=group.title,
            title=task.title,
            acceptance_criteria=task.acceptance_criteria,
            story_label=task.story_label,
            parallel=task.parallel,
            estimate_points=task.estimate_points,
            context_ref=task.context_ref,
            artifact_links=dict(task.artifact_links or artifact.artifact_links),
        )
        for group in artifact.task_groups
        for task in group.tasks
    ]
    return FeatureProjection(
        feature_num=artifact.feature_num,
        feature_key=_feature_projection_key(artifact),
        short_name=artifact.short_name,
        title=artifact.title,
        parent_num=artifact.parent_num,
        artifact_links=dict(artifact.artifact_links),
        task_projections=task_projections,
    )


def discover_feature_projections(specs_root: Path) -> list[FeatureProjection]:
    """Discover canonical feature projections from repo speckit artifacts."""
    return [build_feature_projection(artifact) for artifact in discover_spec_artifacts(specs_root)]
