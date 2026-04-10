---
description: Decompose approved `sketch.md` into executable tasks, run estimate/breakdown subprocess loop, then generate HUDs and acceptance tests. Sub-agent of /speckit.solution; callable standalone.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

Generate `tasks.md` from an approved sketch blueprint and finalize downstream execution artifacts in this order:

1. task decomposition,
2. estimate/breakdown subprocess loop,
3. deterministic format gate,
4. HUD generation,
5. acceptance-test generation.

## Outline

1. **Setup**: Run `.specify/scripts/bash/check-prerequisites.sh --json` from repo root. Parse `FEATURE_DIR` and `AVAILABLE_DOCS`.

2. **Hard-block gate**:
   - Require `FEATURE_DIR/sketch.md`.
   - Require a passing sketch review (latest `solutionreview_completed` must have `critical_count == 0`).

3. **Load context**:
   - Required: `sketch.md`, `spec.md`, `plan.md`
   - Optional: `research.md`, `catalog.yaml`

4. **Generate `tasks.md`** by pre-scaffolding:
   ```bash
   uv run python .specify/scripts/pipeline-scaffold.py speckit.tasking --feature-dir "$FEATURE_DIR" FEATURE_NAME="[Feature Name]"
   ```
   Then fill tasks from sketch units with:
   - phase/story grouping,
   - `[H]` task placement before implementation tasks,
   - `file:symbol` annotations,
   - dependency ordering and parallel opportunities.

5. **Estimate/breakdown subprocess loop (mandatory)**:
   - Invoke `/speckit.estimate` against current `tasks.md`.
   - If any task scores 8/13, invoke `/speckit.breakdown`, then re-run estimate.
   - Repeat until no 8/13 tasks remain.
   - Emit **one aggregated** `estimation_completed` event for the final settled task set.

6. **Deterministic tasks format gate (mandatory)**:
   ```bash
   python scripts/speckit_tasks_gate.py validate-format --tasks-file "$FEATURE_DIR/tasks.md" --json
   ```
   - If non-zero exit: fix and re-run before continuing.

7. **Generate HUDs only after tasks are stable**:

   **Code task HUD**
   ```bash
   uv run python .specify/scripts/pipeline-scaffold.py speckit.tasking.hud-code \
     TASK_ID=T0XX DESCRIPTION="[Task description]" FEATURE_ID="[feature-id]"
   ```

   **Human task HUD**
   ```bash
   uv run python .specify/scripts/pipeline-scaffold.py speckit.tasking.hud-runbook \
     TASK_ID=T0XX DESCRIPTION="[Task description]" FEATURE_ID="[feature-id]"
   ```

8. **Generate acceptance tests**:
   - For each story, write `.speckit/acceptance-tests/story-N.py` from independent test criteria in `tasks.md`.
   - Tests must be deterministic PASS/FAIL oracles.

9. **Emit pipeline event**:
   ```json
   {"event": "tasking_completed", "feature_id": "NNN", "phase": "solution", "task_count": N, "story_count": N, "actor": "<agent-id>", "timestamp_utc": "..."}
   ```
   Append to `.speckit/pipeline-ledger.jsonl`.

10. **Report**:
   - path to `tasks.md`
   - settled estimate summary
   - HUD count and acceptance-test count
   - suggested next: `/speckit.analyze`

## Task format rules

Every task MUST follow: `- [ ] TNNN [P?] [H?] [USN?] Description — file:symbol`

- `[P]` only if parallelizable with no incomplete dependencies
- `[H]` only if external human action is required; mutually exclusive with `[P]`
- `[USN]` required in user-story phases
- `file:symbol` required unless net-new file has no symbol yet

## Behavior rules

- Do not create HUDs before estimate/breakdown stabilization.
- Do not skip deterministic format validation.
- Do not mutate `sketch.md`; treat it as input contract.
