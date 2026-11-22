# Tasks: codebase MCP registration

**Input**: `spec.md`, `plan.md`, and `spec.json` in `specs/050-codebase-mcp-registration/`
**Prerequisites**: Approved plan slice PL-01
**Terminal boundary**: Register existing Codex MCP services and validate the configuration; do not alter either server implementation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Task may run in parallel when it changes a different file.
- **[Story]**: Traceability to a specification user story.

## Phase 1: Setup

**Purpose**: Establish executable configuration assertions before changing behavior.

- [ ] T001 Create failing configuration assertions for MCP registrations and approval policies in `tests/unit/test_codex_config.py`

**Checkpoint**: The requested configuration behavior is represented by targeted assertions.

---

## Phase 2: User Story 1 - Use registered code intelligence (Priority: P1) 🎯 MVP

**Goal**: Codex discovers the existing CodeGraph and codebase-LSP MCP services.

**Independent Test**: Parse `.codex/config.toml` and assert both registrations preserve their established commands, arguments, and working directory.

### Acceptance Criteria

- CodeGraph is registered as `uv run cgc mcp start`.
- codebase-LSP is registered as `uv run python -m mcp_codebase` and diagnostics retain `approve` mode.

### Tests for User Story 1

- [ ] T002 [US1] Extend `tests/unit/test_codex_config.py` with failing CodeGraph and codebase-LSP registration assertions

### Implementation for User Story 1

- [ ] T003 [US1] Register CodeGraph and codebase-LSP without altering unrelated settings in `.codex/config.toml`

**Checkpoint**: Both code-intelligence MCP registrations parse and pass their targeted assertions.

---

## Phase 3: User Story 2 - Search without repeated approval (Priority: P2)

**Goal**: Semble discovery operations run automatically.

**Independent Test**: Parse `.codex/config.toml` and assert `search` and `find_related` both use `auto` approval.

### Acceptance Criteria

- Semble `search` uses `auto` approval.
- Semble `find_related` uses `auto` approval.

### Tests for User Story 2

- [ ] T004 [US2] Extend `tests/unit/test_codex_config.py` with failing Semble approval assertions

### Implementation for User Story 2

- [ ] T005 [US2] Set only Semble `search` and `find_related` approval modes to `auto` in `.codex/config.toml`

**Checkpoint**: Read-only Semble discovery calls have the configured automatic approval policy.

---

## Phase 4: User Story 3 - Follow accurate language guidance (Priority: P3)

**Goal**: Repository guidance states the intended CodeGraph-compatible language policy.

**Independent Test**: Read `AGENTS.md` and assert that it prefers common CodeGraph-compatible languages while retaining the direct-shell-scripting prohibition.

### Acceptance Criteria

- The guidance prefers common CodeGraph-compatible languages, including Python.
- The guidance continues to prohibit Bash and other direct shell scripting languages.

### Tests for User Story 3

- [ ] T006 [US3] Extend `tests/unit/test_codex_config.py` with the technology-guidance assertion for `AGENTS.md`

### Implementation for User Story 3

- [ ] T007 [US3] Update the technology-choice sentence in `AGENTS.md`

**Checkpoint**: The instruction wording is precise and its targeted assertion passes.

---

## Phase 5: Verification and Handoff

**Purpose**: Validate the one coherent configuration change.

- [ ] T008 Run configuration assertions and TOML parsing for `.codex/config.toml` and `tests/unit/test_codex_config.py`
- [ ] T009 Review the scoped diff for `.codex/config.toml`, `AGENTS.md`, and `tests/unit/test_codex_config.py` to confirm no unrelated configuration changed

## Dependencies & Execution Order

- T001 establishes the shared assertion file.
- T002 and T003 deliver the P1 registration outcome.
- T004 and T005 deliver the P2 approval outcome after the shared assertion file exists.
- T006 and T007 deliver the P3 guidance outcome after the shared assertion file exists.
- T008 and T009 run after T003, T005, and T007.

## Parallel Opportunities

- T004/T005 and T006/T007 can proceed independently after T001, provided the shared test file is coordinated.

## Plan Design Slice Index

- Slice PL-01 - Register existing code-intelligence MCP services: T001 through T009.
