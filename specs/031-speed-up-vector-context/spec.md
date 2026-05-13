# Feature Specification: Faster `read_code context` Retrieval

**Feature Branch**: `031-speed-up-vector-context`
**Created**: 2026-05-13
**Status**: Draft
**Input**: User description: "speed up read_code context vector search and preflight by splitting broad vs scoped query paths, reducing unnecessary vector freshness checks, and avoiding redundant markdown/code fallback work"

## One-Line Purpose *(mandatory)*

Developers receive faster `read_code context` results while preserving trustworthy code and markdown discovery.

## Consumer & Context *(mandatory)*

Codex agents and repo operators consume `read_code context` output during local command-line code discovery inside this repository workflow.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fast Scoped Context Reads (Priority: P1)

As an agent with a known file path, symbol, or tightly scoped query, I want `read_code context` to return the right seam quickly so exact follow-up work does not stall on broad freshness and discovery work.

**Why this priority**: Most repeated reads during implementation are scoped, and this path currently pays the highest avoidable latency cost.

**Independent Test**: Can be fully tested by running representative scoped `read_code context` commands against known files and verifying faster completion with unchanged selected seams and output contract.

**Acceptance Scenarios**:

1. **Given** a scoped query with a known target file, **When** `read_code context` resolves the request, **Then** it returns the same intended seam without paying unrelated broad-search costs.
2. **Given** a query shaped like an exact symbol or file-local anchor, **When** `read_code context` runs, **Then** it avoids unnecessary search scopes that do not affect the answer.
3. **Given** a healthy indexed state for the requested scope, **When** a scoped query runs repeatedly in the same working session, **Then** follow-up reads complete faster without losing result trust.

### User Story 2 - Efficient Broad Discovery (Priority: P2)

As an agent with only a broad natural-language question, I want `read_code context` to stay reliable while avoiding heavyweight freshness work unless the query outcome actually needs it.

**Why this priority**: Broad discovery still matters, but it happens less often than scoped lookups and can tolerate a more selective slow path.

**Independent Test**: Can be fully tested by running broad discovery prompts that do not specify a path or symbol and verifying that relevant seams still surface with bounded latency and bounded output.

**Acceptance Scenarios**:

1. **Given** a broad query with no known file path, **When** `read_code context` runs, **Then** it returns a relevant seam without regressing discovery quality.
2. **Given** a broad query that can be answered from trusted current index state, **When** `read_code context` runs, **Then** it avoids unnecessary blocking work before showing ranked results.
3. **Given** a broad query whose first-pass result is weak, empty, or ambiguous, **When** `read_code context` escalates, **Then** it uses a slower trust-recovery path instead of silently returning misleading output.

### User Story 3 - Clear Freshness Escalation (Priority: P3)

As a maintainer, I want freshness and fallback behavior to be predictable so I can understand when `read_code context` trusts cached state and when it performs slower recovery work.

**Why this priority**: Operational clarity prevents future latency regressions and makes it safer to simplify the current guard stack.

**Independent Test**: Can be fully tested by exercising healthy, stale, and ambiguous index states and verifying that each state follows a documented fast path or escalation path with observable outputs.

**Acceptance Scenarios**:

1. **Given** a request that can be served from trusted current state, **When** `read_code context` runs, **Then** it uses the fast path and does not trigger unnecessary refresh work.
2. **Given** a request whose trust state is unknown or stale, **When** `read_code context` runs, **Then** it performs the slower validation or recovery path before returning an answer that depends on that state.
3. **Given** a query that triggers fallback behavior, **When** the tool escalates, **Then** the user can distinguish a normal fast-path read from a recovery-path read.

### Edge Cases

- Broad queries that match both code and markdown content must still rank the correct seam without paying avoidable dual-scope costs for obviously code-only or markdown-only requests.
- If code and markdown both remain relevant for a broad query, the system must either perform both lookups efficiently or avoid delaying the answer with redundant sequential work.
- Scoped queries must not reuse trusted state after relevant local edits make that state unsafe.
- Empty, low-confidence, or conflicting result sets must escalate to a safer path instead of returning a fast but misleading answer.
- Repeated queries in the same session must not accumulate stale trust decisions after the repo state changes.

## Flowchart *(mandatory)*

```text
[User runs read_code context]
        |
        v
[Classify query as scoped or broad]
        |
        +--> [Scoped request]
        |         |
        |         v
        |   [Check scope-local trust]
        |         |
        |         +--> [Trusted] --> [Run fast retrieval path] --> [Return seam]
        |         |
        |         +--> [Unknown or stale] --> [Escalate validation/recovery] --> [Return seam]
        |
        +--> [Broad request]
                  |
                  v
[Check session-level trust]
                  |
                  +--> [Trusted] --> [Run broad retrieval path] --> [Return ranked seam]
                  |
                  +--> [Unknown, weak, or ambiguous] --> [Escalate validation/recovery] --> [Return ranked seam]
```

## Data & State Preconditions *(mandatory)*

- The repository has a local code discovery environment with code and markdown index data available to `read_code`.
- The command runs inside a working session that may already hold trust state about prior healthy reads.
- Repo state may be healthy, stale, partially refreshed, or newly edited between repeated reads.

