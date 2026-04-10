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

## Next Steps

- Read the feature specification: [spec.md](./spec.md)
- Review design artifacts: [plan.md](./plan.md), [data-model.md](./data-model.md)
- Move to solution design after plan review: `/speckit.solution`
