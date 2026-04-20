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

## Validation Procedure

Use the operator runbook below to verify the approval path and the failure-sidecar path before handing off to implementation.

1. Dry-run the driver to confirm phase resolution is side-effect free:

   ```bash
   uv run python scripts/pipeline_driver.py --feature-id 023 --dry-run --json
   ```

   Expected: JSON includes `phase_state` and a deterministic `step_result`, with no ledger mutation.
2. Verify the approval workflow with an explicit token:

   ```bash
   uv run python scripts/pipeline_driver.py --feature-id 023 --phase plan --approval-token phase:approved --json
   ```

   Expected: `ok=true`, `exit_code=0`, and a machine-readable `next_phase`.
3. Verify the failure-sidecar workflow on a blocked or runtime-error path:

   ```bash
   uv run pytest tests/unit/test_pipeline_driver.py -k "timeout_routes_runtime_failure or invalid_json_persists_runtime_sidecar" -q
   ```

   Expected: runtime-failure regressions pass and confirm `debug_path` is populated in the sidecar payload while the ledger remains unchanged.

---

## Operator Handoff

The solution phase is a producer-vs-driver ownership boundary: `/speckit.solution` produces the `solution_approved` payload, and the pipeline driver records the event after the payload is accepted.

- Keep the command doc focused on payload production during migration-safe updates.
- Do not hand-write `.speckit/pipeline-ledger.jsonl`; rerun `/speckit.solution` after manifest or command-doc changes instead.
- After `plan_approved` is emitted, continue to `/speckit.solution`; after `solution_approved` is recorded, move on to `/speckit.e2e` or `/speckit.implement` as appropriate.

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
