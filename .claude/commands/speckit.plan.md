---
description: Combined plan phase. Triage duplicate/LOE/risk first, then scaffold and fill only the research, architecture, and design-slice sections needed for tasking.
model: opus
handoffs:
  - label: Begin Tasking
    agent: speckit.solution
    prompt: Combined plan is approved. Generate tasks from plan.md design slices.
    send: false
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

Produce one combined `plan.md` artifact that replaces the old `discovery.md`, `research.md`, and `sketch.md` outputs for the normal pipeline path.

## Compact Contract

Run this command through the deterministic plan script:

```bash
uv run python scripts/speckit_plan_step.py --feature-id "$FEATURE_ID" --phase plan --correlation-id "$CORRELATION_ID"
```

The script owns scaffolding. Do not invoke `/speckit.research`, `/speckit.sketch`, or ad hoc subcommands from this command.

The script does the workflow in this order:

1. Resolve `spec.md` and scaffold `plan.md` from the manifest template.
2. Run bounded internal discovery with `scripts/read_code.py context`.
3. Ask Codex to triage the spec from the spec text and discovery:
   - duplicate: if this already exists in the codebase, stop and request `duplicate_marked`
   - t-shirt size: generative LOE judgment, not match-count logic
   - risk: requirement, repo, external, state, runtime, and human/operator risk
4. If not duplicate, rewrite `plan.md` with only the sections required by the triage routing.
5. Fill the selected sections in `plan.md`.
6. Return a driver event request for `plan_approved`; the pipeline driver appends the event.

## Artifact Shape

Always present:

- `## Triage`
- `## Routing Contract`
- `## Internal Discovery`

Non-duplicate plans must also include:

- `## Summary`
- `## Internal Research`
- `## Design Slices`
- `## Plan Completion Summary`

Conditional sections appear only when triage requires them:

- `## External Research`
- `## Architecture Plan`
- `## Architecture Diagram`
- `## Expanded Design Notes`

Do not create `discovery.md`, `research.md`, `sketch.md`, `data-model.md`, or `quickstart.md` in the normal plan path.

## Design Slice Minimum

Every non-duplicate plan must include at least one tasking-ready design slice. For the simplest low-risk work, emit exactly one low-estimated slice.

Each slice must include objective, estimated LOE, primary seam, touched files, touched symbols, likely new files, reuse/modify/create classification, constraints, dependency relationship, verification concern, and an implementation directive.

## Driver Contract

The script returns a normal step-result envelope plus `pipeline_event_request`.

Duplicate outcome:

```json
{"event":"duplicate_marked","fields":{"triage":{},"routing":{},"risk":{}}}
```

Approved outcome:

```json
{"event":"plan_approved","fields":{"feasibility_required":false,"triage":{},"routing":{},"risk":{}}}
```

The command doc describes the requested event only. The pipeline driver records the ledger event after the script result is accepted.

## Behavior Rules

- Do not infer t-shirt size from the number of discovery matches.
- Do not keep irrelevant empty sections after triage.
- Do not use separate research or sketch artifacts for normal pipeline execution.
- Do not generate `tasks.md`; solution/tasking consumes the design slices in `plan.md`.
- If repo reads do not support a design claim, record the gap in the smallest relevant selected section instead of inventing certainty.
