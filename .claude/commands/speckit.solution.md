---
description: LLD solutioning phase. Orchestrates sketch -> solutionreview -> tasking -> analyze. Produces the solution_approved payload before analyze.
model: opus
handoffs:
  - label: Begin Implementation
    agent: speckit.implement
    prompt: Solution and analysis phases complete. Begin implementation.
    send: false
  - label: Run Feasibility Check
    agent: speckit.feasibilityspike
    prompt: Open feasibility questions found — run feasibility spike before proceeding.
    send: false
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Compact Contract (Load First)

Top-level LLD phase for sketch-first planning. Produce the `solution_approved` payload and keep the sketch/review/tasking/analyze sequence driver-owned.

- Resolve `FEATURE_DIR`, `IMPL_PLAN`, and `AVAILABLE_DOCS` from the feature workspace.
- Read the spec routing contract first and treat it as authoritative for plan/sketch size.
- Use `plan.md` as a required input only when `plan_profile != skip`; otherwise ground the solution flow in `spec.md`, the routing contract, and repo reality.
- Preserve the downstream handoff contract that yields `solution_approved` for pipeline orchestration.
- Keep the detailed repo-grounding and auto-invoke sequence in the expanded guidance.

## Expanded Guidance (Load On Demand)

### 1. Setup

Run `.specify/scripts/bash/check-prerequisites.sh --json` from repo root. Parse `FEATURE_DIR`, `IMPL_PLAN`, and `AVAILABLE_DOCS`.

### 2. Hard-block gate (MANDATORY)

- Read the routing contract from `spec.md` first.
- If `plan_profile != skip`:
  - Read `## Open Feasibility Questions` in `plan.md`.
  - If any unchecked items remain, stop and route to `/speckit.feasibilityspike`.
- If `plan_profile = skip`:
  - Do not require `plan.md`.
  - Do not route to `/speckit.feasibilityspike` only because the skipped plan artifact is absent.

### 2a. Read hierarchy gate (MANDATORY for this phase and all auto-invoked subcommands)

- Use this order whenever repo code/docs are used for sketching, review, decomposition, or drift analysis:
  1. Run helper entrypoints first:
     - Code: `source scripts/read-code.sh && read_code_context <file> <symbol_or_pattern> 80`
     - Markdown: `source scripts/read-markdown.sh && read_markdown_section <file> <section_heading>`
  2. Treat helper output as semantic-first + exact bounded read anchor.
  3. Run `discovery checks` (`codegraph` blast-radius/caller/callee/import checks) from that anchored seam.
- Do not start with broad `codegraph` sweeps before helper-driven reads, unless those reads fail.
- This ordering applies to `/speckit.sketch`, `/speckit.solutionreview`, `/speckit.tasking`, and `/speckit.analyze` in the current solution run.

### 3. Auto-invoke `/speckit.sketch`

- Produce `FEATURE_DIR/sketch.md`.
- Sketch must include the current template's core sections:
  - Coverage
  - Current → Target
  - Primary Seam
  - Required Edit / Solution
  - Verification
  - Constraints / Preserve
  - Implementation Directive
  - Design-to-Tasking Contract
  - Sketch Completion Summary
- Conditional sketch sections are only required when the routing contract or actual repo context triggers them.
- If `sketch_profile = core`, do not require the expanded conditional sections just to satisfy the review loop.

### 4. Auto-invoke `/speckit.solutionreview`

- Review `sketch.md`.
- If CRITICAL findings exist, loop back to `/speckit.sketch` and re-run `/speckit.solutionreview`.

### 5. Auto-invoke `/speckit.tasking`

- Decompose approved sketch into `tasks.md`.
- Treat the core sketch contract as sufficient input when `sketch_profile = core`.
- Only require the expanded/conditional sketch sections when the routing contract enables them or the work truly needs them.
- Run estimate/breakdown subprocess loop to settle points.
- Run deterministic tasks format gate.
- Generate HUDs and acceptance tests only after stabilization.

### 6. Produce `solution_approved`

The command doc describes the `solution_approved` payload only. The pipeline driver records the event after the payload is accepted:

```json
{"event":"solution_approved","feature_id":"NNN","phase":"solution","task_count":N,"story_count":N,"estimate_points":N,"actor":"<agent-id>","timestamp_utc":"..."}
```

### 7. Auto-invoke `/speckit.analyze`

- Analyze consistency across `spec -> sketch -> tasks`, and include `plan.md` in that chain only when routing kept the plan phase enabled.
- `analysis_completed` remains a separate event emitted by `/speckit.analyze`.

### 8. Report

- "Solution phase complete and analysis executed."
- List generated artifacts: `sketch.md`, `solutionreview.md`, `tasks.md`, `estimates.md`, HUDs, acceptance tests, analysis report.
- Suggested next: `/speckit.e2e`.

## Behavior rules

- Hard-block on unresolved Open Feasibility Questions.
- Enforce phase read hierarchy: `helper-driven read (semantic+exact) -> discovery checks` before any design claim grounded in repo context.
- Do not emit `solution_approved` before sketch review and tasking stabilization complete.
- Do not claim direct ledger append ownership in the command doc; `solution_approved` is produced for orchestration, not written here.
- `solution_approved` is solution-phase completion; analysis remains a separate post-solution gate event.
