---
description: Generate a pre-task low-level design blueprint (`sketch.md`) from approved planning context and repo reality. Sub-agent of `/speckit.solution`; callable standalone.
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

Produce the feature-level low-level design that bridges the approved plan to the actual repository before task decomposition.

`/speckit.sketch` runs **before** `/speckit.tasking`.

This phase owns `sketch.md` only. It is **design-only**.

## Inputs

- Approved planning context for the active feature
- The scaffolded `sketch.md` template
- Repo and codebase discovery outputs available to this phase
- Any required gate results for entering sketch

## Execution

- Ground the sketch in the approved planning context and repo-discovery outputs.
- Scaffold and complete `sketch.md` for the feature without changing the artifact shape.
- Capture the implementation surfaces, reuse seams, symbol boundaries, and blast radius needed for downstream tasking.
- Hand off the completed sketch to `/speckit.solutionreview` through the manifest-declared completion event.

## Repo-grounding requirements

Sketch must be grounded in the actual repository, not inferred from plan text alone.

Use this discovery order:

1. Use the project’s bounded read helpers for direct inspection:
   - use `scripts/read-code.sh` for code files
   - use `scripts/read-markdown.sh` for markdown artifacts

2. Use **CodeGraphContext** first to identify the relevant modules, symbols, callers, callees, import relationships, and likely touched surfaces.

Do not determine touched files, touched symbols, or blast radius from intuition alone.

## Sketch responsibilities

The sketch must:

- translate approved plan decisions into a repo-grounded low-level design
- preserve decisions already settled upstream and refine only what belongs in sketch
- identify the relevant existing seams, modules, scripts, templates, contracts, and runtime touchpoints
- define the feature’s solution narrative and construction strategy
- identify reuse unchanged, modify/extend, compose-from-existing, and net-new design surfaces
- identify the primary implementation seam and the expected blast radius
- define the major components, interfaces, boundaries, state/lifecycle considerations, and verification intent that shape the implementation
- identify human/operator boundaries that downstream tasking must encode explicitly
- produce decomposition-ready design slices for `/speckit.tasking`

## Required handoff contract to tasking

`sketch.md` must be concrete enough that `/speckit.tasking` does not need to invent major architecture.

Every decomposition-ready design slice must identify, at minimum:

- objective
- primary seam
- touched files
- touched symbols
- likely net-new files if any
- reuse / modify / create classification
- major constraints and invariants
- dependency relationship to other slices
- verification or regression concern

If the available artifacts and repo context are not sufficient to determine the solution shape, seams, boundaries, or decomposition-ready slices, stop and surface the gap rather than guessing.

## Behavior rules

- Do not generate `tasks.md`.
- Do not generate HUDs, acceptance tests, or estimates.
- Do not mutate production code.
- Prefer repository-grounded reuse over speculative net-new design.
- If codebase reality materially contradicts the plan, record the contradiction explicitly in `sketch.md`.
- If a key design dependency cannot be validated from the repo or artifacts, surface it as a design gap instead of guessing.
- Do not leave human/operator boundaries implicit if downstream `[H]` tasks are likely.
- If re-run, update only the parts of `sketch.md` affected by changed plan/spec/research/codebase context.
