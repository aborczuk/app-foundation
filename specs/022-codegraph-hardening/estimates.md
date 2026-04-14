# Effort Estimate: CodeGraph Reliability Hardening

**Date**: 2026-04-14 | **Total Points**: 38 | **T-shirt Size**: L  
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
| T014 | 3 | Add the dedicated recovery integration suite in `tests/integration/test_codegraph_recovery.py` covering stale symbol queries, lock contention, local edit invalidation, and refresh/rebuild behavior | New integration suite that exercises the actual recovery matrix and command-level guidance, but remains bounded to the existing doctor/health seam |

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

---

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup | 4 | 2 | 0 |
| Phase 2: Foundation | 8 | 3 | 0 |
| Phase 3: User Story 1 | 9 | 3 | 2 |
| Phase 4: User Story 2 | 6 | 2 | 1 |
| Phase 5: User Story 3 | 7 | 3 | 2 |
| Phase 6: Polish & Cross-Cutting Concerns | 1 | 1 | 1 |
| Phase 7: Recovery Integration Suite | 3 | 1 | 1 |
| **Total** | **38** | **15** | **7** |

---

## Warnings

- None scored 8 or 13; the biggest integration work remains bounded at 3 points.
- Phase 1 and Phase 2 have no parallel opportunities.
- No async lifecycle guard coverage gaps were identified for this feature.
- No state-safety coverage gaps remain in the task plan; refresh and snapshot behavior is explicitly covered.
- No transaction-integrity coverage gaps remain in the task plan; the feature does not mutate a local DB transactionally.
- The large-graph timeout budget is now explicitly covered by T013.
- The recovery matrix is now explicitly covered by T014.
