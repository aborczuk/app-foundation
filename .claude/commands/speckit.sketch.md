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
- The machine-readable `routing` + `risk` contract from `spec.md`
- The scaffolded `sketch.md` template
- Repo and codebase discovery outputs available to this phase
- Any required gate results for entering sketch

## Execution

- Ground the sketch in the approved planning context and repo-discovery outputs.
- If `spec.md` routes `plan_profile=skip`, ground the sketch directly in the spec routing contract and repo reality rather than waiting on a plan artifact.
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
If the routing contract says `sketch_profile=core`, the core sketch sections are the minimum required handoff; conditional sections only appear when the routing contract enables them.

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
- implementation directive with current behavior, target behavior, concrete edit mechanics, contract/data changes, allowed and forbidden side effects, preservation requirements, and test oracle

If the available artifacts and repo context are not sufficient to determine the solution shape, seams, boundaries, or decomposition-ready slices, stop and surface the gap rather than guessing.

## Implementation directive requirements

Every decomposition-ready design slice must include an `Implementation Directive` subsection. This subsection is the required bridge from architecture-level sketch to implementation-ready tasking.

Each `Implementation Directive` must include:

- **Current repo behavior**: what bounded repo reads show the current symbol/path does today.
- **Target behavior**: what must be true after implementation.
- **Concrete edit mechanics**: the branch, condition, parser, schema, return envelope, manifest field, command-doc section, or side-effect path expected to change.
- **Contract / data changes**: reason codes, fields, payload shapes, manifest keys, emitted events, CLI outputs, or artifact state that must change or be preserved.
- **Side effects allowed**: writes, event appends, generated artifacts, sidecars, or subprocess execution that are permitted after validation.
- **Side effects forbidden**: writes, event appends, generated artifacts, sidecars, or subprocess execution that must not happen on blocked/error paths.
- **Preserve behavior**: compatibility paths, legacy routes, existing valid success cases, idempotency behavior, or operator-visible output that must remain unchanged.
- **Test oracle**: the exact scenario and assertion shape downstream tasking must carry into the HUD.

Do not use generic implementation directives such as "harden behavior", "normalize contract", "wire route", or "add tests" unless paired with concrete behavior, symbols, contracts, and assertions.

If bounded reads do not validate current behavior for a slice, write `BLOCKED: current behavior not validated from repo reads.` in the implementation directive instead of guessing.

## Behavior rules

- Do not generate `tasks.md`.
- Do not generate HUDs, acceptance tests, or estimates.
- Do not mutate production code.
- Prefer repository-grounded reuse over speculative net-new design.
- If codebase reality materially contradicts the plan, record the contradiction explicitly in `sketch.md`.
- If a key design dependency cannot be validated from the repo or artifacts, surface it as a design gap instead of guessing.
- Do not leave human/operator boundaries implicit if downstream `[H]` tasks are likely.
- If re-run, update only the parts of `sketch.md` affected by changed plan/spec/research/codebase context.
