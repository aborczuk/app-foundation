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

Top-level LLD phase for sketch-first planning. Run these steps first; only load expanded guidance when a gate fails or the user asks for detail.

1. Run `.specify/scripts/bash/check-prerequisites.sh --json` from repo root and parse `FEATURE_DIR`, `IMPL_PLAN`, and `AVAILABLE_DOCS`.
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.
2. Read `## Open Feasibility Questions` in `plan.md`.
   - If any unchecked items remain, stop and route to `/speckit.feasibilityspike`.
3. Auto-invoke `/speckit.sketch`.
4. Auto-invoke `/speckit.solutionreview`.
5. Auto-invoke `/speckit.tasking`.
6. Produce the `solution_approved` payload for pipeline orchestration.
7. Auto-invoke `/speckit.analyze` as the post-solution drift gate.

## Expanded Guidance (Load On Demand)

### 1. Setup

Run `.specify/scripts/bash/check-prerequisites.sh --json` from repo root. Parse `FEATURE_DIR`, `IMPL_PLAN`, and `AVAILABLE_DOCS`.

### 2. Hard-block gate (MANDATORY)

- Read `## Open Feasibility Questions` in `plan.md`.
- If any unchecked items remain, stop and route to `/speckit.feasibilityspike`.

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
- Sketch must include the contract sections required by the current sketch template, especially:
  - `Solution Narrative`
  - `Construction Strategy`
  - `Command / Script Surface Map`
  - `Manifest Alignment Check`
  - `Design-to-Tasking Contract`
  - `Decomposition-Ready Design Slices`

### 4. Auto-invoke `/speckit.solutionreview`

- Review `sketch.md`.
- If CRITICAL findings exist, loop back to `/speckit.sketch` and re-run `/speckit.solutionreview`.

### 5. Auto-invoke `/speckit.tasking`

- Decompose approved sketch into `tasks.md`.
- Run estimate/breakdown subprocess loop to settle points.
- Run deterministic tasks format gate.
- Generate HUDs and acceptance tests only after stabilization.

### 6. Produce `solution_approved`

The command doc describes the `solution_approved` payload only. The pipeline driver records the event after the payload is accepted:

```json
{"event":"solution_approved","feature_id":"NNN","phase":"solution","task_count":N,"story_count":N,"estimate_points":N,"actor":"<agent-id>","timestamp_utc":"..."}
```

### 7. Auto-invoke `/speckit.analyze`

- Analyze consistency across `spec -> plan -> sketch -> tasks`.
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
