"""Sync engine for ClickUp bootstrap and reconciliation behavior."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, Protocol

from src.mcp_clickup import (
    ListStatus,
    SpecArtifact,
    StatusSummary,
    SyncManifest,
    SyncReport,
    Task,
    TaskGroup,
)
from src.mcp_clickup.manifest import subtask_manifest_key, task_manifest_key

_REQUIRED_ROUTING_FIELDS = ("workflow_type", "context_ref", "execution_policy")


class ManifestRebuildAmbiguousError(ValueError):
    """Raised when missing-manifest recovery has ambiguous key matches."""


class MissingCustomFieldsError(ValueError):
    """Raised when a list is missing required routing metadata fields."""

    def __init__(self, list_name: str, missing_fields: list[str]) -> None:
        """Initialize."""
        self.list_name = list_name
        self.missing_fields = missing_fields
        joined = ", ".join(missing_fields)
        super().__init__(f"List '{list_name}' is missing required custom fields: {joined}")


class ClickUpClientProtocol(Protocol):
    """Required client operations for sync orchestration."""

    async def get_space(self, space_id: str) -> dict[str, Any]:
        """Fetch a ClickUp Space by id."""
        ...
    async def list_folders(self, space_id: str) -> list[dict[str, Any]]:
        """List folders under a ClickUp space."""
        ...
    async def create_folder(self, space_id: str, name: str) -> dict[str, Any]:
        """Create a folder under a ClickUp space."""
        ...
    async def list_lists(self, folder_id: str) -> list[dict[str, Any]]:
        """List lists under a ClickUp folder."""
        ...
    async def get_list(self, list_id: str) -> dict[str, Any]:
        """Fetch list metadata by ID."""
        ...
    async def create_list(self, folder_id: str, name: str) -> dict[str, Any]:
        """Create a list under a ClickUp folder."""
        ...
    async def list_tasks(self, list_id: str) -> list[dict[str, Any]]:
        """List parent tasks under a ClickUp list."""
        ...
    async def list_subtasks(self, task_id: str) -> list[dict[str, Any]]:
        """List subtasks for a given parent task."""
        ...
    async def create_task(
        self,
        list_id: str,
        name: str,
        parent: str | None = None,
    ) -> dict[str, Any]:
        """Create a task or subtask in a list."""
        ...
    async def update_task(self, task_id: str, *, name: str) -> dict[str, Any]:
        """Update task mutable fields."""
        ...
    async def list_custom_fields(self, list_id: str) -> list[dict[str, Any]]:
        """List custom fields visible on a list."""
        ...
    async def set_custom_field(self, task_id: str, field_id: str, value: str) -> None:
        """Set a task custom field value."""
        ...


class SyncEngine:
    """Coordinate reconciliation and idempotent ClickUp bootstrap orchestration."""

    def __init__(self, client: ClickUpClientProtocol) -> None:
        """Initialize."""
        self._client = client

    def reconcile_manifest(
        self,
        manifest: SyncManifest | None,
        rebuild_candidates: dict[str, list[str]] | None = None,
    ) -> SyncManifest:
        """Resolve an effective manifest before deciding create actions."""
        if manifest is not None:
            return manifest

        candidates = rebuild_candidates or {}
        ambiguous = [key for key, values in candidates.items() if len(values) > 1]
        if ambiguous:
            joined = ", ".join(sorted(ambiguous))
            raise ManifestRebuildAmbiguousError(f"Ambiguous manifest rebuild keys: {joined}")

        rebuilt = SyncManifest(version="1", workspace_id="", space_id="")
        for key, values in candidates.items():
            if len(values) == 1:
                rebuilt.subtasks[key] = values[0]
        return rebuilt

    async def bootstrap_from_artifacts(
        self,
        *,
        artifacts: list[SpecArtifact],
        space_id: str,
        manifest: SyncManifest | None,
        rebuild_candidates: dict[str, list[str]] | None = None,
        flush_manifest: Callable[[SyncManifest], None] | None = None,
    ) -> SyncReport:
        """Bootstrap ClickUp hierarchy from parsed spec artifacts."""
        flush = flush_manifest or (lambda _: None)
        space = await self._client.get_space(space_id)

        discovered = SyncManifest(version="1", workspace_id="", space_id=space_id)
        candidates = rebuild_candidates
        if manifest is None and rebuild_candidates is None:
            discovered, candidates = await self._discover_existing_state(artifacts, space_id)

        resolved = self.reconcile_manifest(manifest, candidates)
        if manifest is None:
            resolved.folders.update(discovered.folders)
            resolved.lists.update(discovered.lists)
            resolved.tasks.update(discovered.tasks)
            resolved.subtasks.update(discovered.subtasks)

        if not resolved.workspace_id:
            resolved.workspace_id = str(space.get("team_id", ""))
        if not resolved.space_id:
            resolved.space_id = space_id

        report = await self._create_missing_items(
            manifest=resolved,
            artifacts=artifacts,
            field_ids_by_list={},
            flush_manifest=flush,
        )
        flush(resolved)
        return report

    async def status_from_manifest(self, manifest: SyncManifest) -> StatusSummary:
        """Build a grouped, read-only status summary from live ClickUp state."""
        summary = StatusSummary()

        for feature_num, list_id in sorted(manifest.lists.items()):
            list_payload = await self._client.get_list(list_id)
            list_name = str(list_payload.get("name", list_id))
            list_status = ListStatus(feature_num=feature_num, list_name=list_name)

            parent_tasks = await self._client.list_tasks(list_id)
            live_subtasks: dict[str, dict[str, Any]] = {}
            for parent_task in parent_tasks:
                parent_id = str(parent_task.get("id", ""))
                if not parent_id:
                    continue
                for subtask in await self._client.list_subtasks(parent_id):
                    subtask_id = str(subtask.get("id", ""))
                    if subtask_id:
                        live_subtasks[subtask_id] = subtask

            manifest_keys = [
                key for key in sorted(manifest.subtasks.keys()) if key.startswith(f"{feature_num}:")
            ]
            for manifest_key in manifest_keys:
                subtask_id = manifest.subtasks[manifest_key]
                live_subtask = live_subtasks.get(subtask_id)
                if live_subtask is None:
                    list_status.drift.append(manifest_key)
                    continue

                bucket = self._status_bucket(live_subtask)
                if bucket == "done":
                    list_status.done += 1
                elif bucket == "in_progress":
                    list_status.in_progress += 1
                elif bucket == "blocked":
                    list_status.blocked += 1
                else:
                    list_status.not_started += 1

            summary.by_list[feature_num] = list_status

        return summary

    async def _discover_existing_state(
        self,
        artifacts: list[SpecArtifact],
        space_id: str,
    ) -> tuple[SyncManifest, dict[str, list[str]]]:
        """Discover existing ClickUp mappings for deterministic missing-manifest recovery."""
        discovered = SyncManifest(version="1", workspace_id="", space_id=space_id)
        candidates: dict[str, list[str]] = {}

        top_level = [artifact for artifact in artifacts if not artifact.is_phase_spec]
        phase_artifacts = self._phase_artifacts(artifacts)

        folders = await self._client.list_folders(space_id)
        folder_by_name = {str(folder.get("name", "")): str(folder.get("id", "")) for folder in folders}

        for artifact in top_level:
            folder_name = self._folder_name(artifact)
            folder_id = folder_by_name.get(folder_name)
            if folder_id:
                discovered.folders[artifact.feature_num] = folder_id

        for phase in phase_artifacts:
            folder_feature = phase.parent_num or phase.feature_num
            folder_id = discovered.folders.get(folder_feature)
            if not folder_id:
                continue

            lists = await self._client.list_lists(folder_id)
            list_by_name = {str(list_.get("name", "")): str(list_.get("id", "")) for list_ in lists}
            list_name = self._list_name(phase)
            list_id = list_by_name.get(list_name)
            if not list_id:
                continue

            discovered.lists[phase.feature_num] = list_id
            if not phase.has_tasks:
                continue

            tasks = await self._client.list_tasks(list_id)
            tasks_by_name: dict[str, list[str]] = {}
            for task in tasks:
                tasks_by_name.setdefault(str(task.get("name", "")), []).append(str(task.get("id", "")))

            for group in phase.task_groups:
                task_key = task_manifest_key(phase.feature_num, group.title)
                group_ids = tasks_by_name.get(task_key, [])
                if len(group_ids) == 1:
                    parent_task_id = group_ids[0]
                    discovered.tasks[task_key] = parent_task_id
                elif len(group_ids) > 1:
                    candidates[task_key] = group_ids
                    continue
                else:
                    continue

                subtasks = await self._client.list_subtasks(parent_task_id)
                subtasks_by_key: dict[str, list[str]] = {}
                for subtask in subtasks:
                    subtask_name = str(subtask.get("name", ""))
                    subtask_id = str(subtask.get("id", ""))
                    canonical_key = subtask_name.split(" - ", 1)[0]
                    subtasks_by_key.setdefault(canonical_key, []).append(subtask_id)

                for task in group.tasks:
                    subtask_key = subtask_manifest_key(phase.feature_num, task.id)
                    ids = subtasks_by_key.get(subtask_key, [])
                    if len(ids) == 1:
                        discovered.subtasks[subtask_key] = ids[0]
                    elif len(ids) > 1:
                        candidates[subtask_key] = ids

        return discovered, candidates

    async def _create_missing_items(
        self,
        *,
        manifest: SyncManifest,
        artifacts: list[SpecArtifact],
        field_ids_by_list: dict[str, dict[str, str]],
        flush_manifest: Callable[[SyncManifest], None],
    ) -> SyncReport:
        """Create or update missing hierarchy elements from manifest + artifacts."""
        del field_ids_by_list

        report = SyncReport()
        top_level = [artifact for artifact in artifacts if not artifact.is_phase_spec]
        phase_artifacts = self._phase_artifacts(artifacts)

        folders = await self._client.list_folders(manifest.space_id)
        folders_by_name = {str(folder.get("name", "")): dict(folder) for folder in folders}

        for artifact in top_level:
            feature_num = artifact.feature_num
            existing_folder_id = manifest.folders.get(feature_num)
            if existing_folder_id:
                report.skipped += 1
                continue

            folder_name = self._folder_name(artifact)
            folder = folders_by_name.get(folder_name)
            if folder:
                manifest.folders[feature_num] = str(folder.get("id", ""))
                report.skipped += 1
                continue

            created = await self._client.create_folder(manifest.space_id, folder_name)
            manifest.folders[feature_num] = str(created.get("id", ""))
            flush_manifest(manifest)
            report.created += 1

        for phase in phase_artifacts:
            folder_feature = phase.parent_num or phase.feature_num
            folder_id = manifest.folders.get(folder_feature)
            if not folder_id:
                continue

            list_id = manifest.lists.get(phase.feature_num)
            list_name = self._list_name(phase)
            if not list_id:
                lists = await self._client.list_lists(folder_id)
                by_name = {str(item.get("name", "")): dict(item) for item in lists}
                existing_list = by_name.get(list_name)
                if existing_list:
                    list_id = str(existing_list.get("id", ""))
                    manifest.lists[phase.feature_num] = list_id
                    report.skipped += 1
                else:
                    created_list = await self._client.create_list(folder_id, list_name)
                    list_id = str(created_list.get("id", ""))
                    manifest.lists[phase.feature_num] = list_id
                    flush_manifest(manifest)
                    report.created += 1
            else:
                report.skipped += 1

            if not phase.has_tasks or not phase.task_groups:
                report.skipped += 1
                continue

            field_ids = await self._required_field_ids(list_id, list_name)

            for group in phase.task_groups:
                parent_task_id, parent_status = await self._ensure_parent_task(
                    manifest=manifest,
                    phase=phase,
                    group=group,
                    list_id=list_id,
                )
                if parent_status == "created":
                    flush_manifest(manifest)
                    report.created += 1
                elif parent_status == "updated":
                    report.updated += 1
                else:
                    report.skipped += 1

                for task in group.tasks:
                    subtask_id, subtask_status = await self._ensure_subtask(
                        manifest=manifest,
                        phase=phase,
                        parent_task_id=parent_task_id,
                        list_id=list_id,
                        task=task,
                    )
                    if subtask_status == "created":
                        flush_manifest(manifest)
                        report.created += 1
                    elif subtask_status == "updated":
                        report.updated += 1
                    else:
                        report.skipped += 1

                    await self._client.set_custom_field(
                        subtask_id,
                        field_ids["workflow_type"],
                        task.workflow_type,
                    )
                    await self._client.set_custom_field(
                        subtask_id,
                        field_ids["context_ref"],
                        task.context_ref,
                    )
                    await self._client.set_custom_field(
                        subtask_id,
                        field_ids["execution_policy"],
                        task.execution_policy,
                    )

        return report

    async def _required_field_ids(self, list_id: str, list_name: str) -> dict[str, str]:
        fields = await self._client.list_custom_fields(list_id)
        by_name = {str(field.get("name", "")): str(field.get("id", "")) for field in fields}

        missing = [name for name in _REQUIRED_ROUTING_FIELDS if not by_name.get(name)]
        if missing:
            raise MissingCustomFieldsError(list_name, missing)

        return {
            "workflow_type": by_name["workflow_type"],
            "context_ref": by_name["context_ref"],
            "execution_policy": by_name["execution_policy"],
        }

    async def _ensure_parent_task(
        self,
        *,
        manifest: SyncManifest,
        phase: SpecArtifact,
        group: TaskGroup,
        list_id: str,
    ) -> tuple[str, str]:
        key = task_manifest_key(phase.feature_num, group.title)
        desired_name = key

        task_id = manifest.tasks.get(key)
        if task_id:
            return task_id, "unchanged"

        tasks = await self._client.list_tasks(list_id)
        matches = [task for task in tasks if str(task.get("name", "")) == desired_name]
        if len(matches) > 1:
            raise ManifestRebuildAmbiguousError(f"Ambiguous parent task match for key '{key}'")
        if len(matches) == 1:
            task_id = str(matches[0].get("id", ""))
            manifest.tasks[key] = task_id
            return task_id, "unchanged"

        created = await self._client.create_task(list_id, desired_name)
        task_id = str(created.get("id", ""))
        manifest.tasks[key] = task_id
        return task_id, "created"

    async def _ensure_subtask(
        self,
        *,
        manifest: SyncManifest,
        phase: SpecArtifact,
        parent_task_id: str,
        list_id: str,
        task: Task,
    ) -> tuple[str, str]:
        key = subtask_manifest_key(phase.feature_num, task.id)
        desired_name = f"{key} - {task.title}"

        subtask_id = manifest.subtasks.get(key)
        if subtask_id:
            return subtask_id, "unchanged"

        subtasks = await self._client.list_subtasks(parent_task_id)
        candidates = [
            subtask
            for subtask in subtasks
            if str(subtask.get("name", "")).split(" - ", 1)[0] == key
        ]

        if len(candidates) > 1:
            raise ManifestRebuildAmbiguousError(f"Ambiguous subtask match for key '{key}'")

        if len(candidates) == 1:
            existing = candidates[0]
            subtask_id = str(existing.get("id", ""))
            current_name = str(existing.get("name", ""))
            manifest.subtasks[key] = subtask_id
            if current_name != desired_name:
                await self._client.update_task(subtask_id, name=desired_name)
                return subtask_id, "updated"
            return subtask_id, "unchanged"

        created = await self._client.create_task(list_id, desired_name, parent=parent_task_id)
        subtask_id = str(created.get("id", ""))
        manifest.subtasks[key] = subtask_id
        return subtask_id, "created"

    @staticmethod
    def _folder_name(artifact: SpecArtifact) -> str:
        return f"{artifact.feature_num}-{artifact.short_name}"

    @staticmethod
    def _list_name(artifact: SpecArtifact) -> str:
        return f"{artifact.feature_num}-{artifact.short_name}"

    @staticmethod
    def _phase_artifacts(artifacts: list[SpecArtifact]) -> list[SpecArtifact]:
        children_by_parent: dict[str, list[SpecArtifact]] = {}
        for artifact in artifacts:
            if artifact.parent_num:
                children_by_parent.setdefault(artifact.parent_num, []).append(artifact)

        phase_artifacts: list[SpecArtifact] = []
        for artifact in artifacts:
            if artifact.is_phase_spec:
                phase_artifacts.append(artifact)
                continue
            if artifact.feature_num not in children_by_parent:
                # Standalone spec acts as its own phase list.
                phase_artifacts.append(
                    SpecArtifact(
                        feature_num=artifact.feature_num,
                        short_name=artifact.short_name,
                        title=artifact.title,
                        spec_dir=artifact.spec_dir,
                        is_phase_spec=False,
                        parent_num=None,
                        has_tasks=artifact.has_tasks,
                        task_groups=artifact.task_groups,
                    )
                )
        return phase_artifacts

    @staticmethod
    def _status_bucket(subtask: dict[str, Any]) -> str:
        """Normalize ClickUp status payloads to reporting buckets."""
        status_payload = subtask.get("status", {})
        if isinstance(status_payload, dict):
            raw = str(status_payload.get("status", "")).strip().lower()
        else:
            raw = str(status_payload).strip().lower()

        if raw in {"done", "complete", "completed", "closed"}:
            return "done"
        if "block" in raw:
            return "blocked"
        if raw in {"in progress", "in_progress", "active", "doing"}:
            return "in_progress"
        return "not_started"


async def run_with_timeout(
    coro: Coroutine[object, object, SyncReport],
    timeout_seconds: float,
) -> SyncReport:
    """Execute a coroutine with timeout/cancel cleanup semantics."""
    return await asyncio.wait_for(coro, timeout=timeout_seconds)
