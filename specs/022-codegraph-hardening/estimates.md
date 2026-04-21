# Effort Estimate: CodeGraph Reliability Hardening

**Date**: 2026-04-14 | **Total Points**: 35 | **T-shirt Size**: L  
**Estimated by**: AI (speckit.estimate) — calibrate against actuals after implementation

---

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T000 | 1 | Record the external ingress / runtime readiness gate as N/A with rationale in `tasks.md` and keep the plan's local-only readiness stance explicit | Pure documentation/governance alignment with one existing plan section; no code path changes |
| T001 | 3 | Create `src/mcp_codebase/health.py` with the shared graph-readiness domain models and classifier seam | New module plus typed classifier logic, but the decision surface is still local and follows existing typed-result patterns |
| T002 | 3 | Add the MCP health tool registration to `src/mcp_codebase/server.py` and serialize the shared health result there with run-scoped JSONL logging | Extends an existing FastMCP adapter and logger path without changing the server architecture |
| T003 | 3 | Create `src/mcp_codebase/doctor.py` and the `scripts/cgc_doctor.sh` wrapper for a direct operator-facing health command | Two new IO-facing surfaces, but both are thin adapters over the shared health seam |
| T004 | 2 | Add structured telemetry fields for health checks in `health.py` and `server.py` | Small logging/schema threading change across two existing files with a clear pattern to follow |
| T005 | 3 | Add unit tests for healthy/stale/locked/unavailable classification and recovery hint selection | Moderate matrix of states and hints with one new test module and no external IO |
| T006 | 3 | Add integration coverage for the doctor command and the MCP health tool contract | Crosses subprocess and MCP adapter boundaries, but remains a bounded contract test |
| T007 | 3 | Implement the explicit recovery-hint mapping and fallback-to-files behavior in `health.py` | New pure decision logic with a few failure-mode branches and deterministic outputs |
| T008 | 3 | Add regression tests for lock contention, unreadable graph state, and query-failure recovery hints | Integration-level failure matrix with multiple recovery paths to verify |
| T009 | 3 | Thread the recovery hint into the MCP adapter and CLI doctor adapter so the agent-facing and operator-facing outputs say the same next action | Touches two adapters and a shared result contract; moderate composition work, but still limited scope |
| T010 | 3 | Add failure-mode coverage proving last-known-good graph preservation after refresh failure | Requires simulated refresh failure and snapshot-preservation checks, which are integration-heavy but bounded |
| T011 | 1 | Update `quickstart.md` with the doctor command, the safe refresh / rebuild flow, and the smoke-test instructions | Documentation-only with one existing feature doc to align |
| T012 | 1 | Add a deterministic smoke validation note for `scripts/validate_doc_graph.sh` and the new doctor flow in the feature docs | Documentation-only smoke guidance with no implementation change |
| T013 | 3 | Add large-graph timeout regression coverage for health/smoke checks in `tests/integration/test_codegraph_recovery.py` | Large-graph timeout handling crosses subprocess and recovery-path boundaries, so it needs a dedicated integration regression |
| T014 | 3 | Add shared graph-health models and read-only classification in `src/mcp_codebase/health.py` with unit coverage for healthy, stale, locked, and unavailable states plus recovery hints | Extends the existing health seam with typed status and hint objects, but the logic stays local and follows the repo's existing typed-result patterns |
| T015 | 3 | Wire the MCP `get_graph_health` tool to the shared contract in `src/mcp_codebase/server.py` and verify the adapter returns the same structured hint payload | Thin adapter work over an existing FastMCP registration path plus run-scoped logging |
| T016 | 3 | Add the CLI doctor entrypoint and shell wrapper hardening in `src/mcp_codebase/doctor.py` and `scripts/cgc_doctor.sh` with deterministic exit codes and subprocess smoke coverage | New operator-facing surface, but it is still a thin wrapper over the shared health contract |
| T017 | 5 | Add graceful shutdown and bounded timeout handling for Kuzu-owned lifecycle paths in `scripts/cgc_safe_index.sh` and `scripts/cgc_index_repo.sh` so refresh/rebuild waits for the owner to exit before recovery proceeds | Crosses shell lifecycle, owner detection, and timeout handling, so there are multiple failure modes to verify |
| T018 | 5 | Add stale-owner cleanup and lock-marker reclamation after a bounded timeout in `scripts/cgc_safe_index.sh` and `scripts/cgc_index_repo.sh` so confirmed orphaned owners are cleaned up without blind killing | Requires distinguishing a live owner from a confirmed stale owner and proving the timeout-based fallback is safe |
| T019 | 3 | Fail fast on buffer-pool exhaustion and other memory-pressure failures in `src/mcp_codebase/health.py` and the safe-index path so the recovery hint is explicit instead of swallowing the error | A focused failure-mapping change against an existing classifier and safe-index flow |
| T020 | 5 | Route query-only CodeGraph probes through `READ_ONLY` connections while keeping refresh and rebuild on the single `READ_WRITE` owner and add concurrency regression coverage for probe-vs-refresh contention | Touches connection ownership, adapter selection, and contention tests, so it is more than a small shim |
| T021 | 5 | Make freshness invalidation edit-aware in `scripts/read-code.sh` and `scripts/cgc_safe_index.sh` so local working-tree edits mark the graph stale before stale symbol answers are served | Requires a freshness signal, invalidation flow, and regression coverage for stale-answer prevention |
| T022 | 1 | Update `specs/022-codegraph-hardening/quickstart.md` and operator notes with the doctor flow, safe recovery, and failure-mode guidance | Documentation-only alignment with one existing feature doc |

