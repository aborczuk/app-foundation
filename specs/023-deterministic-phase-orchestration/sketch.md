# Sketch Blueprint - Deterministic Phase Orchestration

_Date: 2026-04-17_
_Feature: `023-deterministic-phase-orchestration`_
_Source Plan: `plan.md`_
_Artifact: `sketch.md`_

## Feature Solution Frame

### Core Capability

Move phase execution to a deterministic orchestration contract where the pipeline driver is the execution entrypoint, command docs produce artifacts and completion payloads only, and phase events are emitted only after deterministic validation passes.

### Current -> Target Transition

Today the repo already has a pipeline driver, ledger helpers, state resolution helpers, and manifest-driven routing. The remaining problem is contract drift: command docs still carry orchestration-heavy wording, and the plan/task boundary needs to make it explicit that validation, event append, and handoff are driver-owned deterministic steps. The target state keeps the existing script-first spine, but tightens the contract so `speckit.*` command docs become producer-only artifact emitters and the driver becomes the sole phase executor for automated flows.

### Dominant Execution Model

Deterministic CLI orchestration with explicit permission gating, validate-before-emit sequencing, and a ledger-authoritative phase state model. Command docs and templates define artifact shape; the driver decides whether a phase can advance.

### Main Design Pressures

- Human approval before irreversible phase side effects
- Validate before emit, every time
- Producer-only command contracts
- Ledger-authoritative state resolution with advisory mirrors only
- No direct ledger file reads in command docs or templates
- Keep the solution token-efficient by reducing duplicated workflow prose

---

## Solution Narrative

This feature codifies a single phase-execution contract that spans the pipeline driver, command docs, ledger helpers, and the handoff between sketch, solution review, tasking, and analyze. The pipeline driver owns orchestration, state resolution, permission gating, deterministic validation, and event append mechanics. Command docs are treated as producer-only contracts: they gather context, synthesize artifacts, and return completion payloads, but they do not append ledger events directly. The final solution keeps the current manifest-driven routing model, preserves the pipeline ledger as the authoritative state source, and makes validate-before-emit the invariant that downstream phases rely on.

The sketch also preserves the repo's governance posture: no new external runtime is required, no new server is introduced, and the existing command manifest remains the route registry for automation. The main implementation pressure is to keep the solution phase compact enough that the command docs remain readable while still encoding the deterministic boundaries needed for the rest of the pipeline.

---

## Construction Strategy

1. Normalize the solution-phase contract in `specs/023-deterministic-phase-orchestration/contracts/phase-execution-contract.md` so it clearly separates producer output, deterministic validation, event append, and handoff.
2. Keep `scripts/pipeline_driver.py` as the canonical automated phase executor and refine its state-resolution and validate-before-emit flow rather than introducing a second orchestrator.
3. Preserve `scripts/pipeline_ledger.py` as the only append path for phase events and keep append mechanics behind deterministic validation.
4. Update command docs so they are producer-only and point to the driver-owned execution model instead of embedding direct ledger instructions.
5. Keep `command-manifest.yaml` aligned with the driver-owned phase contract and any emitted event field expectations.
6. Add deterministic tests for permission rejection, validate-before-emit ordering, ledger-authoritative state resolution, and idempotent retry behavior.
7. Update `quickstart.md` and related notes so the run path is visible to operators and future tasking stays aligned.

### Construction Notes

- Keep orchestration logic in scripts, not prompt prose.
- Treat the driver and ledger as the trust boundary for progression.
- Prefer small, additive changes to the existing pipeline contract over new workflow infrastructure.

---

## Command / Script Surface Map

