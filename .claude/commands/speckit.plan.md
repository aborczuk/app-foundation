## User Input

- `FEATURE_ID`: required feature identifier, for example `023` or `023-some-feature`

## Purpose

Run one combined plan command that starts with duplicate/LOE/risk triage, then scales the plan and sketch depth only as far as the spec actually needs.

## Compact Contract

This is a normal command-file workflow. Do not call `scripts/speckit_codex_handoff_runner.py`, do not create a nested Codex subrunner, and do not hide the plan logic in another prompt payload.

Use [`scripts/speckit_plan_step.py`](/Users/andreborczuk/app-foundation/scripts/speckit_plan_step.py) only as a local scaffold and validation helper.

The full documented section set lives in [`plan-template.md`](/Users/andreborczuk/app-foundation/.specify/templates/plan-template.md). The helper script prunes that template by heading so `plan.md` only contains the sections justified by triage.

1. Run the triage scaffold helper:

```bash
uv run python scripts/speckit_plan_step.py prepare-triage --feature-id "$FEATURE_ID"
```

2. Open `plan.md`. At this point it must contain only:
   - `## Triage`
   - `## Strategy Contract`
   - `## Internal Discovery`

3. Fill only `## Triage` and `## Strategy Contract` first.
   - Duplicate is a generative judgment based on the spec plus repo evidence.
   - T-shirt size is a generative judgment. Do not infer t-shirt size from the number of discovery matches.
   - Risk is a generative judgment across `overall`, requirement clarity, repo uncertainty, external dependency uncertainty, state/data migration risk, runtime side-effect risk, and human/operator dependency.
   - Relevant domains are a generative judgment using the 17 constitution domains. Only include domains that need explicit planning treatment.
   - Strategy is a generative judgment about whether this plan needs external research, architecture strategy, an architecture diagram, or expanded design notes.

4. If triage says `duplicate: true`:
   - Stop the workflow there.
   - Do not add research, architecture, or design-slice sections.
   - Add `## Plan Completion Summary` that explains the duplicate call and why the plan stopped.
   - Run finalize and return the exact JSON it prints:

```bash
uv run python scripts/speckit_plan_step.py finalize --feature-id "$FEATURE_ID" --phase plan --correlation-id "$CORRELATION_ID"
```

5. If triage says `duplicate: false`:
   - Run the strategy rewrite helper:

```bash
uv run python scripts/speckit_plan_step.py apply-strategy --feature-id "$FEATURE_ID"
```

   - Re-open `plan.md` after the rewrite.
   - Fill only the sections the helper selected. Do not reintroduce omitted sections.
   - Run finalize and return the exact JSON it prints:

```bash
uv run python scripts/speckit_plan_step.py finalize --feature-id "$FEATURE_ID" --phase plan --correlation-id "$CORRELATION_ID"
```

## Artifact Shape

Initial scaffold from `prepare-triage`:

- `## Triage`
- `## Strategy Contract`
- `## Internal Discovery`

The documented superset of possible sections lives in `.specify/templates/plan-template.md`.

Possible post-triage sections chosen by `apply-strategy`:

- `## Summary`
- `## Relevant Domains`
- `## Internal Research`
- `## External Research`
- `## Architecture Strategy`
- `## Architecture Diagram`
- `## Expanded Design Notes`
- `## Design Slices`
- `## Plan Completion Summary`

The helper rewrites `plan.md` after triage by pruning the documented template. The template stays comprehensive as documentation; the emitted artifact stays minimal.

## Strategy

Use the strategy contract to express the selected planning treatment:

- `domains.relevant`: which constitution domains need explicit planning treatment
- `domains.reasoning`: why each selected domain matters
- `external_research`: `true` only when repo-local evidence is not enough
- `architecture_strategy`: `true` only when the plan needs explicit architecture treatment
- `architecture_diagram`: `true` only when the plan genuinely needs an architecture view
- `expanded_design_notes`: `true` only when terse slices would be too handwavey

Domain selection should be the primary driver. Size and risk explain breadth and rigor; domains explain what kind of problem is being solved.

Smaller path:

- internal discovery
- relevant domains
- short internal research
- one low-estimated design slice
- concise completion summary

Broader or riskier path:

- relevant domains with reasoning
- internal research plus external research
- architecture strategy plus architecture diagram
- expanded design notes when needed
- as many tasking-ready design slices as the actual seams require

## Design Slice Minimum

Every non-duplicate plan must include at least one tasking-ready design slice so tasking can register work and implement can start.

For the smallest low-risk scope, emit exactly one low-estimated slice. That slice must still be concrete enough for tasking to create one task from it.

## Driver Contract

The command ends by running `finalize`. The final response from this command must be the exact JSON emitted by `finalize`, with no extra prose around it. That payload is what the pipeline driver uses to append either:

- `duplicate_marked`
- `plan_approved`

The payload must preserve triage, domains, strategy, and risk so the ledger documents why the selected planning treatment was used.

## Behavior Rules

- Do not create `discovery.md`, `research.md`, `sketch.md`, `data-model.md`, or `quickstart.md` in the normal plan path.
- Do not call `/speckit.research` or `/speckit.sketch`.
- Do not re-expand the scaffold after `apply-strategy`.
- Do not include external research unless the strategy contract requires it.
- Do not omit `## Plan Completion Summary`; finalize depends on it.
- If repo evidence is insufficient for a claim, say so directly in the smallest relevant selected section instead of pretending the repo proves more than it does.
