# Quickstart: Deterministic Pipeline Driver with LLM Handoff

Get plan artifacts and deterministic gates running locally in ~10 minutes.

---

## Prerequisites

- Python 3.12+: `python3 --version`
- `uv` package manager: `uv --version`
- Repo checkout at root with feature branch: `git branch --show-current`

---

## Installation

### 1. Sync project dependencies

```bash
cd /Users/andreborczuk/app-foundation
UV_CACHE_DIR=/tmp/uv-cache uv sync --all-groups
```

### 2. Verify core tooling

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pyright --version
UV_CACHE_DIR=/tmp/uv-cache uv run ruff --version
```

### 3. Ensure feature artifacts exist

```bash
.specify/scripts/bash/setup-plan.sh --json
UV_CACHE_DIR=/tmp/uv-cache uv run python .specify/scripts/pipeline-scaffold.py speckit.plan \
  --feature-dir specs/019-token-efficiency-docs \
  FEATURE_NAME="Deterministic Pipeline Driver with LLM Handoff"
```

---

## Run the Feature

```bash
# 1) Validate specification checklist gate for planning
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/speckit_gate_status.py \
  --mode plan \
  --feature-dir specs/019-token-efficiency-docs \
  --json

# 2) Validate pipeline ledger structure
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/pipeline_ledger.py validate \
  --file .speckit/pipeline-ledger.jsonl
```

Expected results:
- Gate output includes `"ok": true`
- Ledger validation exits with code `0`

---

## Smoke Test

Verify deterministic workflow quality checks pass:

```bash
# Plan gate must pass
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/speckit_gate_status.py \
  --mode plan \
  --feature-dir specs/019-token-efficiency-docs \
  --json

# Lint and type check (project baseline)
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check scripts .claude .specify
UV_CACHE_DIR=/tmp/uv-cache uv run pyright
```

Expected:
- Plan gate returns `ok: true`
- Lint/type checks report no new errors for touched files

---

## Common Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| Using bare `python3` instead of `uv run` | `ModuleNotFoundError: No module named 'yaml'` | Run script as `UV_CACHE_DIR=/tmp/uv-cache uv run python ...` |
| Checklist not generated | Plan gate fails with `missing_requirements_checklist` | Run scaffold: `uv run python .specify/scripts/pipeline-scaffold.py speckit.specify --feature-dir specs/019-token-efficiency-docs FEATURE_NAME=...` |
| Checklist exists but still blocks | Plan gate shows `incomplete_checklist_items` | Mark all checklist rows `[x]` or `[N/A]` in `specs/019-token-efficiency-docs/checklists/requirements.md` |
| uv cache permission error | `Failed to initialize cache ... Operation not permitted` | Set `UV_CACHE_DIR=/tmp/uv-cache` for all uv commands |

---

## Step Result Contract & Operator Runbook

All orchestrator steps emit a canonical result envelope with deterministic routing semantics:

### Result Envelope Structure

```json
{
  "schema_version": "1.0.0",
  "ok": true|false,
  "exit_code": 0|1|2,
  "correlation_id": "run_ID:step_name",
  
  // Exit code 0 (success): next phase specified
  "next_phase": "phase_name",
  
  // Exit code 1 (blocked): gate + reasons specified
  "gate": "gate_name",
  "reasons": ["reason1", "reason2"],
  
  // Exit code 2 (error): error details specified
  "error_code": "error_type",
  "debug_path": ".speckit/failures/diagnostic.json"
}
```

### Exit Code Semantics

| Code | Meaning | Action | Example |
|------|---------|--------|---------|
| **0** | Success | Proceed to next phase | Spec approved, move to planning |
| **1** | Blocked | Review gate/reasons, human action needed | Plan rejected (high risk), needs rework |
| **2** | Error | Check debug_path for diagnostics, may retry | LLM timeout, check logs in sidecar |

### Reading Step Results

1. **Check exit_code first** — determines the routing path
2. **For exit_code=0**: Read `next_phase` to determine next step
3. **For exit_code=1**: Read `gate` and `reasons` to understand what's blocking
4. **For exit_code=2**: Read `error_code` and load the sidecar file at `debug_path` for full diagnostics

### Debugging Failed Steps (exit_code=2)

Use the drill-down command to get detailed diagnostics:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/pipeline_driver.py \
  --feature-id 019 \
  --drill-down <correlation_id>
```

This loads the sidecar diagnostics file and returns:
- Initial failure output (stdout/stderr)
- Rerun output with `SPECKIT_VERBOSE=1`
- Full command context for reproduction

---

## Next Steps

- Read the feature specification: [spec.md](./spec.md)
- Review design artifacts: [plan.md](./plan.md), [data-model.md](./data-model.md)
- Move to solution design after plan review: `/speckit.solution`
