---
description: Generate a pre-task low-level design blueprint (`sketch.md`) from spec, plan, research, manifest, domain guidance, and codebase reality. Sub-agent of `/speckit.solution`; callable standalone.
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

Produce the **feature-level low-level design** that bridges the approved implementation plan to the actual repository and operating pipeline.

`/speckit.sketch` runs **before** `/speckit.tasking`. Its job is to turn the target-state plan into a **repo-grounded, decomposition-ready solution blueprint** that `/speckit.tasking` can convert into executable tasks, HUDs, estimates, and acceptance artifacts **without inventing major architecture**.

This command must:

- ground the plan in the current codebase and artifact landscape,
- identify the relevant existing seams, modules, scripts, templates, contracts, and runtime touchpoints,
- use **CodeGraphContext** to traverse the relevant code and determine the likely **blast radius** of the change,
- define the proposed low-level solution shape,
- capture the domain constraints that must shape the design,
- define the feature’s implementation narrative and construction strategy,
- produce design slices that are ready for task decomposition.

This command is **design-only**. It must not generate `tasks.md`, per-task HUDs, acceptance tests, estimates, or implementation code.

## Pipeline role

This command exists inside the sketch-first solution flow:

- `speckit.sketch` → produces `sketch.md`
- `speckit.solutionreview` → reviews `sketch.md`
- `speckit.tasking` → decomposes approved `sketch.md` into `tasks.md`, then performs estimate/breakdown stabilization and generates HUDs + acceptance tests
- `speckit.solution` → orchestrates `sketch -> solutionreview -> tasking -> analyze`

Design the handoff accordingly: `sketch.md` must hand tasking **design slices, touched files/symbols, constraints, and verification intent**, not task artifacts.

## Required outcome

By the end of this command, `sketch.md` must make the following concrete enough that `/speckit.tasking` does not need to invent major solution structure:

1. What capability or change surface this feature is implementing
2. What existing code/scripts/templates/artifacts are relevant
3. What should be reused unchanged
4. What should be extended or modified
5. What must be net-new
6. What the primary seams, interfaces, trust boundaries, and module boundaries are
7. What the direct and indirect **blast radius** is
8. What the construction path is — how the feature will actually be built
9. What feature-level design slices should become tasks
10. What constraints, risks, assumptions, and domain MUST rules tasking must preserve
11. What non-functional, operational, migration, rollback, and verification requirements must carry forward
12. What public symbols, contracts, and typed boundaries must exist before implementation begins

If these cannot be determined from the available artifacts and codebase context, stop and surface the gap rather than guessing.

## Outline

### 1. Setup

Run from repo root:

```bash
.specify/scripts/bash/check-prerequisites.sh --json
```

Parse at minimum:

- `FEATURE_DIR`
- `IMPL_PLAN`
- `AVAILABLE_DOCS`

Also load, if present:

- `command-manifest.yaml`
- `catalog.yaml`
- `constitution.md`

### 2. Hard-block gates

Require:

- `spec.md`
- `plan.md`

If either is missing, **STOP** and report the missing prerequisite.

Inspect `plan.md` for `## Open Feasibility Questions`.

If unresolved feasibility items exist (`- [ ]`), **STOP** and instruct `/speckit.feasibilityspike`.

If the plan still contains unresolved architecture placeholders, ambiguous target runtime shape, or ungrounded design assumptions that prevent identifying seams, boundaries, or decomposition-ready slices, **STOP** and report that the plan is not yet solutionable.

### 3. Load design context

Read required artifacts:

- `spec.md`
- `plan.md`

Read optional artifacts if present:

- `research.md`
- `spike.md`
- `data-model.md`
- `quickstart.md`
- `contracts/*`
- `catalog.yaml`
- `constitution.md`
- `command-manifest.yaml`

Read the following command files if available to align handoffs and artifact ownership:

- `speckit.plan.md`
- `speckit.planreview.md`
- `speckit.solution.md`
- `speckit.solutionreview.md`
- `speckit.tasking.md`
- `speckit.estimate.md`
- `speckit.analyze.md`
- `speckit.e2e.md`
- `speckit.implement.md`

Extract and normalize:

