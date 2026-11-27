# Feature Specification: Single-Dispatch Speckit Run

**Feature Branch**: `057-speckit-run-single-dispatch`
**Created**: 2026-11-23
**Status**: Draft
**Input**: User description: "Prevent duplicate Speckit workflow dispatch: make the Codex speckit-run entrypoint invoke the pipeline driver exactly once, remove its second command-doc execution path, and preserve a clear, deterministic bootstrap result for new feature descriptions."

## One-Line Purpose *(mandatory)*

Speckit users start each requested workflow exactly once and receive one deterministic result.

## Consumer & Context *(mandatory)*

Codex users invoke the `speckit-run` skill in a repository session to start either a new-feature bootstrap or an existing-feature workflow.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Start a new feature once (Priority: P1)

A user submits a new feature description through `speckit-run` and receives one specification scaffold and one result identifying that feature.

**Why this priority**: A duplicate bootstrap can create conflicting feature directories and makes the workflow unsafe to use.

**Independent Test**: Invoke the entrypoint with a new description and verify that its execution transcript contains one driver invocation, one Specify invocation, and one generated feature identity.

**Acceptance Scenarios**:

1. **Given** no existing feature identity, **When** a user starts `speckit-run` with a description, **Then** the entrypoint invokes the pipeline driver once and the driver bootstraps Specify once.
2. **Given** the bootstrap succeeds, **When** the result is returned, **Then** it includes the generated feature ID and identifies `specify` as the next phase.
3. **Given** the bootstrap succeeds, **When** the result is returned, **Then** no second command-document dispatch or duplicate specification scaffold is created.

### User Story 2 - Continue an existing feature once (Priority: P2)

A user starts `speckit-run` for an existing feature and the driver alone determines the allowed next work.

**Why this priority**: Existing feature flows need the same single-owner routing guarantee.

**Independent Test**: Invoke the entrypoint with an existing feature identity and verify that it issues one driver invocation and does not independently route a second phase.

**Acceptance Scenarios**:

1. **Given** an existing feature ID, **When** a user starts `speckit-run`, **Then** the entrypoint delegates once to the pipeline driver.
2. **Given** the driver returns a blocked, failed, or handoff result, **When** the entrypoint completes, **Then** that result is preserved without a second dispatch.

### User Story 3 - Understand routing ownership (Priority: P3)

A maintainer can identify the sole runtime routing owner and distinguish its contract from reference guidance.

**Why this priority**: Clear ownership prevents the same regression from being reintroduced.

**Independent Test**: Review the entrypoint and its adjacent documentation to confirm that the pipeline driver is the sole runtime dispatch path.

**Acceptance Scenarios**:

1. **Given** the skill instructions, **When** a maintainer reads them, **Then** they contain one runtime dispatch to the pipeline driver and no instruction to execute a command document afterward.

### Edge Cases

- The pipeline driver rejects or fails the bootstrap request.
- Specify returns an invalid or incomplete bootstrap result.
- An existing feature is blocked by an authoritative phase gate.

## Flowchart *(mandatory)*

```text
speckit-run request
        |
        v
pipeline_driver.py (one invocation)
        |
        +-- new description --> speckit_specify_step.py (one bootstrap) --> feature ID, next phase: specify
        |
        +-- existing feature --> resolve gates and route allowed phase
        |
        v
one result returned to user
```

## Data & State Preconditions *(mandatory)*

- A new description has no feature ID, spec directory, or feature ledger state before bootstrap.
- An existing feature is resolved from its explicit identity and ledger-authoritative state.
- The pipeline driver remains the owner of runtime routing and result assembly.

## Inputs & Outputs *(mandatory)*

- **Input**: a new-feature description or an existing feature identifier passed to `speckit-run`.
- **Output**: one canonical result from the pipeline driver, including bootstrap feature identity and next phase when applicable.
- **Observable evidence**: bounded execution transcript or targeted tests demonstrating one entrypoint dispatch and no duplicate scaffold.

## Constraints & Non-Goals *(mandatory)*

- Preserve the pipeline driver's existing bootstrap contract for description-only requests.
- Do not redesign Specify, the ledger state machine, or downstream phase execution.
- Do not add a second routing abstraction, retry policy, or automatic cleanup behavior.
- This feature does not implement the agent analytics view.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `speckit-run` Codex entrypoint MUST invoke `scripts/pipeline_driver.py` exactly once per user request.
- **FR-002**: The entrypoint MUST NOT instruct the agent to load and execute `.claude/commands/speckit.run.md` as a second runtime action after driver invocation.
- **FR-003**: A description-only driver request MUST bootstrap Specify once and return its canonical feature identity and `specify` next-phase result.
- **FR-004**: An existing-feature request MUST preserve the pipeline driver's result without an independent second phase dispatch.
- **FR-005**: Automated coverage MUST detect an entrypoint instruction that would create a second runtime dispatch.
- **FR-006**: The routing ownership and new-feature bootstrap path MUST be documented clearly enough for a maintainer to distinguish reference guidance from executable dispatch.

### Key Entities *(include if feature involves data)*

- **Speckit-run entrypoint**: Codex-facing skill instruction surface.
- **Pipeline driver**: sole runtime router and canonical result owner.
- **Specify bootstrap result**: generated feature identity plus next-phase state for a new description.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new-feature request produces exactly one driver invocation and exactly one Specify bootstrap invocation in automated verification.
- **SC-002**: An existing-feature request produces exactly one driver invocation and no secondary command-document dispatch in automated verification.
- **SC-003**: Successful new-feature bootstrap output contains one non-empty feature ID and `next_phase: "specify"`.

## Definition of Done *(mandatory)*

In production, a Speckit user can start a new or existing workflow through `speckit-run` and receive one deterministic driver-owned result without duplicate routing or duplicate scaffolds.

## Open Questions *(include if any unresolved decisions exist)*

None.
