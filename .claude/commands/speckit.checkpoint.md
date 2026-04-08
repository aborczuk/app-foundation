---
description: Validate a phase checkpoint from tasks.md by running the software and verifying observable behavior. Can be invoked standalone or called from /speckit.implement after each phase.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

This command is a **validation gate** — it verifies that the software actually works as described in a phase checkpoint, not just that unit tests pass. It exists because unit tests validate components in isolation but cannot validate that components are wired together and the system behaves as specified end-to-end.

**This command can be invoked in two ways:**
1. **From `/speckit.implement`**: Called automatically after all tasks in a phase are marked `[X]`. The phase number is passed as the argument.
2. **Manually**: Run `/speckit.checkpoint [phase]` to validate a specific phase (e.g., `/speckit.checkpoint Phase 3`).

## Outline

1. **Locate the feature and tasks file**:
   - Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list. All paths must be absolute.
   - Read tasks.md from FEATURE_DIR.
   - Read plan.md from FEATURE_DIR (for tech stack context — how to run the software, what entrypoints exist).

2. **Determine which phase to validate**:
   - If user input specifies a phase (e.g., "Phase 3", "3", "US1"): validate that specific phase.
   - If user input is empty or "next": find the first phase where all tasks are `[X]` but the checkpoint has not been validated yet. If all phases are validated, report that and stop.
   - If user input is "all": validate all phases with completed tasks, in order.

3. **Parse the checkpoint**:
   - Locate the `**Checkpoint**:` line at the end of the target phase in tasks.md.
   - Extract the checkpoint text — this describes the **observable behavior** that MUST be true.
   - Parse the checkpoint into discrete, verifiable claims. For example:
     - "System connects to IBKR" → verify connection event in logs or output
     - "reconciles positions" → verify reconciliation ran (log entry or DB state)
     - "submits BTC orders when profit target reached" → verify order submission logic executes
   - If no checkpoint line exists for the phase, report this as an error and stop.

4. **Verify all phase tasks are complete**:
   - Check that every task in the target phase is marked `[X]`.
   - Check that all `[H]` tasks in the phase have `human_action_verified` in the task ledger.
   - If any tasks are `[ ]` or any `[H]` tasks are unverified, report which and **STOP** — the checkpoint cannot be validated until all tasks are done.

4a. **Run story acceptance tests (MANDATORY for User Story phases)**:
   - For each User Story in the phase, locate the failing acceptance test committed during the per-story RED step (test file committed as `T0XX-story-N-red: ...`).
   - Run all story acceptance tests for the phase.
   - Every story acceptance test MUST pass. If any fail: **STOP** — the story goal is not met. Do not proceed to the phase observable behavior check until all story tests are green.
   - Report pass/fail per story with test output as evidence.

5. **Identify external dependencies**:
   - Analyze the checkpoint claims for external dependencies:
     - Database servers (PostgreSQL, MySQL, Redis, etc.)
     - API gateways or third-party services
     - Hardware devices or local services (e.g., IBKR Gateway, hardware wallets)
     - Network services (message queues, cloud APIs)
     - Environment variables that must be set (API keys, connection strings)
   - For each identified dependency, check whether it is available:
     - Try to connect/ping the service
     - Check if required env vars are set
     - Check if required config files exist
   - **If any external dependency is unavailable**:
     - List all missing dependencies clearly
     - **STOP and ask the human**: "The following external dependencies are needed for checkpoint validation but are not available: [list]. Please set them up and confirm when ready, or tell me to skip this checkpoint."
     - Wait for human response before continuing
     - If human says to skip: log that the checkpoint was **SKIPPED (external dependency)** and report this clearly — the phase is NOT fully validated

6. **Run the software**:
   - Determine the appropriate execution method from plan.md and tasks.md:
     - Look for `--dry-run` flags or equivalent safe modes
     - Look for CLI entrypoints (e.g., `uv run csp-trader --config config.yaml --dry-run`)
     - Look for test commands that exercise integration (not just unit tests)
   - **Execution priority** (try in order):
     1. Run with `--dry-run` or equivalent safe mode if available
     2. Run the entrypoint and capture output (with a timeout — max 30 seconds unless the checkpoint requires longer)
     3. Run smoke-test imports (`python -c "from module import Class"`) for each module touched in the phase
   - Capture ALL output: stdout, stderr, log files, and exit code
   - If the application requires a running process (not a one-shot command), start it in the background, wait for it to produce output, then terminate it gracefully
   - **Async process management guard** (mandatory when asyncio/event loops/background workers are involved):
     - Use async-native execution paths in active async code; do not validate with sync wrappers that spin nested event loops.
     - Track every spawned process/task with explicit ownership and lifecycle evidence: start, ready, timeout/cancel, shutdown.
     - After validation run, assert no orphan processes/tasks remain for the section under test.
     - Treat lifecycle signals such as `"event loop is already running"` or `"Task was destroyed but it is pending"` as automatic checkpoint failures.
   - **State safety and reconciliation guard** (mandatory when local state mirrors live external state):
     - Verify reconciliation runs before risk/scoring/side-effect decisions in the validated path.
     - Verify source-of-truth drift does not leave local records in active states when live state is closed/missing.
     - Treat log-only state transitions (without persisted lifecycle updates) as automatic checkpoint failures.
   - **Local DB transaction integrity guard** (mandatory when local DB mutations represent lifecycle/risk/financial state):
     - Verify multi-step/cross-table writes use explicit transaction boundaries with atomic commit/rollback behavior.
     - Verify failure paths do not leave partial writes or impossible lifecycle transitions in local state.
     - Treat swallowed persistence errors or partial-commit evidence as automatic checkpoint failures.

