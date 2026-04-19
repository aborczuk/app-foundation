# Sketch Blueprint - Deterministic Phase Orchestration

Feature purpose: Pipeline operators run phase work through a deterministic orchestrator that validates outputs before any ledger event is emitted.

---

## Feature Solution Frame

### Core Capability

Move phase execution to a deterministic contract where `scripts/pipeline_driver.py` is the canonical execution entrypoint, command docs are producer-only, and completion events are emitted only after deterministic validation passes.

### Current -> Target Transition

Current repo behavior already includes a working pipeline driver, manifest-driven routing, ledger validation, and gate scripts. The target state tightens ownership boundaries so command docs produce artifacts/completion payloads only, while the driver and ledger scripts own state resolve, permission gating, validation, and emit/handoff progression.

### Dominant Execution Model

Synchronous deterministic CLI orchestration with an explicit approval boundary and validate-before-emit ordering:
`orchestrate -> extract -> scaffold -> LLM Action -> validate -> emit/handoff`.

### Main Design Pressures

- Explicit operator approval before side effects.
- Validate-before-emit invariant with no exception path.
- Ledger-authoritative phase state and drift detection.
- Producer-only command docs to reduce duplicated workflow logic.
- Manifest contract fidelity between routes, artifacts, and events.
- Idempotent retries and predictable blocked/error envelopes.

---

## Solution Narrative

This feature consolidates phase execution into a single deterministic boundary composed of the driver, route contracts, and ledger append semantics. `scripts/pipeline_driver.py` resolves current phase state via `scripts/pipeline_driver_state.py`, gates permission, executes producer work, validates generated artifacts and step envelopes, and appends success events through `scripts/pipeline_ledger.py` only after validation success. `scripts/pipeline_driver_contracts.py` enforces step-result schema and manifest-route normalization so producer outputs cannot skip deterministic checks. The implementation reuses existing script surfaces and test suites, with focused modifications to preserve governance invariants and improve command-doc token efficiency.

---

## Construction Strategy

1. Preserve the phase-execution contract in `contracts/phase-execution-contract.md` as the architectural boundary.
2. Keep `scripts/pipeline_driver.py` as the canonical automated executor and refine validate-before-emit flow.
3. Preserve `scripts/pipeline_ledger.py` as the only event append path and keep append sequence validation strict.
4. Keep `scripts/pipeline_driver_state.py` as the ledger-authoritative state resolver and drift guard.
5. Keep `scripts/pipeline_driver_contracts.py` as the step-envelope and route normalization gate.
6. Maintain producer-only command doc behavior across solution/tasking/analyze related docs.
7. Validate with deterministic unit/integration suites and ledger gate commands before phase completion events.

### Construction Notes

- Sequence integrity is more important than minimizing command count.
- Route and event metadata must remain manifest-sourced.
- Any migration slice that weakens approval or validation boundaries is rejected.

---

## Acceptance Traceability

| Story / Requirement / Constraint | Design Element(s) That Satisfy It | Reuse / Modify / Create | Verification / Migration Note |
|----------------------------------|-----------------------------------|-------------------------|-------------------------------|
| User Story 1 - Deterministic Phase Completion | Driver validate-before-emit path (`validate_generated_artifact`, `append_pipeline_success_event`) + ledger sequence checks (`validate_sequence`) | Modify + Reuse | Failed validation must produce blocked result and zero completion append |
| User Story 2 - Permissioned Phase Start | Driver gate path in `main` using explicit approval token and blocked reason contract | Modify | Permission reject must stop before producer execution |
| User Story 3 - Producer-Only Command Contracts | Route-mode normalization in `load_driver_routes` + command-doc boundaries in `.claude/commands/` | Modify | Command docs must not own ledger append mechanics |
| FR-001 / FR-007 / FR-009 | Canonical flow + artifact validation + event append only after pass | Modify | Validate fail path verified with no append side effect |
| FR-002 / FR-003 / FR-004 / FR-005 | `resolve_phase_state` + approval gate + blocked envelope (`exit_code=1`) | Modify | Deterministic blocked reason codes required |
| FR-006 / FR-010 / FR-011 | Producer-only docs, ordered handoff, idempotent retry via ledger/state lock semantics | Modify | Repeated runs must avoid duplicate terminal outcomes |
| FR-012 / FR-013 / FR-014 | Ledger-authoritative state, append gate in ledger script, canonical driver entrypoint naming | Reuse + Modify | Drift and partial-write paths must remain non-complete |

---

## Work-Type Classification

| Capability / Story Area | Work Type(s) | Dominant Pattern in Repo | Reuse-First / Extension-First / Net-New | Special Constraints |
|-------------------------|--------------|---------------------------|-----------------------------------------|--------------------|
| Deterministic phase execution | Orchestration + validation | Script-first driver orchestration | Extension-first | No completion emit before validation pass |
| Phase state resolution | State reconciliation + guardrails | Ledger-derived phase state | Reuse-first + targeted extension | Mirrors are advisory only |
| Event append safety | Sequence validation + append | Append-only JSONL + transition validation | Reuse-first | No direct ledger writes outside ledger script |
| Command contract governance | Manifest/doc alignment | Manifest route metadata + command docs | Extension-first | Producer-only docs, script-owned emit behavior |

---

## Current-System Inventory

