---
feature_id: "[FEATURE_ID]"
task_id: "[TASK_ID]"
---

# HUD: [FILL: TASK_ID] — [FILL: task title from tasks.md]

<!--
Template rules:
- Text inside [FILL: ...] is required generated content.
- Text inside [EXAMPLE: ...] is illustrative only and must be replaced or removed.
- Do not leave generic verbs such as "harden", "wire", "normalize", or "update" unless paired with concrete behavior, symbols, contracts, or assertions.
- If current behavior cannot be verified from bounded repo reads, mark the HUD blocked instead of guessing.
-->

## Objective

[FILL: One sentence describing the outcome this task must achieve.]

[EXAMPLE: Ensure a generative driver route without runner configuration fails before execution and cannot emit a completion event.]

## Relevant Domains

- Inherit from `plan.md` `Strategy Contract` and keep only the domains that materially affect this task.
- `[FILL: constitution domain]` — [FILL: why this domain is relevant to the task.]
- `[FILL: constitution domain]` — [FILL: why this domain is relevant to the task.]

[EXAMPLE: `edge delivery` — route or delivery behavior changes at the runtime boundary.]
[EXAMPLE: `client/UI` — user-visible browser behavior and restart affordance must change.]

## Candidate Design Slices

- `[FILL: slice id]` — [FILL: exact slice title], [FILL: exact slice directive], [FILL: why this slice appears relevant to the task, with confidence or basis.]
- `[FILL: slice id]` — [FILL: include only when more than one slice legitimately applies.]

[EXAMPLE: `PL-01` — Tetris Runtime Surface, "Extend the FastAPI runtime with an isolated Tetris route and supporting delivery helpers without perturbing existing control-plane endpoints.", route/runtime seam overlap from `app.py` and router work; high confidence.]
[EXAMPLE: `PL-03` — Playable Browser Shell, "Build the thinnest browser shell that can render board state, collect keyboard input, display score/game-over state, and synchronize with the authoritative gameplay flow.", browser shell file overlap from template/static assets; high confidence.]

## Proposed Solution

- Solve the relevant design slice for this task before writing the rest of the HUD.
- Carry that solved slice-local implementation into the task ticket here.
- `[FILL: concrete implementation approach this task will take.]`
- `[FILL: exact symbols, files, or contracts this solution will change.]`

[EXAMPLE: Add `restart_tetris_session()` to the router, delegate the reset to `TetrisSession.reset()`, preserve the existing response envelope shape, and refresh the browser state through the existing restart handler path in `tetris.js`.]

## Current Repo Behavior

[FILL: Describe the current behavior verified from bounded repo reads. Include the observed file/symbol/branch/contract when possible.]

If current behavior was not verified, write exactly:

`BLOCKED: current behavior not validated from repo reads.`

[EXAMPLE: `run_generative_handoff` currently accepts a generative route after route resolution but does not fail deterministically before execution when runner configuration is absent.]

## Target Behavior

[FILL: Describe the expected behavior after this task is complete. Include envelope shape, reason code, side-effect behavior, and compatibility expectations where applicable.]

[EXAMPLE: A generative route with missing runner configuration returns a deterministic blocked/error envelope with reason code `missing_generative_runner`, performs no command execution, and emits no ledger event.]

## Primary Edit Seam

**File:Symbol**: `[FILL: primary file:symbol from tasks.md or bounded symbol discovery]`

[EXAMPLE: `scripts/pipeline_driver.py:run_generative_handoff`]

## Reuse Candidates

- Only list reuse candidates that were validated from repo reads. Do not claim reuse speculatively.
- `[FILL: existing file:symbol or file path]` — [FILL: how it can be reused.]
- `None validated from repo reads.` [FILL: use only when no concrete reuse candidate was verified.]

[EXAMPLE: `src/app/router.py:existing_handler` — preserve route registration and extend the restart path in place.]
[EXAMPLE: `None validated from repo reads.`]

## Required Edits

[FILL: Replace this section with concrete implementation bullets. Each bullet must identify the exact behavior, branch, condition, return contract, field, side effect, or invariant being changed.]

Every required edit bullet must attach to at least one matched design slice and specialize that slice into a task-specific obligation. Do not merely cite `PL-01`/`PL-02`; explain what that slice requires in this exact task.

Required edits are invalid if they only restate intent, such as:
- [EXAMPLE INVALID: Harden runtime behavior.]
- [EXAMPLE INVALID: Normalize the envelope.]
- [EXAMPLE INVALID: Add tests.]
- [EXAMPLE INVALID: Honor PL-02.]

