---
description: Legacy sketch command. Normal pipeline design slices are folded into speckit.plan.
model: opus
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Status

`/speckit.sketch` is retained for compatibility only.

Normal pipeline execution no longer produces a separate `sketch.md`. Run `/speckit.plan`; the combined plan artifact includes the design slices that tasking consumes.

## Behavior rules

- Do not use this command for the normal pipeline path.
- Do not generate `tasks.md`.
- Do not emit `sketch_completed` for new combined-plan features.
- If invoked manually, keep the result advisory and reconcile it back into `plan.md` before tasking.