| Surface | Type | Role Today | Relationship to Feature | Condition | Primary Seam or Blast Radius Only |
|---------|------|------------|--------------------------|-----------|-----------------------------------|
| `scripts/pipeline_driver.py` | script | Orchestrates phase execution and envelope handling | Core execution seam for this feature | Extension-friendly | Primary |
| `scripts/pipeline_driver_state.py` | script | Resolves current phase and lock semantics | Source for ledger-authoritative reconciliation | Extension-friendly | Primary |
| `scripts/pipeline_driver_contracts.py` | script/module | Validates result envelope + loads routes | Enforces producer/driver contract boundary | Extension-friendly | Primary |
| `scripts/pipeline_ledger.py` | script | Validates event shape/sequence and appends events | Event authority and sequence gate | Reusable | Primary |
| `command-manifest.yaml` | manifest | Registry for command routes/artifacts/events | Route and emit contract source of truth | Reusable with updates | Primary |
| `.claude/commands/speckit.solution.md` | command doc | Parent solution-phase contract and auto-invoke ordering | Must preserve producer-only boundaries and hierarchy gates | Extension-friendly | Blast radius |
| `tests/unit/test_pipeline_driver.py` | test | Driver behavior verification | Regression surface for validate-before-emit and envelope semantics | Reusable | Blast radius |
| `tests/integration/test_pipeline_driver_feature_flow.py` | test | End-to-end phase progression coverage | Guards migration regressions across phases | Reusable | Blast radius |

---

## Command / Script Surface Map

| Name | Owning File / Script / Template | Pipeline Role | Classification | Inputs | Outputs / Artifacts | Events | Extension Seam | Planned Change |
|------|---------------------------------|---------------|----------------|--------|----------------------|--------|----------------|----------------|
| `uv run python scripts/pipeline_driver.py --feature-id <FEATURE_ID> [--phase <PHASE>]` | `scripts/pipeline_driver.py` | Canonical phase executor | Deterministic | Feature id, phase, approval token, manifest routes | Step result envelope, handoff payload, artifact metadata | Success append delegated to ledger script | Main orchestration and gate flow | Modify |
| `resolve_phase_state(...)` | `scripts/pipeline_driver_state.py` | Reconciles current phase and drift | Deterministic | Feature id, optional hint, ledger path | Phase state dict with drift reasons | None direct | Ledger reconcile + artifact existence checks | Modify minimally |
| `parse_step_result(...)` / `validate_reason_codes(...)` | `scripts/pipeline_driver_contracts.py` | Envelope and gate-reason contract validation | Deterministic | Step result payload, reason registry, manifest data | Validated normalized envelope or error | None direct | Conditional field enforcement and reason registry checks | Modify |
| `load_driver_routes(...)` | `scripts/pipeline_driver_contracts.py` | Normalizes manifest route metadata | Deterministic | Manifest path | Driver-managed route map with emit contracts | None direct | Mode normalization and emit contract extraction | Modify |
| `cmd_append` / `validate_sequence` | `scripts/pipeline_ledger.py` | Sequence-safe append authority | Deterministic | Feature/event payloads | Append success/failure and validation state | Pipeline events | Transition enforcement and required-field checks | Reuse |
| `speckit.sketch` command contract | `.claude/commands/speckit.sketch.md` | Produces sketch artifact only | Hybrid producer | Feature context, plan/spec/repo anchors | `sketch.md` | `sketch_completed` (driver/ledger-owned emit path) | Keep producer-only behavior | Modify wording only if needed |
| Solution orchestration contract | `.claude/commands/speckit.solution.md` | Controls sketch->review->tasking->analyze ordering | Hybrid governance | Feature artifacts + gates | Routed subcommand execution order | `solution_approved` after tasking/review | Preserve hard-block/read-order rules | Modify wording only if needed |

---

## CodeGraphContext Findings

### Seed Symbols

- `scripts/pipeline_driver.py:main` - canonical phase execution control flow and gate ordering.
- `scripts/pipeline_driver.py:validate_generated_artifact` - deterministic artifact validation before append.
- `scripts/pipeline_driver.py:append_pipeline_success_event` - manifest-derived success append bridge.
- `scripts/pipeline_driver_state.py:resolve_phase_state` - ledger-authoritative state reconciliation.
- `scripts/pipeline_driver_contracts.py:load_driver_routes` - route mode + emit contract normalization.
- `scripts/pipeline_driver_contracts.py:parse_step_result` - envelope schema gate.
- `scripts/pipeline_ledger.py:validate_sequence` - transition and required-field enforcement.
- `scripts/pipeline_ledger.py:cmd_append` - immutable append entrypoint.

### Primary Implementation Surfaces

| File | Symbol(s) | Why This Surface Is Primary | Planned Change Type |
|------|-----------|-----------------------------|---------------------|
| `scripts/pipeline_driver.py` | `main`, `validate_generated_artifact`, `append_pipeline_success_event` | Controls permission, validation, and emit/handoff sequence | Modify |
| `scripts/pipeline_driver_state.py` | `resolve_phase_state` | Owns authoritative phase reconciliation and drift signaling | Modify minimally |
| `scripts/pipeline_driver_contracts.py` | `parse_step_result`, `load_driver_routes`, `validate_reason_codes` | Enforces contract correctness for producer outputs and routing | Modify |
| `scripts/pipeline_ledger.py` | `validate_sequence`, `cmd_append` | Owns event-order safety and append authority | Reuse |
| `command-manifest.yaml` | `commands.*` entries, `emits.required_fields` | Declares route and completion contracts consumed by driver | Modify |
| `.claude/commands/speckit.solution.md` | compact/expanded guidance + behavior rules | Defines solution phase orchestration and read/gate rules | Modify |

### Secondary Affected Surfaces

