# Behavior Map: Speckit ClickUp Sync

This file maps the runtime behavior of the ClickUp sync module to the modules that own it.

## Scope

- Runtime mode: ClickUp sync CLI (`uv run python -m src.mcp_clickup`)
- Main behaviors: artifact discovery, manifest persistence, bootstrap reconciliation, status reporting

## How To Read

- `Entrypoint`: first function or module that owns the behavior.
- `Observe`: visible signal that the behavior is active.
- `Tests`: fastest file to inspect when changing the behavior.

## Behavior Catalog

| Behavior | Entrypoint | Core Code Path | Observe | Tests |
|---|---|---|---|---|
| Spec artifact discovery | `src/mcp_clickup/artifact_parser.py::discover_spec_artifacts` | Walks repo spec directories and builds `SpecArtifact` records for top-level and phase specs | Parsed artifact list contains feature numbers, titles, and phase flags | `tests/unit/mcp_clickup/test_artifact_parser.py` |
| Manifest load/save | `src/mcp_clickup/manifest.py::load_manifest` / `save_manifest` | Loads versioned JSON, validates the manifest version, and writes atomically via temp-file swap | Manifest round-trips without partial writes | `tests/unit/mcp_clickup/test_manifest.py` |
| Manifest reconciliation | `src/mcp_clickup/sync_engine.py::SyncEngine.reconcile_manifest` | Accepts a current manifest or rebuild candidates and rejects ambiguous rebuild keys | Ambiguous rebuild keys raise `ManifestRebuildAmbiguousError` | `tests/unit/mcp_clickup/test_sync_engine.py` |
| Bootstrap from artifacts | `src/mcp_clickup/sync_engine.py::SyncEngine.bootstrap_from_artifacts` | Discovers existing ClickUp state, creates missing folders/lists/tasks/subtasks, and flushes the manifest | `SyncReport` records created, updated, and skipped items | `tests/unit/mcp_clickup/test_sync_engine.py` |
| Status summaries | `src/mcp_clickup/sync_engine.py::SyncEngine.status_from_manifest` | Reads live ClickUp subtasks for each manifest list and groups them by status bucket | `StatusSummary` contains per-list counts and drift markers | `tests/unit/mcp_clickup/test_sync_engine.py` |
| CLI lifecycle | `src/mcp_clickup/__main__.py` | Handles `bootstrap` and `status` subcommands, runtime env checks, and error rendering | CLI exits with sanitized error messages on missing env or API failures | `tests/unit/mcp_clickup/test_manifest.py`, `tests/unit/mcp_clickup/test_sync_engine.py` |

## Maintenance Rule

When changing the sync flow, manifest format, or bootstrap/status behavior, update one row in this file in the same PR.
