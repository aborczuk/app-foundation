---
description: Close a completed task through the canonical append-first ledger path and hand off to checkpoint when a user story ends
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding.

## Purpose

Close the current task through one append-first path that records the task evidence, updates the task ledger, marks `[X]` in `tasks.md`, and emits a compact next-action payload. When the current user story is complete, the command hard-stops by handing off to `/speckit.checkpoint`.

## Outline

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --include-tasks` from repo root and parse `FEATURE_DIR` and `AVAILABLE_DOCS`.
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.
2. Require `--commit-sha` and `--qa-run-id` in the user input or reject the request.
3. Invoke:

   ```bash
   uv run python scripts/speckit_closeout_task.py \
     --feature-id "<feature_id>" \
     --task-id "T0XX" \
     --tasks-file "$FEATURE_DIR/tasks.md" \
     --ledger-file ".speckit/task-ledger.jsonl" \
     --commit-sha "<commit_sha>" \
     --qa-run-id "<qa_run_id>" \
     --json
   ```

4. Parse the JSON payload:
   - `next_action=continue`: report the compact status line and stop.
   - `next_action=checkpoint`: invoke `/speckit.checkpoint [phase]` and stop.
5. Do not emit a prose summary. Return only the compact status line plus the closeout payload fields.

## Contract

- Closeout must remain ledger-first.
- The command must not manually rewrite task state outside the canonical closeout script.
- The command must preserve the silent-continuation behavior between tasks and the hard stop at story boundaries.