---

### T000 — sketch: trivial

No detailed sketch required. This is a repo-process documentation update.

### T001 — Solution Sketch

**Modify**: `src/mcp_codebase/health.py:classify_graph_health` — introduce the shared health classifier seam and result types.  
**Create**: `src/mcp_codebase/health.py` — new domain module with `GraphHealthStatus`, `GraphHealthResult`, and `GraphRecoveryHint`.  
**Reuse**: `src/mcp_codebase/type_tool.py:get_type_impl`, `src/mcp_codebase/diag_tool.py:get_diagnostics_impl`, and `src/mcp_codebase/security.py:validate_path` patterns for typed result envelopes and local-path validation.  
**Composition**: the classifier consumes local graph state, chooses a stable health status, and returns a typed recovery hint that both the MCP server and doctor CLI can present unchanged.  
**Failing test assertion**: the unit test should fail until a healthy fixture reports `healthy`, a stale fixture reports `stale`, a lock fixture reports `locked`, and an unreadable/query-failure fixture reports the correct fallback state with a specific recovery hint.  
**Domains touched**: `.claude/domains/02_data_modeling_schemas.md`, `.claude/domains/10_observability.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/13_identity_access_control.md`, `.claude/domains/14_security_controls.md`, `.claude/domains/17_code_patterns.md`

### T002 — Solution Sketch

**Modify**: `src/mcp_codebase/server.py:_register_tools` and `src/mcp_codebase/server.py:_setup_logging` — register the health tool and include run-scoped telemetry fields.  
**Create**: none.  
**Reuse**: `src/mcp_codebase/server.py`'s existing FastMCP registration pattern and `_JsonlFormatter` logging path.  
**Composition**: the MCP server asks the shared health seam for a result, serializes the same status/hint payload, and logs the run metadata alongside the health verdict.  
**Failing test assertion**: the integration test should fail until the MCP health tool returns the shared status/hint payload and the JSONL log contains the expected run-scoped fields.  
**Domains touched**: `.claude/domains/10_observability.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/13_identity_access_control.md`, `.claude/domains/14_security_controls.md`, `.claude/domains/16_ops_governance.md`, `.claude/domains/17_code_patterns.md`

### T003 — Solution Sketch