- user stories / capabilities
- acceptance criteria anchors
- architecture decisions already settled by plan
- explicit constraints and non-goals
- runtime shape
- integration points
- named components, commands, pipelines, services, scripts, artifacts, storage, env/config surfaces, external systems, or operator flows
- declared downstream artifacts and events
- expected solution-phase handoff boundaries

Do not begin decomposition until the intended feature boundary is clear.

### 4. Establish the feature solution frame (mandatory)

Before detailed code traversal, synthesize the feature at the solution level.

Produce an internal framing of:

- the core capability being added or changed,
- the current-to-target transition implied by the plan,
- the likely major subsystem boundaries involved,
- the dominant execution model or control model,
- the main design pressures, constraints, and operating assumptions.

This is not task generation. This is the feature-level solution frame tasking will later decompose.

### 5. Solution narrative (mandatory)

Write a concise solution narrative that explains:

- what is being built,
- what existing surfaces are being reused,
- what new seams or modules are being introduced,
- what the finished solution will look like in operational terms,
- why this is the correct realization of the already-approved plan.

This section must read like a coherent build thesis, not an audit.

### 6. Construction strategy (mandatory)

Describe the major implementation moves in the order they should be realized.

This is not task decomposition. It is the **construction logic** that tasking must preserve.

Typical structure:

1. establish or extend the core seam,
2. define or refine interfaces/contracts,
3. wire orchestration/integration path,
4. add state/validation/guard behavior,
5. attach observability/recovery/operator surfaces,
6. validate end-to-end construction path.

If the feature needs a different construction order, state it explicitly.

### 7. Acceptance traceability (mandatory)

Build a design traceability map from:

- user stories / goals,
- functional requirements,
- explicit constraints,
- plan decisions,

to the major design elements the solution will require.

For each major requirement or constraint, identify:

- which design element(s) satisfy it,
- whether the requirement drives reuse, extension, or net-new work,
- whether it introduces special verification or migration implications.

If a functional requirement has no corresponding design element, record this as a design gap.

### 8. Work-type classification (mandatory)

Classify each story/capability into one or more work types, such as:

- integration
- orchestration / workflow
- state transition / lifecycle
- policy / gating
- data flow / transformation
- API / contract shaping
- storage / persistence
- migration / compatibility
- observability / diagnostics
- UI / presentation
- background / async processing
- security / authz / trust boundary
- deployment / rollout / operational readiness
- human / operator interaction

For each work type:

- identify common patterns already used in this repo,
- identify whether the likely solution is reuse-first, extension-first, or net-new,
- identify special constraints that must be preserved in the design.

### 9. Mandatory codebase discovery order

Use the following repo discovery order:

1. **Discovery first**
   - Use **CodeGraphContext** to identify relevant symbols, modules, import relationships, callers, callees, and dependency paths.
   - If remote repository context is needed, use GitHub search first.
2. **Verification second**
   - Use type/diagnostic tooling as needed to verify exact types and impacted files.
3. **Fallback last**
   - Use `rg` or direct file inspection only if CodeGraphContext remains incomplete after a scoped refresh.

Do not begin low-level design from raw intuition if codegraph discovery has not been used.

### 10. CodeGraphContext traversal and impact mapping (mandatory)

Use **CodeGraphContext** as a required discovery mechanism, not an optional lookup.

Start from capability and architecture signals in `spec.md`, `plan.md`, `research.md`, `spike.md`, `catalog.yaml`, and named files/symbols. Use them to identify **seed symbols** and relevant modules.

Then traverse outward to determine both the **implementation seam** and the **blast radius**.

At minimum, inspect:

- candidate symbols and owning files/modules
- direct callers
- direct callees
- transitive callers where needed
- transitive callees where needed
- importers / module dependencies
- class hierarchy / overrides where relevant
- variable or state ownership where relevant
- policy, validation, logging, storage, queue, and ledger touchpoints where relevant

When useful, use query types equivalent to:

- `find_callers`
- `find_callees`
- `find_all_callers`
- `find_all_callees`
- `find_importers`
- `module_deps`
- `who_modifies`
- `class_hierarchy`
- `overrides`
- `call_chain`

If codegraph discovery appears stale or incomplete, use the project’s scoped safe refresh pattern first. Do not force a full re-index.

