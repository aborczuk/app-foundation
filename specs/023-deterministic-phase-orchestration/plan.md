# Implementation Plan: Deterministic Phase Orchestration

**Feature Branch**: `023-deterministic-phase-orchestration`  
**Spec**: `specs/023-deterministic-phase-orchestration/spec.md`  
**Research**: `specs/023-deterministic-phase-orchestration/research.md`

---

## Summary

### Feature Goal

Move phase execution to a deterministic orchestration contract where the pipeline driver is the execution entrypoint, command docs produce artifacts/completion payloads only, and phase events are emitted only after deterministic validation passes.

### Architecture Direction

Adopt a strict phase execution model aligned to `docs/governance/phase-execution`:

`orchestrate -> extract -> scaffold -> LLM Action -> validate -> emit/handoff`

The pipeline driver owns orchestration, state resolution, permission breakpointing, validation gating, and event append mechanics. Command docs and templates own artifact structure and synthesis intent only.

### Why This Direction

- It matches existing repo strengths (`pipeline_driver.py`, `pipeline_ledger.py`, manifest-driven routing).
- It reduces repeated command-doc prompt schema, improving token efficiency.
- It makes event emission auditable and deterministic.
- It cleanly separates deterministic work (scripts/validators) from judgment work (LLM synthesis).

---

## Technical Context

| Area | Decision / Direction | Notes |
|------|-----------------------|-------|
| Language / Runtime | Python 3.12 + Bash + uv | Existing repo baseline and tooling. |
| Technology Direction | Script-first deterministic orchestration with manifest contracts | Prefer extending current scripts over introducing a new workflow engine. |
| Technology Selection | `scripts/pipeline_driver.py`, `scripts/pipeline_driver_contracts.py`, `scripts/pipeline_ledger.py`, `scripts/speckit_gate_status.py`, `command-manifest.yaml` | Reuse current surfaces as primary control plane. |
| Storage | Append-only JSONL ledger + feature artifacts under `specs/<feature>/` | Event trail remains source of truth for phase progress. |
| Testing | Pytest unit/integration + deterministic validator commands | Existing tests around pipeline driver and manifest coverage are reusable. |
| Target Platform | Local/dev CLI execution on macOS/Linux | No new external runtime required for this phase. |
| Project Type | Governance/pipeline orchestration feature | Changes command contracts and phase mechanics, not product runtime endpoints. |
| Performance Goals | Dry-run and phase resolution should complete in seconds; no unnecessary LLM retries | Keep command loops deterministic and bounded. |
| Constraints | Human approval required before execution; no direct ledger file reads; validate-before-emit invariant | Governed by AGENTS/constitution/phase-execution model. |
| Scale / Scope | Phase-contract migration starting with pipeline-driver-managed flow; downstream phases consume stable contracts | Enables phased rollout without breaking legacy commands immediately. |

### Async Process Model

Primary execution remains synchronous CLI orchestration. Optional deferred handoff is allowed via `--handoff-runner`, but phase completion remains blocked until deterministic validation and event append outcome are known.

### State Ownership / Reconciliation Model

`pipeline-ledger.jsonl` is authoritative for feature phase state. Any derived/mirrored phase hints are non-authoritative and must reconcile to ledger state through driver resolution before execution.

### Local DB Transaction Model

No relational DB transaction is introduced in this phase. Reliability boundary is: command completion payload validation must pass before any append call to `pipeline_ledger.py`. Partial success without event append is treated as non-complete.

### Venue-Constrained Discovery Model

Routing metadata is manifest-constrained (`command-manifest.yaml`). Phase discovery and dispatch are only valid for commands declared in manifest contracts.

### Implementation Skills

- Pipeline contract design (phase contract + artifact contract alignment)
- Deterministic validation and gate modeling
- Manifest-driven orchestration and migration safety

---

## Repeated Architectural Unit Recognition

### Does a repeated architectural unit exist?

Yes.

### Chosen Abstraction

**Phase Contract + Artifact Contract** as first-class pipeline constructs.

- Phase Contract: execution lifecycle, gate logic, validation rules, event emission, handoff invariants.
- Artifact Contract: required structure and controlled vocabulary for each owned artifact.

### Why It Matters

- Prevents command docs from embedding duplicated structural rules.
- Keeps deterministic behavior in scripts/validators.
- Provides stable assumptions for sketch/tasking/analyze downstream.

---

## Reuse-First Architecture Decision

### Existing assets reused as-is

- `scripts/pipeline_driver.py` core dispatch/orchestration flow
- `scripts/pipeline_ledger.py` append/validation mechanics
- `scripts/speckit_gate_status.py` deterministic entry gate checks
- `.specify/scripts/pipeline-scaffold.py` artifact scaffolding path

### Existing assets extended