**Modify**: `src/mcp_codebase/doctor.py:main` — create the CLI entrypoint that renders the same health contract for operators.  
**Create**: `src/mcp_codebase/doctor.py` and `scripts/cgc_doctor.sh`.  
**Reuse**: `scripts/validate_doc_graph.sh` for shell-wrapper shape and `src/mcp_codebase/health.py` for the shared decision logic.  
**Composition**: the shell wrapper launches the Python CLI, the CLI calls the shared classifier, and the CLI output mirrors the MCP tool's next-action text so operators and agents see the same guidance.  
**Failing test assertion**: the subprocess test should fail until the doctor command prints a clear healthy/stale/locked/unavailable verdict and exits non-zero on unhealthy states.  
**Domains touched**: `.claude/domains/10_observability.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/13_identity_access_control.md`, `.claude/domains/14_security_controls.md`, `.claude/domains/16_ops_governance.md`, `.claude/domains/17_code_patterns.md`

### T004 — sketch: trivial

No detailed sketch required. The task only threads structured telemetry fields through existing logging and result objects.

### T005 — Solution Sketch

**Modify**: `tests/unit/test_health.py:test_classify_graph_health` — cover the status matrix and recovery-hint selection.  
**Create**: `tests/unit/test_health.py`.  
**Reuse**: the pure health seam from `src/mcp_codebase/health.py` and the existing typed-result test style used across the repo.  
**Composition**: the test feeds synthetic healthy/stale/locked/unreadable states into the classifier and checks that each result includes the expected status and hint id.  
**Failing test assertion**: the test should fail until every synthetic failure mode returns the correct status plus its specific recovery hint.  
**Domains touched**: `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/13_identity_access_control.md`, `.claude/domains/14_security_controls.md`, `.claude/domains/17_code_patterns.md`

### T006 — Solution Sketch

**Modify**: `tests/integration/test_codegraph_health.py:test_doctor_and_mcp_health_contract` — verify the CLI and MCP surfaces agree.  
**Create**: `tests/integration/test_codegraph_health.py`.  
**Reuse**: the subprocess test style already present in `.speckit/acceptance-tests/` and the shared health contract from `src/mcp_codebase/health.py`.  
**Composition**: the test runs the doctor command and the MCP health tool contract against the same repo state, then compares the emitted status and recovery hint.  
**Failing test assertion**: the test should fail until both surfaces produce the same next-action guidance for a healthy and unhealthy checkout.  
**Domains touched**: `.claude/domains/10_observability.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/13_identity_access_control.md`, `.claude/domains/14_security_controls.md`, `.claude/domains/16_ops_governance.md`, `.claude/domains/17_code_patterns.md`

### T007 — Solution Sketch

**Modify**: `src/mcp_codebase/health.py:build_recovery_hint` — make the failure-mode mapping explicit and deterministic.  
**Create**: `src/mcp_codebase/health.py` recovery-hint helpers if needed.  
**Reuse**: `src/mcp_codebase/diag_tool.py:get_diagnostics_impl` and `src/mcp_codebase/type_tool.py:get_type_impl` for the established local-failure vocabulary.  
**Composition**: the classifier maps each failure state to a hint that says retry, refresh, or fall back to file reads, and every caller renders the same hint object.  
**Failing test assertion**: the unit test should fail until lock contention, unreadable graph state, and query failure each produce distinct recovery hints instead of a generic error.  
**Domains touched**: `.claude/domains/10_observability.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/13_identity_access_control.md`, `.claude/domains/14_security_controls.md`, `.claude/domains/17_code_patterns.md`

### T008 — Solution Sketch

**Modify**: `tests/integration/test_codegraph_recovery.py:test_lock_and_query_failure_modes` — verify the lock/unreadable/query-failure matrix.  
**Create**: `tests/integration/test_codegraph_recovery.py`.  
**Reuse**: the safe index wrapper behavior in `scripts/cgc_safe_index.sh` and the health contract from `src/mcp_codebase/health.py`.  
**Composition**: the test drives a deliberately unhealthy graph state and confirms that the recovery hint changes with the failure class rather than collapsing to a single opaque error.  
**Failing test assertion**: the test should fail until each failure mode emits its own recovery guidance and the command path remains deterministic.  
**Domains touched**: `.claude/domains/10_observability.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/13_identity_access_control.md`, `.claude/domains/14_security_controls.md`, `.claude/domains/17_code_patterns.md`

