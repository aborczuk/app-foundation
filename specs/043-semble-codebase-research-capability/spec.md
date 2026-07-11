Feature Specification: Semble Codebase Research Capability

Feature Branch: 043-semble-codebase-research-capability
Created: 2026-07-11
Status: Draft
Input: User description: “Install Semble as a repo-level codebase research capability for agents so codebase investigation uses Semble MCP search/find-related before bounded local reads and existing CodeGraph structural analysis. Semble should be treated as an installed capability for proper codebase research, with dump-control, candidate anchoring, and fallbacks documented.”

One-Line Purpose (mandatory)

Coding agents use focused codebase research to locate and verify relevant implementation evidence without consuming excessive repository context.

Consumer & Context (mandatory)

Repository-aware coding agents consume the research results while investigating, planning, reviewing, or modifying code in a checked-out repository.

User Scenarios & Testing (mandatory)

User Story 1 - Discover Relevant Code with Semble (Priority: P1)

A coding agent investigating a repository uses Semble semantic search as its first code-discovery step and receives a focused set of relevant code candidates before reading files.

Why this priority: This establishes the primary research path and prevents broad grep or file-reading operations from becoming the default discovery mechanism.

Independent Test: Can be fully tested by giving an agent a behavior-oriented question whose wording differs from repository symbols and verifying that Semble identifies relevant code locations before any local file read occurs.

Acceptance Scenarios:

1. Given Semble is available and the repository is accessible, When an agent begins a codebase investigation without a known file or symbol, Then it uses Semble search before local content search, directory traversal, or file reads.
2. Given Semble returns relevant candidates, When the agent evaluates the results, Then it records candidate file paths, symbols, line locations, and relevance before selecting bounded evidence to inspect.
3. Given a Semble response contains more candidates or content than needed, When the agent processes the response, Then it retains only the highest-value candidates required to continue the investigation.

⸻

User Story 2 - Expand Research from Anchored Candidates (Priority: P2)

A coding agent starts from a Semble result or known code location and uses related-code discovery plus bounded local reads to verify the behavior surrounding that anchor.

Why this priority: Search results are only hypotheses until the agent confirms them against exact code and nearby context.

Independent Test: Can be fully tested by supplying a known file and line anchor and verifying that the agent uses related-code discovery, reads only a bounded region, and cites exact repository evidence in its conclusion.

Acceptance Scenarios:

1. Given a relevant file and line location has been identified, When the agent needs connected implementation evidence, Then it uses Semble find-related from that anchor before conducting another broad repository search.
2. Given a candidate requires verification, When the agent reads repository content, Then it reads only the candidate’s relevant symbol or a bounded line range rather than the entire file by default.
3. Given the bounded read does not contain enough context, When the agent expands the read, Then it expands incrementally around the same anchor and records why additional context is required.
4. Given sufficient evidence has been collected, When the agent reports its findings, Then it identifies the exact files, symbols, or line ranges supporting the conclusion.

⸻

User Story 3 - Add Structural Analysis with CodeGraph (Priority: P3)

A coding agent uses the existing CodeGraph capability when the investigation requires structural relationships that semantic similarity and local context cannot establish.

Why this priority: Semantic retrieval identifies likely code, while structural analysis verifies relationships such as callers, dependencies, ownership boundaries, and impact paths.

Independent Test: Can be fully tested by asking an impact or call-chain question and verifying that the agent first establishes semantic anchors, then uses CodeGraph to trace the required structural relationships.

Acceptance Scenarios:

1. Given the investigation asks about callers, callees, dependency direction, inheritance, hierarchy, ownership, or change impact, When semantic candidates have been established, Then the agent uses CodeGraph to analyze the relevant relationships.
2. Given Semble and CodeGraph return conflicting or incomplete evidence, When the agent forms a conclusion, Then it verifies the disputed relationship through bounded source reads and explicitly reports the uncertainty.
3. Given the question can be answered from Semble results and bounded reads alone, When no structural relationship must be proven, Then the agent does not invoke CodeGraph unnecessarily.

