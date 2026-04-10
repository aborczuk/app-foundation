---
description: Execute the implementation planning workflow. Produces `plan.md`, then auto-invokes `planreview` and `feasibilityspike` as sub-processes. Plan phase is not complete until both finish successfully.
model: opus
handoffs:
  - label: Create Checklist
    agent: speckit.checklist
    prompt: Create a checklist for the following domain...
    send: false
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

`/speckit.plan` is the **architecture and planning phase**.

Its job is to convert an approved specification plus research into an implementation plan that is:

- architecturally coherent,
- explicit about system boundaries, trust boundaries, and execution model,
- grounded in real repo and pipeline constraints,
- strong enough that `/speckit.sketch` can later turn it into repo-grounded low-level design without re-deciding major architecture.

This phase decides and documents:

- the architecture direction,
- major system boundaries,
- the execution model,
- state/integration/reliability constraints,
- reuse-first architecture choices,
- the artifact/event/pipeline contract architecture that later phases must honor.

This phase is **not** task decomposition and **not** implementation.

## Planning outcome

By the end of this command, the plan must make the following clear:

1. what kind of system is being built,
2. what the major architectural components and boundaries are,
3. whether the system contains a repeated architectural unit that should be represented explicitly,
4. what external integrations and trust boundaries exist,
5. what state/storage/async/reliability model applies,
6. what artifacts and contracts must exist by the end of planning,
7. what feasibility questions remain open,
8. what `/speckit.sketch` must later ground into repo-specific LLD.

If any architecture-critical ambiguity remains, the phase is not complete.

## Outline

### 1. Setup

Run:

```bash
.specify/scripts/bash/setup-plan.sh --json
```

Parse:

- `FEATURE_SPEC`
- `IMPL_PLAN`
- `SPECS_DIR`
- `BRANCH`

For single quotes in args like `"I'm Groot"`, use safe shell escaping.

### 1a. Specification checklist gate (MANDATORY — hard block)

- Derive `FEATURE_DIR` from `FEATURE_SPEC`.
- Run:

```bash
python scripts/speckit_gate_status.py --mode plan --feature-dir "$FEATURE_DIR" --json
```

If the command exits non-zero or reports `ok: false`, **STOP immediately** with:

> **Specification checklist is incomplete. `/speckit.plan` cannot proceed.**  
> Complete all checklist items in `FEATURE_DIR/checklists/` (including `requirements.md`) before planning, then re-run `/speckit.plan`.  
> This is a non-negotiable pre-planning quality gate.

### 1b. External ingress + runtime readiness gate initialization (MANDATORY)

Populate the `## External Ingress + Runtime Readiness Gate` section in `plan.md`.

- Detect whether the feature includes external ingress surface area.
- If ingress applies, each row in that gate table MUST be assigned one of:
  - `✅ Pass`
  - `❌ Fail`
  - `N/A`
  with rationale.
- If ingress does not apply, mark rows `N/A` with explicit rationale.
- **Do not leave any gate row blank.**

If any row is `❌ Fail`, planning may continue, but the plan MUST explicitly state that implementation readiness is blocked until the gate is resolved, and downstream tasking must emit a gate task.

### 1c. Core mechanism clarity gate (MANDATORY)

Read the spec’s Functional Requirements.

Identify the **primary automated action**: the concrete tool, command, agent, or service call that executes the core work this feature exists to do.

If this action is not named explicitly in any functional requirement, **STOP** with:

> `spec.md` does not name the automated action this feature triggers. Add an FR that explicitly names the command/tool/agent/service responsible for the core automated work, then re-run `/speckit.plan`.

If named, record it. This action becomes a required node in the Architecture Flow.

---

## 2. Load planning context

Read:

- `spec.md`
- `constitution.md`
- `research.md` if present
- `catalog.yaml` if present
- `command-manifest.yaml` if present
- the scaffolded `plan.md` template

The plan must incorporate both feature requirements and pipeline/governance reality.

### 2b. Load pipeline architecture context (MANDATORY)

Read the pipeline architecture sources if present:

- `command-manifest.yaml`
- `speckit.solution.md`
- `speckit.sketch.md`
- `speckit.tasking.md`
- `speckit.analyze.md`

Extract and normalize:

- which commands own which artifacts,
- which templates and scaffold scripts back those artifacts,
- which events each command emits,
- which downstream handoffs depend on those artifacts/events,
- where the current pipeline already exhibits a repeated structural pattern.

