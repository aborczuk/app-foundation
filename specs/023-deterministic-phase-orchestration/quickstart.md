# Quickstart: Deterministic Phase Orchestration

Get the planning and execution contract checks running locally in about 10 minutes.

---

## What This Feature Is

Deterministic phase orchestration for feature `023` makes the pipeline driver validate phase outputs before any ledger event is emitted. The feature keeps permissioning, validation, and event emission separate so phase progression stays deterministic and auditable.

## How It Runs

### 1. Set up the workspace

```bash
cd /Users/andreborczuk/app-foundation
uv sync
```

### 2. Confirm the repo wiring is ready

```bash
uv run python scripts/pipeline_ledger.py validate-manifest
uv run python scripts/validate_command_script_coverage.py --json

uv run python scripts/speckit_gate_status.py --mode plan --feature-dir specs/023-deterministic-phase-orchestration --json
```

### 3. Resolve the current phase without side effects

```bash
uv run python scripts/pipeline_driver.py --feature-id 023 --dry-run --json
```

Expected: JSON payload with `phase_state` and deterministic `step_result`.

### 4. Run with an explicit approval token when execution is permitted

```bash
uv run python scripts/pipeline_driver.py --feature-id 023 --phase plan --approval-token phase:approved --json
```

Expected: valid step envelope; blocked or error outcomes are deterministic and machine-readable.

## What Was Done

This feature now keeps the original `T001-T029` task graph intact and appends the sketch-derived delta as `T030-T049` in `tasks.md`. The implementation run followed the task ledger lifecycle through start, discovery, QA, and close events for the delta tasks.

For task-by-task details, see [`tasks.md`](./tasks.md). For the implementation and closeout trail, inspect the task ledger and the current branch history.

## Implementation Notes

- The regenerated sketch work was appended as a delta instead of overwriting the existing task history.
- Targeted QA passed for the driver flow, contract surface, and unit coverage around the delta work.
- Task ledger state for feature `023` is now fully closed for the current task graph.
- Markdown doc-shape validation now rejects compact command docs that still embed executable gate/append procedures, so the producer-only command-doc cleanup stays enforced while the docs are migrated.

## Decision Log

- Preserved the original `T001-T029` task graph and appended the regenerated sketch work as `T030-T049` so the ledger and HUDs stay aligned.
- Kept the delta task lifecycle explicit in the task ledger with discovery, QA, and close events.
- Updated the operator quickstart to point readers at `tasks.md` for the combined base + delta plan.
- Tightened command-doc validation so executable gate/append procedures are rejected instead of slipping through under a compact/expanded heading shape.

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

Use the operator runbook below to verify the approval path and the failure-sidecar path when re-running the feature.

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

- Review [`tasks.md`](./tasks.md) for the task-by-task execution log.
- Inspect commits `0592df6` and `1a199a8` for the implementation and closeout trail.
- Re-run the smoke test and validation procedure if you change the driver, ledger, or manifest wiring.
