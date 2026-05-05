
1. If the description is empty, error with `No feature description provided`.
2. If the description starts with `--update-current-spec`, treat it as update mode and strip the flag before continuing.

## Spec Writing

1. Load the scaffolded `SPEC_FILE` in the feature folder first.
2. Fill the scaffolded `SPEC_FILE` using the feature description, the `discovery.md` file in the spec folder, and the template structure.
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
