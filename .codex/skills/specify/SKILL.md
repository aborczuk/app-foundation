---
name: specify
description: Use when a user asks Codex to run the repository spec workflow for a new or updated feature.
metadata:
  short-description: Dispatch to speckit.specify
---

# Specify

Use this skill as the Codex-native entrypoint for the repo's `speckit.specify` workflow.

## Dispatch
**IMMEDIATELY**:
1. Run `uv run --no-sync python scripts/pipeline_driver.py [--short-name "<name>"] "$ARGUMENTS"` to scaffold `spec.md` on `main` (no branch, no subrunner).
2. Load `.claude/commands/speckit.specify.md` and write `spec.md` locally.
3. Run `uv run --no-sync python scripts/pipeline_driver.py --feature-id <feature_id>` to validate `spec.md` and emit `backlog_registered`.

## Notes

- Do not spawn a Codex subrunner or create a feature branch during `specify`; branching belongs to `implement`.
- `scripts/speckit_specify_step.py` handles deterministic scaffold creation and deterministic `spec.md` validation only; the current agent authors `spec.md`.
- If `.claude/commands/speckit.specify.md` is missing, stop and report the missing path.
