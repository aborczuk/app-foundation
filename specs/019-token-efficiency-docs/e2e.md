# E2E Testing Pipeline: Deterministic Pipeline Driver with LLM Handoff

This pipeline validates end-to-end deterministic orchestration for feature `019-token-efficiency-docs`: state resolution, allowlisted step routing, compact result contract parsing, migration/governance coverage checks, and mixed-mode safety invariants.

---

## Prerequisites

- Python `3.12+`, `uv`, and `git` are installed and available in `PATH`.
- Feature artifacts exist: `spec.md`, `plan.md`, `tasks.md`, `estimates.md`, and this `e2e.md`.
- Repository root has `.specify/command-manifest.yaml`; mirror drift checks are enforced against `command-manifest.yaml` when present.
- Run standalone `uv` commands with `UV_CACHE_DIR=/tmp/uv-cache`; for the E2E script itself, override with `E2E_UV_CACHE_DIR=/tmp/uv-cache` when needed.
- Optional config file path may be passed to the script; when provided, the script copies it to a temp file and never mutates the live source.

---

## Recommended Pipeline (Run This)

Use the pipeline script instead of ad-hoc commands:

```bash
# Full E2E flow
scripts/e2e_019_token_efficiency_docs.sh full

# Preflight only (dry-run, no feature mutation expected)
scripts/e2e_019_token_efficiency_docs.sh preflight

# Run story sections only (US1 -> US2 -> US3)
scripts/e2e_019_token_efficiency_docs.sh run

# Print verification commands and run lightweight checks
scripts/e2e_019_token_efficiency_docs.sh verify

# CI-safe non-interactive checks only
E2E_NON_INTERACTIVE=1 scripts/e2e_019_token_efficiency_docs.sh ci
```

With an optional config file copy:

```bash
scripts/e2e_019_token_efficiency_docs.sh full path/to/local-e2e-config.yaml
```

---

## Section 1: Preflight (Dry-Run Smoke Test)

**Purpose**: Validate deterministic prerequisites, manifest/ledger integrity, and test discoverability before story execution.  
**External deps**: None (local CLI checks only)

1. Validate toolchain and expected feature files.
   - Verify: `python3`, `uv`, and key script/test files exist.
2. Run deterministic governance prechecks.
   - Verify: `pipeline_ledger.py validate-manifest` passes.
   - Verify: `speckit_gate_status.py --mode implement --json` returns `ok: true`.
3. Collect and discover target test modules.
   - Verify: `pytest --collect-only` succeeds for unit/integration/contract suites.
4. Execute timestamp-gated evidence checks and safety assertions.
   - Verify: section log artifact timestamp is newer than section start.
   - Verify: no orphan feature lock (`.speckit/locks/019*.lock`) remains.
   - Verify: no event-loop/lifecycle warnings appear in output.

**Pass criteria**: All preflight commands pass, no lifecycle warnings are detected, and no unresolved state drift is reported.

---

## Section 2: User Story 1 - Deterministic Step Routing (Priority: P1)

**Purpose**: Validate deterministic phase resolution and allowlisted route dispatch with explicit handoff behavior.  
**External deps**: None (local tests + governance scripts)

**User asks before starting**:
- [ ] Working tree is in expected state for running tests.
- [ ] `UV_CACHE_DIR` points to a writable path.

**Steps**:
1. Run US1 targeted tests:
   - `test_deterministic_route_success`
   - `test_deterministic_route_blocked`
   - `test_handoff_contract`
2. Run reconcile/retry guard coverage to assert deterministic drift handling:
   - `test_reconcile_and_retry_guards`
3. Validate pipeline + task ledgers after execution.
4. Apply lifecycle and state-safety assertions:
   - fail on event-loop/pending-task warnings
   - fail if feature lock residue remains
   - fail if canonical-vs-mirror manifest state drift is unresolved

**Pass criteria**: US1 tests pass, ledger validation remains clean, no orphan lock/process residue remains, and deterministic routing/handoff behavior is verified.

---

## Section 3: User Story 2 - Compact Parsing Contract (Priority: P2)

**Purpose**: Validate canonical envelope parsing, strict three-line status contract, dry-run no-mutation safety, and approval-breakpoint behavior.  
**External deps**: None (local test harness only)