⸻

User Story 4 - Continue Through Controlled Fallbacks (Priority: P4)

A coding agent follows a documented fallback sequence when Semble is unavailable, fails to index, or returns insufficient candidates.

Why this priority: Repository research must remain usable without silently reverting to uncontrolled repository dumps.

Independent Test: Can be fully tested by disabling Semble or forcing an empty result and verifying that the agent follows the fallback order while preserving query scope and read limits.

Acceptance Scenarios:

1. Given Semble is unavailable or returns an execution error, When the agent continues the investigation, Then it records the failure and uses targeted symbol or text search followed by bounded reads.
2. Given Semble returns no useful candidates, When the initial query used conceptual language, Then the agent retries with repository terminology, probable symbols, or alternate behavioral descriptions before falling back.
3. Given targeted fallback search produces many matches, When the agent selects evidence, Then it narrows matches by path, symbol, file type, or known anchor rather than reading every result.
4. Given all available research paths remain inconclusive, When the agent reports its result, Then it distinguishes verified findings, candidate explanations, and unresolved questions without inventing an answer.

⸻

Edge Cases

* The repository is empty, inaccessible, unsupported, or contains no indexable source files.
* The repository changes after Semble creates its initial index.
* Generated, vendored, dependency, fixture, snapshot, or build-output files dominate search results.
* A natural-language query has no lexical overlap with repository symbols.
* A query matches many repeated implementations, adapters, tests, or generated variants.
* The most relevant result is a test, interface, schema, configuration file, migration, or documentation file rather than runtime code.
* A Semble result references a stale or deleted location.
* A result begins or ends inside a larger symbol and lacks enough context to interpret safely.
* Multiple repositories or worktrees are present and the active repository root is ambiguous.
* Semble, CodeGraph, and direct source inspection provide inconsistent evidence.
* MCP output exceeds the configured research budget or contains duplicate candidates.
* The agent already knows an exact file and symbol, making a new broad semantic search unnecessary.
* Binary files, minified files, large lockfiles, or unsupported encodings are encountered.
* No CodeGraph index exists for a question requiring structural analysis.

Flowchart (mandatory)

flowchart TD
    A[Begin repository investigation] --> B{Exact file and symbol already known?}
    B -- No --> C{Semble available?}
    B -- Yes --> H[Establish known file and line anchor]
    C -- Yes --> D[Run Semble search before local discovery]
    C -- No --> N[Record Semble failure]
    D --> E{Useful candidates returned?}
    E -- No --> F[Retry using repository terminology or alternate behavior]
    F --> G{Useful candidates returned?}
    G -- No --> O[Use targeted symbol or text search]
    G -- Yes --> I[Record and rank candidate anchors]
    E -- Yes --> I
    N --> O
    O --> P[Narrow matches by path symbol or file type]
    P --> Q{Bounded candidates found?}
    Q -- No --> Z[Report verified facts candidates and unresolved questions]
    Q -- Yes --> I
    I --> R[Retain only highest-value candidates]
    R --> H
    H --> J{Related implementation evidence needed?}
    J -- Yes --> K{Semble find-related available?}
    J -- No --> L[Read bounded symbol or line range]
    K -- Yes --> M[Run find-related from anchor]
    K -- No --> O
    M --> L
    L --> S{Enough local context?}
    S -- No --> T[Incrementally expand around same anchor]
    T --> L
    S -- Yes --> U{Structural relationship must be proven?}
    U -- Yes --> V{CodeGraph available?}
    U -- No --> Y[Produce evidence-grounded conclusion]
    V -- Yes --> W[Analyze callers dependencies hierarchy or impact]
    V -- No --> X[Verify relationship with targeted search and bounded reads]
    W --> AA{Structural and source evidence agree?}
    X --> AB{Relationship verified?}
    AA -- Yes --> Y
    AA -- No --> AC[Inspect disputed locations with bounded reads]
    AC --> AD[Report conflict or remaining uncertainty]
    AD --> Y
    AB -- Yes --> Y
    AB -- No --> Z
    Y --> AE[Reference exact files symbols or line ranges]
    AE --> AF[End]
    Z --> AF