### T009 — Solution Sketch

**Modify**: `src/mcp_codebase/server.py:get_graph_health` and `src/mcp_codebase/doctor.py:main` — thread the shared recovery hint through both adapters.  
**Create**: `src/mcp_codebase/server.py:get_graph_health` if it does not already exist as a tool-facing helper.  
**Reuse**: the shared `GraphHealthResult` and `GraphRecoveryHint` types from `src/mcp_codebase/health.py`.  
**Composition**: both the MCP adapter and the doctor CLI consume the same result object, so the next-action phrasing cannot drift between operator and agent surfaces.  
**Failing test assertion**: the test should fail until the CLI and MCP output match on recovery hint id and next-action wording.  
**Domains touched**: `.claude/domains/10_observability.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/13_identity_access_control.md`, `.claude/domains/14_security_controls.md`, `.claude/domains/16_ops_governance.md`, `.claude/domains/17_code_patterns.md`

### T010 — Solution Sketch

**Modify**: `tests/integration/test_codegraph_recovery.py:test_last_known_good_snapshot_preserved` — prove a refresh failure does not destroy the last known good graph.  
**Create**: `tests/integration/test_codegraph_recovery.py` snapshot-preservation fixtures if needed.  
**Reuse**: `scripts/cgc_safe_index.sh` and `scripts/cgc_index_repo.sh` for safe refresh/rebuild semantics, plus the snapshot/recovery model from `specs/022-codegraph-hardening/plan.md`.  
**Composition**: the test forces a refresh failure, then checks that the previous snapshot remains usable and that the recovery hint still points to the safe path.  
**Failing test assertion**: the test should fail until the prior snapshot survives a failed refresh and remains the fallback target.  
**Domains touched**: `.claude/domains/03_data_storage_persistence.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/13_identity_access_control.md`, `.claude/domains/14_security_controls.md`, `.claude/domains/17_code_patterns.md`

### T011 — sketch: trivial

No detailed sketch required. This is a docs-only quickstart alignment task.

### T012 — sketch: trivial

No detailed sketch required. This is a docs-only smoke-note task.

### T013 — Solution Sketch

**Modify**: `tests/integration/test_codegraph_recovery.py:test_large_graph_timeout_budget` — add the large-graph timeout regression assertion.  
**Create**: `tests/integration/test_codegraph_recovery.py` if the timeout regression lands in the same integration module as the other recovery tests.  
**Reuse**: the doctor/health command path and the safe-index wrapper behavior already planned for the feature.  
**Composition**: the test exercises the health/smoke path against a dense graph fixture or a bounded large-repo surrogate and asserts that the command completes within the defined budget instead of timing out.  
**Failing test assertion**: the test should fail until the health/smoke path completes inside the budget for a graph-heavy checkout and returns an explicit non-hanging result.  
**Domains touched**: `.claude/domains/04_caching_performance.md`, `.claude/domains/10_observability.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/13_identity_access_control.md`, `.claude/domains/14_security_controls.md`, `.claude/domains/17_code_patterns.md`

### T014 — Solution Sketch

**Modify**: `src/mcp_codebase/health.py:classify_graph_health` and `src/mcp_codebase/health.py:build_recovery_hint` — extend the shared health classifier seam and keep the result contract typed and deterministic.  
**Create**: any missing `GraphHealthStatus`, `GraphHealthResult`, and `GraphRecoveryHint` helpers required by the hardened health contract.  
**Reuse**: the repo's existing path-validation and typed-result patterns from `src/mcp_codebase/security.py`, `type_tool.py`, and `diag_tool.py`.  
**Composition**: the classifier reads local repo state once, turns it into healthy/stale/locked/unavailable, and emits a stable next-action hint that both CLI and MCP paths can reuse unchanged.  
**Failing test assertion**: the unit test should fail until each fixture maps to the expected status and recovery hint pair, including the unreadable/fallback state.  
**Domains touched**: `.claude/domains/02_data_modeling_schemas.md`, `.claude/domains/10_observability.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/14_security_controls.md`, `.claude/domains/17_code_patterns.md`

