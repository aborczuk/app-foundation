# Feature Specification: Deterministic Pipeline Driver with LLM Handoff

**Feature Branch**: `019-token-efficiency-docs`
**Created**: 2026-04-09
**Status**: Draft
**Input**: User description: "Introduce a deterministic pipeline driver that executes scripted gates/steps directly, invokes LLM only for generative phases, and enforces low-token response parsing defaults."

## One-Line Purpose *(mandatory)*

A build operator runs one deterministic pipeline driver command that advances speckit phases automatically and invokes the LLM only when generation work is required.

## Consumer & Context *(mandatory)*

Speckit operators and automation jobs consume this capability from local CLI execution in the repository root during normal spec-to-implementation workflows.

## Clarifications

### Session 2026-04-09

- Q: What reconciliation precedence applies if ledger and artifacts disagree? → A: Ledger is authoritative; mismatch returns `state_drift_detected` and blocks until a reconcile step completes.
- Q: What feature-level lock mechanism should orchestration use? → A: File lock at `.speckit/locks/<feature_id>.lock` with stale-lock timeout and owner metadata.
- Q: Should default script responses be compact or full JSON? → A: Full structured JSON by default for code consumers; raw heavy debug dumps remain opt-in (`--verbose`) and exit code `2` triggers one mandatory verbose rerun.
- Q: Should orchestrator state be persisted separately or derived each run? → A: Ledger is the sole authoritative state source for phase progression; artifact reads are validation checks only.
- Q: How should legacy migration toggles be controlled? → A: Per-phase manifest flags (`driver_managed`) for incremental rollout and rollback.
- Q: How should timeout policy be configured? → A: Manifest-driven per-phase-type timeouts with repo defaults fallback.
- Q: How should partial mutation before event emission be handled? → A: Block with deterministic failure (`partial_mutation_detected`) and require explicit reconcile; no automatic rollback.
- Q: Which steps require mandatory human approval? → A: Only irreversible/security-sensitive operations (schema/auth/destructive/external write side effects).
- Q: What should the default human-facing step output look like? → A: Exactly three status lines (`Done`, `Next`, `Blocked`) emitted verbatim; deep diagnostics are retrieved only on explicit follow-up.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deterministic Step Routing (Priority: P1)

An operator invokes one pipeline driver command with a feature context, and the driver evaluates current ledger/artifact state, executes deterministic scripts for the current step, and returns the next actionable state without requiring prompt-level interpretation of phase rules.

**Why this priority**: This removes the highest-frequency source of token waste and workflow drift by replacing repeated instruction re-reading with deterministic state transitions.

**Independent Test**: Can be fully tested by running the driver against a feature fixture where deterministic gates pass/fail in known combinations and verifying that the returned next-step state is correct.

**Acceptance Scenarios**:

1. **Given** a feature state where the next step is deterministic and all gate inputs are present, **When** the operator runs the driver, **Then** the driver executes the mapped script, records the result, and returns the next pipeline state.
2. **Given** a feature state where a deterministic gate fails, **When** the operator runs the driver, **Then** the driver returns a blocked state with gate identity and reason codes without requiring the LLM to inspect full logs.
3. **Given** a feature state that requires generative output (for example spec/plan/task synthesis), **When** the operator runs the driver, **Then** the driver returns an explicit LLM handoff contract containing step name and minimal required inputs.

---

### User Story 2 - Compact Parsing Contract (Priority: P2)

The pipeline scripts return a compact, uniform response contract so normal success paths do not emit large payloads and orchestration only parses failure-routing fields when needed.

**Why this priority**: The biggest avoidable token burn is reading full JSON/log output on successful paths where only pass/fail matters.

**Independent Test**: Can be fully tested by invoking representative scripts in success, business-failure, and runtime-failure modes and verifying exit-code-first behavior plus compact payload schema.

**Acceptance Scenarios**:

1. **Given** a script invocation that succeeds, **When** the driver executes it, **Then** the driver advances without reading large detail payloads.
2. **Given** a script invocation that returns business gate failure, **When** the driver executes it, **Then** it parses gate + reason codes and routes remediation deterministically.
3. **Given** a script invocation that returns runtime/contract failure, **When** the driver executes it, **Then** it returns a tooling error state distinct from business gate failure.
4. **Given** a step completes or blocks, **When** status is surfaced to the human, **Then** the interface emits only `Done`, `Next`, and `Blocked` lines, with no additional summary/paraphrase.

---

