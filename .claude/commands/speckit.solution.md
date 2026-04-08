---
description: LLD solutioning phase. Orchestrates tasking → sketch → estimate → solutionreview loop until stable. Hard-blocks if plan.md has unresolved Open Feasibility Questions.
model: opus
handoffs:
  - label: Begin Implementation
    agent: speckit.implement
    prompt: Solution phase complete. Begin implementation.
    send: false
  - label: Run Feasibility Check
    agent: speckit.feasibilityspike
    prompt: Open feasibility questions found — run feasibility spike before proceeding.
    send: false
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

Top-level LLD phase. Reads the proven plan (post-feasibilityspike) and orchestrates three iterative sub-agents until stable: tasking → sketch → estimate. After convergence, runs solutionreview as a quality gate. Emits `solution_approved` when all sub-agents have converged and solutionreview passes (no CRITICAL findings).

## Outline

1. **Setup**: Run `.specify/scripts/bash/check-prerequisites.sh --json` from repo root. Parse `FEATURE_DIR`, `IMPL_PLAN`, `AVAILABLE_DOCS`.

2. **Hard-block gate (MANDATORY)**:
   - Read `## Open Feasibility Questions` in plan.md.
   - If any `- [ ]` items remain (unchecked): **STOP immediately**:
     > "plan.md has N unresolved Open Feasibility Questions. Run `/speckit.feasibilityspike` first to prove all architecture assumptions before the solution phase can proceed."
   - Do NOT continue to sub-agents until this gate passes.

3. **Load context**: Read plan.md `## Technology Selection` — confirm all TBD entries have been filled by feasibilityspike. If any remain TBD: warn and ask user whether to proceed or run `/speckit.feasibilityspike` first.

4. **Auto-invoke `/speckit.tasking`** (MANDATORY):
   - tasking reads plan.md + design artifacts + catalog.yaml
   - Produces `tasks.md` with symbol annotations, [H] tasks, async/state guards
   - If tasks.md already exists: tasking presents a diff and asks for confirmation before overwriting

5. **Auto-invoke `/speckit.sketch`** (MANDATORY — runs after tasking completes):
   - sketch reads tasks.md + codebase context (codegraph, catalog.yaml, touched domain files)
   - Applies reuse-first decision tree per task
   - Produces: estimates.md (sketches + test specs), `.speckit/tasks/T0XX.md` (HUDs), `.speckit/acceptance-tests/story-N.py`
   - sketch may propose task splits → if accepted, loop back to tasking for tasks.md update, then re-run sketch for affected tasks

6. **Auto-invoke `/speckit.estimate`** (MANDATORY — runs after sketch completes):
   - estimate scores all tasks with Fibonacci points
   - If any tasks score 8 or 13: auto-invoke `/speckit.breakdown` for those tasks, then loop back to tasking + sketch for the broken-down tasks
   - Loop continues until no 8/13-point tasks remain

7. **Convergence check**: Confirm loop is stable — tasks.md, estimates.md, and HUDs are all consistent. No task in tasks.md lacks a HUD. No HUD references a symbol not in tasks.md.

8. **Auto-invoke `/speckit.solutionreview`** (MANDATORY — runs after tasking/sketch/estimate converge):
   - solutionreview checks domain compliance at sketch level, cross-task DRY, acceptance test Domain 12 compliance, optimization scan
   - If CRITICAL findings: **HARD BLOCK** — loop back to `/speckit.sketch` for affected tasks, then re-run solutionreview
   - If no CRITICAL findings: solutionreview emits `solutionreview_completed` and solution phase may proceed

9. **Emit `solution_approved`** to `.speckit/pipeline-ledger.jsonl`:
   ```json
   {"event": "solution_approved", "feature_id": "NNN", "phase": "solution", "task_count": N, "story_count": N, "estimate_points": N, "actor": "<agent-id>", "timestamp_utc": "..."}
   ```

10. **Report**: "Solution phase complete. tasks.md, estimates.md, HUDs, and acceptance tests ready. Suggested next: `/speckit.analyze`."

    Always append at end of report:
    ```
    ## Remaining Pipeline to Implementation

    tasks.md + estimates.md are ready. Complete all of the following steps in order before running /speckit.implement:

    1. /speckit.analyze    — cross-artifact consistency check (resolve CRITICAL issues before proceeding)
    2. /speckit.e2e        — generate e2e.md + E2E script (REQUIRED — /speckit.implement will hard-block without these artifacts)
    3. /speckit.implement  — execute tasks in phase order (hard-blocks if estimates.md is missing)
    ```

## Sub-agent loop behavior

- **tasking → sketch → estimate** form an iterative loop. Sub-agents are auto-invoked in sequence; each is independently callable for targeted re-runs.
- sketch may propose splits (if codebase review reveals a task is broader than expected). Any split accepted by the user feeds back to tasking before sketch re-runs for affected tasks.
- estimate's breakdown loop (8/13-point tasks) feeds back to both tasking (for tasks.md update) and sketch (for HUD + acceptance test updates on split tasks).
- The loop is stable when: all tasks ≤ 5 points, all HUDs exist, no sketch-driven task changes are pending.

## Behavior rules

- Hard-block on unresolved Open Feasibility Questions — no exception
- Sub-agents are auto-invoked; user may also call them individually for targeted re-runs
- Trello/ClickUp sync (if auto-sync env vars are set) runs after tasks.md is produced by tasking and stable
- solution_approved is NOT emitted until solutionreview passes with zero CRITICAL findings
