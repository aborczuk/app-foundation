---
description: DEPRECATED. Use /speckit.solution (full flow) or /speckit.tasking (post-sketch decomposition) instead.
---

## User Input

```text
$ARGUMENTS
```

## Outline

1. **Stop immediately** and report deprecation:
   - `/speckit.tasks` is no longer an active generation path.

2. **Route to canonical commands**:
   - Use `/speckit.solution` for full sketch-first orchestration.
   - Use `/speckit.tasking` only when an approved `sketch.md` already exists and task decomposition must be re-run.

3. **Do not write artifacts** from this command.

## Behavior rules

- Never generate `tasks.md` from this command.
- Never emit pipeline events from this command.
