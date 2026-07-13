"""Regression tests for speckit artifact parsing."""

from __future__ import annotations

from pathlib import Path

from src.mcp_clickup.artifact_parser import discover_feature_projections, discover_spec_artifacts


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_discover_specs_maps_parent_spec_and_task_groups(tmp_path: Path) -> None:
    """Spec discovery should map Parent Spec and parse task groups."""
    specs_root = tmp_path / "specs"

    _write(
        specs_root / "014-clickup-n8n-control-plane" / "spec.md",
        "# Feature Specification: 014 Super\n",
    )

    _write(
        specs_root / "015-control-plane-dispatch" / "spec.md",
        "# Feature Specification: 015 Dispatch\n\n**Parent Spec**: 014\n",
    )
    _write(
        specs_root / "015-control-plane-dispatch" / "tasks.md",
        """
## User Story 1 - Bootstrap
- [ ] T001 Implement first task
- [ ] T002 Implement second task

## User Story 2 - Status
- [ ] T003 Implement status task
""".strip(),
    )

    artifacts = discover_spec_artifacts(specs_root)

    assert [artifact.feature_num for artifact in artifacts] == ["014", "015"]

    super_spec = artifacts[0]
    assert super_spec.is_phase_spec is False
    assert super_spec.parent_num is None
    assert super_spec.has_tasks is False

    phase_spec = artifacts[1]
    assert phase_spec.is_phase_spec is True
    assert phase_spec.parent_num == "014"
    assert phase_spec.has_tasks is True
    assert [group.title for group in phase_spec.task_groups] == [
        "User Story 1 - Bootstrap",
        "User Story 2 - Status",
    ]
    assert [task.id for task in phase_spec.task_groups[0].tasks] == ["T001", "T002"]


def test_discover_specs_enriches_task_projection_metadata(tmp_path: Path) -> None:
    """Spec discovery should parse acceptance, story, estimate, and artifact-link metadata."""
    specs_root = tmp_path / "specs"
    feature_dir = specs_root / "048-composio-clickup-trigger-sync"

    _write(
        feature_dir / "spec.md",
        "# Feature Specification: 048 Sync ClickUp\n",
    )
    _write(feature_dir / "plan.md", "## Design Slices\n")
    _write(
        feature_dir / "tasks.md",
        """
## Phase 3: User Story 1 - Sync stabilized feature work to ClickUp

**Independent Test**: Fallback text that should not win.

### Acceptance Criteria

- Sync creates or updates the mapped ClickUp task.
- Re-running sync updates the item in place.

### Implementation for User Story 1

- [ ] T009 [US1] Implement canonical feature/task projection extraction
- [ ] T010 [P] [US1] Implement stable mapping updates
""".strip(),
    )
    _write(
        feature_dir / "estimates.md",
        """
## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T009 | 3 | Implement canonical feature/task projection extraction | Parser/model work |
| T010 | 5 | Implement stable mapping updates | Mapping work |
""".strip(),
    )

    artifacts = discover_spec_artifacts(specs_root)

    phase_spec = artifacts[0]
    assert phase_spec.artifact_links == {
        "spec": "specs/048-composio-clickup-trigger-sync/spec.md",
        "plan": "specs/048-composio-clickup-trigger-sync/plan.md",
        "tasks": "specs/048-composio-clickup-trigger-sync/tasks.md",
        "estimates": "specs/048-composio-clickup-trigger-sync/estimates.md",
    }

    task_1, task_2 = phase_spec.task_groups[0].tasks
    assert task_1.title == "Implement canonical feature/task projection extraction"
    assert task_1.story_label == "US1"
    assert task_1.parallel is False
    assert task_1.estimate_points == 3
    assert task_1.context_ref == "specs/048-composio-clickup-trigger-sync/tasks.md"
    assert task_1.acceptance_criteria == (
        "Sync creates or updates the mapped ClickUp task. "
        "Re-running sync updates the item in place."
    )
    assert task_1.artifact_links == phase_spec.artifact_links

    assert task_2.title == "Implement stable mapping updates"
    assert task_2.story_label == "US1"
    assert task_2.parallel is True
    assert task_2.estimate_points == 5

    projections = discover_feature_projections(specs_root)
    feature_projection = projections[0]
    assert feature_projection.feature_key == "048"
    assert feature_projection.title == "048 Sync ClickUp"
    assert feature_projection.artifact_links == phase_spec.artifact_links

    task_projection_1, task_projection_2 = feature_projection.task_projections
    assert task_projection_1.task_key == "048:T009"
    assert task_projection_1.group_title == "Phase 3: User Story 1 - Sync stabilized feature work to ClickUp"
    assert task_projection_1.title == "Implement canonical feature/task projection extraction"
    assert task_projection_1.acceptance_criteria == task_1.acceptance_criteria
    assert task_projection_1.story_label == "US1"
    assert task_projection_1.parallel is False
    assert task_projection_1.estimate_points == 3
    assert task_projection_1.context_ref == "specs/048-composio-clickup-trigger-sync/tasks.md"
    assert task_projection_1.artifact_links == phase_spec.artifact_links

    assert task_projection_2.task_key == "048:T010"
    assert task_projection_2.parallel is True


def test_discover_specs_falls_back_to_independent_test_acceptance(tmp_path: Path) -> None:
    """Spec discovery should fall back to Independent Test text when acceptance criteria are absent."""
    specs_root = tmp_path / "specs"
    feature_dir = specs_root / "049-trigger-sync"

    _write(
        feature_dir / "spec.md",
        "# Feature Specification: 049 Trigger Sync\n",
    )
    _write(
        feature_dir / "tasks.md",
        """
## User Story 2 - Trigger implementation from stabilized ClickUp tasks

**Independent Test**: Trigger selection stays repo-owned and stable.

### Implementation for User Story 2

- [ ] T013 [P] [US2] Implement trigger selection
""".strip(),
    )

    artifacts = discover_spec_artifacts(specs_root)

    task = artifacts[0].task_groups[0].tasks[0]
    assert task.id == "T013"
    assert task.title == "Implement trigger selection"
    assert task.story_label == "US2"
    assert task.parallel is True
    assert task.estimate_points is None
    assert task.acceptance_criteria == "Trigger selection stays repo-owned and stable."