| File / Surface | Why It Is Affected | Type of Impact |
|----------------|--------------------|----------------|
| `.claude/commands/speckit.sketch.md` | Producer-only and handoff rules must remain aligned | Docs/governance blast radius |
| `specs/023-deterministic-phase-orchestration/contracts/phase-execution-contract.md` | Contract artifact must match actual script boundaries | Contract consistency |
| `specs/023-deterministic-phase-orchestration/quickstart.md` | Operator execution and approval behavior documentation | Operator/runbook |
| `tests/unit/test_pipeline_driver.py` | Unit assertions for gate and envelope behavior | Regression |
| `tests/unit/test_pipeline_ledger_sequence.py` | Sequence/required-field invariants for append | Regression |
| `tests/integration/test_pipeline_driver_feature_flow.py` | End-to-end progression consistency across phases | Regression |

### Caller / Callee / Dependency Notes

- CodeGraph callers confirm `main` as caller for `resolve_phase_state`, `validate_generated_artifact`, and `append_pipeline_success_event`.
- `append_pipeline_success_event` calls `load_driver_routes` and `_execute_command` to delegate append to `pipeline_ledger.py append`.
- `resolve_phase_state` loads ledger events and runs `validate_sequence` before resolving current phase.
- `parse_step_result` validates conditional fields by `exit_code`, and blocked envelopes validate reason codes against `docs/governance/gate-reason-codes.yaml`.

### Missing Seams or Contradictions

- `cgc analyze deps pipeline_driver` currently fails with a Kuzu binder error (`Variable file is not in scope`), so module dependency extraction is not reliable for this run.
- `scripts/pipeline_driver.py` module docstring still says "skeleton" while the file now contains full orchestration behavior; this is a documentation contradiction, not a runtime blocker.

---

## Blast Radius

### Direct Implementation Surfaces

- `scripts/pipeline_driver.py`
- `scripts/pipeline_driver_state.py`
- `scripts/pipeline_driver_contracts.py`
- `command-manifest.yaml`
- `.claude/commands/speckit.solution.md` and related producer docs

### Indirect Affected Surfaces

- `scripts/pipeline_ledger.py` transition/append behavior expectations
- `specs/023-deterministic-phase-orchestration/contracts/phase-execution-contract.md`
- `specs/023-deterministic-phase-orchestration/quickstart.md`
- `docs/governance/gate-reason-codes.yaml`

### Regression-Sensitive Neighbors

- `tests/unit/test_pipeline_driver.py`
- `tests/unit/test_pipeline_ledger_sequence.py`
- `tests/unit/test_speckit_solution_command_doc.py`
- `tests/integration/test_pipeline_driver_feature_flow.py`
- `tests/integration/test_speckit_pipeline_driver.py`

### Rollout / Compatibility Impact

- Mixed migration mode is supported; commands can remain legacy until explicitly driver-managed.
- Emit contracts in manifest must stay synchronized with driver append logic.
- Existing phase IDs/events remain stable; no new event taxonomy is required for this feature.

### Operator / Runbook / Deployment Impact

- Operators continue using CLI execution via `pipeline_driver.py`; approval token behavior must stay explicit.
- Runbook docs must describe blocked/error envelopes and rerun expectations.
- No new external service deployment is introduced.

---

## Reuse / Modify / Create Matrix

### Reuse Unchanged

- `scripts/pipeline_ledger.py` as append authority and sequence validator.
- Existing phase/event taxonomy in ledger scripts.
- Existing unit/integration test harness structure.

### Modify / Extend Existing

- `scripts/pipeline_driver.py` orchestration ordering and artifact/emit gate behavior.
- `scripts/pipeline_driver_state.py` drift handling and phase-state reconciliation details.
- `scripts/pipeline_driver_contracts.py` route normalization and envelope validation.
- `command-manifest.yaml` route metadata and event contract clarity.
- `.claude/commands/speckit.solution.md` and related docs for producer-only boundaries.

### Compose from Existing Pieces

- Driver + state resolver + route contracts + ledger append forms the execution contract.
- Spec/plan/review artifacts + command docs + manifest metadata form the producer contract boundary.

### Create Net-New

- No net-new runtime service or workflow engine.
- Net-new work is limited to feature artifact content (`sketch.md`) and potentially focused test cases.

### Reuse Rationale

The repository already contains the deterministic building blocks. Reusing and tightening these seams minimizes risk, preserves governance continuity, and avoids introducing parallel orchestration infrastructure.

---

## Manifest Alignment Check

| Affected Command / Phase | Existing Manifest Coverage? | New Artifact Needed? | New Event / Field Needed? | Handoff / Event Flow Impact | Status |
|--------------------------|-----------------------------|----------------------|---------------------------|-----------------------------|--------|
| `speckit.sketch` | Yes | `specs/023-deterministic-phase-orchestration/sketch.md` | No new event type; keep `sketch_completed` | Completion event remains append-only after validation | Aligned |
| `speckit.solution` | Yes | None (orchestrates downstream artifacts) | No new event type; keep `solution_approved` | Must not emit before solutionreview + tasking stabilization | Aligned |
| `speckit.solutionreview` | Yes | `solutionreview.md` | No | Remains quality gate before tasking | Aligned |
| `speckit.tasking` | Yes | `tasks.md` | No new event type; keep `tasking_completed` contracts | Must consume sketch slices without architecture invention | Aligned |
| `speckit.analyze` | Yes | `analysis.md` | No new event type; keep `analysis_completed` constraints | Must stay post-solution drift gate | Aligned |
| `command-manifest.yaml` governance metadata | Partial | N/A | Potential metadata tighten for migration reporting only | Keep root manifest canonical and synced with driver assumptions | Needs update watch |

### Manifest Alignment Notes

