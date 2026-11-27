# Feature Specification: Stable Semble MCP and Legacy Vector Removal

**Feature Branch**: `061-persistent-repo-research-backends`  
**Created**: 2026-11-27  
**Status**: Draft  
**Input**: User description: "Make the existing local Semble MCP reliable and consistently available in Codex sessions using Semble's standard MCP integration. Fix startup/configuration and approval behavior first. Then remove the duplicate legacy vector-search/read-code semantic discovery machinery that Semble supersedes. Do not add a separate daemon, HTTP service, warmed-reranker service, or duplicate index lifecycle."

## One-Line Purpose *(mandatory)*

Use the standard local Semble MCP as the reliable semantic-discovery path, then delete the obsolete vector-search machinery that duplicates it.

## Consumer & Context *(mandatory)*

Codex agents and SpecKit workflows need semantic repository discovery that is available immediately, does not repeatedly prompt for read-only searches, and does not depend on custom vector-index lifecycle code. Semble already provides the semantic-search capability through its local MCP integration; the foundation should configure and consume that capability cleanly rather than recreating its process, cache, index, embedding, or reranking lifecycle.

CodeGraph remains responsible for structural graph questions and LSP remains responsible for symbol-precise navigation. This feature does not replace either system.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Semble MCP Is Reliably Available (Priority: P1)

As a repository agent, I want the configured local Semble MCP to be available in every Codex session so semantic discovery works without ad hoc recovery or duplicate process management.

**Why this priority**: Semble is already the intended semantic-discovery system. Reliability of the existing MCP integration must be fixed before deleting the legacy fallback machinery.

**Independent Test**: Start fresh Codex sessions against the target repository and verify Semble registers successfully, searches execute through the MCP, and failures identify the actual startup/configuration cause.

**Acceptance Scenarios**:

1. **Given** a correctly configured repository session, **When** Codex starts, **Then** the Semble MCP launches and its expected read-only search tools are registered.
2. **Given** a healthy Semble MCP, **When** multiple searches execute in one session, **Then** they reuse the existing MCP process/index path rather than spawning one Semble process per search.
3. **Given** Semble fails to register or launch, **When** readiness is checked, **Then** the failure identifies the relevant configuration, executable/environment, working-directory, repository, or tool-registration cause.
4. **Given** the intended read-only approval policy, **When** Semble search tools execute, **Then** they do not generate unnecessary approval prompts.

---

### User Story 2 - Remove Duplicate Legacy Semantic Discovery (Priority: P2)

As a maintainer, I want the old vector-search/read-code semantic-discovery stack removed once Semble is stable so the foundation has one semantic index lifecycle instead of two.

**Why this priority**: The legacy path adds substantial initialization, health, refresh, persistence, embedding, reranking, and maintenance code for capability now provided by Semble.

**Independent Test**: Trace all semantic-discovery callers after the Semble MCP is stable, migrate remaining valid consumers, and verify normal discovery no longer initializes or queries the legacy vector backend.

**Acceptance Scenarios**:

1. **Given** a normal semantic-discovery request, **When** discovery runs, **Then** it uses Semble rather than the legacy vector/read-code semantic backend.
2. **Given** legacy vector indexing, embedding, reranking, persistence, refresh, or health code with no remaining demonstrated consumer, **When** cleanup completes, **Then** that code is removed.
3. **Given** existing strict-read and bounded-evidence guardrails, **When** the legacy vector backend is removed, **Then** those governance constraints remain intact.
4. **Given** CodeGraph and LSP consumers, **When** semantic cleanup completes, **Then** their structural and symbol-precision responsibilities remain unchanged.

### Edge Cases

- A fresh Codex session starts from a repository other than the expected target; Semble must operate against the actual configured repository rather than silently using stale state.
- Semble is configured but the executable or environment cannot be resolved; the failure must be explicit and bounded.
- The MCP launches but expected tools are not registered; this is reported as tool-registration failure rather than generic search failure.
- Multiple searches occur in one session; they must use the already-running MCP path rather than custom batching/process orchestration in the runner.
- A legacy read-code/vector caller remains after migration; it must be identified explicitly rather than kept as an undocumented fallback.

## Flowchart *(mandatory)*

```text
Codex / SpecKit discovery request
        |
        v
Semble MCP available?
        |
        +-- no --> report concrete startup/config/tool-registration failure
        |
        v
Semble semantic search
        |
        v
bounded discovery evidence
        |
        +--> LSP when symbol precision is needed
        |
        +--> CodeGraph when structural dependency/impact analysis is needed
```

After Semble stability is verified:

```text
legacy semantic/vector caller
        |
        +-- still required --> migrate to Semble or document demonstrated exception
        |
        +-- no consumer ----> remove vector/index/embed/rerank lifecycle code
```

## Data & State Preconditions *(mandatory)*

- `FOUNDATION_ROOT` remains distinct from the repository being researched.
- The Semble MCP is configured through the normal Codex MCP configuration for the target repository.
- The Semble process owns its own supported cache/index behavior; the runner does not recreate that lifecycle.
- Read-only Semble tool approval policy is configured intentionally and separately from process-start or sandbox permissions.
- Existing CodeGraph and LSP integrations remain available for their current responsibilities.

## Inputs & Outputs *(mandatory)*

**Inputs**:

