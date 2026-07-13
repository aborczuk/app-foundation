# app-foundation Quickstart

## Overview

This repository uses a **specification-driven pipeline** (speckit) for feature development. Every feature flows through research, planning, tasking, implementation, and QA before closure.

## Prerequisites

- Python 3.12+
- `uv` package manager
- Git

## Bootstrap

```bash
git clone https://github.com/YOUR-ORG/app-foundation.git
cd app-foundation
uv sync
```

## Development Workflow

### 1. Start a Feature

Use speckit commands to drive the pipeline:

```bash
# Create specification
/speckit.specify "Your feature description"

# Research and plan
/speckit.research
/speckit.plan

# Generate tasks
/speckit.tasking
```

### 2. Implement Tasks

Implement one task at a time using the task entry in `tasks.md` as your contract:

```bash
/speckit.implement --feature-id 023 --task-id T001
```

Each executable task entry in `tasks.md` carries the task contract, including:
- **Acceptance Criteria / Independent Test** — what must be true for the task to be complete
- **Primary Edit Seam** — the main implementation target
- **Required Edits** — concrete changes to make
- **Tests to Add/Update** — test coverage requirements

### 3. Run Behavioral QA

After implementation, QA verifies your work against the acceptance criteria:

```bash
# Validate an edit batch through the guarded workflow
uv run python scripts/edit_code.py validate \
  --paths src/mcp_codebase/server.py \
  --tests tests/unit/test_pipeline_driver.py

# For the full closeout flow on a task, use the sync handoff command
uv run python scripts/edit_code.py sync \
  --paths src/mcp_codebase/server.py \
  --tests tests/unit/test_pipeline_driver.py \
  --commit-message "Describe one coherent edit unit" \
  --handoff \
  --feature-id 023 \
  --task-id T001
```

The QA agent:
1. Reads the HUD acceptance criteria
2. Runs actual tests for changed files
3. Checks for implementation drift
4. Emits `PASS` or `FIX_REQUIRED`

**QA is mandatory** — tasks cannot close without a PASS verdict.

### 4. Close Task

If QA passes, close the task:

```bash
python scripts/speckit_closeout_task.py \
  --feature-id 023 \
  --task-id T001 \
  --tasks-file specs/023-*/tasks.md \
  --ledger-file .speckit/task-ledger.jsonl \
  --commit-sha $(git rev-parse HEAD) \
  --qa-run-id offline-qa-t001-20260425T120000Z \
  --json
```

## Key Scripts

| Script | Purpose |
|---|---|
| `scripts/edit_code.py` | Canonical validate/refresh/sync workflow wrapper |
| `scripts/offline_qa.py` | Schema + behavioral QA verifier |
| `scripts/speckit_behavioral_qa.py` | Runs tests and checks drift |
| `scripts/speckit_closeout_task.py` | Closes task if QA passed |
| `scripts/speckit_offline_qa_handoff.py` | Orchestrates QA pipeline |
| `scripts/task_ledger.py` | Task event audit trail |
| `scripts/pipeline_ledger.py` | Feature phase transitions |

## QA Rules

- **Missing acceptance criteria** → `FIX_REQUIRED`
- **Tests fail** → `FIX_REQUIRED`
- **Implementation drift** (wrong files changed) → `FIX_REQUIRED`
- **No test evidence** → `FIX_REQUIRED`

To skip behavioral QA for legacy specs:
```bash
python scripts/offline_qa.py --payload-file ... --skip-behavioral
```

## Testing

```bash
# Run targeted tests through the guard
uv run --no-sync python scripts/pytest_guard.py run -- tests/unit/test_pipeline_driver.py -q

# Run validation for a coherent edit batch
uv run python scripts/edit_code.py validate --paths scripts/pipeline_driver.py --tests tests/unit/test_pipeline_driver.py
```

## Governance

- `constitution.md` — Pipeline constitution
- `AGENTS.md` — Agent instructions
- `CLAUDE.md` — AI assistant context
- `docs/architecture/` — Canonical repo and subsystem maps
- `docs/governance/` — Detailed governance docs

## Services

```bash
# Control plane
uvicorn src.clickup_control_plane.app:app --host 0.0.0.0 --port 8000

# MCP servers
uv run python -m src.mcp_codebase
uv run python -m src.mcp_trello
uv run python -m src.mcp_clickup
```
