---
name: speckit-run
description: Use when a user asks Codex to run the repository's speckit.run workflow for an existing feature or a new feature description.
metadata:
  short-description: Dispatch to speckit.run
---

# Speckit Run

Use this skill as the Codex-native entrypoint for the repo's `speckit.run` workflow.

## Dispatch

**IMMEDIATELY**:
1. Run `uv run --no-sync python scripts/pipeline_driver.py "$ARGUMENTS"`.
2. Load `.claude/commands/speckit.run.md`.
3. Execute that command doc exactly.

## Notes

- Do not bypass the driver for phase execution.
- If the request is a new feature description, let the driver bootstrap specify and continue the ledger-driven phase flow.
- The command doc owns the actual workflow, handoffs, gates, and outputs.
- If the command doc is missing, stop and report the missing path.