| Name | Owning File / Script / Template | Pipeline Role | Classification | Inputs | Outputs / Artifacts | Events | Extension Seam | Planned Change |
|------|---------------------------------|---------------|----------------|--------|----------------------|--------|----------------|----------------|
| `uv run python scripts/pipeline_driver.py --feature-id <FEATURE_ID> [--phase <PHASE>]` | `scripts/pipeline_driver.py` | Canonical automated phase executor | Deterministic | Feature id, phase, repo context | Phase progression result, handoff payload, validation status | `plan_started`, `plan_approved`, `solution_approved`, post-solution analysis output | Keep orchestration driver-owned and deterministic | Modify |
| `scripts/pipeline_driver_state.py` | `scripts/pipeline_driver_state.py` | Resolve current step and phase state | Deterministic | Ledger state, feature context | Current step / state resolution | None directly | Keep ledger-authoritative state resolution | Modify minimally |
| `scripts/pipeline_ledger.py` | `scripts/pipeline_ledger.py` | Append and validate phase events | Deterministic | Event payloads, feature id, actor | JSONL ledger append / validation result | Phase events | Preserve as the only append path | Reuse |
| `scripts/pipeline_driver_contracts.py` | `scripts/pipeline_driver_contracts.py` | Validate phase contract boundaries | Deterministic | Phase contract payloads, manifest data | Contract validation result | None directly | Add contract checks for producer-only docs and validate-before-emit | Modify |
| `command-manifest.yaml` | repo root manifest | Route registry for phase commands | Declarative | Command IDs, artifact contracts, event contracts | Command routing metadata | Manifest-declared events | Keep canonical registry aligned to driver behavior | Modify if contract fields need tightening |
| `.claude/commands/speckit.solution.md` | command doc | Solution-phase orchestration guide | Human-facing / hybrid | Repo context, feature artifacts | Sketch, review, tasking, analyze handoff instructions | `solution_approved` emitted elsewhere | Remove direct event-emitter phrasing from producer docs | Modify |
| `specs/023-deterministic-phase-orchestration/contracts/phase-execution-contract.md` | contract artifact | Shared phase execution contract | Declarative | Plan, sketch, tasking inputs | Contractual boundary for implementation | No direct events | The main reference for tasking slices | Create / refine |
| `scripts/speckit_gate_status.py` | `scripts/speckit_gate_status.py` | Deterministic entry gate | Deterministic | Feature dir, mode | Gate status JSON | None | Keep as preflight check for solution and implement | Reuse |

---

## Manifest Alignment Check

| Affected Command / Phase | Existing Manifest Coverage? | New Artifact Needed? | New Event / Field Needed? | Handoff / Event Flow Impact | Status |
|--------------------------|-----------------------------|----------------------|---------------------------|-----------------------------|--------|
| `speckit.solution` | Yes | `contracts/phase-execution-contract.md` | No new event type | Solution phase must remain producer-only at the command-doc level | Aligned |
| `speckit.planreview` | Yes | No | No | Plan review remains a feasibility gate, not an emitter | Aligned |
| `speckit.tasking` | Yes | `tasks.md` and estimate artifacts | No new event type | Task generation must consume the approved sketch contract | Aligned |
| `speckit.analyze` | Yes | Analysis report | `analysis_completed` stays separate | Post-solution drift analysis remains its own gate | Aligned |
| `command-manifest.yaml` | Yes | Possibly updated event field docs | Only if contract validation requires tighter fields | Keep the registry as the source of truth for routing | Watch |

### Manifest Alignment Notes

- No new workflow command is required for this feature.
- The manifest may need tighter contract wording, but the command IDs stay stable.
- Any manifest edits should mirror the driver-owned execution flow rather than reintroduce prompt-owned event emission.

---

## Architecture Flow Delta

- **Architecture Flow refined**

### Delta Summary

The plan-level flow remains correct, but this sketch makes the execution seam explicit: the driver resolves state, gets permission, runs command synthesis, validates outputs, appends events only after pass, and then emits handoff. The command docs sit entirely on the producer side of the boundary.

### Added / Refined Nodes, Edges, or Boundaries

| Change | Why Needed at LLD Level | Must Preserve in Tasking / Implementation |
|--------|--------------------------|-------------------------------------------|
| Driver-owned state resolution | Ensures one authoritative current-step result | No duplicate state engines |
| Driver-owned validation gate | Prevents false-positive completion | No event append before pass |
| Ledger append as the only terminal event write path | Keeps audit behavior deterministic | No direct JSONL writes from command docs |
| Producer-only command docs | Reduces duplicated workflow prose and token overhead | Command docs synthesize artifacts, not events |
| Separate analyze gate | Keeps drift detection distinct from solution completion | Do not merge analysis into solution completion |

---

## Component and Boundary Design

