"""Regression tests for speckit artifact parsing."""

from __future__ import annotations

from pathlib import Path

from src.mcp_clickup.artifact_parser import discover_spec_artifacts


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
