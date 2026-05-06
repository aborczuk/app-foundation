---
description: Legacy research command. Normal pipeline research is folded into speckit.plan.
model: opus
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Status

`/speckit.research` is retained for compatibility only.

Normal pipeline execution no longer produces separate `discovery.md` or `research.md` artifacts. Run `/speckit.plan`; the combined plan script performs internal discovery, proportional external/internal research, architecture planning, and design-slice scaffolding inside `plan.md`.

## Behavior Rules

- Do not use this command for the normal pipeline path.
- Do not make architecture or LOE decisions here.
- If invoked manually, treat the result as advisory only and do not emit pipeline events directly.
