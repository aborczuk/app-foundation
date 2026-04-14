# Sketch Blueprint - CodeGraph Reliability Hardening

_Date: 2026-04-14_  
_Feature: `022-codegraph-hardening`_  
_Source Plan: `plan.md`_  
_Artifact: `sketch.md`_

## Feature Solution Frame

### Core Capability

Build a shared Graph Readiness Guard for the local CodeGraph/Kuzu path so developers and agents get a deterministic health verdict, a concrete recovery hint, and a safe fallback path when the graph is stale, locked, or unavailable.

### Current -> Target Transition

Today the repo has reusable graph-adjacent pieces, but no single health/doctor surface that classifies graph readiness in one place. `src/mcp_codebase/server.py` exposes type and diagnostics tools, `PyrightClient` manages the browse-time subprocess lifecycle, and `scripts/cgc_safe_index.sh` / `scripts/cgc_index_repo.sh` protect indexing, but the repo still lacks a unified doctor flow with explicit healthy/stale/locked/unavailable states. The target state adds a shared health module, a CLI doctor entrypoint, and an MCP health tool that all use the same classification and recovery vocabulary.

### Dominant Execution Model

Read-only local probe first, then explicit recovery action. The health path should inspect repo-local state, classify the current condition, and return structured status without mutating source or graph state. Recovery remains a separate safe refresh/rebuild path that preserves the last known good snapshot until a validated replacement is ready.

### Main Design Pressures

- No source mutation during health checks
- Local-only behavior with no network dependency
- Explicit, typed status categories and recovery hints
- Preserve the current safe-index recovery path and last-known-good snapshot

---

## Solution Narrative

This feature introduces a shared graph-readiness core in `src/mcp_codebase/health.py` and uses it from two thin adapters: a new CLI doctor entrypoint and a new MCP health tool in `src/mcp_codebase/server.py`. The shared core classifies the local graph as healthy, stale, locked, or unavailable, emits an explicit recovery hint, and stays read-only by default. The CLI adapter gives maintainers a direct health command, while the MCP adapter gives agents the same answer inside the existing codebase server. Existing surfaces are reused rather than replaced: `PyrightClient` stays the subprocess lifecycle manager for browse-time type work, `security.py` stays the trust-boundary validator, and `scripts/cgc_safe_index.sh` / `scripts/cgc_index_repo.sh` remain the safe refresh and rebuild path. The finished solution is a single health vocabulary across CLI, MCP, and recovery scripts, with no new backend and no network requirement.

---

## Construction Strategy

1. Define the shared health domain models and classification service in a new `src/mcp_codebase/health.py` seam.
2. Add the MCP health tool to `src/mcp_codebase/server.py` and keep it as a thin adapter over the shared service.
3. Add a CLI doctor entrypoint, likely `src/mcp_codebase/doctor.py` plus `scripts/cgc_doctor.sh`, that renders the same health result and exit codes.
4. Thread recovery hints through the safe refresh path by reusing `scripts/cgc_safe_index.sh` and `scripts/cgc_index_repo.sh` instead of inventing a second recovery implementation.
5. Add deterministic tests for status classification, unreadable/locked/unavailable states, CLI exit behavior, and fallback/recovery guidance.
6. Update `quickstart.md` and any runbook-style notes so the new doctor flow is visible and reproducible.

### Construction Notes

- Keep decision logic in the shared service layer and IO in adapters.
- Treat the CLI doctor and MCP health tool as the same contract with different shells.
- Preserve the current browse-time `get_type` / `get_diagnostics` paths unchanged except for shared health-aware fallback behavior.

---

## Acceptance Traceability