7. **Validate each checkpoint claim**:
   - For each discrete claim parsed in step 3, check the captured output/logs/state for evidence:
     - **PASS**: Evidence found that the behavior occurs (log entry, output text, DB state, exit code)
     - **FAIL**: Expected behavior absent or contradicted by error output
     - **INCONCLUSIVE**: Cannot determine from available evidence (e.g., requires manual observation)
   - Build a validation report:

     ```text
     ## Checkpoint Validation: Phase [N] — [Phase Title]

     **Checkpoint**: "[full checkpoint text from tasks.md]"

     | # | Claim | Status | Evidence |
     |---|-------|--------|----------|
     | 1 | System connects to IBKR | PASS | Log: "ibkr_connected" at 14:32:01 |
     | 2 | Reconciles positions | PASS | Log: "reconciliation_complete" positions_synced=3 |
     | 3 | Submits BTC orders | FAIL | No "btc_order_submitted" log entry found |

     **Overall**: FAIL (2/3 claims passed)
     ```

8. **Report result and determine next action**:

   - **If ALL claims PASS**:
     - Report: "Checkpoint PASSED for Phase [N]"
     - Confirm async lifecycle guard passed (no orphan process/task and no loop-lifecycle errors) when applicable.
     - Confirm state safety guard passed (no unresolved live-vs-local drift, no log-only transitions) when applicable.
     - Confirm local DB transaction guard passed (no partial writes/impossible transitions, explicit transaction behavior) when applicable.
     - The phase is validated. Implementation can proceed to the next phase.

   - **If ANY claim FAILS**:
     - Report the full validation table with failure details
     - Analyze the failure:
       - Is it a missing implementation? (code not written or not wired)
       - Is it a runtime error? (crash, import error, config issue)
       - Is it an environment issue? (missing dependency, wrong config)
       - Is it a state consistency issue? (source-of-truth drift unresolved, log-only lifecycle transition)
       - Is it a transaction integrity issue? (partial commit, missing rollback, impossible persisted lifecycle state)
     - **STOP and report**: "Checkpoint FAILED for Phase [N]. The following claims failed: [list]. This phase is NOT complete."
     - Suggest specific fixes for each failure
     - Do NOT proceed to the next phase
     - If called from `/speckit.implement`, return control to the implement workflow with FAIL status so it can address the failures

   - **If any claim is INCONCLUSIVE**:
     - Report the inconclusive claims
     - **Ask the human**: "The following checkpoint claims could not be verified automatically: [list]. Can you confirm whether these behaviors are working? (yes/no/skip)"
     - If human confirms: treat as PASS
     - If human denies: treat as FAIL
     - If human skips: log as SKIPPED

9. **Log the checkpoint result**:
   - Append checkpoint validation status to the end of the phase section in tasks.md (as a comment or note) so future runs know which checkpoints have been validated:

     ```markdown
     **Checkpoint**: [original text]
     <!-- Checkpoint validated: PASS | 2026-03-11 | All 3 claims verified -->
     ```

   - If the checkpoint was SKIPPED or FAILED, note this too:

     ```markdown
     <!-- Checkpoint validated: FAIL | 2026-03-11 | 2/3 claims passed, "submits BTC orders" failed -->
     ```

## Notes

- This command is a **read-and-run** operation — it reads the spec, runs the software, and reports results. It does NOT fix failures itself. Fixes are the responsibility of the implementation workflow or the human.
- Unit tests passing is NECESSARY but NOT SUFFICIENT. This command validates end-to-end wiring, not isolated components.
- The 30-second execution timeout is a default. If the checkpoint describes behavior that takes longer (e.g., "system runs for 5 evaluation cycles"), adjust accordingly.
- When run from `/speckit.implement`, the implement workflow should pass the phase identifier and await the result before proceeding.
- Checkpoint validation results are idempotent — running the same checkpoint twice overwrites the previous result comment.
- If stateful external integrations exist, unresolved source-of-truth drift is a hard FAIL, not a warning.
- If local DB mutation paths exist, partial writes or impossible lifecycle transitions are a hard FAIL, not a warning.
