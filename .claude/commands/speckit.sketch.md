---
description: Generate pre-task low-level design blueprint (`sketch.md`) from plan/spec/codebase context. Sub-agent of /speckit.solution; callable standalone.
handoffs:
  - label: Review Sketch Blueprint
    agent: speckit.solutionreview
    prompt: Sketch blueprint is ready. Run sketch-focused solution review.
    send: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

Produce a design-first blueprint before task decomposition. `/speckit.sketch` now runs **before** `/speckit.tasking` and owns only `sketch.md` generation. It must not create `tasks.md`, HUDs, acceptance tests, or estimates.

## Outline

1. **Setup**: Run `.specify/scripts/bash/check-prerequisites.sh --json` from repo root. Parse `FEATURE_DIR`, `IMPL_PLAN`, and `AVAILABLE_DOCS`.

2. **Hard-block gate**:
   - Require `spec.md` and `plan.md` to exist.
   - If plan has unresolved `## Open Feasibility Questions` (`- [ ]`), **STOP** and instruct `/speckit.feasibilityspike`.

3. **Load design context**:
   - Required: `spec.md`, `plan.md`
   - Optional: `research.md`, `spike.md`, `catalog.yaml`
   - Extract story goals, acceptance criteria anchors, constraints, and architecture decisions.

4. **Work-type classification (mandatory)**:
   - Classify each story/capability into work types (integration, async orchestration, data flow, policy/gating, etc.).
   - For each work type, identify common strategy patterns already used in this codebase or documented in research artifacts.

5. **Codebase symbol recon (mandatory)**:
   - Use codegraph discovery for candidate `file:symbol` targets.
   - Resolve callers/callees for impacted symbols.
   - Record reusable local symbols and external reuse candidates.

6. **Domain review by work type (mandatory)**:
   - Read only touched domain files inferred by work type.
   - Always include Domain 13, Domain 14, and Domain 17.
   - Record MUST constraints that tasking/implementation must preserve.

7. **Generate `sketch.md` blueprint**:
   - Run scaffold:
     ```bash
     uv run python .specify/scripts/pipeline-scaffold.py speckit.sketch --feature-dir "$FEATURE_DIR" FEATURE_ID="NNN" FEATURE_NAME="[Feature Name]"
     ```
   - Fill sections with:
     - work-type classification,
     - symbol/call-graph recon,
     - preferred strategy + alternatives,
     - domain guardrails,
     - decomposition-ready sketch units.

8. **Emit pipeline event**:
   ```json
   {"event": "sketch_completed", "feature_id": "NNN", "phase": "solution", "actor": "<agent-id>", "timestamp_utc": "..."}
   ```
   Append to `.speckit/pipeline-ledger.jsonl`.

9. **Report**:
   - Path to `sketch.md`
   - Work types covered
   - Symbols reviewed
   - Reuse strategy summary
   - Domain constraints captured
   - Suggested next: `/speckit.solutionreview`

## Behavior rules

- This command is **design-only**; no task/HUD/test/estimate artifacts are generated.
- Do not write `.speckit/tasks/` or `.speckit/acceptance-tests/` here.
- Do not mutate production code.
- If sketch is re-run, update only blueprint sections affected by changed plan/spec/research context.
