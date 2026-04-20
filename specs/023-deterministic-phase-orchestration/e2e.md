# E2E Testing Pipeline: Deterministic Phase Orchestration

## Prerequisites

- Python 3.12 + `uv`: `uv --version`
- Repository root present: `git rev-parse --show-toplevel`
- Feature artifacts present:
  - `specs/023-deterministic-phase-orchestration/spec.md`
  - `specs/023-deterministic-phase-orchestration/plan.md`
  - `specs/023-deterministic-phase-orchestration/tasks.md`
- No external networked services are required for this feature; all checks are local CLI, ledger, and manifest validations.

---

## Recommended Pipeline (Run This)

Use the pipeline script instead of manual commands:

```bash
# Full E2E flow
scripts/e2e_023_deterministic_phase_orchestration.sh full

# Preflight only (dry-run, no side effects)
scripts/e2e_023_deterministic_phase_orchestration.sh preflight

# Run the user-story sections only
scripts/e2e_023_deterministic_phase_orchestration.sh run

# Print verification commands
scripts/e2e_023_deterministic_phase_orchestration.sh verify

# CI-safe non-interactive checks only
scripts/e2e_023_deterministic_phase_orchestration.sh ci
```

---

## Section 1: Preflight (Dry-Run Smoke Test)

**Purpose**: Validate local tooling, manifest coverage, task formatting, and a no-side-effect driver dry-run.

**External deps**: None beyond the local repo and Python toolchain.

**Prerequisites checklist**:
- `uv sync` completed successfully.
- `tasks.md` passes deterministic format validation.
- `command-manifest.yaml` validation passes.

**Steps**:
1. Validate ledger consistency.
   - Verify: `uv run python scripts/pipeline_ledger.py validate` exits `0`.
2. Validate task formatting and task/story labels.
   - Verify: `uv run python scripts/speckit_tasks_gate.py validate-format --tasks-file specs/023-deterministic-phase-orchestration/tasks.md --json` returns `ok: true`.
3. Validate command-script coverage.
   - Verify: `uv run python scripts/validate_command_script_coverage.py --canonical-manifest command-manifest.yaml --scaffold-script .specify/scripts/pipeline-scaffold.py --bash-scripts-dir .specify/scripts/bash --json` returns `ok: true`.
4. Run a dry-run driver pass.
   - Verify: `uv run python scripts/pipeline_driver.py --feature-id 023 --dry-run --json` exits `0`, reports `dry_run_mode: true`, and returns `next_phase: implement`.

**Pass criteria**:
- All checks exit successfully.
- No ledger mutations occur during dry-run.

---

## Section 2: Deterministic Phase Completion (Priority: P1)

**Purpose**: Confirm validation gates prevent completion events until the driver reports a validated success path.

**External deps**: Local pipeline driver and pipeline ledger only.

**Prerequisites checklist**:
- `analysis_completed` exists for feature `023`.
- Baseline ledger event count is recorded before the run.

**Steps**:
1. Capture the current ledger line count.
   - Verify: count is stable before any e2e action.
2. Run the driver in dry-run mode for feature `023`.
   - Verify: JSON result shows `phase_state.phase == "solution"`, `phase_state.last_event == "analysis_completed"`, `step_result.ok == true`, and `step_result.next_phase == "implement"`.
3. Recount the ledger lines after the dry-run.
   - Verify: ledger count is unchanged, proving no completion event was appended during the dry-run gate.

**Pass criteria**:
- Dry-run resolves deterministically.
- No completion event is emitted during dry-run.

---

## Section 3: Permissioned Phase Start (Priority: P2)

**Purpose**: Confirm the driver rejects invalid approval input and preserves ledger state.

**External deps**: Local pipeline driver module only.

**Prerequisites checklist**:
- Ledger line count is captured before the approval-gate attempt.
- The command is run in a local shell where exit status is visible.

**Steps**:
1. Run the approval-breakpoint helper with a synthetic enabled breakpoint config and an invalid token scope.
   - Verify: the returned payload has `ok == false`, `gate == "approval_required"`, and `reasons` includes `approval_token_scope_mismatch`.
2. Re-run the helper with no token at all.
   - Verify: the returned payload has `ok == false` and reports the required breakpoint scope.
3. Recount the ledger lines after both helper checks.
   - Verify: ledger count is unchanged.

**Pass criteria**:
- Invalid approval is rejected deterministically.
- No side effects occur.

---

## Section 4: Producer-Only Command Contracts (Priority: P3)

**Purpose**: Confirm command docs stay producer-only and the manifest/script contract stays aligned.

**External deps**: Local manifest and markdown validators only.

**Prerequisites checklist**:
- `command-manifest.yaml` is readable.
- `speckit.solution` command docs exist and are in sync with the manifest.

**Steps**:
1. Validate manifest coverage and command-script alignment.
   - Verify: `uv run python scripts/pipeline_ledger.py validate-manifest` passes.
   - Verify: `uv run python scripts/validate_command_script_coverage.py --json` passes.
2. Validate markdown command-shape rules.
   - Verify: `uv run python scripts/validate_markdown_doc_shapes.py --json` passes for `speckit.solution`.
3. Confirm no command doc claims direct ledger append ownership.
   - Verify: doc-shape validator and command coverage validator stay green together.

**Pass criteria**:
- Manifest and command docs remain aligned.
- Command docs remain producer-only.

---

## Section Final: Full Feature E2E

**Purpose**: Run all sections in order and verify the feature behaves as a coherent deterministic phase orchestration boundary.

**External deps**: Local repo toolchain only.

**Prerequisites checklist**:
- Preflight passes.
- Story 1, Story 2, and Story 3 sections are available.

**Steps**:
1. Run preflight.
   - Verify: no side effects.
2. Run Story 1, Story 2, and Story 3 checks in order.
   - Verify: each section passes independently.
3. Re-run the ledger validation at the end.
   - Verify: no invalid transitions were introduced by the E2E run.

**Pass criteria**:
- All sections pass.
- Ledger validation passes after the run.

---

## Verification Commands

- `uv run python scripts/pipeline_ledger.py validate`
- `uv run python scripts/pipeline_ledger.py validate-manifest`
- `uv run python scripts/speckit_tasks_gate.py validate-format --tasks-file specs/023-deterministic-phase-orchestration/tasks.md --json`
- `uv run python scripts/validate_command_script_coverage.py --json`
- `uv run python scripts/pipeline_driver.py --feature-id 023 --dry-run --json`

---

## Common Blockers

- `uv sync` not run or local Python toolchain missing.
- `tasks.md` fails deterministic format validation.
- The pipeline driver dry-run no longer reports `next_phase: implement`.
- Approval helper unexpectedly returns success for invalid or missing tokens.
- Command-doc validation detects direct ledger append ownership in `speckit.solution`.
- Repo-wide `pipeline_ledger.py validate-manifest` currently fails because the global event catalog includes entries not present in the transition map; this is a repository-level blocker, not a feature-023 issue.
