# Tasks: CodeGraph Reliability Hardening

**Input**: Design documents from `/specs/022-codegraph-hardening/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/
**Skills**: Invoke any workflow skills listed in plan.md `Implementation Skills` field before the tasks that depend on them (Constitution V: Reuse, VIII: Reuse Over Invention)

**Tests**: The feature explicitly requires deterministic health, recovery, and smoke verification, so test tasks are included.

**Organization**: Tasks are grouped by user story / build slice so each part of the graph-hardening flow can be implemented and verified independently.

## Format: `[ID] [P?] [Story] Description — file:symbol`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the repo-level readiness contract and the new shared health seam.

- [X] T000 Record the external ingress / runtime readiness gate as N/A with rationale in `specs/022-codegraph-hardening/tasks.md` and keep the plan's local-only readiness stance explicit — `specs/022-codegraph-hardening/plan.md:External Ingress + Runtime Readiness Gate`
- [X] T001 Create `src/mcp_codebase/health.py` with the shared graph-readiness domain models and classifier seam (`GraphHealthStatus`, `GraphHealthResult`, `GraphRecoveryHint`, `classify_graph_health`) — `src/mcp_codebase/health.py:classify_graph_health`

**Checkpoint**: The shared health seam exists and the feature's readiness gate is explicitly recorded as local-only / N/A for ingress.
<!-- Checkpoint validated: PASS | 2026-04-14 | Shared health seam present; readiness gate recorded as local-only / N/A -->

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the adapters that will expose the shared health contract to agents and maintainers.

- [X] T002 Add the MCP health tool registration to `src/mcp_codebase/server.py` and serialize the shared health result there with run-scoped JSONL logging — `src/mcp_codebase/server.py:_register_tools`
- [X] T003 Create `src/mcp_codebase/doctor.py` and the `scripts/cgc_doctor.sh` wrapper for a direct operator-facing health command — `src/mcp_codebase/doctor.py:main`
- [X] T004 Add structured telemetry fields for health checks (`run_id`, recovery hint id, status classification, latency) in `src/mcp_codebase/health.py` and `src/mcp_codebase/server.py` — `src/mcp_codebase/server.py:_setup_logging`

**Checkpoint**: A single health vocabulary exists for both the MCP server and the new doctor command.
<!-- Checkpoint validated: PASS | 2026-04-14 | Doctor CLI and MCP health contract share the same vocabulary and recovery hints -->

## Phase 3: User Story 1 - Graph Health Check for Developers (Priority: P1)

**Goal**: A developer can run a deterministic health check and see a clear healthy/stale/locked/unavailable verdict.

**Independent Test**: Run the doctor command on a healthy checkout and a deliberately unhealthy checkout; the output should distinguish the states without crashing.

### Tests for User Story 1

- [X] T005 [P] [US1] Add unit tests for healthy/stale/locked/unavailable classification and recovery hint selection in `tests/unit/test_health.py` — `tests/unit/test_health.py:test_classify_graph_health`
- [X] T006 [P] [US1] Add integration coverage for the doctor command and the MCP health tool contract in `tests/integration/test_codegraph_health.py` — `tests/integration/test_codegraph_health.py:test_doctor_and_mcp_health_contract`

### Implementation for User Story 1

- [X] T007 [US1] Implement the explicit recovery-hint mapping and fallback-to-files behavior in `src/mcp_codebase/health.py` so the health result always names retry/refresh/fallback guidance — `src/mcp_codebase/health.py:build_recovery_hint`

**Checkpoint**: Health checks are deterministic and return actionable status plus recovery guidance.
<!-- Checkpoint validated: PASS | 2026-04-14 | Story acceptance tests pass and doctor output is stable -->

## Phase 4: User Story 2 - Agent-Facing Recovery on Lock / Query Failure (Priority: P1)

**Goal**: An agent gets a clear failure mode and next action when the graph is locked, stale, unreadable, or query-failing.

**Independent Test**: Simulate lock contention and unreadable graph state; the health result should say whether to retry, refresh, or fall back to direct file reads.

### Tests for User Story 2

- [X] T008 [P] [US2] Add regression tests for lock contention, unreadable graph state, and query-failure recovery hints in `tests/integration/test_codegraph_recovery.py` — `tests/integration/test_codegraph_recovery.py:test_lock_and_query_failure_modes`

### Implementation for User Story 2

- [X] T009 [US2] Thread the recovery hint into the MCP adapter and CLI doctor adapter so the agent-facing and operator-facing outputs say the same next action — `src/mcp_codebase/server.py:get_graph_health`

**Checkpoint**: Failure modes are distinguishable and the same recovery guidance is visible to both agents and maintainers.
<!-- Checkpoint validated: PASS | 2026-04-14 | Healthy/stale/locked/unavailable states and recovery hints are observable via doctor -->

## Phase 5: User Story 3 - Safe Refresh and Rebuild (Priority: P2)

**Goal**: A maintainer can refresh or rebuild safely without losing the last known good graph.

**Independent Test**: Force or simulate a refresh failure, then verify the prior good snapshot remains usable and the recovery path still points at the safe index wrapper.

### Tests for User Story 3

- [X] T010 [P] [US3] Add failure-mode coverage proving last-known-good graph preservation after refresh failure in `tests/integration/test_codegraph_recovery.py` — `tests/integration/test_codegraph_recovery.py:test_last_known_good_snapshot_preserved`

### Implementation for User Story 3

- [X] T011 [US3] Update `specs/022-codegraph-hardening/quickstart.md` with the doctor command, the safe refresh / rebuild flow, and the smoke-test instructions — `specs/022-codegraph-hardening/quickstart.md:Run the Feature`

**Checkpoint**: Safe recovery remains atomic, the operator path is documented, and large-graph health checks have an explicit timeout budget regression.
<!-- Checkpoint validated: PASS | 2026-04-14 | Quickstart documents recovery flow; large-graph timeout budget regression is covered -->

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Align docs and smoke checks with the new health surface.

- [X] T012 [P] Add a deterministic smoke validation note for `scripts/validate_doc_graph.sh` and the new doctor flow in the feature docs — `scripts/validate_doc_graph.sh:main`
- [X] T013 [P] Add large-graph timeout regression coverage for health/smoke checks in `tests/integration/test_codegraph_recovery.py` — `tests/integration/test_codegraph_recovery.py:test_large_graph_timeout_budget`
- [X] T014 [P] Add shared graph-health models and read-only classification in `src/mcp_codebase/health.py` with unit coverage for healthy, stale, locked, and unavailable states plus recovery hints - `src/mcp_codebase/health.py:classify_graph_health`
- [X] T015 [P] Wire the MCP `get_graph_health` tool to the shared contract in `src/mcp_codebase/server.py` and verify the adapter returns the same structured hint payload - `src/mcp_codebase/server.py:get_graph_health`
- [X] T016 [P] Add the CLI doctor entrypoint and shell wrapper hardening in `src/mcp_codebase/doctor.py` and `scripts/cgc_doctor.sh` with deterministic exit codes and subprocess smoke coverage - `src/mcp_codebase/doctor.py:main`
- [X] T017 [P] Add graceful shutdown and bounded timeout handling for Kuzu-owned lifecycle paths in `scripts/cgc_safe_index.sh` and `scripts/cgc_index_repo.sh` so refresh/rebuild waits for the owner to exit before recovery proceeds - `scripts/cgc_safe_index.sh`, `scripts/cgc_index_repo.sh`
- [X] T018 Add stale-owner cleanup and lock-marker reclamation after a bounded timeout in `scripts/cgc_safe_index.sh` and `scripts/cgc_index_repo.sh` so confirmed orphaned owners are cleaned up without blind killing - `scripts/cgc_safe_index.sh`, `scripts/cgc_index_repo.sh`
- [X] T019 [P] Fail fast on buffer-pool exhaustion and other memory-pressure failures in `src/mcp_codebase/health.py` and the safe-index path so the recovery hint is explicit instead of swallowing the error - `src/mcp_codebase/health.py:build_recovery_hint`
- [X] T020 [P] Route query-only CodeGraph probes through `READ_ONLY` connections while keeping refresh and rebuild on the single `READ_WRITE` owner and add concurrency regression coverage for probe-vs-refresh contention - `src/mcp_codebase/server.py:get_graph_health`, `src/mcp_codebase/doctor.py:main`, `src/mcp_codebase/health.py:classify_graph_health`
- [X] T021 [P] Make freshness invalidation edit-aware in `scripts/read-code.sh` and `scripts/cgc_safe_index.sh` so local working-tree edits mark the graph stale before stale symbol answers are served - `scripts/read-code.sh`, `scripts/cgc_safe_index.sh`
- [X] T022 [P] Update `specs/022-codegraph-hardening/quickstart.md` and operator notes with the doctor flow, safe recovery, and failure-mode guidance - `specs/022-codegraph-hardening/quickstart.md:Run the Feature`

**Checkpoint**: The feature has a documented smoke path and the repo-level smoke gate remains usable.
<!-- Checkpoint validated: PASS | 2026-04-14 | Doc graph smoke validation passes and the doctor flow is documented -->

## Phase 7: Recovery Integration Suite

**Purpose**: Prove the real recovery path for stale symbols, lock contention, and refresh/rebuild behavior under local edits.

**Independent Test**: Run the dedicated recovery integration suite against deliberate stale, locked, and refresh-failure scenarios; stale symbol reads should fail or redirect until the graph is patched, and safe rebuild paths should preserve the last known good state.

### Tests for Recovery Coverage

- [X] T014 [P] Add the dedicated recovery integration suite in `tests/integration/test_codegraph_recovery.py` covering stale symbol queries, lock contention, local edit invalidation, and refresh/rebuild behavior for `022-codegraph-hardening` — `tests/integration/test_codegraph_recovery.py:test_lock_and_query_failure_modes`

**Checkpoint**: The recovery suite exists and proves the feature fails gracefully until the graph is refreshed or rebuilt.

## Phase 8: Query Failure & Input Validation

**Purpose**: Make the query tools fail explicitly for malformed input and real query execution failures instead of collapsing them into generic or misleading errors.

**Independent Test**: Call the query tools with empty input and a simulated query failure; malformed requests should fail validation, and a failed hover/query should return a clear query-failure recovery path rather than SYMBOL_NOT_FOUND.

### Tests for Query Tool Recovery

- [X] T015 [P] Add unit coverage in `tests/unit/test_query_tools.py` for malformed input and query-failure handling in `src/mcp_codebase/type_tool.py` and `src/mcp_codebase/diag_tool.py` — `tests/unit/test_query_tools.py:test_query_failure_and_validation_contract`

**Checkpoint**: The query tools distinguish malformed input, missing symbols, and real execution failures.

## Phase 9: Add-to-Backlog - Python Orchestration Migration

**Purpose**: Move orchestration-critical shell scripts to Python entrypoints so blast-radius analysis and dependency visibility improve without breaking existing command paths.

**Independent Test**: Run parity contracts for each migrated wrapper and execute Speckit plan/implement smoke flows; outputs, exit codes, and required JSON payloads must remain compatible.

### Migration Tasks

### Safety-First Execution Order (Mandatory)

- [X] T016 [P] Add contract tests that compare legacy shell wrappers vs Python implementations for args, stdout/stderr, JSON fields, and exit codes for all migrated entrypoints — `tests/integration/test_specify_script_parity.py:test_script_contract_parity`
- [X] T017 [P] Add source-compatible shell wrapper tests proving `source scripts/read-code.sh` / `source scripts/read-markdown.sh` still expose callable shell functions after Python migration — `tests/integration/test_read_helper_wrapper_compat.py:test_source_compat`
- [X] T018 [P] Add golden fixture tests for `.specify/scripts/bash/check-prerequisites.sh` JSON payloads and exit-code behavior across `--json`, `--paths-only`, `--require-tasks`, and `--include-tasks` combinations — `tests/integration/test_check_prerequisites_python_migration.py:test_check_prerequisites_json_include_tasks_contract`
- [X] T019 [P] Add parity checks for tool availability/error handling (`uv`, `git`, `python3`) between legacy shell and Python entrypoints — `tests/integration/test_script_tool_dependency_parity.py:test_tool_dependency_failures`
- [X] T020 [P] Add stderr contract tests for known failure modes (branch validation, missing plan/tasks, unresolved sections/symbols) to lock error-message compatibility — `tests/integration/test_script_stderr_contract.py:test_known_failure_messages`
- [X] T021 [P] Add a temporary shadow-compare mode to emit output diffs between legacy and Python paths during rollout and fail on parity regression — `src/mcp_codebase/orchestration/shadow_compare.py:compare_outputs`
- [X] T022 Migrate shared helpers in `.specify/scripts/bash/common.sh` into a Python utility module consumed by the migrated entrypoints — `.specify/scripts/bash/common.sh:main`
- [X] T023 Migrate `.specify/scripts/bash/create-new-feature.sh` into Python with compatible branch/spec creation behavior and permission-failure messaging — `.specify/scripts/bash/create-new-feature.sh:main`
- [X] T024 Migrate `.specify/scripts/bash/setup-plan.sh` into Python while preserving plan artifact resolution outputs — `.specify/scripts/bash/setup-plan.sh:main`
- [X] T025 Migrate `.specify/scripts/bash/update-agent-context.sh` into Python while preserving agent-context update semantics and write targets — `.specify/scripts/bash/update-agent-context.sh:main`
- [X] T026 Migrate `.specify/scripts/bash/check-prerequisites.sh` into Python and preserve all JSON/output and exit-code contracts consumed by Speckit commands — `.specify/scripts/bash/check-prerequisites.sh:main`
- [X] T027 Migrate `scripts/read-markdown.sh` orchestration logic into a Python entrypoint while preserving current CLI contract through a shell wrapper — `scripts/read-markdown.sh:read_markdown_section`
- [X] T028 Migrate `scripts/read-code.sh` orchestration logic into a Python entrypoint while preserving current CLI contract through a shell wrapper — `scripts/read-code.sh:read_code_context`
- [X] T029 [P] Add Speckit pipeline smoke coverage for plan/implement/addtobacklog paths that depend on `check-prerequisites` and `setup-plan` after migration — `tests/integration/test_speckit_pipeline_driver.py:test_python_orchestration_entrypoints`
- [X] T030 [P] Rework `scripts/read_code.py` to use a ranked anchor-selection pipeline where HUD hints, vector chunk metadata, and strict local symbols compete before bounded file reads, with the selected chunk's stored line span driving the window — `scripts/read_code.py:read_code_context`
- [X] T031 [P] Rework `scripts/read_markdown.py` so vector section hits anchor the read first and normalized heading prefixes like `Phase 9` can resolve to full headings before exact heading fallback — `scripts/read_markdown.py:read_markdown_section`
- [X] T032 [P] Add regression tests covering vector-vs-header precedence, HUD hint priority, ambiguous symbol handling, and markdown prefix resolution for the read helpers — `tests/integration/test_read_code_python_migration.py:test_read_code_context_vector_anchor_precedence`
- [X] T033 [P] Allow unsupported read-code file types to skip codegraph discovery and still use vector or bounded local anchoring instead of failing early — `tests/unit/test_read_code_unsupported_file_type.py:test_unsupported_file_type_can_still_use_vector_anchor`
- [X] T034 [P] Document that post-edit refreshes go through `scripts/hook_refresh_indexes.py` before the codegraph/vector helpers fan out — `CLAUDE.md:211`
- [X] T035 [P] Add operator-facing instructions to `scripts/hook_refresh_indexes.py` describing stdin payloads, codegraph fan-out, and vector refresh behavior — `scripts/hook_refresh_indexes.py:main`

## Ad-Hoc Tasks

- [X] T036 [P] Add a progressive-load tool routing section to `CLAUDE.md` so the repo routes topology questions to `catalog.yaml`, feature behavior to `specs/*/behavior-map.md`, and narrows default reads to the smallest relevant tool first — `CLAUDE.md:178`
- [X] T037 [P] Add a route-tree scaffold template plus a Python generator so new functions and scripts can emit a companion progressive-load/how-to artifact instead of relying on ad-hoc documentation — `.specify/templates/route-tree-template.md`
- [X] T038 [P] Move the detailed markdown read-efficiency guidance out of `CLAUDE.md` and into the `scripts/read_markdown.py` / `scripts/read-markdown.sh` tool documentation so the root doc only points to the executable helper — `scripts/read_markdown.py`
- [X] T039 [P] Generate the first concrete route-tree artifact for `scripts/read_markdown.py` so the progressive-load pattern exists as a real output, not just a scaffold — `.specify/route-trees/scripts/read_markdown__read_markdown_section.md`
- [X] T040 [P] Add a root-level `CLAUDE.md` rule that Python function docstrings are mandatory for new or modified functions so executable docs stay colocated with the implementation — `CLAUDE.md:186`
- [X] T041 [P] Add a repo-level docstring validator that checks every Python function, including private helpers, and wire it into the post-edit workflow so doc coverage is enforced beyond Ruff's public-function default — `scripts/validate_python_docstrings.py`
- [X] T042 [P] Wire the Python docstring validator into CI so changed Python files are checked in GitHub Actions as well as in the editor hook — `.github/workflows/ci.yml`
- [X] T043 [P] Remove the route-tree scaffold/template/generator/artifact layer and keep the progressive-load documentation in the router or tool itself — `.specify/scripts/python/generate_route_tree.py`
- [X] T044 [P] Swap the repo source-of-truth docs so `AGENTS.md` carries the operational instructions and `CLAUDE.md` becomes the pointer back to `AGENTS.md` — `AGENTS.md`
- [X] T045 [P] Keep a single feature-purpose reminder in each Speckit command template and remove duplicate step-level copies so the workflow intent stays visible without repetition — `.claude/commands/speckit.*.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - blocks all user stories
- **User Stories (Phase 3+)**: All depend on Foundational completion
- **Polish (Final Phase)**: Depends on all desired user stories being complete
- **Add-to-Backlog Migration (Phase 9)**: Starts after core recovery phases; may run in parallel with follow-on hardening work but must preserve existing command contracts.

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - no dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational - may reuse User Story 1 surfaces but must remain independently testable
- **User Story 3 (P2)**: Can start after Foundational - may reuse User Story 1 / 2 surfaces but must remain independently testable

### Within Each User Story

- Tests MUST be written and should fail before implementation where practical
- Async integrations (if any) must include lifecycle coverage and no-orphan verification
- Live-vs-local state paths must include explicit reconciliation and drift handling
- If runtime behavior or operator flow changes, preserve the quickstart and smoke path
- Models before services
- Services before adapters
- Core implementation before integration polish

### Parallel Opportunities

- Setup / foundational tasks touching different files can run in parallel when they do not share the same module
- The user-story test tasks marked [P] can run in parallel with each other
- Implementation tasks can be split across the health module, server adapter, CLI adapter, and docs once the shared contract is stable

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. STOP and validate the health command before touching recovery behavior

### Incremental Delivery

1. Complete Setup + Foundational
2. Add User Story 1 health classification and validate it
3. Add User Story 2 recovery guidance and failure-mode tests
4. Add User Story 3 safe refresh / rebuild verification and docs

### Parallel Team Strategy

1. One developer can own `src/mcp_codebase/health.py`
2. One developer can own `src/mcp_codebase/server.py` and the doctor adapter
3. One developer can own the unit/integration tests and quickstart updates
