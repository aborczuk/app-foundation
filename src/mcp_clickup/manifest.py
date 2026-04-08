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


def task_manifest_key(feature_num: str, group_title: str) -> str:
    """Build canonical manifest key for a ClickUp parent task."""
    return f"{feature_num}:{group_title}"


def subtask_manifest_key(feature_num: str, task_id: str) -> str:
    """Build canonical manifest key for a ClickUp subtask."""
    return f"{feature_num}:{task_id}"


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
