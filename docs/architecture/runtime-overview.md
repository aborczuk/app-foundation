# Runtime Overview

Status: canonical
Last reviewed: 2026-05-09
Owner: runtime architecture

## Purpose

This document maps the runtime surfaces implemented under `src/`.

It answers:

- which services and tools actually run
- how runtime packages are separated
- where external integrations enter the codebase
- which files are the correct starting seams

## Runtime Components

| Component | Package | Entry surface | External dependencies |
|---|---|---|---|
| ClickUp control plane | `src/clickup_control_plane` | `src/clickup_control_plane/app.py` | ClickUp webhook payloads, ClickUp API, n8n |
| Codebase MCP / LSP server | `src/mcp_codebase` | `python -m src.mcp_codebase` | FastMCP, Pyright, Chroma/fastembed index |
| ClickUp sync bridge | `src/mcp_clickup` | `python -m src.mcp_clickup` | ClickUp API, local spec artifacts |
| Trello sync bridge | `src/mcp_trello` | `python -m src.mcp_trello` | Trello API, local `tasks.md` artifacts |

## Package Boundaries

### `src/clickup_control_plane`

Handles webhook intake, dispatch policy, task-run state, reconciliation, and workflow completion callbacks.

### `src/mcp_codebase`

Handles codebase intelligence:

- FastMCP tool registration
- Pyright-backed diagnostics and type lookups
- vector index build/query/refresh operations
- health and recovery checks

### `src/mcp_clickup`

Handles synchronization between feature/task artifacts in the repo and ClickUp folders, lists, tasks, subtasks, and custom fields.

### `src/mcp_trello`

Handles synchronization between `tasks.md` and Trello board lists/cards with deterministic deduplication markers.

## External Integration Boundaries

| Integration | Boundary files |
|---|---|
| ClickUp webhook + outcome/status APIs | `src/clickup_control_plane/app.py`, `src/clickup_control_plane/clickup_client.py` |
| n8n workflow dispatch | `src/clickup_control_plane/dispatcher.py`, `src/clickup_control_plane/service.py` |
| Pyright | `src/mcp_codebase/pyright_client.py`, `src/mcp_codebase/server.py` |
| Vector index storage/query | `src/mcp_codebase/index/service.py`, `src/mcp_codebase/index/store/` |
| ClickUp sync APIs | `src/mcp_clickup/clickup_client.py`, `src/mcp_clickup/sync_engine.py` |
| Trello sync APIs | `src/mcp_trello/trello_client.py`, `src/mcp_trello/sync_engine.py` |

## Runtime Invariants

- Runtime code lives in Python packages under `src/`.
- External credentials and tokens are loaded from environment variables, not hardcoded into runtime modules.
- Synchronization tools are designed to be idempotent or explicitly fail on ambiguous state.
- Runtime packages should expose clear package-level entrypoints instead of routing users through arbitrary scripts.

## Recommended Reading Order

1. This file
2. The relevant subsystem doc under `docs/architecture/`
3. The package entrypoint under `src/<package>/`
4. Related tests under `tests/unit/`, `tests/contract/`, and `tests/integration/`