This step must produce:

#### A. Primary implementation surfaces
Files, symbols, scripts, templates, contracts, or configs most likely to be directly changed.

#### B. Secondary affected surfaces
Neighboring code, policy boundaries, state surfaces, tests, docs, or integration points likely to be indirectly affected.

#### C. Candidate reuse paths
Existing abstractions, utilities, workflows, patterns, or packages that should be reused or extended.

#### D. Missing seams or contradictions
Plan assumptions that appear unsupported by current codebase reality.

Do not stop at “symbols reviewed.” Use graph traversal to determine both the **solution boundary** and the **impact boundary**.

### 11. Current-system inventory (mandatory)

Build a current-state inventory of the feature’s relevant surfaces.

Include, where applicable:

- entrypoints
- modules/packages/services
- scripts/commands
- templates/artifacts
- configs/manifests
- storage/state/ledger touchpoints
- validation/gating/policy surfaces
- observability/diagnostic surfaces
- deployment/release surfaces
- test surfaces
- runbook / operator surfaces if applicable

For each relevant surface, note:

- what it appears to do,
- how it relates to the feature,
- whether it is reusable, extension-friendly, brittle, or mismatched,
- whether it is part of the primary implementation seam or blast radius only.

This inventory must be more than a list of filenames.

### 12. Command / script surface map (mandatory)

Because this pipeline orchestrates existing commands, scripts, templates, manifests, and generated artifacts, sketch must explicitly model that runtime surface.

For each relevant command, script, manifest entry, or pipeline-owned artifact, record:

- name
- owning file/script/template
- role in the pipeline
- deterministic / human / external / hybrid classification
- inputs
- outputs/artifacts
- emitted events if any
- extension seam
- whether it is reused, wrapped, modified, or newly introduced
- whether it is a primary implementation surface or blast-radius-only surface

If the design depends on a command/script/manifest seam that does not exist, record that explicitly as a design gap.

### 13. Blast-radius analysis (mandatory)

Determine the **direct and indirect blast radius** of the proposed change.

Classify affected surfaces as one or more of:

- direct implementation surface
- integration dependency
- contract/policy dependency
- state/persistence dependency
- regression-sensitive neighbor
- observability/test-only impact
- rollout/compatibility risk
- operator/runbook impact
- deployment/release impact

For each major affected area, identify:

- why it is in the blast radius,
- what kind of breakage or drift is plausible,
- what constraints or validation later phases must preserve.

### 14. Reuse / modify / create model (mandatory)

Classify the design surface into:

- **Reuse unchanged**
- **Modify / extend existing**
- **Compose from existing pieces**
- **Create net-new**

Do this at the feature design level, not yet as tasks.

Prefer repository-grounded reuse over speculative net-new construction.

If the plan implies a seam or capability that does not actually exist, say so explicitly.

### 15. Manifest alignment check (mandatory)

Validate the proposed design against the command manifest and artifact ownership model.

For each affected command or phase, determine:

- whether an existing manifest entry already covers the needed artifact ownership,
- whether the design introduces a new artifact that should be reflected in the manifest,
- whether the design introduces a new event or required field,
- whether an existing handoff or event flow becomes invalid,
- whether downstream commands would become inconsistent with the proposed design.

If manifest alignment is unclear, record that as a blocking design issue rather than leaving it implicit.

### 16. Architecture Flow delta (mandatory)

If `plan.md` already contains an Architecture Flow, sketch must explicitly state one of:

- **No Architecture Flow delta** — the plan-level flow remains correct and only implementation detail is added, or
- **Architecture Flow refined** — sketch adds implementation-relevant boundaries, trust edges, async return paths, operator boundaries, state authority details, or execution seams.

If refined, record the delta clearly:

- what nodes/edges/boundaries were added,
- why they are needed at LLD level,
- what tasking and implementation must preserve.

Do not silently diverge from the plan’s Architecture Flow.

### 17. Component and boundary design (mandatory)

Define the major components/modules involved in the solution.

For each component or boundary, record:

- responsibility,
- owning file(s) or likely touched file(s),
- likely touched symbol(s),
- whether it is reused, modified, or net-new,
- inbound/outbound dependencies,
- control-flow and data-flow role.

