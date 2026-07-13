"""Manifest loading/saving helpers for ClickUp sync."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from src.mcp_clickup import SyncManifest

MANIFEST_VERSION = "1"


class ManifestVersionError(ValueError):
    """Raised when the manifest schema version is unsupported."""


class ClickUpTaskMappingError(ValueError):
    """Raised when a ClickUp task cannot be resolved to exactly one repo task."""


def task_manifest_key(feature_num: str, group_title: str) -> str:
    """Build canonical manifest key for a ClickUp parent task."""
    return f"{feature_num}:{group_title}"


def feature_projection_manifest_key(feature_num: str) -> str:
    """Build canonical manifest key for one feature-level projection record."""
    return feature_num


def subtask_manifest_key(feature_num: str, task_id: str) -> str:
    """Build canonical manifest key for a ClickUp subtask."""
    return f"{feature_num}:{task_id}"


def task_projection_manifest_key(feature_num: str, task_id: str) -> str:
    """Build canonical manifest key for one executable task projection record."""
    return subtask_manifest_key(feature_num, task_id)


def resolve_task_projection_mapping(
    manifest: SyncManifest,
    clickup_task_id: str,
) -> dict[str, object]:
    """Resolve one ClickUp subtask id back to exactly one repo task projection."""
    normalized_task_id = str(clickup_task_id).strip()
    matches: list[dict[str, object]] = []
    for key, payload in manifest.task_projection_meta.items():
        if str(payload.get("subtask_id", "")).strip() != normalized_task_id:
            continue
        feature_num, _, task_id = str(key).partition(":")
        match = dict(payload)
        match.setdefault("feature_num", feature_num)
        match.setdefault("task_id", task_id)
        match.setdefault("task_key", key)
        matches.append(match)

    if not matches:
        raise ClickUpTaskMappingError(f"mapping_not_found:{normalized_task_id}")
    if len(matches) != 1:
        raise ClickUpTaskMappingError(f"ambiguous_mapping:{normalized_task_id}")
    return matches[0]


def load_manifest(path: Path) -> SyncManifest:
    """Load and validate a sync manifest file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = str(payload.get("version", ""))
    if version != MANIFEST_VERSION:
        raise ManifestVersionError(
            f"Unsupported manifest version '{version}', expected '{MANIFEST_VERSION}'"
        )

    return SyncManifest(
        version=version,
        workspace_id=str(payload.get("workspace_id", "")),
        space_id=str(payload.get("space_id", "")),
        folders=dict(payload.get("folders", {})),
        lists=dict(payload.get("lists", {})),
        tasks=dict(payload.get("tasks", {})),
        subtasks=dict(payload.get("subtasks", {})),
        feature_projection_meta={
            str(key): dict(value)
            for key, value in dict(payload.get("feature_projection_meta", {})).items()
        },
        task_projection_meta={
            str(key): dict(value)
            for key, value in dict(payload.get("task_projection_meta", {})).items()
        },
    )


def save_manifest(path: Path, manifest: SyncManifest) -> None:
    """Persist a sync manifest via atomic os.replace swap."""
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)
