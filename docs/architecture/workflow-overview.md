# Workflow Overview

Status: canonical
Last reviewed: 2026-05-09
Owner: workflow architecture

## Purpose

This document maps how work moves through the repository workflow, independent of runtime application behavior.

## Core Workflow Surfaces

| Concern | Primary files |
|---|---|
| Repo operating constraints | `AGENTS.md`, `constitution.md` |
| Command contracts | `.claude/commands/speckit.*.md` |
| Artifact and routing registry | `command-manifest.yaml` |
| Feature-level phase transitions | `scripts/pipeline_ledger.py` |
| Task-level ordering and closeout | `scripts/task_ledger.py` |
| Deterministic phase orchestration | `scripts/pipeline_driver.py`, `scripts/pipeline_driver_state.py`, `scripts/pipeline_driver_contracts.py` |
| Edit/validation/handoff loop | `scripts/edit_code.py` |
| Deterministic guards | `scripts/pytest_guard.py`, `scripts/ruff_guard.py`, `scripts/pyright_guard.py`, `scripts/git_diff_guard.py` |

## Workflow Layers

### Command Layer

Command behavior is described in `.claude/commands/speckit.*.md`.

### Manifest Layer

`command-manifest.yaml` records:

- command descriptions
- driver routing mode
- script dependencies
- artifacts
- emitted events

### State Layer

State is split between:

- feature-level events in `.speckit/pipeline-ledger.jsonl`
- task-level events in `.speckit/task-ledger.jsonl`
- runtime lock files and handoff artifacts under `.speckit/`

### Execution Layer

The pipeline driver resolves current state, validates the requested command, loads route metadata, and executes deterministic or generative work.

### Validation Layer

Validation is not ad hoc. The canonical loop runs through guarded scripts and `scripts/edit_code.py`.

## Workflow Invariants

- `command-manifest.yaml` at repo root is the canonical manifest.
- Ledgers are append-only and must be accessed through their scripts, not by reading JSONL files directly.
- Feature state and task state are separate concerns.
- Guards and validation scripts are part of the workflow contract, not optional helper scripts.
- `specs/` artifacts describe features; they do not replace repo-wide workflow documentation.

## Related Deep-Dive Docs

- `docs/governance/pipeline-driver-readme.md`
- `docs/governance/speckit-end-to-end.md`
- `docs/governance/phase-execution.md`
- `docs/governance/how-to-add-speckit-step.md`

## Reading Order

1. `AGENTS.md`
2. `docs/architecture/source-of-truth.md`
3. `docs/architecture/workflow-overview.md`
4. `docs/governance/speckit-end-to-end.md`
5. `docs/governance/pipeline-driver-readme.md`

