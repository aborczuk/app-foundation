---
name: specify
description: Use when a user asks Codex to run the repository spec workflow for a new or updated feature.
metadata:
  short-description: Dispatch to speckit.specify
---

# Specify

Use this skill as the Codex-native entrypoint for the repo's `speckit.specify` workflow.

## Dispatch

1. Run `python3 scripts/specify_fastpath.py [--short-name "<name>"] "$ARGUMENTS"`.
2. Load `.claude/commands/speckit.specify.md`.
3. Execute that command doc exactly.

## Notes

- Do not substitute a shortened helper-only flow.
- The command doc owns the actual spec workflow, handoffs, gates, and outputs.
- If the command doc is missing, stop and report the missing path.
