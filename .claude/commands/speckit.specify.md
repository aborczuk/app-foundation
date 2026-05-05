
1. If the description is empty, error with `No feature description provided`.
2. If the description starts with `--update-current-spec`, treat it as update mode and strip the flag before continuing.

## Spec Writing

1. Load the scaffolded `SPEC_FILE` in the feature folder first.
2. Fill the scaffolded `SPEC_FILE` using the feature description and the template structure.
3. Keep the spec focused on user value, requirements, and clarifications, not implementation details or routing decisions.
4. If clarification markers appear, extract them and resolve them before moving on.

## Validation

1. Validate any clarification markers:

   ```bash
   uv run --no-sync python3 scripts/speckit_spec_gate.py extract-clarifications --spec-file "$SPEC_FILE" --json
   ```

2. Review the generated spec output and mark findings.
3. If clarification markers remain, update the spec and re-run the extractor until it is clean.

## Completion

1. After validation passes, confirm the spec requirements are complete.
2. Report:
   - branch name
   - spec file path
   - the actual next phase from the pipeline driver
   - readiness for the next phase, only after the spec content is fully populated and clarification markers are resolved
   - `Next phase: <Insert Phase>`
3. In update mode, explicitly state that the spec was updated in place and no new branch was created.

## Notes

- The fast-path helper covers cache setup and scaffold creation so those steps are not repeated manually; research owns patterns and discovery.
- `scripts/bootstrap_session.py` is the shared bootstrap entrypoint for implement-side UV cache setup and codegraph warmup.
- Do not substitute a shortened helper-only flow for the actual spec writing and validation steps above.