The goal is to make the construction path mechanically visible to tasking.

### 18. Interface, symbol, and contract design (mandatory)

Define the public interfaces and symbol boundaries that the solution requires.

This section must include, where applicable:

- key interfaces and schemas,
- message or artifact contracts,
- function boundaries,
- typed result/error expectations,
- ownership boundaries,
- validation points.

For any new or materially changed **public symbol**, record its exact intended signature in the design.

Signatures are required before task generation for new public classes, functions, and constants.

Do not defer public contract shape to implementation.

### 19. State / lifecycle / failure model (mandatory)

Where applicable, define:

- state machines and lifecycle transitions,
- authoritative state ownership,
- reconcile-before-decision requirements,
- invalid transitions,
- timeout / retry / cancellation behavior,
- crash/restart semantics,
- duplicate/replay/out-of-order handling,
- degraded modes,
- fallback behavior for critical dependencies,
- rollback / compensation / recovery expectations.

If the feature has no lifecycle or recovery complexity, state that explicitly.

### 20. Non-functional design implications (mandatory)

Record only the non-functional requirements that materially shape the design, such as:

- latency / throughput / saturation constraints that affect module boundaries,
- concurrency and backpressure implications,
- idempotency requirements,
- observability seams and correlation requirements,
- config/secret boundaries,
- deployment / rollout compatibility constraints,
- rollback triggers and operator implications.

Do not restate broad plan-level NFRs unless they materially alter the design.

### 21. Human-task and operator boundaries (mandatory)

Identify where the design inherently requires human action, operator approval, or manual intervention.

For each such boundary, record:

- why it cannot be fully automated,
- whether it is a true human task or a review checkpoint,
- what preconditions must exist before the human step,
- what artifact or evidence the human step consumes,
- what downstream phase should encode it as `[H]`,
- what failure/retry/escalation path applies if it is not completed.

This section exists so `/speckit.tasking` does not have to infer `[H]` placement from vague prose.

### 22. Verification strategy (mandatory)

Define the verification intent that tasking must preserve.

This is not acceptance-test generation. It is a design-level statement of what later phases must validate, such as:

- unit-testable seams,
- contract verification needs,
- integration reality-check paths,
- lifecycle / retry / duplicate-path coverage,
- rollout verification,
- regression-sensitive areas,
- deterministic pass/fail oracles where known.

### 23. Domain review by touched surface (mandatory)

Determine touched domains from the actual design, not only from story labels.

Always include:

- Domain 12 — Testing & quality gates
- Domain 13 — Identity & access control
- Domain 14 — Security controls
- Domain 16 — Ops & governance
- Domain 17 — Code patterns

Also include any additionally touched domains from 01–11 and 15.

For each touched domain, read **core principles**, **best practices**, and any sketch-relevant LLD rules. Record:

- MUST constraints,
- forbidden shortcuts,
- invariants tasking and implementation must preserve,
- any domain-driven design obligations that must appear in `sketch.md`.

Do not run task-level subchecklists here.

### 24. LLD decision log (mandatory)

Add a structured decision log to distinguish what is settled from what is still provisional.

For each major design item, classify it as one of:

- **Decided**
- **Assumed**
- **Deferred**
- **Blocked**
- **Needs manifest update**
- **Needs human confirmation**

For each entry, record:

- subject,
- status,
- rationale,
- downstream implication,
- whether tasking may proceed on it.

Do not collapse all uncertainty into a generic risks section.

### 25. Design gaps and repo contradictions (mandatory)

Record only:

- missing seams,
- unsupported assumptions,
- contradictions between plan and codebase reality,
- unresolved design blockers that affect decomposition or implementation shape.

Do not re-run broad plan review here.

### 26. Design-to-tasking contract (mandatory)

Before finalizing `sketch.md`, define the explicit contract that `/speckit.tasking` must follow.

The contract must state:

