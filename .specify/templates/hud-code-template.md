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

## Required Edits

[FILL: Replace this section with concrete implementation bullets. Each bullet must identify the exact behavior, branch, condition, return contract, field, side effect, or invariant being changed.]

Required edits are invalid if they only restate intent, such as:
- [EXAMPLE INVALID: Harden runtime behavior.]
- [EXAMPLE INVALID: Normalize the envelope.]
- [EXAMPLE INVALID: Add tests.]

Required edits should look like:
- [EXAMPLE: In `run_generative_handoff`, detect when the resolved route has `mode: generative` but no runner command/config is available.]
- [EXAMPLE: Return a deterministic blocked/error envelope before command execution.]
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

## Done Criteria

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