### T015 — Solution Sketch

**Modify**: `src/mcp_codebase/server.py:_register_tools` and `src/mcp_codebase/server.py:_setup_logging` — register the new health tool and serialize the shared result contract.  
**Create**: the `get_graph_health` tool handler if it is not already present in the adapter layer.  
**Reuse**: existing FastMCP tool registration and JSONL logging.  
**Composition**: MCP asks the shared health seam for a result, returns the same status/hint payload, and emits run-scoped logging for later diagnosis.  
**Failing test assertion**: the integration test should fail until the MCP health tool returns the shared payload and the JSONL log contains the expected run-scoped fields.  
**Domains touched**: `.claude/domains/10_observability.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/13_identity_access_control.md`, `.claude/domains/14_security_controls.md`, `.claude/domains/16_ops_governance.md`, `.claude/domains/17_code_patterns.md`

### T016 — Solution Sketch

**Modify**: `src/mcp_codebase/doctor.py:main` and `scripts/cgc_doctor.sh` — create the CLI entrypoint that renders the same health contract for operators.  
**Create**: the hardened doctor wrapper and any formatting helper needed to keep the summary text deterministic.  
**Reuse**: `scripts/validate_doc_graph.sh` for shell-wrapper shape and `src/mcp_codebase/health.py` for the shared decision logic.  
**Composition**: the shell wrapper launches the Python CLI, the CLI calls the shared classifier, and the CLI output mirrors the MCP tool's next-action text so operators and agents see the same guidance.  
**Failing test assertion**: the subprocess test should fail until the doctor command prints a clear healthy/stale/locked/unavailable verdict and exits non-zero on unhealthy states.  
**Domains touched**: `.claude/domains/10_observability.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/16_ops_governance.md`, `.claude/domains/17_code_patterns.md`

### T017 — Solution Sketch

**Modify**: `scripts/cgc_safe_index.sh` and `scripts/cgc_index_repo.sh` — add the bounded wait loop and graceful owner-shutdown handling before a refresh proceeds.  
**Create**: small shell helpers for the timeout window and process-state polling if the current wrapper does not already expose them.  
**Reuse**: the existing `KUZUDB_PATH`, `IGNORE_DIRS`, and safe-index guardrails already present in the wrapper scripts.  
**Composition**: the refresh/rebuild path checks for an active owner, waits within a bounded window, and only advances when the live owner has exited cleanly.  
**Failing test assertion**: the shell smoke test should fail until the refresh path waits instead of killing a live owner or hanging indefinitely.  
**Domains touched**: `.claude/domains/03_data_storage_persistence.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/16_ops_governance.md`, `.claude/domains/17_code_patterns.md`

### T018 — Solution Sketch

**Modify**: `scripts/cgc_safe_index.sh` and `scripts/cgc_index_repo.sh` — add the stale-owner cleanup branch that runs only after the bounded timeout proves the owner is stale.  
**Create**: the cleanup routine or lock-marker reclamation helper that removes confirmed stale ownership without touching a live owner.  
**Reuse**: the timeout state and owner-detection logic introduced by T017 plus the existing lock-marker conventions.  
**Composition**: once the timeout expires, the wrapper checks that the owner is truly stale, reclaims the lock markers, and preserves the last known good snapshot rather than blindly killing processes.  
**Failing test assertion**: the regression should fail until a confirmed stale owner is reclaimed and a live owner is never force-killed.  
**Domains touched**: `.claude/domains/03_data_storage_persistence.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/16_ops_governance.md`, `.claude/domains/17_code_patterns.md`