- Manifest command IDs and event taxonomy remain stable.
- Event append still requires script-owned path and deterministic pass conditions.
- Any manifest metadata edit must be validated against `load_driver_routes` and command coverage tests.

---

## Architecture Flow Delta

Choose one:

- **Architecture Flow refined**

### Delta Summary

Plan-level flow is preserved; this sketch refines implementation boundaries by making concrete symbol/file ownership explicit for permission gating, validation, append authority, and handoff sequencing.

### Added / Refined Nodes, Edges, or Boundaries

| Change | Why Needed at LLD Level | Must Preserve in Tasking / Implementation |
|--------|--------------------------|-------------------------------------------|
| Explicit `main -> resolve_phase_state` boundary | Prevents ambiguous current-step source of truth | Ledger remains authoritative |
| Explicit `main -> validate_generated_artifact -> append_pipeline_success_event` chain | Ensures validate-before-emit is enforceable in code | No completion append before validation pass |
| `append_pipeline_success_event -> pipeline_ledger.py append` delegation | Keeps append authority script-owned | No direct ledger file mutation from docs/templates |
| `parse_step_result` + reason-code registry validation | Enforces deterministic blocked/error payload quality | Blocked envelopes must use registered gates/reasons |
| Producer-only command doc boundary | Reduces duplicated orchestration prose and drift | Command docs generate artifacts only |

---

## Component and Boundary Design

| Component / Boundary | Responsibility | Owning or Likely Touched File(s) | Likely Touched Symbol(s) | Reuse / Modify / Create | Inbound Dependencies | Outbound Dependencies |
|----------------------|----------------|----------------------------------|--------------------------|-------------------------|---------------------|----------------------|
| Driver orchestrator | Execute phase flow with gate ordering | `scripts/pipeline_driver.py` | `main`, `validate_generated_artifact`, `append_pipeline_success_event` | Modify | Manifest routes, phase state, approval token | Ledger append, handoff payloads |
| Phase state resolver | Resolve current phase and drift | `scripts/pipeline_driver_state.py` | `resolve_phase_state`, lock helpers | Modify minimally | Ledger events, feature hints | Driver decision logic |
| Route/envelope contracts | Validate route mode + step envelopes | `scripts/pipeline_driver_contracts.py` | `load_driver_routes`, `parse_step_result`, `validate_reason_codes` | Modify | Manifest, reason-code registry | Driver gate decisions |
| Event append authority | Validate sequence and append events | `scripts/pipeline_ledger.py` | `validate_sequence`, `cmd_append` | Reuse | Append payload from driver | Pipeline ledger state |
| Manifest registry | Declare command artifacts/events/routes | `command-manifest.yaml` | command entries for solution pipeline | Modify | Governance decisions | Driver route resolution |
| Producer command docs | Produce artifacts and completion payload intent | `.claude/commands/speckit.*.md` | compact contracts and behavior rules | Modify | Spec/plan/research context | Sketch/review/tasking/analyze artifacts |

### Control Flow Notes

- `resolve_phase_state` executes before any side-effecting phase action.
- Approval failure returns blocked envelope and exits with no append/handoff.
- Artifact/envelope validation precedes success append attempt.
- Append timeout/failure path remains non-success and must preserve debug information.

### Data Flow Notes

- Input context: feature id, optional phase, manifest routes, ledger state.
- Intermediate payloads: producer output, generated artifact metadata, normalized step envelope.
- Output contracts: canonical three-line status + optional JSON envelope + ledger append side effect only on pass.

---

## Interface, Symbol, and Contract Notes

### Public Interfaces and Contracts

| Interface / Contract | Purpose | Owner | Validation Point | Failure / Error Shape |
|----------------------|---------|-------|------------------|-----------------------|
| `pipeline_driver.py` CLI args (`--feature-id`, `--phase`, `--dry-run`, `--approval-token`) | Trigger deterministic phase execution | Driver script | Arg parse + early gate checks in `main` | Blocked envelope (`exit_code=1`, gate/reasons) |
| Step-result envelope (`schema_version`, `ok`, `exit_code`, `correlation_id`, conditional fields) | Canonical execution result for routing and status | Driver contracts module | `parse_step_result` | Contract violation raises deterministic error path |
| Reason-code registry (`docs/governance/gate-reason-codes.yaml`) | Governs blocked reason taxonomy | Governance docs + contracts module | `validate_reason_codes` | Unknown gate/reason failure |
| Manifest route contract (`command-manifest.yaml`) | Declares mode/script/emits/artifacts | Manifest maintainer + governance | `load_driver_routes` | Route normalization/shape errors |
| Pipeline append contract (`pipeline_ledger.py append`) | Immutable append with sequence enforcement | Ledger script | `cmd_append` + `validate_sequence` | Append rejected with sequence validation errors |

### New or Changed Public Symbols

