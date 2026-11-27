# Feature Specification: Persistent Repo-Scoped Research Backends

**Feature Branch**: `061-persistent-repo-research-backends`
**Created**: 2026-11-27
**Status**: Draft
**Input**: User description: "Keep one warm, repo-scoped Semble MCP process and one separate warm read-code backend for each Codex/workflow session; derive both from TARGET_REPO; preserve narrow per-request authority; expose startup identity, readiness, and bounded failure reasons; use native MCP tools normally and bounded CLI fallback only when health checks fail; prevent repeated reranker initialization; verify stable process identity and live parallel reuse; and move warmed-reranker ownership out of feature 059."

## One-Line Purpose *(mandatory)*

Repository researchers reuse ready, repo-scoped research capabilities throughout a workflow session so repeated discovery remains fast, safe, and observable.

## Consumer & Context *(mandatory)*

Codex agents and SpecKit workflows consume Semble and read-code research capabilities across multiple turns and overlapping requests while working in one target repository. Operators also need to distinguish an approved tool call from a server that failed to start because of environment, sandbox, repository, cache, or backend initialization conditions.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reuse Warm Research Services (Priority: P1)

As a repository agent, I want repeated Semble and read-code requests to reuse their respective ready services so discovery does not repeatedly pay process, index, or model startup costs.

**Why this priority**: Repeated cold starts are the observed failure and make the normal research workflow slow and unreliable.

**Independent Test**: Start one repo-session, issue repeated Semble and read-code requests across at least two turns, and verify stable process/start identities and exactly one read-code vector-index and reranker initialization.

**Acceptance Scenarios**:

1. **Given** a healthy repo-session runtime, **When** an agent performs multiple Semble searches, **Then** every request reaches the same Semble process without another `uv`, Python, or Semble startup.
2. **Given** a healthy repo-session runtime, **When** an agent performs multiple semantic read-code requests, **Then** every request reuses the same read-code process, vector index, and reranker.
3. **Given** five overlapping valid requests for one repo-session, **When** they execute, **Then** they share the appropriate warm service without duplicate startup, state corruption, or repository mixing.

---

### User Story 2 - Diagnose Availability Correctly (Priority: P2)

As an operator, I want startup and health evidence for each service so a missing MCP tool is not silently misreported as an unavailable research capability or blamed on tool approval.

**Why this priority**: Tool-level automatic approval and process startup authority are different controls and require different remediation.

**Independent Test**: Exercise each defined startup and readiness failure and verify that health output identifies the process, repository, cache/index state, tool availability, and one bounded failure category.

**Acceptance Scenarios**:

1. **Given** Semble `search` and `find_related` are auto-approved, **When** Semble startup is blocked by sandbox or environment authority, **Then** health reports the startup failure without prompting for approval of the tool call itself.
2. **Given** an MCP process is absent, **When** the agent checks health, **Then** the result distinguishes process absence from cache, index, tool-registration, backend, and model failures.
3. **Given** a runtime recovers by replacement, **When** the replacement becomes ready, **Then** health exposes the changed process/start identity and the reason for replacement.

---

### User Story 3 - Fall Back Without Hidden Heavyweight Work (Priority: P3)

As a repository agent, I want a bounded fallback only after native health fails so research can continue without silently loading a heavyweight reranker in each CLI process.

**Why this priority**: Fallback is useful for recovery, but it must not recreate the repeated cold-start behavior this feature removes.

**Independent Test**: Make each native service unhealthy, invoke its supported fallback, and verify bounded output, explicit fallback selection, and zero heavyweight model or reranker initialization in the fallback process.

**Acceptance Scenarios**:

1. **Given** a healthy native MCP service, **When** discovery is requested, **Then** the native tool is used and CLI fallback is not started.
2. **Given** a failed native health check, **When** supported fallback is used, **Then** it returns bounded results and failure context without loading the read-code reranker.
3. **Given** an invalid repository or out-of-scope request, **When** either native or fallback research is attempted, **Then** the request is rejected before repository work begins.

### Edge Cases

