"""Regression tests for sync-engine reconciliation and bootstrap behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.mcp_clickup import SpecArtifact, SyncManifest, SyncReport, Task, TaskGroup
from src.mcp_clickup.sync_engine import (
    ManifestRebuildAmbiguousError,
    MissingCustomFieldsError,
    SyncEngine,
)


@dataclass
class _CreatedItem:
    id: str
    name: str


class _FakeClickUpClient:
    def __init__(self) -> None:
        self.space_id = "space-1"
        self.team_id = "team-1"
        self.folder_seq = 0
        self.list_seq = 0
        self.task_seq = 0
        self.subtask_seq = 0

        self.folders: dict[str, dict[str, Any]] = {}
        self.lists: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, dict[str, Any]] = {}
        self.subtasks: dict[str, dict[str, Any]] = {}
        self.custom_fields_by_list: dict[str, dict[str, str]] = {}
        self.field_sets: list[tuple[str, str, str]] = []
        self.use_default_fields = True

    async def get_space(self, space_id: str) -> dict[str, Any]:
        return {"id": space_id, "team_id": self.team_id}

    async def list_folders(self, space_id: str) -> list[dict[str, Any]]:
        return [f for f in self.folders.values() if f["space_id"] == space_id]

    async def create_folder(self, space_id: str, name: str) -> dict[str, Any]:
        self.folder_seq += 1
        folder_id = f"folder-{self.folder_seq}"
        record = {"id": folder_id, "name": name, "space_id": space_id}
        self.folders[folder_id] = record
        return record

    async def list_lists(self, folder_id: str) -> list[dict[str, Any]]:
        return [
            list_item
            for list_item in self.lists.values()
            if list_item["folder_id"] == folder_id
        ]

    async def create_list(self, folder_id: str, name: str) -> dict[str, Any]:
        self.list_seq += 1
        list_id = f"list-{self.list_seq}"
        record = {"id": list_id, "name": name, "folder_id": folder_id}
        self.lists[list_id] = record
        return record

    async def get_list(self, list_id: str) -> dict[str, Any]:
        return self.lists[list_id]

    async def list_tasks(self, list_id: str) -> list[dict[str, Any]]:
        return [t for t in self.tasks.values() if t["list_id"] == list_id and t["parent"] == ""]

    async def list_subtasks(self, task_id: str) -> list[dict[str, Any]]:
        return [t for t in self.subtasks.values() if t["parent"] == task_id]

    async def create_task(self, list_id: str, name: str, parent: str | None = None) -> dict[str, Any]:
        if parent:
            self.subtask_seq += 1
            task_id = f"subtask-{self.subtask_seq}"
            record = {"id": task_id, "name": name, "list_id": list_id, "parent": parent}
            self.subtasks[task_id] = record
            return record

        self.task_seq += 1
        task_id = f"task-{self.task_seq}"
        record = {"id": task_id, "name": name, "list_id": list_id, "parent": ""}
        self.tasks[task_id] = record
        return record

    async def update_task(self, task_id: str, *, name: str) -> dict[str, Any]:
        if task_id in self.tasks:
            self.tasks[task_id]["name"] = name
            return self.tasks[task_id]
        self.subtasks[task_id]["name"] = name
        return self.subtasks[task_id]

    async def list_custom_fields(self, list_id: str) -> list[dict[str, Any]]:
        defaults = {
            "workflow_type": "f-workflow",
            "context_ref": "f-context",
            "execution_policy": "f-policy",
        }
        base = defaults if self.use_default_fields else {}
        return [
            {"id": field_id, "name": field_name}
            for field_name, field_id in self.custom_fields_by_list.get(list_id, base).items()
        ]

    async def set_custom_field(self, task_id: str, field_id: str, value: str) -> None:
        self.field_sets.append((task_id, field_id, value))


def _artifact(
    feature_num: str,
    *,
    parent_num: str | None,
    has_tasks: bool,
    groups: list[TaskGroup] | None = None,
) -> SpecArtifact:
    return SpecArtifact(
        feature_num=feature_num,
        short_name=f"spec-{feature_num}",
        title=f"Spec {feature_num}",
        spec_dir=__import__("pathlib").Path(f"/tmp/spec-{feature_num}"),
        is_phase_spec=parent_num is not None,
        parent_num=parent_num,
        has_tasks=has_tasks,
        task_groups=groups or [],
    )


def _group(feature_num: str, title: str, task_ids: list[str]) -> TaskGroup:
    return TaskGroup(
        feature_num=feature_num,
        title=title,
        tasks=[Task(id=task_id, title=f"Task {task_id}") for task_id in task_ids],
    )


class _TrackingSyncEngine(SyncEngine):
    def __init__(self, client: _FakeClickUpClient) -> None:
        super().__init__(client)
        self.call_order: list[str] = []

    def reconcile_manifest(
        self,
        manifest: SyncManifest | None,
        rebuild_candidates: dict[str, list[str]] | None = None,
    ) -> SyncManifest:
        self.call_order.append("reconcile")
        return super().reconcile_manifest(manifest, rebuild_candidates)

    async def _create_missing_items(
        self,
        *,
        manifest: SyncManifest,
        artifacts: list[SpecArtifact],
        field_ids_by_list: dict[str, dict[str, str]],
        flush_manifest,
    ) -> SyncReport:
        self.call_order.append("create")
        return await super()._create_missing_items(
            manifest=manifest,
            artifacts=artifacts,
            field_ids_by_list=field_ids_by_list,
            flush_manifest=flush_manifest,
        )


@pytest.mark.asyncio
async def test_reconcile_happens_before_create_decisions() -> None:
    """Bootstrap must reconcile manifest before any create decisions."""
    client = _FakeClickUpClient()
    engine = _TrackingSyncEngine(client)
    manifest = SyncManifest(version="1", workspace_id="w1", space_id="s1")

    await engine.bootstrap_from_artifacts(
        artifacts=[],
        space_id="space-1",
        manifest=manifest,
    )

    assert engine.call_order == ["reconcile", "create"]


@pytest.mark.asyncio
async def test_manifest_rebuild_ambiguous_fails_closed() -> None:
    """Ambiguous manifest rebuild candidates should abort before create."""
    client = _FakeClickUpClient()
    engine = _TrackingSyncEngine(client)

    with pytest.raises(ManifestRebuildAmbiguousError):
        await engine.bootstrap_from_artifacts(
            artifacts=[],
            space_id="space-1",
            manifest=None,
            rebuild_candidates={
                "018:T001": ["subtask-1", "subtask-2"],
            },
        )

    assert engine.call_order == ["reconcile"]


@pytest.mark.asyncio
async def test_hierarchy_mapping_and_skip_when_tasks_missing() -> None:
    """Engine creates Folder/List/Task/Subtask hierarchy and skips taskless spec."""
    client = _FakeClickUpClient()
    engine = SyncEngine(client)

    artifacts = [
        _artifact("014", parent_num=None, has_tasks=False),
        _artifact("015", parent_num="014", has_tasks=True, groups=[_group("015", "US1", ["T001", "T002"])]),
        _artifact("016", parent_num="014", has_tasks=False),
    ]

    report = await engine.bootstrap_from_artifacts(
        artifacts=artifacts,
        space_id="space-1",
        manifest=None,
    )

    assert report.aborted is False
    assert len(client.folders) == 1
    assert len(client.lists) == 2
    assert len(client.tasks) == 1
    assert len(client.subtasks) == 2
    assert report.skipped >= 1


@pytest.mark.asyncio
async def test_idempotent_rerun_and_append_only_new_subtask() -> None:
    """Second run should be unchanged; adding one task should append one subtask."""
    client = _FakeClickUpClient()
    engine = SyncEngine(client)

    artifacts_v1 = [
        _artifact("014", parent_num=None, has_tasks=False),
        _artifact("015", parent_num="014", has_tasks=True, groups=[_group("015", "US1", ["T001"])]),
    ]

    flushes: list[SyncManifest] = []

    def _flush(manifest: SyncManifest) -> None:
        flushes.append(
            SyncManifest(
                version=manifest.version,
                workspace_id=manifest.workspace_id,
                space_id=manifest.space_id,
                folders=dict(manifest.folders),
                lists=dict(manifest.lists),
                tasks=dict(manifest.tasks),
                subtasks=dict(manifest.subtasks),
            )
        )

    report1 = await engine.bootstrap_from_artifacts(
        artifacts=artifacts_v1,
        space_id="space-1",
        manifest=None,
        flush_manifest=_flush,
    )
    manifest_after_v1 = flushes[-1]

    report2 = await engine.bootstrap_from_artifacts(
        artifacts=artifacts_v1,
        space_id="space-1",
        manifest=manifest_after_v1,
        flush_manifest=_flush,
    )

    artifacts_v2 = [
        _artifact("014", parent_num=None, has_tasks=False),
        _artifact("015", parent_num="014", has_tasks=True, groups=[_group("015", "US1", ["T001", "T002"])]),
    ]
    report3 = await engine.bootstrap_from_artifacts(
        artifacts=artifacts_v2,
        space_id="space-1",
        manifest=flushes[-1],
        flush_manifest=_flush,
    )

    assert report1.created > 0
    assert report2.created == 0
    assert report3.created == 1
    assert len(client.subtasks) == 2


@pytest.mark.asyncio
async def test_missing_manifest_rebuild_deterministic_success() -> None:
    """Existing hierarchy should rebuild manifest deterministically when unambiguous."""
    client = _FakeClickUpClient()
    engine = SyncEngine(client)

    folder = await client.create_folder("space-1", "014-spec-014")
    list_ = await client.create_list(folder["id"], "015-spec-015")
    client.custom_fields_by_list[list_["id"]] = {
        "workflow_type": "f-workflow",
        "context_ref": "f-context",
        "execution_policy": "f-policy",
    }
    task = await client.create_task(list_["id"], "015:US1")
    await client.create_task(list_["id"], "015:T001 - Task T001", parent=task["id"])

    artifacts = [
        _artifact("014", parent_num=None, has_tasks=False),
        _artifact("015", parent_num="014", has_tasks=True, groups=[_group("015", "US1", ["T001"])]),
    ]

    report = await engine.bootstrap_from_artifacts(
        artifacts=artifacts,
        space_id="space-1",
        manifest=None,
    )

    assert report.aborted is False
    assert report.created == 0


@pytest.mark.asyncio
async def test_missing_custom_field_gate_blocks_subtask_writes() -> None:
    """Missing required fields should fail before any subtask creation."""
    client = _FakeClickUpClient()
    client.use_default_fields = False
    engine = SyncEngine(client)

    artifacts = [
        _artifact("014", parent_num=None, has_tasks=False),
        _artifact("015", parent_num="014", has_tasks=True, groups=[_group("015", "US1", ["T001"])]),
    ]

    with pytest.raises(MissingCustomFieldsError):
        await engine.bootstrap_from_artifacts(
            artifacts=artifacts,
            space_id="space-1",
            manifest=None,
        )

    assert len(client.subtasks) == 0
    assert client.field_sets == []


@pytest.mark.asyncio
async def test_status_aggregation_counts_by_list() -> None:
    """Status mode should aggregate done/in-progress/blocked/not-started by list."""
    client = _FakeClickUpClient()
    engine = SyncEngine(client)

    folder = await client.create_folder("space-1", "014-spec-014")
    list_ = await client.create_list(folder["id"], "015-spec-015")
    parent = await client.create_task(list_["id"], "015:US1")
    st1 = await client.create_task(list_["id"], "015:T001 - Task T001", parent=parent["id"])
    st2 = await client.create_task(list_["id"], "015:T002 - Task T002", parent=parent["id"])
    st3 = await client.create_task(list_["id"], "015:T003 - Task T003", parent=parent["id"])
    st4 = await client.create_task(list_["id"], "015:T004 - Task T004", parent=parent["id"])
    client.subtasks[st1["id"]]["status"] = {"status": "done"}
    client.subtasks[st2["id"]]["status"] = {"status": "in progress"}
    client.subtasks[st3["id"]]["status"] = {"status": "blocked"}
    client.subtasks[st4["id"]]["status"] = {"status": "open"}

    manifest = SyncManifest(
        version="1",
        workspace_id="team-1",
        space_id="space-1",
        lists={"015": list_["id"]},
        subtasks={
            "015:T001": st1["id"],
            "015:T002": st2["id"],
            "015:T003": st3["id"],
            "015:T004": st4["id"],
        },
    )

    summary = await engine.status_from_manifest(manifest)
    list_status = summary.by_list["015"]

    assert list_status.done == 1
    assert list_status.in_progress == 1
    assert list_status.blocked == 1
    assert list_status.not_started == 1
    assert list_status.drift == []


@pytest.mark.asyncio
async def test_status_drift_reports_missing_manifest_subtasks() -> None:
    """Status mode should report drift when manifest subtask IDs are missing in ClickUp."""
    client = _FakeClickUpClient()
    engine = SyncEngine(client)

    folder = await client.create_folder("space-1", "014-spec-014")
    list_ = await client.create_list(folder["id"], "015-spec-015")
    parent = await client.create_task(list_["id"], "015:US1")
    st1 = await client.create_task(list_["id"], "015:T001 - Task T001", parent=parent["id"])
    client.subtasks[st1["id"]]["status"] = {"status": "done"}

    manifest = SyncManifest(
        version="1",
        workspace_id="team-1",
        space_id="space-1",
        lists={"015": list_["id"]},
        subtasks={
            "015:T001": st1["id"],
            "015:T999": "subtask-missing",
        },
    )

    summary = await engine.status_from_manifest(manifest)
    list_status = summary.by_list["015"]
    assert list_status.done == 1
    assert list_status.drift == ["015:T999"]