- `create-new-feature.sh` branch creation now deterministic from `main` by default
- root `command-manifest.yaml` becomes canonical command registry path
- `read-markdown.sh` exact heading lookup to avoid regex ambiguity

### Net-new architecture required

- Explicit plan-level contract for producer-only command docs and validate-before-emit handoff
- Feature-scoped contracts artifact under `specs/023.../contracts/`

### Why this minimizes unnecessary custom code

The design keeps existing execution surfaces and adds contract clarity/validation boundaries instead of replacing pipeline runtime infrastructure.

---

## Pipeline Architecture Model

### Recurring Unit Name

**Phase Execution Node**

### Defining Properties

- Has deterministic prerequisites/gates.
- Uses deterministic extraction and scaffolding.
- Runs one bounded LLM synthesis action.
- Requires deterministic artifact validation.
- Emits phase events only after validation pass.
- Produces explicit downstream handoff contract.

### Owned Artifacts and Events

- Owned artifacts are declared per command in `command-manifest.yaml`.
- Completion events are declared in manifest and appended by driver/ledger scripts after validation.

### Invariants Downstream May Rely On

- If a completion event exists, validation already passed.
- If validation fails, no completion event is emitted.
- Command docs are not responsible for direct ledger append instructions.
- Pipeline driver command is the execution entrypoint for automated phase flow.

---

## Artifact / Event Contract Architecture

| Phase Command | Owned Artifacts | Emit Event(s) | Downstream Consumers | Contract Note |
|---------------|------------------|---------------|----------------------|---------------|
| `speckit.specify` | `spec.md`, `checklists/requirements.md` | `backlog_registered` | `speckit.research`, `speckit.plan` | Entry artifacts only; no phase completion without structure. |
| `speckit.research` | `research.md` | `research_completed` | `speckit.plan` | Prior-art assembly contract for planning decisions. |
| `speckit.plan` | `plan.md`, `data-model.md`, `quickstart.md`, `contracts/*` | `plan_started`, `plan_approved` | `speckit.planreview`, `speckit.solution` | Planning phase must settle architecture thesis and handoff constraints. |
| `speckit.planreview` | `planreview.md` | `planreview_completed` | `speckit.feasibilityspike`, `speckit.solution` | Feasibility ambiguity count gates solutioning. |
| `speckit.feasibilityspike` | `spike.md` | `feasibility_spike_completed`/`feasibility_spike_failed` | `speckit.plan`, `speckit.solution` | Evidence contract for unresolved feasibility items. |

Manifest update requirement for this feature: **Yes** (root manifest canonicalization and routing assumptions must remain aligned to driver behavior).

---

## Architecture Flow

```mermaid
flowchart TD
    U[User / Operator] --> O[Pipeline Driver Orchestration]
    O --> G[Deterministic Gates + Phase Resolve]
    G --> P{Permission Granted?}
    P -- No --> B[Blocked Result / No Side Effects]
    P -- Yes --> X[Context Extraction]
    X --> S[Artifact Scaffolding]
    S --> L[LLM Action (command synthesis)]
    L --> V[Deterministic Validation]
    V -- Fail --> F[Fail Result / No Event Emission]
    V -- Pass --> E[Append Phase Event via pipeline_ledger.py]
    E --> H[Emit Handoff Payload]
```

### Trust Boundaries

- Human approval boundary: user/operator approval is required before execution side effects.
- Deterministic governance boundary: driver and validators decide pass/fail; LLM does not decide event append.
- Event authority boundary: ledger append path is script-owned (`pipeline_ledger.py`), not prompt-owned.

### Primary Automated Action

`uv run python scripts/pipeline_driver.py --feature-id <FEATURE_ID> [--phase <PHASE>]`

This is the canonical automated phase execution entrypoint.

---

## External Ingress + Runtime Readiness Gate

| Gate Item | Status | Rationale |
|-----------|--------|-----------|
| Public HTTP/Webhook ingress introduced by this feature | N/A | Feature changes CLI pipeline orchestration contracts only; no new inbound endpoint. |
| External callback receiver required for approval | N/A | Approval is modeled via driver-gated token/explicit human confirmation path in CLI workflow. |
| Runtime sidecar/worker required before safe execution | ✅ Pass | Existing script runtime is sufficient for this planning scope; no new service bootstrap gate. |
| Deterministic validation gate before emission is defined | ✅ Pass | Validation step explicitly precedes event append in architecture flow and contracts. |

### Readiness Blocking Summary

No `❌ Fail` rows. Implementation readiness is not blocked by external ingress/runtime gates for this feature.

---

## State / Storage / Reliability Model

### State Authority

Feature phase progression authority is ledger-derived phase state. Driver-resolved phase state must match ledger sequence before execution.

### Persistence Model

- Append-only ledger persistence for phase events.
- Artifact files under feature directory as phase outputs.
- No event append on failed validation.

### Retry / Timeout / Failure Posture

