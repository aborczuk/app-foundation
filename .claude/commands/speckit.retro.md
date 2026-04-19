---
description: Produce a post-delivery retrospective (`retro.md`) for the active feature after implementation and verification. Callable standalone or after /speckit.e2e-run.
handoffs:
  - label: Feed Learnings Back to Backlog
    agent: speckit.addtobacklog
    prompt: Retro is complete. Convert actionable follow-up improvements into backlog items where appropriate.
    send: false
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

Produce a durable retrospective for the active feature after delivery.

This phase owns `retro.md` only.

## Inputs

- The completed feature artifacts for the active feature
- The scaffolded `retro.md` template
- The approved upstream context, including:
  - `spec.md`
  - `plan.md`
  - `sketch.md`
  - `tasks.md`
  - `estimates.md` if present
  - `analysis.md` if present
  - `solutionreview.md` if present
  - `e2e.md` and execution evidence if present
- Any implementation, testing, and operational evidence available to this phase

## Execution

1. Run the retro gate / prerequisite checks for the active feature.
2. **Generate `retro.md`**
   - Scaffold:
     ```bash
     uv run python .specify/scripts/pipeline-scaffold.py speckit.retro --feature-dir "$FEATURE_DIR" FEATURE_ID="NNN" FEATURE_NAME="[Feature Name]"
     ```
   - Fill the scaffolded artifact completely.
   - Preserve template structure.
3. Load the approved upstream artifacts and available delivery evidence.
4. Compare delivered work against the original spec, plan, sketch, tasks, and estimates.
5. Produce the retrospective by filling the scaffolded artifact completely.
6. Preserve the scaffold structure.
7. Emit the manifest-declared completion event for this phase.

## Retro responsibilities

The retro must:

- identify what was missed or under-specified between `spec.md` and `tasks.md`
- identify where task decomposition failed to fully represent the intended scope
- compare estimates against actual implementation difficulty and call out where work was smaller or larger than expected
- identify what could have gone better across planning, design, tasking, implementation, testing, and review
- capture what went well and should be repeated
- record concrete lessons for future feature delivery
- document how the resulting service/system should be managed going forward, including:
  - how to read or inspect it
  - how to test it
  - how to observe and monitor it
  - what operators or future maintainers should pay attention to
- distinguish between:
  - process problems
  - design problems
  - implementation problems
  - operational problems
- produce actionable follow-ups where meaningful

## Behavior rules

- This phase is reflective and read-only with respect to production code.
- Do not modify implementation artifacts here.
- Do not rewrite history to hide misses or estimate errors.
- Be explicit about what was missing, what was misestimated, and what should change next time.
- Prefer concrete examples over vague summaries.
- If re-run, update only the retrospective content affected by newly available evidence or corrected delivery context.