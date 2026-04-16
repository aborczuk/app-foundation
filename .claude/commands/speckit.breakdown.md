---
description: Break down tasks flagged with 8 or 13-point warnings in estimates.md into smaller pieces (≤5 points each), updating tasks.md in place.
handoffs:
  - label: Re-Estimate
    agent: speckit.estimate
    prompt: Re-run estimation to verify all tasks now score ≤5 points
    send: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

Goal: For every task in estimates.md flagged with an 8 or 13-point warning, split it into 2–3 smaller tasks (each expected to score ≤5 points), update tasks.md in place, and re-sequence task IDs. This step runs AFTER `/speckit.estimate` and BEFORE `/speckit.implement`.

**Prerequisites**:
- `tasks.md` must exist (run `/speckit.solution` first if missing)
- `estimates.md` must exist (run `/speckit.estimate` first if missing)

---

### Execution Steps

1. **Run prerequisites check** from repo root:
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.
   ```
   .specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
   ```
   Parse `FEATURE_DIR`. Derive paths for `tasks.md` and `estimates.md`.
   - If either file is missing, abort with a clear error and the appropriate next command.

2. **Load context**:
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.
   - `estimates.md` — parse the Warnings section to identify flagged task IDs (8 or 13 pts)
   - `tasks.md` — load the full task list
   - `plan.md` — for module boundaries and tech context
   - `data-model.md` (if present) — for entity-level breakdown guidance

3. **Identify tasks to break down**: Extract all task IDs that appear in the estimates.md Warnings section (scored 8 or 13). If none are found, report "No tasks require breakdown" and stop.
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.

4. **For each flagged task**, design a breakdown:
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.

   **Split rules**:
   - Each original task becomes exactly 2 or 3 sub-tasks — no more.
   - Each sub-task must be independently completable (different files, or distinct phases of work on the same file: e.g., "write the data structure" then "write the business logic").
   - A valid split follows one of these natural seams:
     - **Data vs. Logic**: schema/model definition → business logic/methods
     - **Happy path vs. Error handling**: core implementation → error handling, retries, validation
     - **Layer split**: internal implementation → integration wiring (connecting to other modules)
     - **Test vs. Implementation**: if the original task bundled both (unusual — tasks.md should already separate them)
   - Do NOT invent new scope. Sub-tasks must cover exactly the same scope as the original.
   - Preserve the `[P]`, `[USn]` labels from the original task on each sub-task if applicable.
   - Re-evaluate parallelism: sub-tasks within a split are usually sequential (sub-task B depends on sub-task A). Remove `[P]` from sub-task B if it depends on sub-task A.
   - Guard-preserving split: if the original task includes async lifecycle, state-safety/reconciliation, or local DB transaction-integrity scope, preserve those guard outcomes across sub-tasks (no-orphan cleanup, reconcile-before-decision, drift validation, no-partial-write guarantees).

   **Naming sub-tasks**:
   - Use descriptive suffixes: e.g., original `T008` → `T008a`, `T008b`
   - The original task ID is retired; do NOT keep it as a parent task.

5. **Rewrite tasks.md**:
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.
   - Replace each flagged task with its sub-tasks (using `a`, `b`, `c` suffixes).
   - Do NOT renumber other tasks — keep all existing task IDs stable.
   - Do NOT modify any task that was not flagged.
   - Keep all other content (phase headers, dependency notes, parallel examples, implementation strategy) unchanged.
   - If splitting a guard-oriented task, include both implementation and validation/regression sub-task coverage so original safety intent is not weakened.
   - Each sub-task MUST follow the standard checklist format:
     ```
     - [ ] T008a [USn] Description with exact file path
     ```

6. **Update the Parallel Examples and Dependencies sections** in tasks.md:
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.
   - Replace any mention of the original task ID with the appropriate sub-task IDs.

7. **Write a breakdown summary** to stdout:
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.
   - Which tasks were split and into what sub-tasks
   - Updated task count (original count → new count)
   - Suggested next step: `/speckit.estimate` (to re-score and verify ≤5 pts)

---

## Behavior Rules

- **Scope discipline**: Sub-tasks must cover exactly the original task's scope — no added features, no dropped scope.
- **Two or three, not one**: A split into a single task is not a split. Minimum 2 sub-tasks.
- **No ID gaps**: Use `a/b/c` suffix notation, not new sequential IDs, to avoid renumbering cascades.
- **Idempotent**: Running this command twice on a task that was already split should detect there are no remaining 8/13-point warnings and exit cleanly.
- **tasks.md is the source of truth**: estimates.md is read-only in this step. The updated tasks.md will be re-estimated by `/speckit.estimate` in the next step.
- **Do not modify tasks that do not need breakdown**: All non-flagged tasks must be byte-for-byte identical after this step.
- **Safety invariants must survive splitting**: Never split in a way that drops async lifecycle cleanup, state-safety/reconciliation verification intent, or local DB transaction-integrity verification intent.