Data & State Preconditions (mandatory)

* A repository root has been identified and is accessible to the consuming agent.
* The agent has permission to inspect the repository files required by the investigation.
* Semble is installed and registered as an MCP capability unless the documented fallback path is being tested.
* The Semble capability is associated with the active repository rather than an unrelated checkout or worktree.
* Existing ignore rules and approved research exclusions are known before candidate selection begins.
* CodeGraph is available and sufficiently current when structural analysis is required, or its absence is reported.
* Candidate anchors refer to the same repository state being inspected by local reads.
* The investigation has a defined question, behavior, symbol, failure, or change objective against which relevance can be judged.

Inputs & Outputs (mandatory)

Direction	Description	Format
Input	A repository-scoped research question, optional known anchors, and applicable investigation constraints	Caller-defined
Output	A bounded, evidence-grounded set of findings, candidate locations, structural relationships, uncertainties, and source anchors	Caller-defined

Constraints & Non-Goals (mandatory)

Must NOT:

* Must NOT begin an unknown-location codebase investigation with recursive file reads, repository-wide content dumps, or unbounded grep output while Semble is available.
* Must NOT treat semantic similarity, CodeGraph relationships, or search matches as verified behavior without inspecting sufficient source evidence.
* Must NOT read entire large files, expand every candidate, or return raw tool output when a smaller bounded result can answer the research question.
* Must NOT conceal Semble, indexing, CodeGraph, or fallback failures from the resulting research record.
* Must NOT allow generated, vendored, binary, dependency, or build-output content to overwhelm first-party implementation candidates without an explicit reason.
* Must NOT continue expanding research after the question has been answered with sufficient anchored evidence.

Adopted dependencies:

* Semble — provides repository-level semantic code search and anchor-based related-code discovery through MCP; requires installation, MCP registration, repository indexing, ignore-rule validation, capability verification, fallback documentation, and agent usage instructions.
* CodeGraph — provides existing structural analysis for callers, callees, dependency relationships, hierarchy, ownership, and change impact; requires a usable index and documented invocation criteria.
* Bounded local source tools — provide exact symbol or line-range inspection used to verify candidates returned by Semble, CodeGraph, or fallback search.

Out of scope:

* Replacing CodeGraph with Semble or using Semble as proof of structural relationships.
* Building a new semantic embedding model, vector database, source parser, or code graph.
* Automatically modifying code based solely on retrieved candidates.
* Cross-repository semantic search or dependency analysis unless all repositories are explicitly included in the active research scope.
* Remote code hosting, centralized index services, or organization-wide code intelligence.
* General web research, package-documentation research, or searching repositories that are not part of the active codebase investigation.
* Guaranteeing correctness when repository source, indexes, generated artifacts, or runtime behavior are incomplete or stale.

Requirements (mandatory)

Functional Requirements

Functional Requirements

* FR-001: The system MUST install and register Semble as an available MCP capability in each supported coding-agent environment.
* FR-002: The system MUST verify that Semble can index and search the active repository before it is treated as available.
* FR-003: Agents MUST use Semble search as the default first discovery step when an investigation does not begin with a trusted file or symbol anchor.
* FR-004: The system MUST convert relevant Semble results into a bounded set of candidate anchors containing sufficient repository location information for verification.
* FR-005: Agents MUST use Semble find-related when additional semantically connected code is needed from an established anchor.
* FR-006: Agents MUST verify candidate behavior through bounded local source reads and MUST expand context incrementally rather than reading entire large files by default.
* FR-007: Agents MUST use CodeGraph when callers, dependencies, hierarchy, ownership, or change impact must be established.
* FR-008: The system MUST limit duplicate, low-relevance, generated, vendored, dependency, binary, and build-output content from dominating retained research results.
* FR-009: When Semble returns insufficient results, agents MUST refine the query before falling back to targeted symbol or text search.
* FR-010: When Semble is unavailable or fails, agents MUST follow a documented fallback path that preserves candidate narrowing and bounded-read controls.
* FR-011: Research outputs MUST distinguish verified findings, plausible candidates, conflicting evidence, unresolved questions, and capability failures.
* FR-012: Verified findings MUST reference exact repository files and symbols or line ranges.
* FR-013: The preferred research order, skip conditions, exclusions, dump controls, and fallback behavior MUST be documented for supported agents.
* FR-014: The feature MUST include verification tests covering semantic discovery, related-code expansion, bounded reads, CodeGraph use, excessive-result control, stale anchors, empty results, and Semble failure.