This context is required for architecture planning. Do not treat command files, templates, artifacts, and ledger events as unrelated implementation trivia if they clearly form a recurring system pattern.

---

## 3. Research prerequisite gate (MANDATORY)

Check that `research.md` exists in `FEATURE_DIR` and includes all required sections:

- `## Zero-Custom-Server Assessment`
- `## Repo Assembly Map`
- `## Package Adoption Options`
- `## Conceptual Patterns`

If missing or incomplete, **STOP** with:

> Run `/speckit.research` first to assemble prior art and architecture options, then re-run `/speckit.plan`.

If present, load it as planning context.

**Important:** the Repo Assembly Map governs which FRs already have copyable/adaptable code sources. The architecture must use those sources or explicitly justify not using them.

### 3b. Repeated architectural unit recognition (MANDATORY)

Before filling detailed plan sections, determine whether the system is built from a repeated architectural unit.

A repeated unit exists when the pipeline consistently combines some or all of:

- instructions,
- owned artifacts,
- templates,
- scaffold/generation scripts,
- emitted events,
- handoffs to downstream phases,
- completion invariants.

If such a pattern exists, the plan MUST:

- name the abstraction explicitly,
- define its architectural role,
- explain why it should be treated as a first-class system construct rather than scattered command-specific behavior.

For this repo, a likely abstraction is a **Phase Contract** with one or more **Artifact Contracts**, but use whatever name best fits the system.

This is an architecture-level decision. `/speckit.sketch` will later ground it in repo-specific surfaces.

### 3c. Reuse-first architecture across pipeline surfaces (MANDATORY)

Reuse-first analysis must apply not only to code and packages, but also to:

- commands,
- scripts,
- templates,
- manifest-owned artifacts,
- ledger/event patterns,
- gate/status helpers,
- existing pipeline surfaces.

The plan must explicitly state:

- which existing pipeline surfaces are reused as-is,
- which are extended,
- which require net-new architecture,
- why any net-new pipeline surface is justified.

Do not allow the architecture to assume new command/script/template behavior when an existing pattern already fits.

---

## 4. Codebase and pipeline architecture discovery

If the codebase tools are available, use:

- `codegraph` first for discovery and scope,
- then type/diagnostic tools for verification.

Use discovery to answer planning-level questions such as:

- what existing modules/services/scripts already embody parts of the feature,
- what existing commands/artifacts/events already form a stable execution pattern,
- what boundaries are real versus assumed,
- where the architecture is extending existing surfaces versus introducing new ones.

This is still architecture discovery, not low-level design.

---

## 5. Fill the implementation plan

Follow the `plan.md` template structure and fill it with architecture decisions, not implementation details.

### 5a. Technical Context

Fill:

- Language/Version
- Technology Direction
- Technology Selection
- Storage
- Testing
- Target Platform
- Project Type
- Performance Goals
- Constraints
- Scale/Scope
- Async Process Model
- State Ownership/Reconciliation Model
- Local DB Transaction Model
- Venue-Constrained Discovery Model
- Implementation Skills

Rules:

- **Technology Direction** should describe category + constraints, not concrete library names.
- Specific library/tool selection belongs in **Technology Selection** only after feasibility evidence is available.
- Unknowns must be marked `NEEDS CLARIFICATION`.
- Technical Context defines architecture-level direction and constraints.
- It does **not** name touched files, touched symbols, or decomposition-ready implementation slices.
- Repo-grounded surfaces belong to `/speckit.sketch`.

### 5b. Pipeline architecture model (MANDATORY)

If the system uses repeated phase/command units with owned artifacts, templates, scaffold scripts, and events, document that explicitly in plan.

This section must answer:

- what the recurring unit is called,
- what properties define it,
- what artifacts it owns,
- what events complete it,
- what handoffs it enables,
- what invariants downstream phases may rely on.

This is the architecture-level representation only. Do not descend into touched files, symbols, or decomposition-ready slices here.

### 5c. Architecture Flow (MANDATORY)

Generate the Architecture Flow after design artifacts are available.

It must cover:

- the major components,
- trust boundaries,
- major data/event flow,
- key state transitions,
- the primary automated action,
- async return paths where relevant.

Rules:

- every major component in Project Structure must appear,
- every key external service/trust boundary must appear,
- any external service node must include both outbound and return-path semantics if async applies,
- every inbound trigger must show how it reaches the core automated action.

