---
description: Estimate and break down seam-sized tasks in one generative stabilization step, then finalize tasking.
handoffs:
  - label: Analyze For Consistency
    agent: speckit.analyze
    prompt: Run cross-artifact consistency analysis after tasking finalization
    send: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding if it is not empty.

## Contract

This is the single generative estimate/breakdown skill after `/speckit.tasking` has authored `tasks.md`. It owns the complete stabilization boundary:

`estimate -> breakdown when required -> re-estimate -> repeat -> finalize`

Do not invoke `scripts/speckit_tasking_chain.py` or `scripts/speckit_tasking_codex_runner.py` from this skill. Those are deterministic/compatibility helpers, not the canonical execution path.

### Required Context

Load `tasks.md`, `plan.md`, `spec.json`, `spec.md`, and any existing `estimates.md` from the feature directory. If `tasks.md` is missing, stop and direct the user to `/speckit.tasking`.

### Generative Execution

1. Read the task graph and the approved plan slices. Do not invent architecture absent from `plan.md`.
2. Write or replace `estimates.md` with a per-task Fibonacci estimate, seam boundary, integration surface, phase totals, and warnings.
3. Apply the current breakdown rules directly when any task scores 8 or 13:
   - 5 means one cohesive implementation seam and one closeout unit.
   - 8 means multi-seam work that must be split into smaller cohesive tasks.
   - 13 means epic-scale multi-seam work that must be split before implementation.
   - Preserve the slice-to-task contract and do not split routing, validation, and reporting when they share one closeout seam.
   - Assign fresh sequential numeric `TNNN` IDs to replacement tasks. Do not use alphabetic or dotted child IDs such as `T003a` or `T003.1`; the task guard requires canonical numeric IDs.
4. Re-estimate the updated task graph after every breakdown pass. Repeat until no current estimate row scores 8 or 13.
5. If estimation or breakdown cannot complete, stop with the failure and do not fabricate `estimates.md`, bypass the loop, or continue to finalization.
6. Run the deterministic task format gate:

   ```bash
   uv run python scripts/speckit_tasks_gate.py validate-format --tasks-file "$FEATURE_DIR/tasks.md" --json
   ```

7. Only after the estimate/breakdown loop and task gate pass, run the tasking finalizer:

   ```bash
   uv run python scripts/speckit_tasking_step.py finalize \
     --feature-id "$FEATURE_ID" \
     --phase tasking \
     --correlation-id "$CORRELATION_ID" \
     --json
   ```

8. The finalizer owns task registration, acceptance scaffolding, and the `tasking_completed` event request. Do not append that event before finalization succeeds.

## Guidance

### Completion Report

Report the paths to `tasks.md` and `estimates.md`, task and story counts, total points, confirmation that no task scores 8 or 13, finalizer status, and the next command `/speckit.analyze` or `/speckit.implement` as returned by the pipeline.

## Behavior rules

- Do not invoke the deterministic tasking chain or Codex runner.
- Do not fabricate estimates, bypass the breakdown loop, or finalize after a failed gate.
- Keep each estimate tied to a coherent implementation seam and its integration surface.