Required edits should look like:
- [EXAMPLE: From `PL-02`'s deterministic state-transition directive, reject ended-session move/tick input in `TetrisSessionService` instead of letting the router branch on game-over state.]
- [EXAMPLE: From `PL-01`'s runtime-surface directive, add `restart_tetris_session()` in `router.py` without introducing a second payload shape.]
- [EXAMPLE: Use reason code `missing_generative_runner`.]
- [EXAMPLE: Ensure this path does not call `append_pipeline_success_event`.]
- [EXAMPLE: Preserve current behavior for configured generative runners.]
- [EXAMPLE: Preserve legacy route behavior.]

## Touched Symbols

### Modify

- `[FILL: file:symbol]` — [FILL: specific intended change.]
- `[FILL: optional file:symbol]` — [FILL: include only if caller/callee behavior must change.]

[EXAMPLE: `scripts/pipeline_driver.py:run_generative_handoff` — add missing-runner preflight before invoking the runner adapter.]
[EXAMPLE: `scripts/pipeline_driver.py:run_step` — only update if caller-side envelope handling is required.]

### Create

- `[FILL: symbol_name(...)]` in `[FILL: file path]` — [FILL: purpose/signature; use `None` if no new symbols are required.]

[EXAMPLE: None.]

### Preserve

- [FILL: Existing behavior that must remain unchanged.]
- [FILL: Existing compatibility path or invariant that must remain unchanged.]

[EXAMPLE: Existing legacy route behavior.]
[EXAMPLE: Existing configured-runner behavior.]

## Tests To Add Or Update

### Test 1

**File**: `[FILL: test file path]`  
**Name**: `[FILL: test function name]`

Given:
- [FILL: setup condition]
- [FILL: setup condition]

When:
- [FILL: action under test]

Then assert:
- [FILL: exact assertion]
- [FILL: exact assertion]
- [FILL: exact assertion]

[EXAMPLE:
**File**: `tests/unit/test_pipeline_driver.py`  
**Name**: `test_generative_route_without_runner_blocks_before_emit`

Given:
- manifest route with `mode: generative`
- no runner command/config

When:
- driver resolves and executes the route

Then assert:
- result is blocked/error
- reason code is `missing_generative_runner`
- no completion event is appended
- ledger file remains unchanged
]

## Acceptance Criteria

- This section is mandatory because `/speckit.implement` must be able to execute the task using this HUD alone.
- Carry forward the task-local acceptance criteria from `spec.md`, `spec.json`, matched design slices, and bounded repo reads.
- `[FILL: externally observable or contract-level behavior that must be true when this task is complete.]`
- `[FILL: externally observable or contract-level behavior that must be true when this task is complete.]`

[EXAMPLE: When the session is over, the restart affordance is visible and active controls no longer mutate the ended board.]
[EXAMPLE: When restart is triggered, the next rendered state is a fresh playable session with reset score and reset board state.]

## Done Criteria

- Done criteria are the proof-of-completion checks for implement. Acceptance criteria describe required behavior; done criteria describe the evidence that the task is complete.
- [FILL: Targeted command that must pass.]
- [FILL: Regression command, contract check, or acceptance check that must pass.]
- [FILL: Deterministic artifact/event/side-effect condition that must be true.]

[EXAMPLE: Targeted test command passes: `uv run --no-sync pytest tests/unit/test_pipeline_driver.py -k generative_route_without_runner`.]
[EXAMPLE: Existing driver contract tests pass.]
[EXAMPLE: No ledger append occurs on the missing-runner path.]

## Constraints And Invariants

- [FILL: Constraint or invariant.]
- [FILL: Constraint or invariant.]
- [FILL: Constraint or invariant.]

[EXAMPLE: No event emission before deterministic validation.]
[EXAMPLE: No fallback from generative to legacy on missing runner.]
[EXAMPLE: Preserve append-only ledger semantics.]

## Implementation Checklist

- Carry forward concrete checklist work from the matched design slice(s), story acceptance scenarios, and declared test ownership.
- [ ] [FILL: concrete implementation step]
- [ ] [FILL: concrete implementation step]
- [ ] [FILL: concrete implementation step]

[EXAMPLE: Add the restart route handler and ensure ended sessions cannot mutate before restart.]
[EXAMPLE: Reset board state and score through the authoritative engine path.]
[EXAMPLE: Update the browser control to invoke restart and rerender the fresh session.]

## Dependencies

- [FILL: Dependencies by task ID, or `None`.]

[EXAMPLE: Depends on T050 if manifest route metadata is required first.]

## Process Checklist

- [ ] current_behavior_verified
- [ ] implementation_directive_complete
- [ ] touched_symbols_verified
- [ ] tests_specified
- [ ] constraints_verified
- [ ] done_criteria_passed
