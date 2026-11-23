---
description: Compatibility substep for splitting 8 or 13-point tasks; use /speckit.estimate for the complete generative loop.
---

## User Input

```text
$ARGUMENTS
```

`/speckit.breakdown` is retained for older callers and handoffs. The canonical workflow is the single generative `/speckit.estimate` skill, which estimates, breaks down, re-estimates, and finalizes without returning to this command.

## Contract

This command is a compatibility substep, not an independent pipeline phase. It may split an already identified oversized task, but `/speckit.estimate` remains the only owner of the complete estimate/breakdown loop and finalization.

## Guidance

If this compatibility command is invoked directly:

1. Require `tasks.md` and `estimates.md`.
2. Identify every current task row scored 8 or 13.
3. Split each multi-seam task into cohesive seam tasks of 5 points or fewer.
4. Preserve the slice-to-task contract and do not split one closeout seam into routing, validation, and reporting fragments.
5. Assign fresh sequential numeric `TNNN` IDs to replacement tasks. Do not use alphabetic or dotted child IDs such as `T003a` or `T003.1`; the task guard requires canonical numeric IDs.
6. Return control to `/speckit.estimate` for re-estimation and finalization.

This command does not emit a pipeline event or run finalization by itself.

## Behavior rules

- Do not invoke the deterministic tasking chain or Codex runner.
- Do not emit `tasking_completed` from this compatibility command.
- Return control to `/speckit.estimate` after a breakdown pass.