| Symbol | Change Type | Exact Intended Signature | Layer / Module | Responsibility | Notes |
|--------|-------------|---------------------------|----------------|----------------|------|
| `validate_generated_artifact` | Preserved/extended | `validate_generated_artifact(artifact_path: str | Path, *, correlation_id: str, completion_marker: str | None = None) -> dict[str, Any]` | Driver | Artifact validation gate | Must remain deterministic and side-effect free |
| `append_pipeline_success_event` | Preserved/extended | `append_pipeline_success_event(*, feature_id: str, phase: str, command_id: str | None, actor: str = "pipeline_driver", manifest_path: str | Path | None = None, timeout_seconds: int = 60) -> dict[str, Any]` | Driver | Success append bridge | Must never append when no valid selected event |
| `resolve_phase_state` | Preserved/extended | `resolve_phase_state(feature_id: str, *, pipeline_state: Mapping[str, Any] | None = None, ledger_path: Path | str = ".speckit/pipeline-ledger.jsonl", feature_dir: Path | str | None = None) -> dict[str, Any]` | State resolver | Ledger-authoritative reconciliation | Must surface drift clearly |
| `parse_step_result` | Preserved/extended | `parse_step_result(step_result: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]` | Contracts | Envelope schema enforcement | Conditional fields by `exit_code` are mandatory |
| `load_driver_routes` | Preserved/extended | `load_driver_routes(manifest_path: str | Path | None = None) -> dict[str, dict[str, Any]]` | Contracts | Manifest route normalization | Must keep canonical root manifest behavior |
| `cmd_append` | Preserved | `cmd_append(args: argparse.Namespace) -> None` | Ledger | Sequence-safe append | Append rejection is expected on invalid transition |

### Ownership Boundaries

- Command docs/templates own artifact synthesis intent and completion semantics.
- Driver/state/contracts scripts own deterministic gates, validation, and progression decisions.
- Ledger script owns append/sequence authority.
- Manifest owns route and event declarations consumed by scripts.

---

## State / Lifecycle / Failure Model

### State Authority

| State / Field / Lifecycle Area | Authoritative Source | Reconciliation Rule | Notes |
|--------------------------------|----------------------|---------------------|------|
| Current phase for feature | `.speckit/pipeline-ledger.jsonl` events | `resolve_phase_state` derives phase from last valid event | Feature hints are advisory only |
| Plan/solution approval booleans | Ledger-derived state in `validate_sequence` | Derived from emitted events only | Prevents mirror drift |
| Step-result validity | Contracts module (`parse_step_result`) | Envelope must satisfy required/conditional fields | Invalid envelopes are non-success |
| Event eligibility | Driver validation + manifest emit contracts | Append allowed only after validation pass | Missing/invalid emits means no append |
| Feature lock ownership | Lock files under `.speckit/locks` | Acquire/reuse/replace stale semantics in state module | Prevents conflicting concurrent runs |

### Lifecycle / State Transitions

| Transition | Allowed? | Trigger | Validation / Guard | Failure Handling |
|------------|----------|---------|--------------------|------------------|
| `resolved -> blocked` | Yes | Permission denied, drift, or invalid input | Gate checks in `main` + reason code contract | Return `exit_code=1`, no append |
| `resolved -> producer_executed` | Yes | Permission granted and command route valid | Route normalization + execution checks | Runtime failure sidecar + `exit_code=2` |
| `producer_executed -> validated` | Yes | Artifact + envelope validation pass | `validate_generated_artifact` + `parse_step_result` | Blocked result on validation failure |
| `validated -> appended` | Yes | Selected emit contract with empty required fields and append success | `append_pipeline_success_event` + ledger append result | Non-success on append timeout/failure |
| `validated -> handoff` | Yes | Append success or no-append path considered complete by contract | Driver success envelope with `next_phase` | Must not occur on validation/append failure |

### Retry / Replay / Ordering / Cancellation

- Retry behavior: rerun uses same deterministic gates and phase reconciliation; no direct replay shortcut.
- Duplicate / replay handling: ledger transition checks reject invalid duplicate terminal progression.
- Out-of-order handling: requested phase mismatch and sequence invalidity become blocked outcomes.
- Cancellation / timeout behavior: timeout paths become `exit_code=2` with debug sidecar and no completion append.

### Degraded Modes / Fallbacks / Recovery

- If reason-code registry cannot load, blocked reason validation surfaces explicit contract error.
- If codegraph dependency query is unavailable, fallback to helper-driven bounded reads and caller/callee checks.
- Recovery expectation: operator reruns after correcting artifact, route metadata, or ledger/state conditions.

---

## Non-Functional Design Implications

| Concern | Design Implication | Affected Surface(s) | Notes |
|---------|--------------------|---------------------|-------|
| Determinism | All progression decisions must be script-validated, not prompt-inferred | Driver, contracts, ledger | Core governance invariant |
| Reliability | Validate-before-emit and append sequence checks prevent false completion | Driver + ledger | No completion event on validation fail |
| Concurrency | Feature lock semantics reduce conflicting concurrent runs | State resolver | Stale-lock replacement path required |
| Observability | Canonical status lines + optional JSON + debug sidecar on errors | Driver + tests | Supports deterministic triage |
| Security/governance | Explicit approval gate and no direct ledger reads/writes in docs | Driver + command docs | Human-first and process-first compliance |
| Token efficiency | Producer-only docs reduce repeated orchestration prose | Command docs | Must not hide deterministic steps |

---

## Migration / Rollback Notes

### Migration / Cutover Requirements

- Keep mixed migration mode explicit (`legacy` vs driver-managed routes) per command.
- Migrate command docs and manifest metadata in small slices to maintain route/test parity.
- Maintain hard-block behavior if unresolved feasibility or validation gaps are reintroduced.

### Rollback Triggers

- Completion event emitted on a validation-fail scenario.
- Permission-denied scenario still causes phase side effects.
- Route normalization failures across commands in migrated flow.

### Rollback Constraints

- Rollback must preserve ledger integrity (no event deletions or direct file edits).
- Rollback may only revert script/doc/manifest changes while keeping append-only audit trail semantics.

---

## Human-Task and Operator Boundaries