| Story / Requirement / Constraint | Design Element(s) That Satisfy It | Reuse / Modify / Create | Verification / Migration Note |
|----------------------------------|-----------------------------------|-------------------------|-------------------------------|
| User Story 1 - Graph health check for developers | `GraphHealthResult`, `classify_graph_health()`, `get_graph_health`, `scripts/cgc_doctor.sh` | Create / Modify | Health output must be deterministic and clearly label healthy vs unhealthy. |
| User Story 2 - Agent-facing recovery on lock/query failure | `GraphRecoveryHint`, health adapter error envelopes, direct file-read fallback | Create / Modify | Recovery hint must say whether to retry, refresh, or fall back. |
| User Story 3 - Safe refresh and rebuild | `scripts/cgc_safe_index.sh`, `scripts/cgc_index_repo.sh`, atomic replacement behavior | Reuse / Modify | Rebuild tests must prove the prior good snapshot remains usable. |
| FR-001 deterministic health check | `GraphHealthStatus`, `GraphHealthResult`, `classify_graph_health()` | Create | Unit tests must prove healthy/stale/locked/unavailable outputs. |
| FR-002 clear recovery message | `GraphRecoveryHint`, health service error mapping | Create | Error envelopes must distinguish lock, stale, and unreadable states. |
| FR-003 preserve last known good snapshot | Safe refresh/rebuild flow using `cgc_safe_index.sh` and `cgc_index_repo.sh` | Reuse / Modify | Recovery tests must show previous snapshot remains usable after failure. |
| FR-004 smoke/doctor check | `scripts/cgc_doctor.sh`, `src/mcp_codebase/doctor.py`, MCP health tool | Create | Smoke test must be deterministic and non-destructive. |
| FR-005 safe refresh/rebuild | Existing safe-index scripts plus recovery hint contract | Reuse / Modify | Refresh path must be atomic from the caller perspective. |
| FR-006 distinguish failure modes | Typed status enum, explicit validation/error envelopes | Create / Modify | Tests must prove retry vs refresh vs fallback is decidable. |
| No network for core checks | Local file/state inspection only | Reuse / Modify | Documented as a hard constraint in the service layer. |
| No source mutation during health checks | Read-only probe service and thin adapters | Create | Health checks should have no write side effects. |

---

## Work-Type Classification

| Capability / Story Area | Work Type(s) | Dominant Pattern in Repo | Reuse-First / Extension-First / Net-New | Special Constraints |
|-------------------------|--------------|---------------------------|-----------------------------------------|--------------------|
| Health classification and status vocabulary | state transition, API / contract shaping, observability | Typed error envelopes in `type_tool.py` and `diag_tool.py` | Net-new | Must be read-only and local-only. |
| MCP health tool | integration, API / contract shaping | `src/mcp_codebase/server.py` tool registration pattern | Extension-first | Must preserve existing `get_type` / `get_diagnostics` behavior. |
| CLI doctor entrypoint | human / operator interaction, observability, deployment / operational readiness | Shell wrappers like `cgc_safe_index.sh` | Net-new | Must be deterministic, with clear exit codes and status text. |
| Safe refresh / rebuild path | orchestration / workflow, storage / persistence, state transition | `cgc_safe_index.sh` and `cgc_index_repo.sh` | Reuse-first | Must preserve last known good snapshot. |
| Telemetry / diagnostics | observability / diagnostics, security / trust boundary | JSONL logging in `server.py` | Extension-first | Must include run id and no secret leakage. |
| Verification and smoke gates | testing / quality gates | `scripts/validate_doc_graph.sh`, `pytest` | Reuse-first | Must be deterministic and non-destructive. |

---

## Current-System Inventory

| Surface | Type | Role Today | Relationship to Feature | Condition | Primary Seam or Blast Radius Only |
|---------|------|------------|--------------------------|-----------|-----------------------------------|
| `src/mcp_codebase/server.py` | module | Registers `get_type` and `get_diagnostics`, manages `PyrightClient`, and emits run-scoped JSONL logs | Add a new health tool and route it through shared graph readiness logic | Extension-friendly | Primary |
| `src/mcp_codebase/pyright_client.py` | module | Long-lived Pyright subprocess lifecycle manager | Remains the browse-time lifecycle anchor; health flow should not duplicate it | Reusable | Primary |
| `src/mcp_codebase/type_tool.py` | module | Hover-based type lookup with structured error envelopes | Regression-sensitive neighbor; should not change behavior except via shared health awareness | Reusable | Blast radius |
| `src/mcp_codebase/diag_tool.py` | module | Per-call `pyright --outputjson` diagnostics with explicit failure mapping | Regression-sensitive neighbor; informs browse-time failure vocabulary | Reusable | Blast radius |
| `src/mcp_codebase/security.py` | module | Trust-boundary path validation | Reused by any doctor or browse helper that reads local paths | Reusable | Primary |
| `scripts/cgc_safe_index.sh` | shell script | Safe scoped indexing and refresh wrapper | Reused as the atomic recovery path when graph state is stale or locked | Reusable | Primary |
| `scripts/cgc_index_repo.sh` | shell script | Full-repo rebuild wrapper guarded by explicit opt-in | Reused for intentionally broad recovery operations only | Reusable | Primary |
| `scripts/validate_doc_graph.sh` | shell script | Repository-level governance smoke gate | Reused as a deterministic validation pattern, not as the codegraph health probe itself | Reusable | Blast radius |
| `catalog.yaml` | registry | Service/resource inventory | No new external service is expected, but the plan should not invent one | Stable | Blast radius |