- every decomposition-ready design slice must produce at least one task, unless an explicit omission rationale is recorded,
- no task may introduce scope, seams, symbols, interfaces, or artifacts absent from sketch without explicit rationale,
- `[H]` tasks must come only from identified human/operator boundaries or explicit external dependency constraints,
- `file:symbol` annotations in tasks must trace back to the symbol targets or symbol-creation notes in sketch,
- acceptance tests must derive from the verification intent and acceptance traceability defined in sketch,
- large-point tasks that require later breakdown must still preserve the originating design slice and safety invariants.

### 27. Define decomposition-ready design slices (mandatory)

Define the logical implementation slices that `/speckit.tasking` should convert into executable tasks.

These are **not tasks** yet.

Each design slice must include:

- objective,
- touched files,
- touched symbols,
- likely net-new files if any,
- primary seam,
- blast-radius neighbors,
- reuse/modify/create classification,
- required public symbols or interfaces,
- major constraints,
- dependency relationship to other slices,
- likely verification or regression concern.

These slices are the primary handoff to tasking.

### 28. Generate `sketch.md`

Run scaffold:

```bash
uv run python .specify/scripts/pipeline-scaffold.py speckit.sketch --feature-dir "$FEATURE_DIR" FEATURE_ID="NNN" FEATURE_NAME="[Feature Name]"
```

Fill `sketch.md` with the blueprint produced above.

`sketch.md` must contain, at minimum, the following sections in this order:

1. **Feature Solution Frame**
2. **Solution Narrative**
3. **Construction Strategy**
4. **Acceptance Traceability**
5. **Work-Type Classification**
6. **Current-System Inventory**
7. **Command / Script Surface Map**
8. **CodeGraphContext Findings**
9. **Blast Radius**
10. **Reuse / Modify / Create Matrix**
11. **Manifest Alignment Check**
12. **Architecture Flow Delta**
13. **Component and Boundary Design**
14. **Interface, Symbol, and Contract Notes**
15. **State / Lifecycle / Failure Model**
16. **Non-Functional Design Implications**
17. **Human-Task and Operator Boundaries**
18. **Verification Strategy**
19. **Domain Guardrails**
20. **LLD Decision Log**
21. **Design Gaps and Repo Contradictions**
22. **Design-to-Tasking Contract**
23. **Decomposition-Ready Design Slices**

The document must be strong enough that:

- `/speckit.solutionreview` can perform a real quality gate,
- `/speckit.tasking` can derive tasks, HUDs, estimates, and acceptance artifacts without inventing architecture,
- `/speckit.analyze` can later verify `spec -> plan -> sketch -> tasks` consistency.

### 29. Emit pipeline event

Append:

```json
{"event": "sketch_completed", "feature_id": "NNN", "phase": "solution", "actor": "<agent-id>", "timestamp_utc": "..."}
```

to `.speckit/pipeline-ledger.jsonl`.

### 30. Report

Report:

- path to `sketch.md`,
- capabilities/stories covered,
- work types identified,
- major components/symbols reviewed,
- summary of CodeGraphContext traversal,
- blast-radius summary,
- reuse/modify/create summary,
- key interfaces/boundaries/symbols defined,
- domain constraints captured,
- major risks or unresolved assumptions surfaced,
- suggested next step: `/speckit.solutionreview`

## Behavior rules

- This command is **design-only**.
- Do not generate `tasks.md`.
- Do not generate per-task HUDs.
- Do not generate acceptance tests.
- Do not generate estimates.
- Do not mutate production code.
- Prefer repository-grounded reuse over speculative net-new design.
- Use CodeGraphContext first for discovery and impact mapping.
- If codegraph discovery is stale or incomplete, use scoped safe refresh before falling back.
- If codebase reality materially contradicts the plan, record the contradiction explicitly in `sketch.md`.
- If a key design dependency cannot be validated from the repo or artifacts, surface it as a design gap instead of guessing.
- Treat `command-manifest.yaml` as a source of truth for artifact ownership and event flow when present.
- Do not leave command/script/manifest dependencies implicit if the feature depends on them.
- Do not leave human/operator boundaries implicit if later `[H]` tasks are likely.
- Do not let sketch diverge silently from the Architecture Flow defined in plan.
- Do not leave major design items unclassified; every important decision must be marked decided, assumed, deferred, blocked, manifest-update-needed, or human-confirmation-needed.
- If re-run, update only sections affected by changed plan/spec/research/codebase context.