| Boundary | Why Human / Operator Action Is Required | Preconditions | Artifact / Evidence Consumed | Downstream `[H]` Implication | Failure / Escalation Path |
|----------|-----------------------------------------|---------------|------------------------------|------------------------------|---------------------------|
| Phase start approval | Human remains ultimate decision-maker before side effects | Phase resolved and gate checks passed | CLI status + resolved phase context | Tasking should include explicit approval UX checks | Reject/timeout returns blocked; escalate via runbook |
| Manifest/governance updates | Route/event contract edits can affect all phases | Proposed contract change prepared | `command-manifest.yaml`, contract artifact, tests | Add `[H]` review task for governance-sensitive edits | Block merge until deterministic checks pass |
| Exception triage for error sidecar | Error path may require operator interpretation before rerun | `exit_code=2` with debug path | Sidecar diagnostics + status lines | Include `[H]` rerun decision task where needed | Escalate if repeated timeout/contract errors persist |

---

## Verification Strategy

### Unit-Testable Seams

- `validate_generated_artifact` blocked/pass behavior.
- `parse_step_result` conditional-field enforcement.
- `validate_reason_codes` gate/reason registry enforcement.
- `validate_sequence` transition and required-field checks.

### Contract Verification Needs

- Manifest route shape and emit contract normalization through `load_driver_routes`.
- Step-result schema conformance for success/blocked/error envelopes.
- Producer-only command-doc wording checks where applicable.

### Integration / Reality-Check Paths

- `tests/integration/test_pipeline_driver_feature_flow.py` for end-to-end progression.
- `tests/integration/test_speckit_pipeline_driver.py` for driver orchestration behavior.
- Repo command checks: `bash .specify/scripts/bash/check-prerequisites.sh --json` and ledger phase asserts.

### Lifecycle / Retry / Duplicate Coverage Needs

- Re-run after blocked validation should not append completion events.
- Re-run after append success should not create invalid transitions.
- Drift and requested-phase mismatch must produce deterministic blocked outcomes.

### Deterministic Oracles (if known)

- `uv run python scripts/pipeline_ledger.py validate`
- `uv run python scripts/pipeline_ledger.py assert-phase-complete --feature-id 023 --event <event>`
- `uv run pytest tests/unit/test_pipeline_driver.py tests/unit/test_pipeline_ledger_sequence.py`
- `uv run pytest tests/integration/test_pipeline_driver_feature_flow.py tests/integration/test_speckit_pipeline_driver.py`

### Regression-Sensitive Areas

- Approval gate behavior in `main`.
- Validate-before-emit chain.
- Manifest mode normalization and emit contract parsing.
- Legacy transition compatibility in ledger sequence validation.

---

## Domain Guardrails

| Domain | Why Touched | MUST Constraints | Forbidden Shortcuts | Invariants to Preserve |
|--------|-------------|------------------|---------------------|------------------------|
| 02 Data modeling | Step envelopes and contract schemas are central | Enforce required/conditional fields deterministically | Accepting partially shaped step results | Canonical envelope schema by exit code |
| 03 Data storage | Ledger append and sequence validation govern state | Append-only, validated transitions, no direct edits | Manual JSONL edits or bypassed append path | Ledger-authoritative progression |
| 07 Compute & orchestration | Driver executes phase flow | Preserve explicit gate ordering and no hidden side effects | Prompt-owned state transitions | `orchestrate -> extract -> scaffold -> LLM Action -> validate -> emit/handoff` |
| 09 Environment & config | Manifest path, reason registry, CLI args are config surfaces | Canonical manifest path and validated config inputs | Ad-hoc route metadata outside manifest | Single source of truth for routes/events |
| 10 Observability | Status lines and debug sidecars support triage | Deterministic status contract and error diagnostics | Silent failure paths | Actionable blocked/error reporting |
| 12 Testing | Deterministic verification is non-negotiable | Unit + integration checks before completion claims | Skipping tests for script/doc contract changes | Verification-first completion policy |

---

## LLD Decision Log

| Subject | Status | Rationale | Downstream Implication | May Tasking Proceed? |
|---------|--------|-----------|------------------------|----------------------|
| Canonical automated entrypoint remains `pipeline_driver.py` | Decided | Already stable and aligned with plan + manifest | Tasking must not introduce alternate orchestrator | Yes |
| Validate-before-emit is script-owned, non-negotiable | Decided | Core governance invariant | Every implementation task must preserve ordering | Yes |
| Ledger remains authoritative for phase state | Decided | Prevents drift and inconsistent phase resolution | Tasks must avoid mirror-authority semantics | Yes |
| Producer-only command docs boundary | Decided | Reduces duplicated orchestration logic and token overhead | Tasking must treat docs as artifact contracts only | Yes |
| CodeGraph dependency command reliability | Deferred | `cgc analyze deps` currently fails with binder error | Use helper reads + caller/callee checks until fixed | Conditional |
| `pipeline_driver.py` top docstring mismatch ("skeleton") | Needs manifest update | Documentation contradicts current implementation maturity | Add doc hygiene task in decomposition | Yes |

---

## Design Gaps and Repo Contradictions

### Missing Seams

- No dedicated deterministic command for verifying producer-only language drift across all speckit command docs in one pass (currently spread across tests).

### Unsupported Assumptions

- Assuming CodeGraph dependency analysis is always available is unsafe right now due the current binder exception in `cgc analyze deps`.

### Plan vs Repo Contradictions

- Plan assumptions remain consistent with runtime behavior; no material architecture contradiction found.
- Minor contradiction: `pipeline_driver.py` file docstring says "skeleton" while the implementation is not skeletal.

### Blocking Design Issues

- None.

---

## Out-of-Scope / Preserve-As-Is Boundaries

- Do not introduce a new workflow engine or external orchestrator.
- Do not change task-ledger lifecycle semantics in this feature.
- Do not add new pipeline event taxonomy unless a future spec explicitly requires it.
- Do not widen command-doc responsibilities to include direct ledger append or state mutation.

