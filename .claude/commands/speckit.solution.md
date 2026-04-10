---
description: LLD solutioning phase. Orchestrates sketch -> solutionreview -> tasking -> analyze. Emits solution_approved before analyze.
model: opus
handoffs:
  - label: Begin Implementation
    agent: speckit.implement
    prompt: Solution and analysis phases complete. Begin implementation.
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

Top-level LLD phase for sketch-first planning. `/speckit.solution` now enforces:

1. sketch blueprint generation,
2. sketch quality review,
3. post-sketch task decomposition with estimate/breakdown stabilization and HUD/test generation,
4. solution approval event,
5. post-solution drift analysis.

## Outline

1. **Setup**: Run `.specify/scripts/bash/check-prerequisites.sh --json` from repo root. Parse `FEATURE_DIR`, `IMPL_PLAN`, and `AVAILABLE_DOCS`.

2. **Hard-block gate (MANDATORY)**:
   - Read `## Open Feasibility Questions` in plan.md.
   - If any unchecked items remain, stop and route to `/speckit.feasibilityspike`.

3. **Auto-invoke `/speckit.sketch`**:
   - Produce `FEATURE_DIR/sketch.md`.
   - Sketch must include symbol recon, strategy options, and domain constraints by work type.

4. **Auto-invoke `/speckit.solutionreview`**:
   - Review `sketch.md`.
   - If CRITICAL findings exist, loop back to `/speckit.sketch` and re-run `/speckit.solutionreview`.

5. **Auto-invoke `/speckit.tasking`**:
   - Decompose approved sketch into `tasks.md`.
   - Run estimate/breakdown subprocess loop to settle points.
   - Run deterministic tasks format gate.
   - Generate HUDs and acceptance tests only after stabilization.

6. **Emit `solution_approved`** to `.speckit/pipeline-ledger.jsonl`:
   ```json
   {"event": "solution_approved", "feature_id": "NNN", "phase": "solution", "task_count": N, "story_count": N, "estimate_points": N, "actor": "<agent-id>", "timestamp_utc": "..."}
   ```

7. **Auto-invoke `/speckit.analyze`** (post-solution drift gate):
   - Analyze consistency across `spec -> plan -> sketch -> tasks`.
   - `analysis_completed` remains a separate event emitted by `/speckit.analyze`.

8. **Report**:
   - "Solution phase complete and analysis executed."
   - List generated artifacts: `sketch.md`, `solutionreview.md`, `tasks.md`, `estimates.md`, HUDs, acceptance tests, analysis report.
   - Suggested next: `/speckit.e2e`.

## Behavior rules

- Hard-block on unresolved Open Feasibility Questions.
- Do not emit `solution_approved` before sketch review and tasking stabilization complete.
- `solution_approved` is solution-phase completion; analysis remains a separate post-solution gate event.
