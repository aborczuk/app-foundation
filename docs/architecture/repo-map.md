# Repository Map

Status: canonical
Last reviewed: 2026-05-09
Owner: repository architecture

## Purpose

This document is the first-stop map for agents and maintainers working in `app-foundation`.

Use it to answer four questions quickly:

- what major areas exist
- which sources are canonical
- where to start reading for a given task
- which docs describe runtime behavior versus workflow behavior

## Top-Level Areas

| Area | Role |
|---|---|
| `src/` | Runtime packages and MCP servers |
| `scripts/` | Deterministic orchestration, validation, guards, and repo tooling |
| `tests/` | Unit, contract, and integration verification |
| `docs/architecture/` | Stable codebase maps for agents and maintainers |
| `docs/governance/` | Process, contract, and workflow documentation |
| `specs/` | Feature-scoped design records and task artifacts |
| `.claude/commands/` | Step-level command contracts |
| `.speckit/` | Runtime ledgers, locks, manifests, and task execution artifacts |

## Canonical Sources Of Truth

| Concern | Canonical source |
|---|---|
| Agent operating rules for this repo | `AGENTS.md` |
| Governance principles and quality gates | `constitution.md` |
| Workflow execution order and command semantics | `docs/architecture/workflow-overview.md` and `docs/governance/` |
| Manifested command artifacts and routing metadata | `command-manifest.yaml` |
| Runtime package boundaries | `docs/architecture/runtime-overview.md` |
| Feature-specific design intent | `specs/<feature-id>-*/` |

## Subsystems

| Subsystem | Primary doc | Primary entrypoints |
|---|---|---|
| ClickUp control plane | `docs/architecture/clickup-control-plane.md` | `src/clickup_control_plane/app.py`, `src/clickup_control_plane/service.py` |
| Codebase MCP / LSP / vector index | `docs/architecture/mcp-codebase.md` | `src/mcp_codebase/server.py`, `src/mcp_codebase/index/service.py` |
| ClickUp sync bridge | `docs/architecture/mcp-clickup.md` | `src/mcp_clickup/__main__.py`, `src/mcp_clickup/sync_engine.py` |
| Trello sync bridge | `docs/architecture/mcp-trello.md` | `src/mcp_trello/server.py`, `src/mcp_trello/sync_engine.py` |
| Script/tooling surface | `docs/architecture/scripts-index.md` | `scripts/edit_code.py`, `scripts/read_code.py`, `scripts/pipeline_driver.py` |
| Speckit workflow | `docs/architecture/workflow-overview.md` | `scripts/pipeline_driver.py`, `scripts/pipeline_ledger.py`, `scripts/task_ledger.py` |

## Runtime Versus Workflow

Keep these concerns separate when reading:

- Runtime architecture describes deployed or directly executed product surfaces under `src/`.
- Workflow architecture describes how the repository plans, validates, routes, and closes work through `scripts/`, manifests, ledgers, and gates.

If a task asks "how does the app behave at runtime?", start in `docs/architecture/runtime-overview.md`.

If a task asks "how does work move through the repo process?", start in `docs/architecture/workflow-overview.md`.

## Common Task Entry Points

See `docs/architecture/entry-points.md` for the task-oriented map.

Short version:

- webhook intake or dispatch behavior: `src/clickup_control_plane/`
- semantic code reading or vector index behavior: `src/mcp_codebase/`
- ClickUp list/task reconciliation: `src/mcp_clickup/`
- Trello sync behavior: `src/mcp_trello/`
- phase routing, task gating, or ledger sequencing: `scripts/pipeline_driver.py`, `scripts/pipeline_ledger.py`, `scripts/task_ledger.py`
- repo validation and handoff flow: `scripts/edit_code.py`

## Known Historical Surfaces

- `specs/` contains many implementation records and feature-local docs, but it is not the canonical explanation of stable repo architecture.
- Some governance docs were written during migration from mirrored manifest docs. `command-manifest.yaml` at repo root is the canonical manifest.
- Feature-specific handoff docs in `docs/governance/` may be useful context, but they do not override canonical runtime or workflow maps.

## Reading Order

For broad orientation:

1. `AGENTS.md`
2. `docs/architecture/source-of-truth.md`
3. `docs/architecture/repo-map.md`
4. `docs/architecture/runtime-overview.md`
5. `docs/architecture/workflow-overview.md`
6. the relevant subsystem doc under `docs/architecture/`