---

## Design-to-Tasking Contract

Tasking must follow these rules:

- Every decomposition-ready design slice must produce at least one task unless an explicit omission rationale is recorded.
- No task may introduce scope, seams, symbols, interfaces, or artifacts absent from this sketch without explicit rationale.
- `[H]` tasks may only come from identified human/operator boundaries or explicit external dependency constraints.
- `file:symbol` annotations in tasks must trace back to symbol targets or symbol-creation notes in this sketch.
- Acceptance artifacts must derive from the verification intent and acceptance traceability in this sketch.
- Large-point tasks that require later breakdown must preserve the originating design slice and its safety invariants.
- Tasking must preserve declared inter-slice dependencies unless an explicit rationale is recorded.
- Tasking must not create tasks against surfaces explicitly marked preserve-as-is unless a rationale is recorded.

### Additional Tasking Notes

- Maintain stable slice IDs (`SK-01`, `SK-02`, ...) in `tasks.md` references so review and checkpoint traces stay deterministic.

---

## Decomposition-Ready Design Slices

### Slice SK-01: Driver orchestration and permission gate

**Objective**  
Preserve deterministic phase orchestration entry flow and explicit approval boundary.

**Touched Files**  
- `scripts/pipeline_driver.py`

**Touched Symbols**  
- `scripts/pipeline_driver.py:main`
- `scripts/pipeline_driver.py:emit_human_status`

**Likely Net-New Files**  
- None expected.

**Primary Seam**  
Driver CLI argument parse and gate ordering in `main`.

**Blast-Radius Neighbors**  
- `tests/unit/test_pipeline_driver.py`
- `tests/integration/test_speckit_pipeline_driver.py`

**Reuse / Modify / Create Classification**  
Modify.

**Required Public Symbols / Interfaces**  
- Driver CLI contract (`--feature-id`, `--phase`, `--dry-run`, `--approval-token`).

**Major Constraints**  
- Approval denial must produce no side effects.
- Requested phase mismatch must remain blocked and deterministic.

**Dependencies on Other Slices**  
- Depends on `SK-02` and `SK-03` for validation and append phases.

**Primary Verification Intent**  
Prove permission-denied and drift paths return blocked envelopes with no emit/handoff side effects.

**Operator Impact**  
Operator confirms execution via approval token path.

**Likely Verification / Regression Concern**  
Gate ordering regressions that execute producer step before permission checks.

### Slice SK-02: Validate-before-emit enforcement

**Objective**  
Ensure completion event append can only happen after artifact and envelope validation pass.

**Touched Files**  
- `scripts/pipeline_driver.py`

**Touched Symbols**  
- `scripts/pipeline_driver.py:validate_generated_artifact`
- `scripts/pipeline_driver.py:append_pipeline_success_event`

**Likely Net-New Files**  
- None expected.

**Primary Seam**  
Validation chain between producer output and append delegation.

**Blast-Radius Neighbors**  
- `tests/unit/test_pipeline_driver.py`
- `tests/unit/test_pipeline_ledger_sequence.py`

**Reuse / Modify / Create Classification**  
Modify.

**Required Public Symbols / Interfaces**  
- Step-result envelope contract.

**Major Constraints**  
- Validation fail, timeout, or append failure must remain non-success.

**Dependencies on Other Slices**  
- Depends on `SK-03` for route metadata and contract checks.

**Primary Verification Intent**  
Prove that no success event is emitted when validation fails.

**Operator Impact**  
None direct; affects reliability of observed phase completion.

**Likely Verification / Regression Concern**  
False-positive completion append on weak validation branches.

### Slice SK-03: Route and envelope contract enforcement

**Objective**  
Keep manifest route metadata and step-envelope validation deterministic and explicit.

**Touched Files**  
- `scripts/pipeline_driver_contracts.py`
- `docs/governance/gate-reason-codes.yaml`

**Touched Symbols**  
- `scripts/pipeline_driver_contracts.py:load_driver_routes`
- `scripts/pipeline_driver_contracts.py:parse_step_result`
- `scripts/pipeline_driver_contracts.py:validate_reason_codes`

**Likely Net-New Files**  
- None expected.

**Primary Seam**  
Route normalization and blocked/error reason taxonomy validation.

**Blast-Radius Neighbors**  
- `tests/unit/test_pipeline_driver.py`
- `tests/unit/test_validate_command_script_coverage.py`

**Reuse / Modify / Create Classification**  
Modify.

**Required Public Symbols / Interfaces**  
- Manifest command route schema.
- Step-result schema (`schema_version`, `exit_code` conditional fields).

**Major Constraints**  
- Unsupported modes and malformed emits must fail deterministically.

**Dependencies on Other Slices**  
- Supports `SK-01`, `SK-02`, and `SK-05`.

**Primary Verification Intent**  
Prove malformed route metadata and reason codes are rejected before progression.

**Operator Impact**  
Low direct impact; high governance impact.

**Likely Verification / Regression Concern**  
Silent acceptance of invalid route/reason metadata.

### Slice SK-04: Ledger-authoritative state and append path

**Objective**  
Preserve ledger state as source of truth and keep append operation sequence-safe.

**Touched Files**  
- `scripts/pipeline_driver_state.py`
- `scripts/pipeline_ledger.py`

**Touched Symbols**  
- `scripts/pipeline_driver_state.py:resolve_phase_state`
- `scripts/pipeline_ledger.py:validate_sequence`
- `scripts/pipeline_ledger.py:cmd_append`