- Two sessions target the same repository at the same time; each session retains an independent runtime identity and does not borrow authority from the other.
- One session changes target repositories; the old runtimes become eligible for shutdown and are never reused for the new target.
- A process exists but its cache or index is not ready; health reports not-ready rather than treating process existence as readiness.
- One of the two research services is healthy while the other fails; their separate failure boundaries preserve the healthy service.
- Concurrent requests race with first startup; only one process per service wins for the repo-session and all valid requests converge on it.
- A runtime fails after successful use; replacement follows the same startup validation and visibly changes runtime identity.

## Flowchart *(mandatory)*

```text
Codex / SpecKit request
        |
        v
resolve TARGET_REPO + session identity
        |
        v
validate request scope and authority
        |
        +-- invalid ----------------------> reject with bounded reason
        |
        v
check service-specific runtime health
        |
        +-- ready ------------------------> native Semble or read-code MCP
        |
        +-- unhealthy / absent ----------> bounded CLI fallback if supported
                                                |
                                                +-- no hidden heavyweight load
```

Semble and read-code follow this flow through separate processes and tool interfaces. They share only the repo-session identity and health vocabulary.

## Data & State Preconditions *(mandatory)*

- `FOUNDATION_ROOT` identifies the foundation installation and remains distinct from the repository being researched.
- `TARGET_REPO` resolves to an authorized repository root before either service starts.
- Each service cache or index path resolves inside `TARGET_REPO/.codegraphcontext/` and is writable only where that service requires state.
- The owning Codex/workflow session provides a stable session identity for the runtime reuse boundary.
- Semble tool policy keeps `search` and `find_related` auto-approved independently of startup and sandbox authority.
- A repo-session ends when its owning Codex/workflow session ends or changes target repository; its runtimes are then eligible for shutdown.

## Inputs & Outputs *(mandatory)*

**Inputs**:

- Target repository root and active session identity.
- A validated Semble `search` or `find_related` request, or a validated read-code request.
- Service-specific cache/index configuration derived from the target repository.
- Startup, filesystem, network, and tool-approval policy.

**Outputs**:

- A bounded native-tool result or an explicitly identified bounded fallback result.
- Runtime identity containing service kind, process identifier, process start identity, target repository, and session identity.
- Health containing cache/index readiness, required tool availability, backend/model readiness where applicable, and the current or most recent bounded failure.

## Constraints & Non-Goals *(mandatory)*

**Constraints**:

- Semble and read-code remain separate processes, public APIs, and failure boundaries.
- Persistence reuses process state but never broadens trust; every request is independently validated.
- A runtime may read only its declared target repository and write only its declared repo-local cache/index locations.
- Arbitrary shell execution and arbitrary repository-file writes are not exposed through either research API.
- Network access is disabled unless a service declares and verifies a concrete requirement for it.
- Health returns only current state and the most recent failure summary, capped at 4 KiB and retained no longer than the active session.
- A failed runtime may be replaced only through the normal validated startup path; replacement identity and reason must be observable.

**Non-goals**:

