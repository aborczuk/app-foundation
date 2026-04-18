# Quickstart: Deterministic Phase Orchestration

Get the planning and execution contract checks running locally in about 10 minutes.

---

## Prerequisites

- Python 3.12 + `uv`: `uv --version`
- Git repository initialized: `git rev-parse --show-toplevel`
- Feature artifacts present: `specs/023-deterministic-phase-orchestration/spec.md`

---

## Installation

### 1. Set up environment

```bash
cd /Users/andreborczuk/app-foundation
uv sync
```

### 2. Validate manifest wiring

```bash
uv run python scripts/pipeline_ledger.py validate-manifest
uv run python scripts/validate_command_script_coverage.py --json
```

### 3. Validate plan gate readiness

```bash
uv run python scripts/speckit_gate_status.py --mode plan --feature-dir specs/023-deterministic-phase-orchestration --json
```

---

## Run the Feature

### 1. Resolve current phase without side effects

```bash
uv run python scripts/pipeline_driver.py --feature-id 023 --dry-run --json
```

Expected: JSON payload with `phase_state` and deterministic `step_result`.

### 2. (When permission is required) run with explicit approval token

```bash
uv run python scripts/pipeline_driver.py --feature-id 023 --phase plan --approval-token phase:approved --json
```

Expected: valid step envelope; blocked/error outcomes are deterministic and machine-readable.

---

## Smoke Test

```bash
uv run pytest tests/unit/test_validate_command_script_coverage.py tests/unit/test_pipeline_driver.py tests/integration/test_pipeline_driver_feature_flow.py -q
```

Expected: all tests pass.

```bash
bash scripts/validate_doc_graph.sh
```

Expected: `Doc graph validation PASSED.`

---

## Common Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| Missing canonical manifest | `manifest not found: .../command-manifest.yaml` | Ensure root `command-manifest.yaml` exists and is committed. |
| Feature branch created from wrong base | Feature branch ancestry does not include latest `main` | Use `.specify/scripts/bash/create-new-feature.sh --base main ...` or rely on new default behavior. |
| Plan gate fails | `missing_requirements_checklist` or incomplete checklist items | Complete `specs/023.../checklists/requirements.md` and rerun gate. |

---

## Next Steps

- Run `/speckit.planreview` to confirm there are no unresolved planning ambiguities.
- If feasibility questions are introduced, run `/speckit.feasibilityspike`.
- Continue to `/speckit.solution` after `plan_approved` is emitted.
