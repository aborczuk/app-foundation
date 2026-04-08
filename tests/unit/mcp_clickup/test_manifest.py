"""Regression tests for manifest versioning and atomic writes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.mcp_clickup.manifest as manifest_module
from src.mcp_clickup import SyncManifest
from src.mcp_clickup.manifest import ManifestVersionError, load_manifest, save_manifest


def test_load_manifest_rejects_unknown_schema_version(tmp_path: Path) -> None:
    """Unknown manifest schema versions should fail fast."""
    manifest_path = tmp_path / "clickup-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": "999",
                "workspace_id": "w1",
                "space_id": "s1",
                "folders": {},
                "lists": {},
                "tasks": {},
                "subtasks": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ManifestVersionError):
        load_manifest(manifest_path)


def test_save_manifest_writes_via_atomic_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Manifest writes should use os.replace for atomic persistence."""
    manifest_path = tmp_path / "clickup-manifest.json"
    calls: list[tuple[str, str]] = []

    real_replace = manifest_module.os.replace

    def _capture_replace(src: str | Path, dst: str | Path) -> None:
        calls.append((str(src), str(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(manifest_module.os, "replace", _capture_replace)

    manifest = SyncManifest(
        version="1",
        workspace_id="w1",
        space_id="s1",
        folders={"014": "f1"},
        lists={"015": "l1"},
        tasks={"015:US1": "t1"},
        subtasks={"015:T001": "st1"},
    )

    save_manifest(manifest_path, manifest)

    assert manifest_path.exists()
    assert len(calls) == 1
    assert calls[0][1] == str(manifest_path)
    loaded = load_manifest(manifest_path)
    assert loaded.subtasks["015:T001"] == "st1"