- Retries must be idempotent at phase boundary.
- Timeout or invalid payload returns deterministic failure envelope.
- Event append timeout/failure is surfaced as error, not silent success.

### Recovery / Degraded Mode Expectations

- On validation or append failure, keep artifacts for inspection, but do not advance phase ledger state.
- Operators can rerun same phase after fixing gate/contract violations.

---

## Contracts and Planning Artifacts

### Data Model

`data-model.md` defines execution entities, relationships, and state transitions for phase requests/results, validation outcomes, and event append decisions.

### Contracts

`contracts/phase-execution-contract.md` defines command-output envelope expectations and validate-before-emit invariants for this feature.

### Quickstart

`quickstart.md` documents local setup, dry-run execution, and smoke checks for deterministic phase orchestration behavior.

---

## Constitution Check

| Check | Status | Notes |
|-------|--------|-------|
| Human-First Decisions | ✅ Pass | Explicit permission gate before phase execution side effects. |
| Security First | ✅ Pass | No new ingress surface; deterministic validation before event append. |
| Reuse at Every Scale | ✅ Pass | Extends existing driver/ledger/scaffold surfaces rather than replacing them. |
| Spec & Process-First | ✅ Pass | Planning artifacts and event flow aligned to command-manifest + phase-execution model. |
| Test-Driven Verification First | ✅ Pass | Existing unit/integration suites cover driver and manifest behavior; plan preserves deterministic checks. |

---

## Behavior Map Sync Gate

| Runtime / Config / Operator Surface | Impact? | Update Target | Notes |
|------------------------------------|---------|---------------|-------|
| Pipeline driver phase execution sequence | Yes | `specs/023-deterministic-phase-orchestration/behavior-map.md` | Add flow + fail/pass paths during sketch/tasking decomposition. |
| Root command manifest ownership | Yes | `docs/governance/speckit-end-to-end.md` and `docs/governance/how-to-add-speckit-step.md` | Canonical registry moved to root and must remain documented. |
| Operator approval step expectations | Yes | `specs/023-deterministic-phase-orchestration/quickstart.md` | Quickstart captures how to run and confirm behavior. |

---

## Open Feasibility Questions

- [x] **FQ-001**: Can root-manifest canonicalization be applied without breaking pipeline validator and driver routing behavior?  
  **Probe:** Run manifest validator + command coverage validator + pipeline driver route tests on rebased branch.  
  **Blocking:** Manifest ownership and deterministic routing contract.

- [x] **FQ-002**: Can deterministic base branch selection in feature scaffolding avoid accidental branch ancestry drift?  
  **Probe:** Create feature branches from a non-main branch in a temp repo and verify new branch head resolves to `main` unless `--base` is provided.  
  **Blocking:** Governance consistency for all future feature branches.

All identified feasibility questions for planning are currently resolved and do not require a spike before solutioning.

---

## Handoff Contract to Sketch

### Settled by Plan

- Phase execution contract follows `orchestrate -> extract -> scaffold -> LLM Action -> validate -> emit/handoff`.
- Pipeline driver is the canonical automated phase executor.
- Completion events are emitted only after deterministic validation passes.
- Command docs are producer contracts, not ledger append instructions.

### Sketch Must Preserve

- Trust boundary between LLM synthesis and deterministic validation/event append.
- Ledger-authoritative phase state resolution and drift blocking.
- Artifact/event ownership defined by `command-manifest.yaml`.
- Reuse-first approach (extend current scripts; avoid net-new orchestration framework).

### Sketch May Refine

- Exact file/symbol touchpoints for driver, contracts, and validators.
- Migration slices across commands/phases.
- Acceptance traceability and design slices for implementation tasking.

### Sketch Must Not Re-Decide

- Primary automated action (`pipeline_driver.py` CLI entrypoint).
- Validate-before-emit invariant.
- Root manifest canonicalization decision.
- Human permission gate requirement before side effects.

---

## Phase 1 Planning Artifacts Summary

| Artifact | Status | Notes |
|----------|--------|-------|
| `plan.md` | updated | Architecture direction, contracts, gates, and handoff thesis finalized. |
| `data-model.md` | created | Execution entities and transitions for deterministic phase flow. |
| `contracts/` | created | Phase execution contract artifact added for downstream use. |
| `quickstart.md` | created | Local runbook for dry-run, execution, and smoke checks. |

---

## Plan Completion Summary

### Ready for Plan Review?

- [x] Architecture direction is explicit
- [x] Repeated architectural unit is modeled or explicitly unnecessary
- [x] Reuse-first decision is explicit
- [x] Architecture Flow is complete
- [x] Trust boundaries are explicit
- [x] Artifact/event contract architecture is explicit
- [x] Open feasibility questions are isolated
- [x] Sketch handoff contract is explicit

### Suggested Next Step

`/speckit.planreview`
