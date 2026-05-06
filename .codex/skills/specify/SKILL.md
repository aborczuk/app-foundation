---
name: specify
description: Use when a user asks Codex to run the repository spec workflow for a new or updated feature.
metadata:
  short-description: Dispatch to speckit.specify
---

# Specify

Use this skill as the Codex-native entrypoint for the repo's `speckit.specify` workflow.

## Dispatch
**IMMEDIATLY**:
1. Run `uv run --no-sync python3 scripts/speckit_specify_step.py [--short-name "<name>"] "$ARGUMENTS"`.

Then,
2. Load `.claude/commands/speckit.specify.md`.
3. Use the scaffold and metadata it produced to write the spec locally.

## Notes

- Do not substitute a shortened helper-only flow or add a Codex subrunner handoff.
- The helper owns bootstrap and scaffold creation; the command doc owns manual spec writing, gates, and outputs.
- The helper does not consume feature ids or correlation ids; pipeline routing handles that adapter concern.
- If the command doc is missing, stop and report the missing path.
