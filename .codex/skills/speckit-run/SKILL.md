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
1. Run `uv run --no-sync python scripts/pipeline_driver.py "$ARGUMENTS"` **once**.
2. Return the driver's result directly. Do not re-dispatch or execute `.claude/commands/speckit.run.md` afterward.

## Notes

- `scripts/pipeline_driver.py` is the sole runtime routing owner; never invoke it twice for one request.
- For a new feature description, the driver scaffolds `spec.md` on `main` (no branch, no subrunner) and returns `next_phase: "specify"`. Author `spec.md` directly, then run `uv run --no-sync python scripts/pipeline_driver.py --feature-id <feature_id>` to validate it and emit `backlog_registered`.
- Do not bypass the driver or create feature branches before `implement`.
