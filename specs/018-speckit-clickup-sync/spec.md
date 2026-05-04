# Feature Specification: Speckit ClickUp Sync

**Feature Branch**: `018-speckit-clickup-sync`
**Status**: Canonical
**Last Updated**: 2026-05-04

## One-Line Purpose

Synchronize parsed speckit artifacts and task metadata into ClickUp folders, lists, tasks, and subtasks.

## Consumer & Context

The ClickUp sync CLI reads spec artifacts from the repository, loads or rebuilds a manifest, reconciles hierarchy against live ClickUp state, and reports a status summary for each feature list.

## Scope

- `src/mcp_clickup/artifact_parser.py::discover_spec_artifacts`
- `src/mcp_clickup/manifest.py::{load_manifest, save_manifest}`
- `src/mcp_clickup/sync_engine.py::SyncEngine`
- `src/mcp_clickup/__main__.py`

## Core Behaviors

- Parse repository spec directories into `SpecArtifact` records.
- Load and save the ClickUp manifest as atomic JSON.
- Reconcile an existing manifest with live ClickUp state or a rebuild candidate set.
- Bootstrap folders, lists, tasks, and subtasks from parsed artifacts when the manifest is missing.
- Produce grouped status summaries from the manifest against live ClickUp subtasks.

## Verification Notes

- `tests/unit/mcp_clickup/test_artifact_parser.py`
- `tests/unit/mcp_clickup/test_manifest.py`
- `tests/unit/mcp_clickup/test_sync_engine.py`