| Component / Boundary | Responsibility | Owning or Likely Touched File(s) | Likely Touched Symbol(s) | Reuse / Modify / Create | Inbound Dependencies | Outbound Dependencies |
|----------------------|----------------|----------------------------------|--------------------------|-------------------------|---------------------|----------------------|
| Phase execution contract | Defines producer, validator, emitter, and handoff boundaries | `specs/023-deterministic-phase-orchestration/contracts/phase-execution-contract.md` | N/A | Create / refine | Plan, research, feature context | Tasking, implementation, review |
| Driver orchestration spine | Resolves state, gates permission, runs validation, and appends events | `scripts/pipeline_driver.py` | core orchestration helpers | Modify | Feature context, ledger state, manifest metadata | `pipeline_ledger.py`, handoff payloads |
| Phase state resolver | Computes current step and guards stale or divergent state | `scripts/pipeline_driver_state.py` | state helpers | Modify minimally | Ledger state, feature id | Driver orchestration |
| Event append path | Appends phase events after validation passes | `scripts/pipeline_ledger.py` | append helpers | Reuse | Validated payloads, actor | Pipeline ledger JSONL |
| Command docs | Producer-only artifact and completion payload contract | `.claude/commands/speckit.solution.md` and related docs | outline sections | Modify | Feature artifacts, plan, research | Sketch, tasking, analyze handoff |
| Manifest registry | Declares command routing and artifact contracts | `command-manifest.yaml` | command entries | Modify if needed | Repository governance model | Driver and speckit workflows |

### Control Flow Notes

- Validation must complete before any event append is attempted.
- Event append must complete before handoff is treated as successful.
- Permission rejection must stop execution without side effects.
- The analyze phase stays separate from solution completion.

---

## Design-to-Tasking Contract

- Tasking must decompose from the design slices below, not invent a new orchestration model.
- Each task should preserve the driver / validator / ledger split.
- Tasks must keep command docs producer-only and avoid direct ledger append instructions.
- Tasks must preserve ledger-authoritative current-step resolution and idempotent retries.
- Tasks must include verification for permission rejection, validate-before-emit ordering, and separate analyze behavior.
- Tasks must include a smoke path for the command docs so the compact and expanded headings remain stable.

---

## Decomposition-Ready Design Slices

| Slice | Files / Symbols | What Tasking Should Build | Verification Intent |
|-------|-----------------|---------------------------|---------------------|
| Driver orchestration and permission gate | `scripts/pipeline_driver.py` | Keep the canonical orchestration spine, current-step resolution, and explicit approval gate deterministic | Unit/integration tests for permission rejection and successful start |
| Validate-before-emit sequencing | `scripts/pipeline_driver.py`, `scripts/pipeline_ledger.py` | Ensure events are appended only after validation passes | Failure-mode tests proving no event append on validation fail |
| Ledger-authoritative phase state | `scripts/pipeline_driver_state.py` | Treat the ledger as the source of truth and mirrors as advisory only | Tests for stale/advisory divergence handling |
| Producer-only command docs | `.claude/commands/speckit.solution.md`, related command docs | Remove direct event-emitter language from command docs and keep them artifact-focused | Markdown smoke test for compact/expanded headings and producer-only wording |
| Contract artifact and routing alignment | `specs/023-deterministic-phase-orchestration/contracts/phase-execution-contract.md`, `command-manifest.yaml` | Encode the phase execution contract and keep manifest routing aligned to the driver | Contract review plus deterministic gate check |
| Post-solution drift analysis | `scripts/pipeline_driver.py`, `scripts/pipeline_driver_contracts.py` | Keep analyze separate from solution completion and make drift visible | Tests for separate analysis event / reporting |
| Quickstart and operator notes | `specs/023-deterministic-phase-orchestration/quickstart.md` | Document the canonical flow for operators and maintainers | Manual review plus smoke verification |

---

## Acceptance Traceability

| Story / Requirement / Constraint | Design Element(s) That Satisfy It | Reuse / Modify / Create | Verification / Migration Note |
|----------------------------------|-----------------------------------|-------------------------|-------------------------------|
| User Story 1 - Deterministic Phase Completion | Driver orchestration spine, validate-before-emit gate, pipeline ledger append path | Modify / Reuse | Validation fail must never emit a completion event |
| User Story 2 - Permissioned Phase Start | Current-step resolver and explicit approval gate | Modify / Reuse | Rejected approval must have zero side effects |
| User Story 3 - Producer-Only Command Contracts | `speckit.solution` and related docs, phase execution contract | Modify / Create | Command docs must stop implying direct ledger writes |
| FR-001 / FR-007 / FR-009 | Driver flow and deterministic validation | Modify | Event emission only after pass |
| FR-002 / FR-003 / FR-004 / FR-005 | State resolver and approval gate | Modify | Deterministic permission failure and no-op rejection |
| FR-006 / FR-010 / FR-011 | Producer-only docs, handoff discipline, retry idempotency | Modify | No duplicate terminal outcomes |
| FR-012 / FR-013 / FR-014 | Ledger-authoritative state, partial-write safety, driver entrypoint naming | Modify / Create | No stale mirror authority and no partial-write acceptance |