---

## Command / Script Surface Map

| Name | Owning File / Script / Template | Pipeline Role | Classification | Inputs | Outputs / Artifacts | Events | Extension Seam | Planned Change |
|------|---------------------------------|---------------|----------------|--------|----------------------|--------|----------------|----------------|
| `uv run python -m src.mcp_codebase` | `src/mcp_codebase/__main__.py`, `src/mcp_codebase/server.py` | MCP server entrypoint | Hybrid | Project root, local config | FastMCP server with tool surface | Run-scoped JSONL logs | Add `get_graph_health` tool | Modify |
| `scripts/cgc_doctor.sh` | new script | Operator doctor / smoke command | Deterministic | Repo root, optional `--json` / `--root` | Health status and exit code | Local command output only | Thin wrapper over shared health service | Create |
| `scripts/cgc_safe_index.sh` | existing script | Safe recovery / refresh | Deterministic | Scoped path, optional force opt-in | Incremental or scoped rebuild | Local command output only | Recovery path after stale/locked status | Reuse / modify minimally |
| `scripts/cgc_index_repo.sh` | existing script | Full-repo rebuild with opt-in | Deterministic | Repo root, explicit `CGC_ALLOW_REPO_INDEX=1` | Full repository index rebuild | Local command output only | Recovery path for intentional rebuilds | Reuse |
| `scripts/validate_doc_graph.sh` | existing script | Smoke / governance validation | Deterministic | Repo root | PASS/FAIL doc graph validation | Local command output only | Regression harness for docs and command coverage | Reuse |
| `speckit.plan` / `speckit.solution` | `.claude/commands/*` and `.specify/command-manifest.yaml` | Workflow orchestration | Hybrid | Feature artifacts | Plan/solution artifacts and ledger events | `plan_started`, `planreview_completed` | No change expected | No-op |

---

## CodeGraphContext Findings

### Seed Symbols

- `src/mcp_codebase/server.py:CodebaseLSPServer` - existing FastMCP lifecycle and run-scoped logging anchor
- `src/mcp_codebase/server.py:get_type` - browse-time tool registration pattern
- `src/mcp_codebase/server.py:get_diagnostics` - browse-time tool registration pattern
- `src/mcp_codebase/pyright_client.py:PyrightClient` - long-lived subprocess lifecycle seam
- `src/mcp_codebase/type_tool.py:get_type_impl` - structured error envelope pattern
- `src/mcp_codebase/diag_tool.py:get_diagnostics_impl` - subprocess diagnostics and error mapping pattern
- `src/mcp_codebase/security.py:validate_path` - trust-boundary validation pattern
- `scripts/cgc_safe_index.sh` - safe scoped indexing and recovery wrapper
- `scripts/cgc_index_repo.sh` - full-repo rebuild wrapper with explicit opt-in
- `scripts/validate_doc_graph.sh` - deterministic smoke gate and command coverage pattern

### Primary Implementation Surfaces

| File | Symbol(s) | Why This Surface Is Primary | Planned Change Type |
|------|-----------|-----------------------------|---------------------|
| `src/mcp_codebase/health.py` | `GraphHealthStatus`, `GraphHealthResult`, `GraphRecoveryHint`, `classify_graph_health()` | New shared graph-readiness core for both CLI and MCP surfaces | Create |
| `src/mcp_codebase/server.py` | `CodebaseLSPServer._register_tools`, new `get_graph_health` tool | Existing MCP server is the right adapter point for the new health tool | Modify |
| `src/mcp_codebase/doctor.py` | `main()` and report helpers | New CLI entrypoint for direct doctor usage | Create |
| `scripts/cgc_doctor.sh` | shell wrapper | Human/operator-facing doctor command and smoke surface | Create |
| `scripts/cgc_safe_index.sh` | safe refresh / rebuild entrypoint | Recovery path must remain atomic and preserve last known good state | Modify minimally |