- Combining Semble and read-code into one privileged process.
- Treating a warm process as permanently trusted.
- Replacing Semble search semantics, read-code ranking semantics, custom specification templates, or SpecKit workflow steps.
- Making CLI invocation the normal research path.
- Preserving stable process identity across an explicitly reported unhealthy-runtime replacement.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST reuse one ready Semble MCP process for each unique target-repository and active-session pair instead of starting a new process for ordinary requests.
- **FR-002**: The system MUST reuse one separate ready read-code service, including its vector index and reranker, for each unique target-repository and active-session pair instead of repeatedly loading model weights.
- **FR-003**: Semble and read-code MUST remain separate processes with separate public tool interfaces and failure boundaries while using one shared repo-session identity and health vocabulary.
- **FR-004**: Both services MUST expose process identifier, process start identity, target repository, session identity, cache/index readiness, required tool availability, backend/model readiness where applicable, and a bounded failure reason.
- **FR-005**: Every request MUST be routed only to the runtime associated with its declared target repository and active session and MUST be validated independently before execution.
- **FR-006**: Runtime working directories and cache/index locations MUST derive from `TARGET_REPO` while preserving the distinction between `FOUNDATION_ROOT` and the repository being researched.
- **FR-007**: Each runtime MUST be limited to reading its target repository and writing its declared repo-local cache/index paths; it MUST NOT expose arbitrary shell execution or arbitrary repository-file writes.
- **FR-008**: Runtime network access MUST be disabled unless the service declares and verifies a concrete network requirement.
- **FR-009**: Tool-level automatic approval, MCP process-start authority, and sandbox filesystem authority MUST remain distinct; granting one MUST NOT grant either of the others.
- **FR-010**: Semble `search` and `find_related` requests MUST remain auto-approved without repetitive tool-level prompts when the registered tools are available.
- **FR-011**: One ready runtime MUST safely serve at least five overlapping valid same-repository requests without duplicate service creation, repository-state leakage, shared-state corruption, or model reinitialization.
- **FR-012**: Native MCP tools MUST be the normal research path whenever their runtime reports ready and available.
- **FR-013**: Supported CLI fallbacks MUST run only after native health failure and MUST return bounded results and failure information without silently starting a heavyweight model or reranker.
- **FR-014**: Startup and runtime failures MUST distinguish process absence, permission/authorization, sandbox, environment resolution, working directory, repository identity, cache/index initialization, tool registration, backend initialization, model initialization, and request validation.
- **FR-015**: A repo-session runtime MUST become eligible for shutdown when its owning Codex/workflow session ends or changes target repository.
- **FR-016**: An unhealthy runtime MAY be replaced only through the same validated startup path, and health MUST expose the new identity and replacement reason.
- **FR-017**: Health MUST retain only current state and the most recent failure summary, cap that summary at 4 KiB, and discard it no later than session shutdown.
- **FR-018**: Live-backend verification MUST demonstrate stable process/start identities across multiple turns and requests, one read-code vector-index and reranker initialization per healthy repo-session runtime, safe five-way parallel reuse, observable failure categories, and no hidden fallback model load.
- **FR-019**: Existing custom specification templates and workflow steps MUST continue to operate without requiring consumers to adopt a replacement workflow.
- **FR-020**: Feature 059 MUST no longer claim ownership of warm read-code reranker reuse; this feature MUST be the single specification owner for that behavior.

### Key Entities *(include if feature involves data)*

- **Repo-session identity**: The target repository and active workflow session pair that defines one service reuse boundary.
- **Service runtime identity**: The service kind, process identifier, process start identity, repository, and session that distinguish one live runtime from replacements or other sessions.
- **Runtime health**: Current readiness of the process, cache/index, required tools, backend, and model, plus at most one bounded failure summary.
- **Research request**: One independently validated operation bound to a repo-session and routed to a native service or explicit fallback.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Repeated Semble requests across at least two turns retain the same process and start identities with no additional `uv`, Python, or Semble startup.
- **SC-002**: Repeated read-code requests across at least two turns retain the same process and start identities and record exactly one vector-index and reranker initialization for the healthy repo-session runtime.
- **SC-003**: Five overlapping valid requests complete through the appropriate same-session service without duplicate runtime creation, repository leakage, state corruption, or extra model initialization.
- **SC-004**: Every failure category in FR-014 is identifiable from a health response whose failure summary is no larger than 4 KiB.
- **SC-005**: Every supported CLI fallback verification completes without starting or loading the read-code reranker or another heavyweight model.
- **SC-006**: Mismatched repositories, invalid session associations, and access outside permitted repository/cache scope are rejected before research begins in 100% of verification cases.
- **SC-007**: Semble `search` and `find_related` execute without tool-level approval prompts when auto-approval is configured, while startup authority failures remain separately observable.
- **SC-008**: Existing custom-template and workflow-step regression checks pass unchanged, and feature 059 contains no warmed-reranker ownership requirement.

## Definition of Done *(mandatory)*

This feature is shipped when production workflows reuse healthy, isolated Semble and read-code runtimes throughout each repo-scoped session; five-way concurrent live verification proves stable warm reuse; operators can diagnose bounded startup and readiness failures; fallbacks never hide heavyweight model loading; and feature 059 no longer owns reranker persistence.

## Open Questions *(include if any unresolved decisions exist)*

None. Session lifetime, recovery visibility, minimum concurrency, and bounded health retention are specified above as explicit feature constraints.