### User Story 3 - Governance and Migration Safety (Priority: P3)

A maintainer can migrate existing command docs and scripts to the driver model incrementally while preserving ledger integrity, existing artifacts, and branch-safe rollout.

**Why this priority**: Adoption must be low risk and reversible to avoid disrupting active feature branches.

**Independent Test**: Can be fully tested by enabling the driver for a subset of phases and confirming no regression in ledger event sequencing or artifact expectations.

**Acceptance Scenarios**:

1. **Given** a phase migrated to driver control, **When** the phase completes, **Then** required pipeline/task ledger events remain valid and in allowed order.
2. **Given** a phase not yet migrated, **When** the driver is used, **Then** it routes to existing command behavior without changing observable outputs.
3. **Given** a manifest/ledger contract change, **When** governance validation runs, **Then** it fails unless command-manifest version and sync metadata are updated.

### Edge Cases

- What happens when the driver receives an unknown phase/state not mapped in the transition matrix?
- How does the driver handle conflicting ledger state (for example duplicate terminal events)?
- What happens when a script exits `0` but emits malformed JSON in verbose mode?
- How does the system behave when a required script path in command-manifest is missing at runtime?
- What happens when a partial migration enables driver control for one phase while adjacent phases still use legacy command routing?
- What happens when two orchestrator invocations for the same feature run concurrently?
- What happens when ledger and filesystem artifacts disagree on phase completion?
- How does the driver prevent duplicate event emission on retry after partial failure?

## Flowchart *(mandatory)*

```mermaid
flowchart TD
    A[Operator runs pipeline driver] --> B[Load manifest, ledger state, and feature context]
    B --> C{Mapped deterministic step?}
    C -- Yes --> D[Execute mapped script]
    D --> E{Exit code}
    E -- 0 --> F[Advance state and return next step]
    E -- 1 --> G[Return blocked state with gate and reason codes]
    E -- 2 --> H[Return tooling error state]
    C -- No --> I{Generative phase required?}
    I -- Yes --> J[Return LLM handoff contract with minimal inputs]
    I -- No --> K[Return unknown-state error for maintainer action]
    F --> L[Append required ledger events]
    G --> L
    J --> L
```

## Data & State Preconditions *(mandatory)*

- The feature directory exists with canonical artifact paths (`spec.md`, optional phase artifacts, and checklist directory).
- Pipeline and task ledgers are readable and contain valid JSONL entries up to the current transition point.
- Command manifest files exist and pass mirror consistency validation.
- Deterministic scripts referenced by the command manifest are present in the repository.

## Inputs & Outputs *(mandatory)*

| Direction | Description | Format |
| :-- | :-- | :-- |
| Input | Driver invocation context including feature identifier, current phase intent, and repository state | Caller-defined |
| Output | Compact orchestration result describing next state, blocking reason codes, or LLM handoff payload | Caller-defined |

## Constraints & Non-Goals *(mandatory)*

**Must NOT**:
- Must NOT remove LLM-generated deliverables from spec/plan/tasking phases.
- Must NOT bypass existing ledger transition rules or required event contracts.
- Must NOT parse or emit verbose script payloads on success paths by default.
- Must NOT introduce branch-destructive automation (forced resets, implicit rebases, or unapproved merges).

**Adopted dependencies**:
- Existing speckit deterministic gate scripts (`speckit_gate_status.py`, `speckit_spec_gate.py`, `speckit_plan_gate.py`, `speckit_tasks_gate.py`, `speckit_implement_gate.py`) for phase checks.
- Existing ledger tooling (`pipeline_ledger.py`, `task_ledger.py`) for authoritative event validation and append operations.
- Command manifest governance files (`command-manifest.yaml`, `command-manifest.yaml`) as script/event mapping source of truth.

