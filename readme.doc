# Pipeline Driver Handoff (Feature 019)

## What Was Built

The deterministic pipeline driver stack is implemented and tested:

- `scripts/pipeline_driver.py`
- `scripts/pipeline_driver_contracts.py`
- `scripts/pipeline_driver_state.py`
- related tests in `tests/unit/test_pipeline_driver.py` and `tests/integration/test_pipeline_driver_feature_flow.py`
- governance/coverage checks wired via `scripts/validate_command_script_coverage.py` and `scripts/speckit_gate_status.py`

The core behavior now exists for:

- ledger-authoritative phase resolution
- mode-aware routing (`deterministic`, `generative`, `legacy`)
- canonical step envelope parsing (`exit_code` 0/1/2)
- runtime failure sidecars and drill-down support
- compact human status output contract

## Current Runtime State (Important)

The command system is **not fully switched over** to deterministic execution yet.

- `.specify/command-manifest.yaml` currently has:
  - `deterministic`: none
  - `generative`: `speckit.specify`, `speckit.research`, `speckit.plan`, `speckit.planreview`, `speckit.sketch`
  - `legacy`: all others (including `speckit.implement`)
- `.claude/commands/speckit.implement.md` still runs the legacy task-ledger orchestration flow.

So this work delivered the engine + contracts + tests, but not the final command cutover.

## Mode Semantics

- `deterministic`: command is driver-managed and should execute through explicit script route metadata.
- `generative`: command produces a handoff contract for artifact/template generation (LLM fill path).
- `legacy`: command is not migrated to driver routing and follows existing legacy flow.

Aliases are normalized in `pipeline_driver_contracts.py` (for example `script` -> `deterministic`, `llm` -> `generative`, `unmanaged` -> `legacy`).

## How To Run It Manually

From repo root:

```bash
# Dry-run: resolve phase/state only (no mutations)
.venv/bin/python scripts/pipeline_driver.py --feature-id 019 --phase plan --dry-run --json

# Execute route for a phase (uses routing metadata)
.venv/bin/python scripts/pipeline_driver.py --feature-id 019 --phase plan --json

# Optional breakpoint approval token
.venv/bin/python scripts/pipeline_driver.py --feature-id 019 --phase implement --approval-token "scope:secret" --json
```

## How To Wire It Into Commands (Post-Spec Agent Step)

1. Pick command(s) to migrate first (start with low-risk phase commands).
2. In `.specify/command-manifest.yaml`, add/confirm `driver` metadata for each migrated command:
   - `mode: deterministic` or `mode: generative`
   - deterministic routes need script path/timeout metadata
3. Update corresponding `.claude/commands/*.md` execution flow so it invokes the driver path (not duplicate legacy orchestration).
4. Keep non-migrated commands as explicit `legacy` until cutover is complete.
5. Run gates/tests:
   - `scripts/speckit_gate_status.py`
   - `scripts/validate_command_script_coverage.py`
   - unit/integration driver tests
6. Validate ledger/task consistency before close.

## Minimal Verification Checklist

```bash
.venv/bin/python scripts/task_ledger.py validate --file .speckit/task-ledger.jsonl
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_pipeline_driver.py tests/integration/test_pipeline_driver_feature_flow.py -q
```

If both pass and manifest modes are intentional, routing state is coherent.

## Operational Note

Feature 019 ledger reconciliation was performed to align `tasks.md` and `task-ledger.jsonl`. Keep task closure events and task checkmarks synchronized going forward to avoid audit drift.