### Secondary Affected Surfaces

| File / Surface | Why It Is Affected | Type of Impact |
|----------------|--------------------|----------------|
| `src/mcp_codebase/type_tool.py` | Shares browse-time failure vocabulary and trust boundary expectations | Blast radius / regression |
| `src/mcp_codebase/diag_tool.py` | Shares browse-time diagnostics and explicit error reporting expectations | Blast radius / regression |
| `src/mcp_codebase/security.py` | New health code may reuse path validation for local probes | Blast radius / reuse |
| `scripts/cgc_index_repo.sh` | Safe rebuild should stay aligned with the new recovery hint contract | Blast radius / recovery |
| `scripts/validate_doc_graph.sh` | Smoke-gate pattern may be referenced from quickstart or runbook notes | Regression / observability |

### Caller / Callee / Dependency Notes

- `server.py` currently owns tool registration and run-scoped JSONL logs; the health tool should reuse that logging convention and not introduce a second server.
- `PyrightClient` remains the browse-time lifecycle primitive. The new health service should not duplicate its long-lived process model.
- Safe refresh/rebuild should continue to flow through `cgc_safe_index.sh` / `cgc_index_repo.sh` rather than a new recovery pipeline.

### Missing Seams or Contradictions

- There is no current doctor/health module or CLI entrypoint; that seam must be introduced.
- The repo has browse-time type and diagnostics tools, but no unified status vocabulary for graph readiness.
- `validate_doc_graph.sh` is a useful smoke pattern, but it is not a codegraph health probe; the new doctor flow must be explicit about that distinction.

---

## Blast Radius

### Direct Implementation Surfaces

- `src/mcp_codebase/health.py`
- `src/mcp_codebase/server.py`
- `src/mcp_codebase/doctor.py`
- `scripts/cgc_doctor.sh`
- `scripts/cgc_safe_index.sh`

### Indirect Affected Surfaces

- `src/mcp_codebase/type_tool.py`
- `src/mcp_codebase/diag_tool.py`
- `src/mcp_codebase/security.py`
- `scripts/cgc_index_repo.sh`
- `scripts/validate_doc_graph.sh`

### Regression-Sensitive Neighbors

- `PyrightClient` startup/shutdown lifecycle
- Existing `get_type` and `get_diagnostics` contract shapes
- Run-scoped JSONL logging in `server.py`

### Rollout / Compatibility Impact

- Existing codebase MCP behavior must remain unchanged for type and diagnostics queries.
- The new doctor flow should be additive, not a replacement for current browse-time tools.
- Recovery scripts must keep their current safety opt-ins and not become more permissive.

### Operator / Runbook / Deployment Impact

- The quickstart and any operator notes need a new doctor command example.
- Recovery instructions should point to the safe index wrapper and the full-rebuild wrapper only when appropriate.
- No deployment or remote ingress changes are expected.

---

## Reuse / Modify / Create Matrix

### Reuse Unchanged

- `src/mcp_codebase/pyright_client.py` lifecycle management
- `src/mcp_codebase/security.py` path validation
- `scripts/cgc_index_repo.sh` rebuild opt-in guard
- `scripts/validate_doc_graph.sh` smoke-gate pattern

### Modify / Extend Existing

- `src/mcp_codebase/server.py` to register a graph-health tool and share the logging contract
- `scripts/cgc_safe_index.sh` to preserve and report the recovery hint contract if needed
- `quickstart.md` to document the doctor command and recovery flow

### Compose from Existing Pieces

- Shared graph readiness guard = `server.py` logging conventions + `security.py` validation + safe-index scripts + new health models

### Create Net-New

- `src/mcp_codebase/health.py`
- `src/mcp_codebase/doctor.py`
- `scripts/cgc_doctor.sh`
- Tests for health classification and doctor behavior

### Reuse Rationale