**Out of scope**:
- Replacing narrative quality of LLM-generated specs/plans with template-only automation.
- Rewriting all existing command documents in one migration step.
- Introducing external orchestrators or hosted workflow engines for this driver.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST invoke a single deterministic driver command that resolves current phase state and dispatches mapped deterministic scripts without requiring prompt-level workflow interpretation.
- **FR-002**: System MUST treat script exit codes with standardized semantics (`0` success, `1` business/gate failure, `2` runtime/contract failure) for orchestration routing.
- **FR-003**: System MUST parse deterministic top-level routing fields (`ok`, `gate`, `reasons`, `error_code`, `schema_version`) and use exit-code-first control flow for orchestration.
- **FR-004**: System MUST return an explicit LLM handoff contract when the next step requires generative work, including step identifier and minimal required input paths.
- **FR-005**: System MUST preserve existing ledger invariants by validating and emitting required pipeline/task events through existing ledger tooling.
- **FR-006**: System MUST source command-to-script routing from command-manifest and fail deterministically when mappings are missing or target scripts do not exist.
- **FR-007**: System MUST support incremental migration mode where migrated phases use driver routing and non-migrated phases continue legacy command flow.
- **FR-008**: System MUST return full structured JSON diagnostics by default for machine consumers, while keeping raw heavy debug dumps opt-in via `--verbose`.
- **FR-009**: System MUST enforce manifest governance such that ledger contract changes require command-manifest update plus manifest version/timestamp update in the same change set.
- **FR-010**: System MUST expose deterministic blocked-state reason codes compatible with `docs/governance/gate-reason-codes.yaml` remediation routing.
- **FR-011**: System MUST define deterministic precedence rules for state reconciliation when ledger events and artifact presence conflict.
- **FR-012**: System MUST require deterministic post-LLM artifact validation before emitting success events to pipeline/task ledgers.
- **FR-013**: System MUST make orchestration retries idempotent so repeated invocation does not duplicate terminal events or corrupt phase progression.
- **FR-014**: System MUST enforce one active orchestrator execution per feature context using a lock or equivalent concurrency guard.
- **FR-015**: System MUST execute only command-manifest allowlisted scripts for deterministic steps and reject unmapped execution requests.
- **FR-016**: System MUST define one canonical response schema used by all orchestrator/gate scripts, with stable routing fields and backward-compatible schema-version handling.
- **FR-017**: System MUST version orchestration and gate payload schemas with an explicit `schema_version` field and fail deterministically on unsupported versions.
- **FR-018**: System MUST enforce per-step timeout and cancellation behavior with deterministic blocked-state routing when execution exceeds configured limits.
- **FR-019**: System MUST define deterministic compensation/recovery behavior for partial-success states (for example artifact written but success event not emitted).
- **FR-020**: System MUST propagate a run-scoped correlation identifier across orchestrator outputs and ledger emissions for end-to-end traceability.
- **FR-021**: System MUST support a dry-run mode that resolves and reports planned step execution without mutating artifacts or ledgers.
- **FR-022**: System MUST support explicit human-approval breakpoints for configured steps before final success-event emission.
- **FR-023**: System MUST trigger one deterministic verbose rerun for `exit_code=2` failures before returning final blocked diagnostics.
- **FR-024**: System MUST emit a strict human-facing status envelope of at most three lines (`Done:`, `Next:`, `Blocked:`) for each orchestrator step result.
- **FR-025**: System MUST keep default stdout free of large diagnostic payloads and write full structured diagnostics to deterministic sidecar files for follow-up inspection.
- **FR-026**: System MUST provide a deterministic issue drill-down interface that, on explicit user request, reads sidecar diagnostics and returns standardized root-cause fields (`gate`, `reasons`, `error_code`, `failed_step`, `debug_path`).

### Key Entities *(include if feature involves data)*

- **Pipeline Driver State**: Resolved orchestration state for a feature, including current phase, next action type (deterministic vs LLM), and block status.
- **Step Mapping**: Manifest-defined relation between pipeline command/phase and executable deterministic scripts.
- **Handoff Contract**: Compact payload returned to the LLM layer when generation is required (step, required inputs, and constraints).
- **Gate Outcome**: Structured result of deterministic script execution containing exit classification and reason codes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For deterministic-only transitions, median orchestration token usage decreases by at least 50% versus current command-doc-driven execution path.
- **SC-002**: At least 95% of deterministic step executions complete without requiring a verbose rerun.
- **SC-003**: Pipeline/task ledger validation passes with zero new ordering/schema regressions across migrated phases.
- **SC-004**: At least one end-to-end feature flow runs in mixed migration mode (driver + legacy phases) with identical observable artifacts and gate decisions.
- **SC-005**: In normal operation, each orchestrator step response shown to the human uses only the `Done/Next/Blocked` line contract, while full diagnostics remain accessible via explicit drill-down.

## Definition of Done *(mandatory)*

In production development workflow, operators can run one deterministic pipeline driver that advances deterministic phases automatically, routes failures by reason code, and invokes the LLM only for required generation handoffs while preserving all ledger and governance guarantees.

## Open Questions *(include if any unresolved decisions exist)*

None at this time.