**Likely Net-New Files**  
- None expected.

**Primary Seam**  
State reconciliation and append transition validation.

**Blast-Radius Neighbors**  
- `tests/unit/test_pipeline_ledger_sequence.py`
- `tests/integration/test_pipeline_driver_feature_flow.py`

**Reuse / Modify / Create Classification**  
Reuse + Modify minimally.

**Required Public Symbols / Interfaces**  
- `pipeline_ledger.py append` CLI.

**Major Constraints**  
- Invalid transitions must be rejected.
- No direct ledger file read/write shortcuts outside owned scripts.

**Dependencies on Other Slices**  
- Supports `SK-01` and `SK-02`.

**Primary Verification Intent**  
Prove state drift and transition violations remain blocked.

**Operator Impact**  
Improves operator trust in phase status.

**Likely Verification / Regression Concern**  
Edge-case transition acceptance under mixed migration conditions.

### Slice SK-05: Manifest and command-doc alignment

**Objective**  
Keep command docs producer-only and manifest contracts synchronized with driver assumptions.

**Touched Files**  
- `command-manifest.yaml`
- `.claude/commands/speckit.solution.md`
- `.claude/commands/speckit.sketch.md`

**Touched Symbols**  
- Manifest `commands.<command_id>.driver.mode`
- Manifest `commands.<command_id>.emits.*`

**Likely Net-New Files**  
- None expected.

**Primary Seam**  
Doc/manifest governance boundary for route + emit behavior.

**Blast-Radius Neighbors**  
- `tests/unit/test_speckit_solution_command_doc.py`
- `tests/unit/test_validate_markdown_doc_shapes.py`

**Reuse / Modify / Create Classification**  
Modify.

**Required Public Symbols / Interfaces**  
- Command compact contracts for solution/sketch/tasking/analyze.

**Major Constraints**  
- Do not reintroduce direct event append instructions into command docs.

**Dependencies on Other Slices**  
- Depends on `SK-03` for route schema assumptions.

**Primary Verification Intent**  
Prove manifest and command docs remain contract-compatible and producer-only.

**Operator Impact**  
Cleaner operator guidance and reduced ambiguity.

**Likely Verification / Regression Concern**  
Doc drift that conflicts with script-owned deterministic behavior.

### Slice SK-06: Verification and regression harness updates

**Objective**  
Codify deterministic test coverage for permission, validation, append, and progression semantics.

**Touched Files**  
- `tests/unit/test_pipeline_driver.py`
- `tests/unit/test_pipeline_ledger_sequence.py`
- `tests/integration/test_pipeline_driver_feature_flow.py`
- `tests/integration/test_speckit_pipeline_driver.py`

**Touched Symbols**  
- Test cases around driver blocked/success/error envelope behavior.

**Likely Net-New Files**  
- Possibly targeted new tests under `tests/unit/` or `tests/integration/` if coverage gaps are found.

**Primary Seam**  
Deterministic oracle validation at unit and integration levels.

**Blast-Radius Neighbors**  
- CI pipeline and checkpoint/e2e gates.

**Reuse / Modify / Create Classification**  
Modify + Create (tests only).

**Required Public Symbols / Interfaces**  
- Existing test fixtures and deterministic gate scripts.

**Major Constraints**  
- Verification-first completion policy is mandatory.

**Dependencies on Other Slices**  
- Depends on `SK-01` through `SK-05` implementation outcomes.

**Primary Verification Intent**  
Prove migrated flow satisfies FR-001..FR-014 deterministically.

**Operator Impact**  
Indirect; stronger confidence and fewer regression surprises.

**Likely Verification / Regression Concern**  
Incomplete coverage for mixed migration edge cases.

### Slice SK-07: Operator runbook and artifact consistency

**Objective**  
Keep operator-facing docs and feature artifacts synchronized with actual deterministic behavior.

**Touched Files**  
- `specs/023-deterministic-phase-orchestration/quickstart.md`
- `specs/023-deterministic-phase-orchestration/contracts/phase-execution-contract.md`
- `specs/023-deterministic-phase-orchestration/sketch.md`

**Touched Symbols**  
- N/A (documentation and contracts).

**Likely Net-New Files**  
- None expected.

**Primary Seam**  
Human/operator boundary documentation and contract clarity.

**Blast-Radius Neighbors**  
- `speckit.solutionreview` and `speckit.tasking` artifacts.

**Reuse / Modify / Create Classification**  
Modify.

**Required Public Symbols / Interfaces**  
- CLI run steps and deterministic gate command examples.

**Major Constraints**  
- Docs must not claim behavior not enforced by scripts/tests.

**Dependencies on Other Slices**  
- Depends on stable behavior from `SK-01` through `SK-04`.

**Primary Verification Intent**  
Prove operator docs match actual execution and failure paths.

**Operator Impact**  
Direct; clearer execution, triage, and rerun guidance.

**Likely Verification / Regression Concern**  
Documentation lag after script-level contract changes.

_Add as many slices as needed, using stable IDs (`SK-02`, `SK-03`, ...)._

---

## Sketch Completion Summary

### Review Readiness

- [x] The solution narrative is clear
- [x] The construction strategy is coherent
- [x] Acceptance traceability is complete
- [x] Touched files and symbols are concrete enough for tasking
- [x] Reuse / modify / create choices are explicit
- [x] Manifest alignment is explicit where relevant
- [x] Human-task boundaries are explicit where relevant
- [x] Verification intent is sufficient for downstream artifact generation
- [x] Domain MUST rules are preserved
- [x] No blocking design contradiction remains unresolved

### Suggested Next Step

`/speckit.solutionreview`