The repo already has the necessary building blocks for browse-time subprocess management, safe recovery, path validation, and deterministic smoke validation. The lowest-risk solution is to compose those blocks into a shared health core rather than introducing a new backend or a second recovery stack.

---

## Manifest Alignment Check

| Affected Command / Phase | Existing Manifest Coverage? | New Artifact Needed? | New Event / Field Needed? | Handoff / Event Flow Impact | Status |
|--------------------------|-----------------------------|----------------------|---------------------------|-----------------------------|--------|
| `speckit.plan` / `speckit.solution` | Yes | No | No | None | Aligned |
| `src/mcp_codebase` runtime | Partial | `scripts/cgc_doctor.sh` and `src/mcp_codebase/doctor.py` | No new Speckit ledger event | None | Aligned |
| CodeGraph safe-index / smoke surface | Partial | Doctor script and health module | No new manifest event | Add a new operator-facing health entrypoint | Aligned |

### Manifest Alignment Notes

- No `speckit` manifest change is expected.
- The new doctor command is a repo utility, not a new workflow command.
- If tasking later decides the health command needs command-manifest coverage, that would be a separate governance change, not part of this feature by default.

---

## Architecture Flow Delta

- **Architecture Flow refined**

### Delta Summary

The plan-level flow stays correct, but the LLD inserts a shared `health.py` seam between the repo-local state probe and the CLI/MCP adapters. The doctor command becomes the operator-facing entrypoint for the same status vocabulary that the MCP tool returns to agents.

### Added / Refined Nodes, Edges, or Boundaries

| Change | Why Needed at LLD Level | Must Preserve in Tasking / Implementation |
|--------|--------------------------|-------------------------------------------|
| New shared `health.py` core | Prevents CLI and MCP surfaces from drifting apart | One status vocabulary and one recovery-hint contract |
| CLI doctor adapter (`doctor.py` / `cgc_doctor.sh`) | Gives maintainers a direct smoke/doctor command | Read-only by default, deterministic exit behavior |
| MCP `get_graph_health` tool | Gives agents the same verdict inside the existing server | No change to browse-time type/diagnostics contracts |
| Recovery path via safe-index wrappers | Preserves existing rebuild safety and last-known-good state | Atomic replacement only; no silent corruption |

---

## Component and Boundary Design

| Component / Boundary | Responsibility | Owning or Likely Touched File(s) | Likely Touched Symbol(s) | Reuse / Modify / Create | Inbound Dependencies | Outbound Dependencies |
|----------------------|----------------|----------------------------------|--------------------------|-------------------------|---------------------|----------------------|
| Graph health domain | Typed status and recovery vocabulary | `src/mcp_codebase/health.py` | `GraphHealthStatus`, `GraphHealthResult`, `GraphRecoveryHint` | Create | Local file state, validation helpers | Service and adapter layers |
| Health classification service | Compute status from local repo state without mutation | `src/mcp_codebase/health.py` | `classify_graph_health()`, `build_recovery_hint()` | Create | `security.validate_path`, local graph metadata | CLI and MCP adapters |
| MCP health adapter | Expose health verdict as a FastMCP tool | `src/mcp_codebase/server.py` | new `get_graph_health` tool registration | Modify | `health.py`, `CodebaseLSPServer` logging | MCP clients, agent workflows |
| CLI doctor adapter | Human/operator command with deterministic exit codes | `src/mcp_codebase/doctor.py`, `scripts/cgc_doctor.sh` | `main()` | Create | `health.py`, repo config | Quickstart, operator workflows |
| Safe recovery adapter | Atomic refresh/rebuild path with last-known-good preservation | `scripts/cgc_safe_index.sh`, `scripts/cgc_index_repo.sh` | existing wrapper behavior | Modify minimally | local graph state, opt-in env vars | New recovery hint contract |

### Control Flow Notes

- Health checks must stop at classification and hinting; they must not trigger destructive recovery automatically.
- Recovery should only be invoked by the operator or a separate explicit flow.
- The CLI and MCP adapters should both serialize the same result structure, not independently invent their own outputs.

### Data Flow Notes

- Repo-local state -> health service -> result object -> CLI/MCP adapter -> human/agent output
- Healthy path returns a plain ready state.
- Unhealthy path returns a specific status plus a recovery hint that points at the safe index wrapper or direct file fallback.