**User asks before starting**:
- [ ] If manual approval-gate simulation is required, run in interactive mode (`E2E_NON_INTERACTIVE=0`).

**Steps**:
1. Run contract and flow tests:
   - `test_step_result_schema`
   - `test_runtime_failure_verbose_rerun`
   - `test_dry_run_does_not_mutate_ledgers_or_artifacts`
   - `test_approval_breakpoint_blocks_without_token`
   - `test_approval_breakpoint_resume_flow`
2. Apply timestamp-gated evidence checks on generated section logs/artifacts.
3. Enforce persistence and transaction safety assertions:
   - fail on swallowed persistence-error signatures
   - fail if partial local DB transaction residue (`*.db-wal`, `*.db-journal`, `*.sqlite-wal`, `*.sqlite-journal`) appears after section start
4. Validate no orphan runtime processes remain after cleanup.

**Pass criteria**: Contract + runtime tests pass, dry-run path is non-mutating, status contract behavior is enforced, and persistence safety assertions remain clean.

---

## Section 4: User Story 3 - Governance and Migration Safety (Priority: P3)

**Purpose**: Validate incremental migration safety, command coverage enforcement, and anti-regression governance checks.  
**External deps**: None (local scripts + tests)

**User asks before starting**:
- [ ] Governance docs/manifest updates for this branch are present.

**Steps**:
1. Run migration/governance tests:
   - `test_mixed_migration_mode`
   - `test_manifest_governance_guard`
2. Run deterministic command coverage and governance validators:
   - `scripts/validate_command_script_coverage.py`
   - `scripts/validate_doc_graph.sh`
   - `pipeline_ledger.py validate-manifest`
3. Validate canonical manifest integrity and unresolved drift detection logic.
4. Assert no lock/process residue remains.

**Pass criteria**: Mixed migration and governance tests pass, coverage validation reports no missing mapped scripts, and manifest/drift invariants remain satisfied.

---

## Section Final: Full Feature E2E

**Purpose**: Validate complete deterministic orchestration behavior across all stories with end-to-end safety invariants.  
**Runs**: After all story tasks are complete and after significant orchestration/governance changes

**User asks before starting**:
- [ ] Preflight and each story section has passed at least once.
- [ ] CI/non-interactive constraints are configured as intended.

**Steps**:
1. Run preflight.
2. Run US1 (deterministic routing).
3. Run US2 (compact parsing contract).
4. Run US3 (migration + governance).
5. Run full targeted suite for pipeline-driver unit/integration/contract tests.
6. Validate ledgers and cross-section safety checks.

**Pass criteria**: All section checks pass in order, no unresolved drift/lock/lifecycle issues remain, and deterministic governance validators pass.

---

## Verification Commands

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/pipeline_ledger.py validate-manifest
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/speckit_gate_status.py --mode implement --feature-dir specs/019-token-efficiency-docs --json
UV_CACHE_DIR=/tmp/uv-cache uv run pytest --collect-only tests/unit/test_pipeline_driver.py tests/integration/test_pipeline_driver_feature_flow.py tests/contract/test_pipeline_driver_contract.py
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_pipeline_driver.py tests/integration/test_pipeline_driver_feature_flow.py tests/contract/test_pipeline_driver_contract.py
scripts/e2e_019_token_efficiency_docs.sh verify
```

---

## Common Blockers

- **Missing uv cache permissions**: Symptom: `Failed to initialize cache ... Operation not permitted`. Fix: set `E2E_UV_CACHE_DIR=/tmp/uv-cache` for script runs and `UV_CACHE_DIR=/tmp/uv-cache` for standalone `uv` commands.
- **Implement gate still blocked**: Symptom: `speckit_gate_status --mode implement` returns `ok: false`. Fix: regenerate missing artifacts and re-run preflight.
- **Manifest drift**: Symptom: canonical/mirror mismatch failure. Fix: reconcile updates to `.specify/command-manifest.yaml` and any mirror references.
- **Lifecycle warnings in logs**: Symptom: `event loop is already running` or pending-task destruction warnings. Fix: resolve async teardown before rerunning.
- **Lock residue**: Symptom: `.speckit/locks/019*.lock` remains after section completion. Fix: clear stale owner state via deterministic lock-handling path and rerun.
