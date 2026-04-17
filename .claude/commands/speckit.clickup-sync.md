---
description: Bootstrap or report ClickUp sync status for the current speckit feature tree.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding. If `--status` is present in user input, run status mode; otherwise run bootstrap mode.

## Outline

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --include-tasks` from repo root and parse `PROJECT_ROOT`, `FEATURE_DIR`, and `AVAILABLE_DOCS`.
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.

2. Validate runtime environment variables:
   - `CLICKUP_API_TOKEN`
   - `CLICKUP_SPACE_ID`

3. Build command:
   - Bootstrap: `uv run python -m mcp_clickup`
   - Status: `uv run python -m mcp_clickup --status`

4. Execute command and summarize outcome:
   - Success: report created/updated/skipped (bootstrap) or grouped status totals (`--status`)
   - Failure: report error code and actionable hint

5. If bootstrap changed ClickUp items, remind the operator that `.speckit/clickup-manifest.json` may have been updated and should be reviewed.

## Usage Examples

- Bootstrap current speckit tree:
  - `uv run python -m mcp_clickup`
- Read-only status summary:
  - `uv run python -m mcp_clickup --status`
- Example environment:
  - `export CLICKUP_API_TOKEN=...`
  - `export CLICKUP_SPACE_ID=...`
  - `export SPECKIT_ROOT=/abs/path/to/repo`

## Status Troubleshooting

- `ERROR [manifest_missing]`:
  - Run bootstrap once to create `.speckit/clickup-manifest.json`.
- `ERROR [manifest_version]`:
  - Regenerate or migrate the manifest to schema version `1`.
- `ERROR [rate_limit]`:
  - Wait for ClickUp's rate window, then re-run.
- `ERROR [space_not_found]`:
  - Verify `CLICKUP_SPACE_ID` and token access scope.