## Inputs & Outputs *(mandatory)*

- **Inputs**:
  - A `read_code context` query that may be broad or scoped
  - Optional query scope such as file path, content type, or candidate stepping flags
  - Current local index trust state for code and markdown discovery
- **Outputs**:
  - Ranked context result selecting the intended seam
  - Stable compact output compatible with current downstream usage
  - Clear escalation behavior when the fast path cannot safely answer

## Constraints & Non-Goals *(mandatory)*

- The feature must preserve the existing user-facing role of `read_code context` as the semantic discovery path.
- The feature must not lower trust by silently serving known-stale results for requests that require validated freshness.
- The feature must not regress markdown discovery for genuine markdown-oriented queries.
- The feature must not require users to manually choose internal freshness strategies for ordinary reads.
- Non-goal: redesigning `read_code find` or `read_code analyze` into a new user-facing interface.
- Non-goal: replacing the repository's underlying vector or graph technologies as part of this feature.
- Non-goal: broad output-format redesign beyond what is required to make fast-path versus escalation behavior understandable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST distinguish between scoped `read_code context` requests and broad `read_code context` requests before selecting a trust and retrieval path.
- **FR-002**: The system MUST provide a fast path for scoped requests that avoids broad freshness work when scope-local trust is sufficient.
- **FR-003**: The system MUST provide a broad-query path that can use trusted current session state without forcing heavyweight validation before every request.
- **FR-004**: The system MUST escalate to a slower validation or recovery path when trust is unknown, stale, weak, empty, or ambiguous for the request being answered.
- **FR-005**: The system MUST avoid unnecessary code-versus-markdown retrieval work when the request shape or declared content type makes one scope irrelevant.
- **FR-006**: The system MUST make fallback behavior conditional rather than unconditional, so expensive recovery work only runs after a miss, weak result, stale trust state, or conflicting candidate set.
- **FR-007**: The system MUST define expected behavior for mixed code-and-markdown broad queries, including whether both scopes are consulted and how that work avoids unnecessary sequential latency.
- **FR-008**: The system MUST preserve current result correctness for representative scoped symbol lookups, broad discovery questions, and markdown-oriented reads.
- **FR-009**: The system MUST keep `read_code context` output compatible with current downstream consumers while making escalation behavior observable.
- **FR-010**: The system MUST ensure trusted session or scope state is invalidated when relevant local edits make that trust unsafe.

### Key Entities *(include if feature involves data)*

- **Query Scope**: Whether a request is broad or scoped, including any known file, symbol, or content-type constraints.
- **Trust State**: The current confidence that indexed data is fresh enough for a given request or session.
- **Escalation Path**: The slower validation or recovery route used when fast-path trust is insufficient.
- **Result Seam**: The selected code or markdown anchor returned to the caller.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Scoped `read_code context` queries complete materially faster than the current baseline while selecting the same intended seams on the benchmark set.
- **SC-002**: Broad `read_code context` discovery queries preserve relevant seam selection quality on the benchmark set without introducing false confidence on stale or ambiguous states.
- **SC-003**: Repeated healthy-session reads avoid repeated heavyweight validation work unless repo changes or ambiguous results require escalation.
- **SC-004**: Validation tests demonstrate that scoped lookups, broad discovery, and markdown discovery all retain expected behavior under healthy and stale conditions.

## Research Baseline *(supporting)*

- Current exact-symbol `read_code context` benchmark measured about `8.65s` end-to-end in-process for a healthy scoped query.
- Of that baseline, vector preflight accounted for about `5.75s`, while semantic query work accounted for about `2.90s`.
- The vector freshness path was dominated by the vector status probe at about `5.63s`, while the codegraph session check was effectively negligible at about `0.003s`.
- The scoped semantic query path spent about `1.32s` on the code search and about `1.30s` on the markdown search for an exact code symbol, with the markdown branch returning no results in that benchmark.
- Direct indexer subprocess timings on the same benchmark were about `6.39s` for `status`, `1.93s` for the scoped code query, and `2.07s` for the scoped markdown query.
- These numbers serve as the current baseline for plan and implementation prioritization and must be updated if later measurement shows materially different timings on the accepted benchmark corpus.

## Definition of Done *(mandatory)*

- The spec requirements cover scoped reads, broad discovery, and freshness escalation end to end.
- Clarification markers have been removed or resolved.
- The benchmark set for scoped, broad, and markdown-oriented queries is defined for validation.
- The feature can be planned without inventing additional user-visible requirements.
- Spec review confirms that the one-line purpose, consumer/context, user stories, and functional requirements all describe the same feature goal.

## Open Questions *(include if any unresolved decisions exist)*

- What exact benchmark set should serve as the acceptance corpus for scoped, broad, and markdown-oriented `read_code context` reads?
- What user-visible signal is sufficient to indicate escalation without cluttering normal fast-path output?
- For mixed broad queries where both code and markdown remain relevant, should both scopes run in parallel, or should one scope be preferred and the other only used as a fallback?