- Target repository/workspace.
- Existing Semble MCP configuration.
- A semantic discovery query.
- Codex MCP startup, environment, working-directory, and approval configuration.

**Outputs**:

- A bounded Semble discovery result.
- A bounded readiness/failure result when the MCP is unavailable.
- Post-migration inventory showing which legacy vector/read-code semantic components were removed or retained with an explicit consumer.

## Constraints & Non-Goals *(mandatory)*

**Constraints**:

- Use Semble's standard local MCP integration.
- The runner MUST NOT add its own Semble process pool, daemon manager, HTTP service, batching service, or index lifecycle.
- Semantic discovery MUST have one system of record after cleanup: Semble.
- Strict-read governance and bounded evidence MUST survive removal of the legacy vector backend.
- CodeGraph structural analysis and LSP symbol analysis remain separate concerns.

**Non-goals**:

- Building a separate Semble daemon or HTTP service.
- Creating a persistent warmed read-code/reranker service.
- Preserving the legacy vector backend merely as a fallback.
- Reimplementing Semble caching, indexing, embeddings, reranking, or refresh behavior in the foundation runner.
- Combining Semble, CodeGraph, and LSP into one service.
- Changing CodeGraph or LSP behavior as part of this feature.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST use the configured local Semble MCP as the normal semantic repository-discovery path.
- **FR-002**: A fresh Codex session MUST expose the expected Semble read-only search tools when configuration and environment are valid.
- **FR-003**: Multiple Semble searches in one session MUST use the existing MCP process path and MUST NOT intentionally spawn one Semble process per query.
- **FR-004**: Semble startup/readiness diagnostics MUST distinguish at minimum configuration, executable/environment resolution, working directory/repository, process startup, and tool-registration failures.
- **FR-005**: Read-only Semble searches MUST execute without repetitive approval prompts when the configured policy permits them.
- **FR-006**: The foundation MUST NOT introduce a separate Semble daemon, HTTP service, process pool, custom batching service, or duplicate index/cache lifecycle.
- **FR-007**: After Semble stability is verified, all callers of legacy semantic vector discovery MUST be inventoried and classified as migrated, explicitly retained for a demonstrated non-Semble requirement, or removed.
- **FR-008**: Normal semantic discovery MUST no longer initialize or query the legacy vector/read-code semantic backend after migration.
- **FR-009**: Legacy vector indexing, embedding, reranking, persistence, refresh, startup, and health machinery with no demonstrated remaining consumer MUST be removed.
- **FR-010**: Strict-read governance, bounded evidence, and repository-scope protections MUST remain enforced after legacy vector removal.
- **FR-011**: CodeGraph MUST remain the structural dependency/impact path and LSP MUST remain the symbol-precision path; this feature MUST NOT duplicate those responsibilities.
- **FR-012**: Existing retrieval specs 025, 027, 031, and 035 MUST be reconciled against the post-Semble architecture, and obsolete vector-backend requirements MUST NOT be implemented solely to complete historical checkboxes.
- **FR-013**: Tests and operator documentation MUST identify Semble as the semantic-discovery system of record after migration.
- **FR-014**: Feature 059 MUST no longer delegate warmed-reranker or persistent read-code backend ownership to feature 061; those requirements are obsolete under this architecture.

### Key Entities *(include if feature involves data)*

- **Semble MCP readiness**: Whether the configured local MCP process launched and registered the expected read-only search tools for the active repository session.
- **Semantic discovery request**: A repository search request handled by Semble.
- **Legacy vector component**: Any foundation-owned indexing, embedding, reranking, persistence, refresh, health, or semantic-query component that duplicates Semble discovery.
- **Retained retrieval guardrail**: Strict-read, bounded-evidence, repository-scope, or other governance behavior that remains valuable independently of the removed vector backend.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Fresh-session verification succeeds repeatedly with Semble tools registered and usable without manual recovery.
- **SC-002**: Five searches in one healthy session execute through the existing Semble MCP path with no intentional per-query Semble process startup.
- **SC-003**: Read-only Semble searches execute without unexpected approval prompts under the intended configured policy.
- **SC-004**: Every tested MCP startup failure is reported as a concrete configuration/environment/working-directory/process/tool-registration category rather than a generic unavailable state.
- **SC-005**: Normal post-migration semantic discovery executes without initializing the legacy vector index or reranker.
- **SC-006**: Every legacy vector/index/embed/rerank lifecycle component remaining after cleanup has a documented active consumer; components without one are removed.
- **SC-007**: Strict-read and bounded-evidence regression tests continue to pass.
- **SC-008**: CodeGraph and LSP regression checks continue to pass without being absorbed into the Semble lifecycle.
- **SC-009**: Feature 059 and related documentation no longer describe feature 061 as the owner of a persistent warmed-reranker/read-code backend.

## Definition of Done *(mandatory)*

This feature is shipped when the standard local Semble MCP is consistently available and correctly approved in fresh Codex sessions, repeated searches reuse that MCP path without custom lifecycle machinery, the obsolete legacy vector/read-code semantic-discovery stack has been removed wherever it lacks a demonstrated consumer, retrieval guardrails remain intact, and documentation/spec ownership reflects Semble as the semantic-discovery system of record.

## Open Questions *(include if any unresolved decisions exist)*

None. This feature deliberately uses the existing Semble MCP integration and removes duplicate semantic-search infrastructure rather than introducing a new process architecture.