---

## Interface, Symbol, and Contract Notes

### Public Interfaces and Contracts

| Interface / Contract | Purpose | Owner | Validation Point | Failure / Error Shape |
|----------------------|---------|-------|------------------|-----------------------|
| `GraphHealthResult` contract | Serialized readiness result for CLI and MCP outputs | `src/mcp_codebase/health.py` | Unit tests and adapter tests | Typed status plus optional recovery hint |
| `scripts/cgc_doctor.sh` exit contract | Human/operator smoke command | `scripts/cgc_doctor.sh` | Shell smoke tests | Exit 0 for healthy, non-zero for unhealthy or invalid input |
| `get_graph_health` MCP tool contract | Agent-facing readiness check | `src/mcp_codebase/server.py` | MCP integration tests | JSON-compatible dict with status and recovery hint or explicit error envelope |
| Safe refresh / rebuild contract | Preserve last known good graph | `scripts/cgc_safe_index.sh` / `scripts/cgc_index_repo.sh` | Recovery tests and smoke tests | Explicit failure state, no partial replacement |

### New or Changed Public Symbols

| Symbol | Exact Intended Signature | Layer / Module | Responsibility | Notes |
|--------|---------------------------|----------------|----------------|------|
| `GraphHealthStatus` | `class GraphHealthStatus(str, Enum)` | domain / `src/mcp_codebase/health.py` | Typed readiness vocabulary | Values: `healthy`, `stale`, `locked`, `unavailable` |
| `GraphRecoveryHint` | `@dataclass(frozen=True)` with `id`, `action`, `summary`, `command`, `preserves_last_good` | domain / `src/mcp_codebase/health.py` | Recovery guidance contract | Must be serializable and stable |
| `GraphHealthResult` | `@dataclass(frozen=True)` with `status`, `detail`, `checked_at`, `source`, `recovery_hint` | domain / `src/mcp_codebase/health.py` | Canonical health result | Adapters convert to JSON-friendly dicts |
| `classify_graph_health` | `def classify_graph_health(project_root: Path) -> GraphHealthResult` | service / `src/mcp_codebase/health.py` | Read-only health classification | No IO side effects other than bounded local reads |
| `get_graph_health_impl` | `async def get_graph_health_impl(project_root: Path) -> dict[str, Any]` | adapter / `src/mcp_codebase/health.py` or `server.py` | MCP-friendly serialization | Mirrors the service result |
| `main` | `def main(argv: Sequence[str] | None = None) -> int` | adapter / `src/mcp_codebase/doctor.py` | CLI doctor entrypoint | Deterministic exit codes and status text |

### Ownership Boundaries

- Domain models own the vocabulary; they should not call the filesystem or subprocesses.
- The health service owns decision logic; adapters own presentation and IO.
- The MCP server should remain a thin registration layer, not the place where health rules accumulate.

---

## State / Lifecycle / Failure Model

### State Authority

| State / Field / Lifecycle Area | Authoritative Source | Reconciliation Rule | Notes |
|--------------------------------|----------------------|---------------------|------|
| Source files | Repo checkout / working tree | The current working tree is authoritative, including uncommitted local edits; health checks must not mutate it | Local edits immediately invalidate graph freshness until patching or refresh occurs |
| Graph snapshot | `.codegraphcontext/db/kuzudb` | Snapshot is authoritative for indexed graph content until a validated replacement exists | Existing safe-index boundary preserved |
| Lock / busy state | Local lock markers and process state | If a lock is observed, report `locked` and do not force mutation | Explicit recovery hint required |
| Latest health verdict | Health service result object | Recomputed on each doctor / MCP probe; not cached as truth | Can be re-probed at any time |

### Lifecycle / State Transitions

| Transition | Allowed? | Trigger | Validation / Guard | Failure Handling |
|------------|----------|---------|--------------------|------------------|
| `healthy -> stale` | Yes | Working-tree content changes after the graph snapshot or graph content lags the checkout | Local probe detects drift or local edit fingerprint changes | Return refresh hint; invalidate/patch before stale symbols are served |
| `stale -> locked` | Yes | Another session or lock file blocks access | Lock marker or active process observed | Suggest safe retry or refresh |
| `locked -> unavailable` | Yes | No safe local read path remains | No valid snapshot / read path | Fall back to direct file reads |
| `unavailable -> healthy` | Yes | Safe refresh/rebuild completes | Replacement snapshot validates | Promote the new snapshot atomically |
| `healthy -> healthy` | Yes | Re-probe confirms readiness | No drift or lock | Return ready status |