Key Entities

* Research Request: The repository-scoped question or objective being investigated, including any known symbols, paths, behaviors, errors, or constraints.
* Repository Context: The active repository root, current source state, applicable ignore rules, and available research capabilities.
* Candidate Anchor: A potentially relevant code location identified by search, represented by its repository-relative location, surrounding symbol or region, relevance, and originating query.
* Evidence Read: A bounded inspection of exact repository content used to confirm or reject a candidate.
* Structural Relationship: A caller, callee, dependency, hierarchy, ownership, or impact relationship evaluated through CodeGraph and, where necessary, verified against source.
* Research Finding: A conclusion classified as verified, plausible, conflicting, or unresolved and linked to the evidence supporting that classification.
* Capability Failure: An unavailable tool, indexing error, stale result, empty result, or other condition requiring query refinement or fallback behavior.
* Research Budget: The practical limit governing candidate count, source expansion, and returned context for a single investigation.

Success Criteria (mandatory)

Measurable Outcomes

* SC-001: In at least 90% of test investigations without a known source location, the first repository discovery operation is Semble search.
* SC-002: In at least 90% of representative behavioral queries, the final verified implementation location appears within the first five retained Semble candidates or is found after one documented query refinement.
* SC-003: At least 95% of source verification operations begin with a bounded symbol or line range rather than a full-file read.
* SC-004: No acceptance test emits an unbounded repository listing, recursive source dump, or unrestricted search-result payload.
* SC-005: At least 90% of completed investigations cite exact repository files and symbols or line ranges for every material verified conclusion.
* SC-006: All structural-analysis tests use CodeGraph only after a relevant semantic or known source anchor has been established.
* SC-007: All simulated Semble failures complete through the documented fallback path or return an explicit inconclusive result without uncontrolled repository reading.
* SC-008: Generated, vendored, dependency, binary, and build-output content constitutes no more than 20% of retained candidates unless the research request explicitly targets that content.
* SC-009: At least 90% of evaluation investigations reach a verified answer or explicit inconclusive result without inspecting more than five candidate locations.
* SC-010: All supported agent environments pass installation, MCP registration, repository indexing, search, find-related, and fallback verification checks.

Definition of Done (mandatory)

This feature is shipped when production coding agents can use the installed Semble capability to discover and anchor repository evidence before bounded reads, invoke CodeGraph only for required structural analysis, follow controlled fallbacks on failure, and satisfy the defined candidate, citation, and dump-control thresholds.

Open Questions (include if any unresolved decisions exist)

* OQ-1: Which coding-agent environments must receive Semble MCP registration as part of this feature? Stakes: An incomplete environment list could produce inconsistent research behavior across supported agents.
* OQ-2: What numeric limits should define the default candidate count, bounded-read size, and total research budget? Stakes: Limits that are too high permit context dumps, while limits that are too low can hide necessary evidence.
* OQ-3: Which repository paths and file categories should be added to Semble-specific exclusions beyond existing repository ignore rules? Stakes: Incorrect exclusions could either pollute results or conceal relevant generated and configuration artifacts.
* OQ-4: What evidence determines whether the Semble and CodeGraph indexes are current enough for the active repository state? Stakes: Stale indexes can produce missing, deleted, or structurally incorrect anchors.