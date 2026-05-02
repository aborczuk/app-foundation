---
description: Create or update the feature specification from a natural language feature description.
model: opus
handoffs:
  - label: Research Prior Art & Integration Options
    agent: speckit.research
    prompt: Research patterns, prior art, and integration options for the spec...
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Fast Path

1. Run the fast-path helper first:

   ```bash
   python3 scripts/specify_fastpath.py [--short-name "<name>"] "$ARGUMENTS"
   ```

   This helper pins the repo-local UV cache, runs the mandatory codegraph discovery terms in parallel, and scaffolds `spec.md`.
2. Use the helper's discovery output and scaffold as the input for the spec-writing pass.
3. If discovery reports matches, read the matched context before writing the spec. If it reports no matches, say so explicitly in the spec output.
4. Do not stop after scaffolding: fully populate every required section in `spec.md` and keep iterating until routing validation passes.
5. In update mode, resolve the current spec paths with:

   ```bash
   uv run --no-sync python3 .specify/scripts/python/check_prerequisites.py --json --paths-only
   ```

   Then update the existing `spec.md` in place.
5. If the description is empty, error with `No feature description provided`.
6. If the description starts with `--update-current-spec`, treat it as update mode and strip the flag before continuing.

## Spec Writing

1. Load `.specify/templates/spec-template.md` for the required section order.
2. Fill the scaffolded `SPEC_FILE` using the feature description and the template structure.
3. Keep the routing contract values exact:
   - `research_route`: `skip` or `required`
   - `plan_profile`: `skip`, `lite`, or `full`
   - `sketch_profile`: `core` or `expanded`
   - `tasking_route`: `required` or `attach_to_existing_feature`
   - `estimate_route`: `required_after_tasking` or `reuse_existing_estimate`
4. If conditional sketch sections are needed, use the canonical names from `scripts/spec_routing.py` exactly.
5. Keep the spec focused on user value, not implementation details.

## Validation

1. Validate the routing contract:

   ```bash
   uv run --no-sync python3 scripts/speckit_spec_gate.py validate-routing --spec-file "$SPEC_FILE" --json
   ```

2. Review the generated spec output and mark findings.
3. If validation fails, update the spec and re-run the gate until it passes.

## Completion

1. After validation passes, estimate the rough feature size.
2. Report:
   - branch name
   - spec file path
   - size estimate
   - the actual next phase from the pipeline driver
   - readiness for the next phase, only after the spec content is fully populated and the routing contract validates
   - `Next phase: <Insert Phase>`
3. In update mode, explicitly state that the spec was updated in place and no new branch was created.

## Notes

- The fast-path helper covers cache setup and discovery so those steps are not repeated manually.
- `scripts/bootstrap_session.py` is the shared bootstrap entrypoint for implement-side UV cache setup and codegraph warmup.
- Do not substitute a shortened helper-only flow for the actual spec writing and validation steps above.