### Retry / Replay / Ordering / Cancellation

- Retry behavior: bounded retries only for recoverable local probe steps; no infinite retry loops.
- Duplicate / replay handling: repeated health probes are idempotent and should return the same status for the same state.
- Out-of-order handling: a stale snapshot must never overwrite a newer validated one.
- Cancellation / timeout behavior: if the doctor probe times out, report `unavailable` with an explicit hint rather than hanging silently.
- Edit-aware invalidation: local working-tree edits must trigger immediate graph staleness or patching so stale symbol answers are not served after a file change.

### Degraded Modes / Fallbacks / Recovery

- Degraded mode 1: direct file reads when graph health is unavailable
- Fallback rule 1: stale or locked graph should point to the safe index wrapper, not a destructive rebuild
- Recovery expectation 1: preserve and reuse the last known good graph snapshot until a replacement validates

---

## Non-Functional Design Implications

| Concern | Design Implication | Enforcement / Verification |
|---------|--------------------|-----------------------------|
| Performance | Health classification should remain bounded and fast on a normal checkout | Time-bounded unit or smoke tests; target under 2 seconds |
| Observability | Health checks must emit structured, parseable status and enough context to reconstruct failures | JSONL logging with run_id and recovery hint id |
| Security | All path input must remain within the repo trust boundary | Reuse `validate_path` and keep errors non-leaky |
| Resilience | Health checks must fail closed and never corrupt graph state | Safe refresh and last-known-good preservation tests |
| Testing | Every major failure mode needs a deterministic PASS/FAIL oracle | Unit, integration, and shell smoke tests |

---

## Human-Task and Operator Boundaries

- The health check itself is fully automated.
- The operator or maintainer decides when to run the safe refresh or rebuild command returned in the recovery hint.
- If a full-repo rebuild is ever needed, it must still respect the existing explicit opt-in guard in `cgc_index_repo.sh`.
- No manual approval is required for read-only health checks; manual action is only for the explicit recovery path.

---

## Verification Strategy

| Verification Target | Proposed Check | Why It Matters |
|---------------------|----------------|----------------|
| Health classification | Unit test `GraphHealthStatus` and `classify_graph_health()` | Proves the shared vocabulary is deterministic |
| MCP adapter | Integration test for new `get_graph_health` tool | Proves agents see the same verdict as CLI users |
| CLI doctor | Shell or subprocess test for `scripts/cgc_doctor.sh` | Proves the operator-facing command behaves deterministically |
| Safe refresh / rebuild | Failure-mode test around `cgc_safe_index.sh` and `cgc_index_repo.sh` | Proves last-known-good preservation |
| Browse-time regression | Existing `get_type` / `get_diagnostics` tests remain green | Ensures the new health path did not break current codebase LSP behavior |
| Smoke / governance gate | `scripts/validate_doc_graph.sh` remains PASS | Ensures the repo-level smoke pattern stays intact |

---

## Domain Guardrails

| Domain | Relevant Guardrail | How the Design Satisfies It |
|--------|--------------------|-----------------------------|
| 02 Data modeling & schemas | Finite-state values must be typed | `GraphHealthStatus` is a constrained enum |
| 03 Data storage & persistence | Concurrency control and atomic replacement are required | Recovery path preserves last-known-good snapshot and replaces atomically |
| 04 Caching & performance | Correctness over speed; explicit staleness | Health checks are read-only and deterministic; no hidden cache truth |
| 10 Observability | No silent failures; structured event logs | Health and doctor paths emit structured JSONL context |
| 11 Resilience & continuity | Fail closed on ambiguous state; recovery must be documented | Unclear states become `unavailable` with explicit hints |
| 12 Testing & quality gates | Deterministic tests are mandatory | Health, doctor, and recovery behavior get explicit PASS/FAIL tests |
| 14 Security controls | Validate all untrusted inputs | Reuse path validation and avoid leaking internals in error text |
| 16 Ops & governance | Runbooks and operator flow must be explicit | `quickstart.md` and the doctor command form the operator path |
| 17 Code patterns | Clear module boundaries and typed symbols | Domain/service/adapter split with single-purpose modules |