### T019 — Solution Sketch

**Modify**: `src/mcp_codebase/health.py:build_recovery_hint` and the safe-index error mapping in the refresh path — convert buffer-pool exhaustion into an explicit recovery hint.  
**Create**: a memory-pressure recovery branch or helper if the current hint mapping does not already cover it.  
**Reuse**: the existing fail-closed status mapping and explicit fallback hints already planned for the health seam.  
**Composition**: buffer-pool exhaustion becomes a deterministic retry/refresh/fallback guidance path instead of a silent hang or generic crash.  
**Failing test assertion**: the regression should fail until memory pressure returns a clear hint and a deterministic exit instead of a swallowed error.  
**Domains touched**: `.claude/domains/10_observability.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/17_code_patterns.md`

### T020 — Solution Sketch

**Modify**: `src/mcp_codebase/server.py:get_graph_health`, `src/mcp_codebase/doctor.py:main`, and `src/mcp_codebase/health.py:classify_graph_health` — route query-only probes through `READ_ONLY` connections and keep the writable owner exclusive to refresh/rebuild.  
**Create**: a read-only connection helper or mode switch if the existing adapter does not already expose one.  
**Reuse**: the single read-write owner path for refresh/rebuild and the shared health contract for query-only probes.  
**Composition**: probes open `READ_ONLY` connections, refresh/rebuild stays exclusive, and the concurrency regression proves the two paths can overlap without contention.  
**Failing test assertion**: the concurrency test should fail until probe traffic no longer contends with the refresh owner.  
**Domains touched**: `.claude/domains/03_data_storage_persistence.md`, `.claude/domains/04_caching_performance.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/16_ops_governance.md`, `.claude/domains/17_code_patterns.md`

### T021 — Solution Sketch

**Modify**: `scripts/read-code.sh` and `scripts/cgc_safe_index.sh` — detect local edits and invalidate graph freshness before stale answers are served.  
**Create**: a freshness fingerprint or invalidation marker if the current wrapper logic needs one.  
**Reuse**: the existing ignore-dir logic and safe-index wrapper behavior already present in the repo.  
**Composition**: when the working tree changes, the graph flips stale and forces patch/reindex before symbol answers continue.  
**Failing test assertion**: the regression should fail until a working-tree edit invalidates cached graph answers before browsing resumes.  
**Domains touched**: `.claude/domains/04_caching_performance.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/16_ops_governance.md`, `.claude/domains/17_code_patterns.md`

### T022 — sketch: trivial

No detailed sketch required. This is documentation-only alignment for the updated operator guidance.

## Changes from Previous Estimate

- Added T014-T022 after splitting the lifecycle cleanup bundle into separate backlog items for graceful shutdown, stale-owner cleanup, memory-pressure handling, read-only routing, freshness invalidation, and docs.
- Split the former single lifecycle cleanup item into T017 and T018, then renumbered the downstream tasks to keep the task list sequential and aligned with the updated HUDs.

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup | 4 | 2 | 0 |
| Phase 2: Foundation | 8 | 3 | 0 |
| Phase 3: User Story 1 | 9 | 3 | 2 |
| Phase 4: User Story 2 | 6 | 2 | 1 |
| Phase 5: User Story 3 | 7 | 3 | 2 |
| Phase 6: Polish & Cross-Cutting Concerns | 33 | 9 | 8 |
| **Total** | **68** | **23** | **13** |

---

## Warnings

- No tasks scored 8 or 13; the biggest integration work now sits at 5 points in T017, T018, T020, and T021.
- Phase 1 and Phase 2 have no parallel opportunities.
- Async lifecycle guard coverage is now explicit in T017, T018, and T020.
- State-safety coverage is now explicit in T020 and T021, alongside the safe recovery path.
- No transaction-integrity coverage gaps remain in the task plan; the feature does not mutate a local DB transactionally.
- The large-graph timeout budget remains explicitly covered by T013.
