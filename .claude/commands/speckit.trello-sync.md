---
description: Sync the current feature's tasks.md to a Trello board using the MCP Trello Bridge.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty). If a board_id is provided in the user input, use it. Otherwise fall back to the TRELLO_BOARD_ID env var.

## Outline

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root and parse `FEATURE_DIR` and `AVAILABLE_DOCS`. All paths must be absolute.
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.

2. Derive the tasks.md path: `FEATURE_DIR/tasks.md`. Confirm it exists.
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.

3. Call the `sync_tasks_to_trello` MCP tool with:
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.
   - `tasks_md_path`: absolute path to tasks.md
   - `board_id`: from user input or omit to use TRELLO_BOARD_ID env var

4. Report the result:
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.
   - **Success**: Show created / updated / unchanged counts
   - **Aborted**: Show abort_reason and suggest fixes
   - **Errors**: List any per-task errors

5. If `created > 0` or `updated > 0`, remind the user the board now reflects the latest tasks.md state.
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.