---

## LLD Decision Log

| Decision | Why It Was Chosen | What It Avoids |
|----------|-------------------|----------------|
| Add a shared `health.py` module | Keeps CLI and MCP verdicts aligned | Duplicated readiness logic in multiple adapters |
| Keep `server.py` as a thin adapter | Preserves the existing MCP server shape | A second, competing server implementation |
| Add a dedicated CLI doctor entrypoint | Gives maintainers a clear smoke command | Overloading `validate_doc_graph.sh` with a non-doc responsibility |
| Reuse `cgc_safe_index.sh` and `cgc_index_repo.sh` for recovery | Preserves the existing safe rebuild guardrails | A new rebuild pipeline with different safety rules |
| Preserve read-only health checks | Makes failure classification safe and repeatable | Unintended mutation during probing |

---

## Design Gaps and Repo Contradictions

- There is no existing `health.py` or doctor entrypoint, so tasking must create those seams explicitly.
- The repo currently has browse-time type and diagnostics tools, but no unified graph-readiness vocabulary; this feature fills that gap.
- `scripts/validate_doc_graph.sh` is a good smoke pattern, but it is not the health probe itself; the new doctor command must be separate and explicit.
- The safe-index wrappers are recovery primitives, not health probes; the design must keep those responsibilities separate.
- `.uv-cache` exclusion is already handled by the existing `IGNORE_DIRS_DEFAULT` guards in `cgc_safe_index.sh`, `cgc_index_repo.sh`, and `read-code.sh`; no new indexing-scope task is needed for that guard.
- What is still missing is edit-aware freshness: local file edits should invalidate the graph immediately and require patch/reindex before stale symbols can be trusted.

---

## Design-to-Tasking Contract

- Tasking must decompose from the design slices below, not invent a new architecture.
- Each task should preserve the domain/service/adapter split.
- Tasks must keep the CLI doctor and MCP health tool aligned on the same shared result contract.
- Tasks must not change existing `get_type` / `get_diagnostics` semantics unless the shared health seam requires a small integration hook.
- Tasks must include verification for the read-only health path, the safe recovery path, and the smoke command.
- Tasks must include verification for edit-aware freshness so local working-tree changes cannot keep serving stale graph answers.

---

## Decomposition-Ready Design Slices

| Slice | Files / Symbols | What Tasking Should Build | Verification Intent |
|-------|-----------------|---------------------------|---------------------|
| Shared health models and classifier | `src/mcp_codebase/health.py` -> `GraphHealthStatus`, `GraphHealthResult`, `GraphRecoveryHint`, `classify_graph_health()` | Create the shared status vocabulary and read-only health classification logic | Unit tests for all statuses and recovery hints |
| MCP health adapter | `src/mcp_codebase/server.py` -> new `get_graph_health` tool | Register a new health tool that serializes the shared result contract | MCP integration test and logging assertion |
| CLI doctor adapter | `src/mcp_codebase/doctor.py`, `scripts/cgc_doctor.sh` | Provide a direct operator command with deterministic exit codes and summary text | Subprocess / shell smoke test |
| Safe refresh / rebuild integration | `scripts/cgc_safe_index.sh`, `scripts/cgc_index_repo.sh` | Keep recovery atomic, preserve the last known good snapshot, and surface hints cleanly | Failure-mode recovery test |
| Edit-aware freshness / invalidation | `scripts/read-code.sh`, `scripts/cgc_safe_index.sh` | Detect local working-tree edits, mark the graph stale, and patch before stale symbols are served | Regression test proving local edits invalidate cached graph answers |
| Observability and reporting | `src/mcp_codebase/server.py`, `src/mcp_codebase/health.py` | Emit structured, parseable status and context for health checks | JSONL/logging assertions |
| Documentation and runbook updates | `specs/022-codegraph-hardening/quickstart.md` and related notes | Show how to run the doctor flow and recover safely | Manual review plus command smoke check |
