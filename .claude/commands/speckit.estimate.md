---
description: Estimate fibonacci complexity for each task in tasks.md and produce estimates.md. Points-only command.
handoffs:
  - label: Break Down Large Tasks
    agent: speckit.breakdown
    prompt: Break down tasks flagged with 8 or 13-point warnings into smaller pieces.
    send: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

Assign fibonacci points (1, 2, 3, 5, 8, 13) to tasks in `tasks.md` using codebase-aware rationale, and write `estimates.md`.

This command is **points-only** in the sketch-first pipeline:
- no HUD generation,
- no acceptance-test generation,
- no task-list editing.

## Outline

1. **Setup**: Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` once from repo root. Parse `FEATURE_DIR` and `TASKS`.

2. **Load context**:
   - Required: `tasks.md`, `plan.md`
   - Optional: `data-model.md`, `contracts/*`, `research.md`, prior `estimates.md`

3. **Evaluate each task** across:
   - code complexity,
   - integration surface,
   - uncertainty/risk.

4. **Assign points and rationale**:
   - Use fibonacci scale and warn on 8/13.
   - Rationale must cite concrete codebase patterns or constraints.

5. **Generate `estimates.md`**:
   ```bash
   uv run python .specify/scripts/pipeline-scaffold.py speckit.estimate --feature-dir "$FEATURE_DIR" FEATURE_NAME="[Feature Name]"
   ```
   Fill:
   - per-task points table,
   - per-phase totals,
   - warnings.

6. **Emit pipeline event**:
   ```json
   {"event": "estimation_completed", "feature_id": "NNN", "phase": "solution", "estimate_points": N, "actor": "<agent-id>", "timestamp_utc": "..."}
   ```
   Append to `.speckit/pipeline-ledger.jsonl`.

7. **Report**:
   - path to `estimates.md`
   - total points and phase totals
   - any 8/13 warnings requiring `/speckit.breakdown`

## Behavior rules

- Read-only on `tasks.md`.
- Do not create or modify HUD files.
- Do not create acceptance tests.
- Do not emit implementation guidance that contradicts `sketch.md` or `plan.md`.