### 5d. Reuse-first architecture decision (MANDATORY)

Using `research.md`, record:

- what existing code/repos/packages/patterns cover the FRs,
- which architecture candidate is preferred,
- why the preferred architecture minimizes unnecessary custom code,
- which FRs still require net-new implementation.

This section should make reuse strategy explicit before LLD begins.

### 5e. Artifact / event contract architecture (MANDATORY when relevant)

For each major architectural unit or phase involved in the feature, record at planning level:

- owned artifacts,
- scaffold/template relationship,
- emitted events,
- downstream consumers of those artifacts/events,
- whether the feature introduces a new artifact or event contract,
- whether the manifest will require update.

This section should stay architectural. It should define the contract shape, not the repo-grounded implementation details.

### 5f. Constitution Check

Fill the Constitution Check section from `constitution.md`.

Any `❌ Fail` blocks the plan unless explicitly resolved.

### 5g. Behavior Map Sync Gate

Fill the behavior map sync gate and identify target behavior-map updates where applicable.

---

## 6. Generate planning artifacts

Phase 1 planning artifacts must include:

- `plan.md`
- `data-model.md`
- `contracts/` when needed
- `quickstart.md`

Generate these using the scaffold scripts/templates already defined by the manifest and template system.

The plan phase must own the existence and architectural coherence of these artifacts.

---

## 7. Re-evaluate architecture completeness before approval

Before emitting final plan approval, verify that the plan now makes clear:

- the selected architecture direction,
- the repeated architectural unit or explicit decision that none is needed,
- the trust boundaries and Architecture Flow,
- the state/storage/async/reliability model,
- the reuse-first posture,
- the artifacts and contracts sketch will later refine,
- the open feasibility questions still requiring proof.

If the plan is still merely descriptive and has not made the architecture explicit enough for sketch, it is incomplete.

### 7b. Handoff contract to sketch (MANDATORY)

Before plan approval, explicitly state what `/speckit.sketch` is expected to ground and what it must **not** re-decide.

This handoff must identify:

- architecture decisions settled by plan,
- repeated architectural abstractions settled by plan,
- trust boundaries and Architecture Flow assumptions sketch must preserve,
- artifact/event contract assumptions sketch must preserve,
- which areas sketch is allowed to refine into repo-grounded LLD,
- which areas remain blocked pending feasibility proof.

The goal is to hand sketch a stable architectural thesis, not a loose collection of prose and gates.

---

## 8. Emit pipeline events and auto-invoke sub-processes

### 8a. Emit `plan_started`

Append:

```json
{"event": "plan_started", "feature_id": "NNN", "phase": "plan", "actor": "<agent-id>", "timestamp_utc": "..."}
```

to `.speckit/pipeline-ledger.jsonl`.

### 8b. Report initial planning artifacts

Report:

- branch,
- `plan.md` path,
- generated `data-model.md`,
- generated `contracts/`,
- generated `quickstart.md`

### 8c. Auto-invoke `/speckit.planreview` (MANDATORY)

Run planreview now.  
The plan phase is not complete until planreview completes at least one pass.

### 8d. After planreview, inspect `## Open Feasibility Questions`

- If any unchecked items remain, auto-invoke `/speckit.feasibilityspike`
- If none remain, skip spike

### 8e. Emit `plan_approved` only after review/spike completion

Append:

```json
{"event": "plan_approved", "feature_id": "NNN", "phase": "plan", "feasibility_required": true/false, "actor": "<agent-id>", "timestamp_utc": "..."}
```

to `.speckit/pipeline-ledger.jsonl`.

**Hard rule:** if feasibility spike fails, do not emit `plan_approved`.

### 8f. Final report

Report:

- plan phase complete,
- architecture direction chosen,
- repeated architectural unit explicitly modeled or explicitly deemed unnecessary,
- Technology Selection confirmed or still awaiting spike confirmation,
- suggested next step: `/speckit.solution`

## Behavior rules

- `plan` owns architecture direction, not tasks.
- `plan` must recognize repeated architectural patterns when they are real.
- `plan` must not leave major system abstractions implicit if later phases depend on them.
- `plan` should remain architectural; repo-grounded file/symbol decomposition belongs to `sketch`.
- `plan` must preserve reuse-first reasoning from research.
- `plan` must not emit `plan_approved` if unresolved feasibility blocks remain.
- `plan` must leave `sketch` with a stable architectural thesis to ground, not a pile of prose and gates.