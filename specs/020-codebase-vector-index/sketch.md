# Sketch Blueprint — Codebase Vector Index

_Date: 2026-04-14_  
_Feature: `020-codebase-vector-index`_  
_Source Plan: `plan.md`_  
_Artifact: `sketch.md`_

## Feature Solution Frame

### Core Capability

Build a repo-local semantic vector index for Python symbols and markdown sections so agents can query the most relevant context with one targeted search instead of broad file scans.

### Current → Target Transition

Today `src/mcp_codebase` only exposes pyright-backed type and diagnostics tools plus doctor/health helpers. The target state adds a local semantic index inside the same package, backed by `.codegraphcontext/global/db/vector-index/`, with query, refresh, and staleness operations that preserve line-level provenance and update as files change.

### Dominant Execution Model

Extract -> normalize -> embed -> persist -> query -> refresh. Queries are read-only and return metadata-rich results from the last good snapshot; refresh is watcher-first with a post-commit fallback and uses atomic swap semantics so partial writes never become visible.

### Main Design Pressures

- Keep the index repo-local and non-networked.
- Preserve atomic refresh behavior and a queryable last-good snapshot.
- Return path/span/breadcrumb metadata that directly feeds read-code and read-markdown follow-up.

---

## Solution Narrative

The feature extends the existing `src/mcp_codebase` package with a dedicated vector-index subsystem. The new subsystem has four responsibilities: typed domain models for indexed content, Python and markdown extractors, a persistent Chroma-backed store with atomic refresh, and a tool surface that exposes query/status/refresh operations through the existing MCP server plus a thin CLI adapter for local operator workflows. Existing repo-local conventions are reused wherever possible: `config.py` supplies project-root behavior, `security.py` provides the path boundary pattern, and `.codegraphcontext/` remains the repository-local storage home. The finished solution should let an agent search for a concept, receive a ranked result with enough metadata to jump straight into `read_code_context` or `read_markdown_section`, and safely keep using the last good index while refresh work runs in the background.

---

## Construction Strategy

1. Define the vector-index domain models and config surface first so the persisted schema, freshness state, and query-result envelope are explicit before implementation begins.
2. Build the Python and markdown extractors next, normalizing source into stable `IndexableContentUnit` records with deterministic ids, hashes, provenance, and preview text.
3. Implement the store and refresh service on top of Chroma with staged writes, atomic swap, and staleness metadata so incremental updates can run without exposing partial state.
4. Expose the service through the existing MCP server and a thin CLI adapter (`python -m src.mcp_codebase.indexer`) so agent queries and local operator workflows share the same backend.
5. Add unit/integration regressions for build, query, refresh, staleness, interruption recovery, and markdown/code exclusion behavior, then update quickstart/docs to match the final entry points.

### Construction Notes

- Keep decision logic in the service layer; adapters should only translate IO.
- Query must remain non-blocking even while refresh is running.
- The store update path must remain idempotent by path/span or breadcrumb plus content hash.

---

## Acceptance Traceability

| Story / Requirement / Constraint | Design Element(s) That Satisfy It | Reuse / Modify / Create | Verification / Migration Note |
|----------------------------------|-----------------------------------|-------------------------|-------------------------------|
| FR-001 / FR-014: extract Python symbols, including no-docstring handling | `src/mcp_codebase/index/extractors/python.py`, `src/mcp_codebase/index/domain.py` | Create | Fixture-backed extractor tests on `src/` and `tests/`; no-docstring symbols must not fail. |
| FR-002 / FR-007: embed code bodies + markdown section text | `src/mcp_codebase/index/service.py`, `src/mcp_codebase/index/store/chroma.py` | Create | Verify embedding payload includes code body, docstring, and signature; markdown uses breadcrumb + content. |
| FR-003 / FR-008: persistent vector store + index metadata | `src/mcp_codebase/index/store/chroma.py`, `src/mcp_codebase/index/domain.py` | Create | Build metadata must record commit hash, timestamp, model id, and counts. |
| FR-004 / FR-005: semantic search with scope filter and top-K | `src/mcp_codebase/index/service.py`, `src/mcp_codebase/server.py` | Modify / Create | Query tests must verify code-only, markdown-only, and both-scope behavior. |
| FR-006: markdown section discovery | `src/mcp_codebase/index/extractors/markdown.py` | Create | Query results must include breadcrumb, section depth, and preview. |
| FR-009 / FR-010: incremental update + watcher/post-commit fallback | `src/mcp_codebase/index/watcher.py`, `src/mcp_codebase/index/service.py`, `src/mcp_codebase/indexer.py` | Create | Integration tests must prove changed files refresh and unchanged builds remain stable. |
| FR-011: staleness check | `src/mcp_codebase/index/service.py`, `src/mcp_codebase/server.py` | Modify / Create | Status output must report recorded commit vs HEAD and freshness state. |
| FR-012: no partial writes on failure | `src/mcp_codebase/index/store/chroma.py` | Create | Interrupted refresh tests must leave the previous snapshot active. |
| FR-013: exclude generated artifacts | `src/mcp_codebase/index/extractors/python.py`, `src/mcp_codebase/index/extractors/markdown.py` | Modify / Create | Tests must confirm `__pycache__`, `.pyc`, and configured exclude patterns are skipped. |

---

## Work-Type Classification

| Capability / Story Area | Work Type(s) | Dominant Pattern in Repo | Reuse-First / Extension-First / Net-New | Special Constraints |
|-------------------------|--------------|---------------------------|-----------------------------------------|--------------------|
| Python symbol indexing | extraction / storage / query | `src/mcp_codebase` service adapters | Net-New | Must keep file span and symbol type provenance. |
| Markdown section indexing | extraction / transformation / query | markdown read helper pattern | Net-New | Breadcrumb and preview must be deterministic. |
| Refresh and staleness | orchestration / lifecycle / state transition | doctor/health classification style | Extension-First | No partial writes; last-good snapshot remains active. |
| MCP + CLI exposure | API / contract shaping / orchestration | current MCP server registration pattern | Extension-First | Additive tool surface only; preserve existing pyright tools. |
| Testing / smoke coverage | testing / regression | current unit+integration+acceptance test style | Reuse-First | Deterministic PASS/FAIL oracles only. |

---

## Current-System Inventory

| Surface | Type | Role Today | Relationship to Feature | Condition | Primary Seam or Blast Radius Only |
|---------|------|------------|--------------------------|-----------|-----------------------------------|
| `src/mcp_codebase/server.py` | module | Registers existing MCP tools | Add new index tools without breaking current tools | Reusable but must be extended | Primary |
| `src/mcp_codebase/config.py` | module | Holds repo-root and pyright runtime config | Add index root/model/path settings | Extension-friendly | Primary |
| `src/mcp_codebase/security.py` | module | Validates file paths against project root | Reuse scope validation for index queries/builds | Reusable | Primary |
| `src/mcp_codebase/health.py` / `doctor.py` | modules | Graph-health and operator output patterns | Guide status/staleness reporting shape | Reusable patterns | Blast radius |
| `.codegraphcontext/` | storage home | Existing repo-local codegraph home | Persist vector index under same home | Reusable convention | Primary |
| `scripts/cgc_safe_index.sh` | script | Scoped safe indexing pattern | Operational fallback / pattern reference only | Reusable pattern | Blast radius |
| `scripts/read-markdown.sh` | script | Section-aware markdown reads | Consumer fallback for query results | Reusable pattern | Blast radius |
| `specs/020-codebase-vector-index/quickstart.md` | docs | Current local setup guide | Must match final storage path and CLI entry points | Needs update | Blast radius |

---

## Command / Script Surface Map

| Name | Owning File / Script / Template | Pipeline Role | Classification | Inputs | Outputs / Artifacts | Events | Extension Seam | Planned Change |
|------|---------------------------------|---------------|----------------|--------|----------------------|--------|----------------|----------------|
| `src/mcp_codebase` MCP server | `src/mcp_codebase/server.py` | Agent query surface | Hybrid | tool args, project root | query/status results | none | tool registration | Modify |
| Vector-index CLI | `src/mcp_codebase/indexer.py` | Local build/watch/query operator surface | Deterministic | subcommand, scope, query, top_k | index build/refesh status, query results | none | thin adapter to service | New |
| Repo-local index storage | `.codegraphcontext/global/db/vector-index/` | Derived state persistence | Deterministic | extracted units, metadata, embeddings | active collection + metadata sidecar | none | storage backend | New |
| Markdown read fallback | `scripts/read-markdown.sh` | Consumer fallback | Deterministic | file path, heading | section excerpt | none | read-after-query path | Reuse |
| Safe scoped indexing pattern | `scripts/cgc_safe_index.sh` | Operational fallback | Deterministic | scoped path | refreshed codegraph state | none | fallback pattern only | Reuse |

---

## CodeGraphContext Findings

### Seed Symbols

- `src/mcp_codebase/server.py:CodebaseLSPServer._register_tools` — current extension seam for adding new MCP tools.
- `src/mcp_codebase/config.py:PROJECT_ROOT` — existing pattern for local repo-root configuration.
- `src/mcp_codebase/security.py:validate_path` — boundary-validation pattern to reuse for query scope and file validation.
- `src/mcp_codebase/health.py:classify_graph_health` — reference for explicit state classification and status reporting.
- `src/mcp_codebase/doctor.py:build_parser` — operator-facing CLI pattern for status/readiness output.

### Primary Implementation Surfaces

| File | Symbol(s) | Why This Surface Is Primary | Planned Change Type |
|------|-----------|-----------------------------|---------------------|
| `src/mcp_codebase/index/domain.py` | `IndexScope`, `IndexableContentUnit`, `CodeSymbol`, `MarkdownSection`, `IndexMetadata`, `QueryResult` | Shared schema and lifecycle model for all indexed records | Create |
| `src/mcp_codebase/index/service.py` | `VectorIndexService`, `build_vector_index_service` | Orchestrates extraction, embedding, store writes, query, and staleness | Create |
| `src/mcp_codebase/index/store/chroma.py` | `ChromaIndexStore` | Owns atomic persistence and last-good snapshot semantics | Create |
| `src/mcp_codebase/index/extractors/python.py` | `extract_python_symbols` | Pulls symbol text, docstrings, and spans from `.py` files | Create |
| `src/mcp_codebase/index/extractors/markdown.py` | `extract_markdown_sections` | Pulls breadcrumbed markdown sections from docs | Create |
| `src/mcp_codebase/indexer.py` | `main` | Thin local build/watch/query CLI wrapper | Create |

### Secondary Affected Surfaces

| File / Surface | Why It Is Affected | Type of Impact |
|----------------|--------------------|----------------|
| `src/mcp_codebase/server.py` | New query/status/refresh MCP tools must be registered here | blast radius |
| `src/mcp_codebase/config.py` | Index storage path, model id, and watcher scope settings live here or in a new index config module | regression |
| `specs/020-codebase-vector-index/quickstart.md` | Quickstart must match the final storage path and entry points | docs |
| `tests/unit/` and `tests/integration/` | Needs coverage for query, refresh, staleness, and interruption recovery | regression |
| `scripts/read-markdown.sh` | Used as consumer fallback when a markdown query result points to a section | observability / operator |

### Caller / Callee / Dependency Notes

- `server.py` should call the vector-index service only through typed service methods, not through store internals.
- The service should call extractors and store adapters; extractors must not call the MCP server.
- Query results should point callers back to existing read-code/read-markdown workflows rather than broad file scanning.

### Missing Seams or Contradictions

- There is no current vector-index service or storage seam in `src/mcp_codebase`; the new package must be introduced.
- The plan/data-model/quickstart now agree on `.codegraphcontext/global/db/vector-index/`; the old `.codegraphcontext/db/chroma/` path was a contradiction and is now resolved.

---

## Blast Radius

### Direct Implementation Surfaces

- `src/mcp_codebase/index/domain.py`
- `src/mcp_codebase/index/service.py`
- `src/mcp_codebase/index/store/chroma.py`
- `src/mcp_codebase/index/extractors/python.py`
- `src/mcp_codebase/index/extractors/markdown.py`
- `src/mcp_codebase/indexer.py`
- `src/mcp_codebase/server.py`

### Indirect Affected Surfaces

- `src/mcp_codebase/config.py`
- `specs/020-codebase-vector-index/quickstart.md`
- `specs/020-codebase-vector-index/data-model.md`
- `tests/unit/`
- `tests/integration/`

### Regression-Sensitive Neighbors

- Existing MCP pyright tools in `type_tool.py` and `diag_tool.py`
- Existing health/doctor patterns in `health.py` and `doctor.py`
- Existing codegraph helper and markdown read fallback scripts

### Rollout / Compatibility Impact

- The new index tools are additive; existing `get_type` and `get_diagnostics` behavior must not change.
- The new CLI is optional and local-only; existing MCP startup remains the primary supported entry point.

### Operator / Runbook / Deployment Impact

- Quickstart and local operator instructions must mention the new storage path and the build/watch/query/status flow.
- No deployment topology change is expected; this remains a local developer-machine feature.

---

## Reuse / Modify / Create Matrix

### Reuse Unchanged

- `src/mcp_codebase/security.py` path validation pattern
- `scripts/read-markdown.sh`
- `scripts/cgc_safe_index.sh`
- `.codegraphcontext/` as the repo-local storage home

### Modify / Extend Existing

- `src/mcp_codebase/server.py` to register vector-index tools
- `src/mcp_codebase/config.py` to add index config and storage settings
- `specs/020-codebase-vector-index/quickstart.md` to match final entry points and storage path

### Compose from Existing Pieces

- The final query surface should compose `extractors -> service -> store -> MCP adapter`
- The CLI wrapper should be a thin adapter over the same `VectorIndexService`

### Create Net-New

- `src/mcp_codebase/index/domain.py`
- `src/mcp_codebase/index/service.py`
- `src/mcp_codebase/index/store/chroma.py`
- `src/mcp_codebase/index/extractors/python.py`
- `src/mcp_codebase/index/extractors/markdown.py`
- `src/mcp_codebase/indexer.py`
- Integration tests for query/build/refresh/recovery behavior

### Reuse Rationale

This mix keeps the change inside the existing `src/mcp_codebase` package and local repo conventions, while introducing only the minimum new seams needed for a real semantic index. The feature gets typed models, atomic persistence, and a stable tool surface without creating a new backend service or duplicating the existing MCP entrypoint.

---

## Manifest Alignment Check

| Affected Command / Phase | Existing Manifest Coverage? | New Artifact Needed? | New Event / Field Needed? | Handoff / Event Flow Impact | Status |
|--------------------------|-----------------------------|----------------------|---------------------------|-----------------------------|--------|
| `src/mcp_codebase` runtime surface | Partial | `src/mcp_codebase/indexer.py`, `src/mcp_codebase/index/*` | No | Existing `mcp_codebase` component in the catalog remains valid; the feature adds runtime tools only | Aligned |

### Manifest Alignment Notes

- No `command-manifest.yaml` change is required for the feature itself.
- The only manifest wiring touched during this cycle was the repo-wide `speckit.planreview` scaffold support, which is unrelated to the feature implementation.

---

## Architecture Flow Delta

- **No Architecture Flow delta**

### Delta Summary

The plan-level Architecture Flow remains correct. The sketch only refines the internal module boundary inside the existing local MCP package and adds a thin local CLI adapter for operator convenience.

### Added / Refined Nodes, Edges, or Boundaries

| Change | Why Needed at LLD Level | Must Preserve in Tasking / Implementation |
|--------|--------------------------|-------------------------------------------|
| New `src/mcp_codebase/index/` service/adapters package | The plan needs concrete seams for extraction, embedding, storage, query, and refresh | Keep the flow local, repo-scoped, and atomic |
| Optional `src/mcp_codebase/indexer.py` CLI adapter | Quickstart and local smoke tests need a reproducible operator entry point | Keep it thin and service-backed |

---

## Component and Boundary Design

| Component / Boundary | Responsibility | Owning or Likely Touched File(s) | Likely Touched Symbol(s) | Reuse / Modify / Create | Inbound Dependencies | Outbound Dependencies |
|----------------------|----------------|----------------------------------|--------------------------|-------------------------|---------------------|----------------------|
| Domain models | Typed record and freshness schemas | `src/mcp_codebase/index/domain.py` | `IndexScope`, `IndexableContentUnit`, `CodeSymbol`, `MarkdownSection`, `IndexMetadata`, `QueryResult` | Create | plan/spec/data-model | service, store, tests |
| Python extractor | Parse `.py` files into symbol units | `src/mcp_codebase/index/extractors/python.py` | `extract_python_symbols` | Create | domain models, security boundary | service, tests |
| Markdown extractor | Parse markdown sections into section units | `src/mcp_codebase/index/extractors/markdown.py` | `extract_markdown_sections` | Create | domain models | service, tests |
| Vector store / refresh boundary | Stage, write, and atomically swap index state | `src/mcp_codebase/index/store/chroma.py`, `src/mcp_codebase/index/service.py` | `ChromaIndexStore`, `VectorIndexService.build_full_index`, `VectorIndexService.refresh_changed_files` | Create | extractors, domain models, config | MCP adapter, CLI, tests |
| MCP tool adapter | Expose search/status/refresh operations | `src/mcp_codebase/server.py` | `register_vector_index_tools` | Modify | service | agents, integration tests |
| CLI adapter | Local build/watch/query/status commands | `src/mcp_codebase/indexer.py` | `main` | Create | service | operator workflow, quickstart |

### Control Flow Notes

- Queries should hit the service immediately and read from the last good snapshot; they must not wait for refresh to finish.
- Refresh should be single-flight per checkout and should coalesce duplicate watcher events.

### Data Flow Notes

- Extracted units are normalized into stable ids and content hashes before embedding.
- Persistent writes must stage all new records before swapping the active snapshot and updating metadata.

---

## Interface, Symbol, and Contract Notes

### Public Interfaces and Contracts

| Interface / Contract | Purpose | Owner | Validation Point | Failure / Error Shape |
|----------------------|---------|-------|------------------|-----------------------|
| `IndexScope` enum | Query scope contract (`code`, `markdown`, `both`) | `src/mcp_codebase/index/domain.py` | Input validation at service boundary | invalid-argument envelope |
| `CodeSymbol` / `MarkdownSection` / `IndexMetadata` / `QueryResult` models | Persistent record and query contract | `src/mcp_codebase/index/domain.py` | Model validation on ingest and response | typed model validation errors |
| `VectorIndexService` | Orchestrates build, refresh, query, and status | `src/mcp_codebase/index/service.py` | Service tests and MCP adapter tests | `QUERY_FAILED`, `INDEX_STALE`, `INDEX_UNAVAILABLE`, or structured validation error |
| `ChromaIndexStore` | Atomic persistence / snapshot swap | `src/mcp_codebase/index/store/chroma.py` | Integration tests against staged writes | retain prior snapshot; fail active op |

### New or Changed Public Symbols

| Symbol | Exact Intended Signature | Layer / Module | Responsibility | Notes |
|--------|---------------------------|----------------|----------------|------|
| `IndexScope` | `class IndexScope(StrEnum): ...` | domain | Scope enum for query filtering | values: `code`, `markdown`, `both` |
| `CodeSymbol` | `class CodeSymbol(BaseModel): ...` | domain | Python symbol record | stable id + provenance |
| `MarkdownSection` | `class MarkdownSection(BaseModel): ...` | domain | Markdown section record | breadcrumb + preview |
| `IndexMetadata` | `class IndexMetadata(BaseModel): ...` | domain | Freshness and build snapshot | source of truth for staleness |
| `QueryResult` | `class QueryResult(BaseModel): ...` | domain | Ranked query response | actionably points to read target |
| `VectorIndexService` | `class VectorIndexService: ...` | service | Build/refresh/query/status orchestration | core LLD seam |
| `build_vector_index_service` | `def build_vector_index_service(*, project_root: Path, storage_path: Path | None = None, embedding_model_id: str | None = None) -> VectorIndexService` | service | Factory for configured service | used by MCP and CLI adapters |
| `register_vector_index_tools` | `def register_vector_index_tools(mcp: FastMCP, service: VectorIndexService) -> None` | adapter | Wire MCP tool handlers | additive tool registration |
| `main` | `def main() -> None` | adapter | CLI entry point for build/watch/query/status | thin wrapper only |

### Ownership Boundaries

- Domain models own validation and typed state, not IO.
- Service code owns decisions and sequencing, not file parsing or vector-store internals.
- Adapters own IO only: file system, embeddings, Chroma, and MCP tool registration.

---

## State / Lifecycle / Failure Model

### State Authority

| State / Field / Lifecycle Area | Authoritative Source | Reconciliation Rule | Notes |
|--------------------------------|----------------------|---------------------|------|
| Source file content | Repo working tree | Reparse on change, path exclude, and content-hash compare | Files are authoritative |
| Index freshness / `head_commit` | `IndexMetadata` persisted with the active snapshot | Compare current HEAD and content hashes before trusting results | Derived state only |
| Vector records | Active Chroma snapshot | Refresh uses staged writes and atomic swap | Last good snapshot remains queryable |
| Query results | Vector search over active snapshot | Include freshness metadata and provenance so callers can decide whether to refresh | Derived and ephemeral |

### Lifecycle / State Transitions

| Transition | Allowed? | Trigger | Validation / Guard | Failure Handling |
|------------|----------|---------|--------------------|------------------|
| missing -> building | Yes | full build starts | refresh lock acquired | keep no active snapshot until success |
| building -> current | Yes | staged write commits atomically | all units embedded and written | persist metadata and release lock |
| current -> stale | Yes | repo files change or HEAD advances | content hash / commit check | keep active snapshot, mark stale |
| stale -> refreshing | Yes | watcher or manual refresh begins | single-flight lock acquired | refresh proceeds against changed paths |
| refreshing -> current | Yes | refresh completes successfully | atomic swap of staged snapshot | update metadata and freshness |
| refreshing -> failed | Yes | error or interruption occurs | previous snapshot remains intact | return error, preserve last good snapshot |

### Retry / Replay / Ordering / Cancellation

- Retry behavior: refresh retries only bounded, idempotent steps; rebuild from the repo source tree if the active snapshot is missing or corrupt.
- Duplicate / replay handling: watcher events coalesce; duplicate file-change notifications must not create duplicate records.
- Out-of-order handling: later content-hash wins only after successful atomic swap; stale intermediate updates never become active.
- Cancellation / timeout behavior: cancel the refresh work but keep the prior snapshot queryable.

### Degraded Modes / Fallbacks / Recovery

- Queries continue against the last good snapshot while refresh runs.
- If the index is stale, status must report staleness rather than silently hiding it.
- If refresh fails, recovery is a rebuild from source files into a new staged snapshot.

---

## Non-Functional Design Implications

| Concern | Design Implication | Affected Surface(s) | Notes |
|---------|--------------------|---------------------|-------|
| Latency | Query path should be low-latency and read-only | service, store, MCP tools | avoid broad file scans on query |
| Throughput / concurrency | Refresh must be single-flight and bounded | watcher, service, store | no orphan background tasks |
| Observability | Build/query/refresh must emit structured state and freshness signals | service, server, CLI | support diagnosis of stale or failed refreshes |
| Security | Validate untrusted query/path inputs at boundaries | security, service, MCP adapters | local-only, no secrets or external ingress |
| Rollout / config | Additive tools and safe defaults only | config, server, quickstart | preserve existing pyright workflows |
| Config | Repo-root path, storage path, and model id must be explicit and deterministic | config, quickstart | no hidden environment dependence |

---

## Human-Task and Operator Boundaries

| Boundary | Why Human / Operator Action Is Required | Preconditions | Artifact / Evidence Consumed | Downstream `[H]` Implication | Failure / Escalation Path |
|----------|-----------------------------------------|---------------|------------------------------|------------------------------|---------------------------|
| No external human task identified | All setup is local and automated; the feature does not depend on a third-party UI or credentialed external system | repo checkout + `uv sync` + local storage path | `spec.md`, `plan.md`, `quickstart.md` | No `[H]` tasks expected in tasking | If local install fails, retry with local tooling; no external escalation |

---

## Verification Strategy

### Unit-Testable Seams

- Python symbol extraction normalization
- Markdown section extraction and breadcrumb generation
- Query-scope validation and top-K handling
- Staleness classification and metadata serialization

### Contract Verification Needs

- Query result schema must always include path/span or breadcrumb plus freshness metadata.
- Invalid query args must fail closed with a structured error envelope.
- Index metadata must include commit hash, timestamp, model id, and counts.

### Integration / Reality-Check Paths

- Build an index over representative repo fixtures.
- Query a known symbol and confirm the top result contains file path + line range.
- Query a markdown topic and confirm breadcrumb + preview are returned.
- Edit one file, trigger refresh, and confirm the new result is surfaced.
- Interrupt refresh and confirm the previous snapshot remains queryable.

### Lifecycle / Retry / Duplicate Coverage Needs

- Duplicate watcher events must not duplicate records.
- Cancelled refresh must leave no partial writes visible.
- Failed refresh must not invalidate the last good snapshot.

### Deterministic Oracles (if known)

- Top result must expose a direct read target (`file_path` + `line_start`/`line_end` or breadcrumb).
- Staleness status must compare current HEAD against the recorded build commit.
- Interrupted refresh must leave the pre-existing query result unchanged.

### Regression-Sensitive Areas

- Symbols with no docstring
- Empty or malformed query strings
- Excluded generated artifacts (`__pycache__`, `.pyc`, configured exclude patterns)
- Markdown sections with nested headings

---

## Domain Guardrails

| Domain | Why Touched | MUST Constraints | Forbidden Shortcuts | Invariants to Preserve |
|--------|-------------|------------------|---------------------|------------------------|
| 02 Data modeling | New indexed entities and freshness state | explicit source of truth per field; typed finite states; derived fields not authoritative | free-text statuses, implicit nullable defaults | stable ids, typed records, explicit freshness |
| 03 Data storage | Persistent local vector store and snapshot swap | atomic multi-write transactions; idempotent refresh; no partial writes | overwrite active snapshot before staging completes | last good snapshot remains queryable |
| 04 Caching & performance | Query acceleration and staleness semantics | cache is not source of truth; explicit staleness/invalidation; bounded growth | serving stale results without freshness metadata | query remains read-only and bounded |
| 07 Compute & orchestration | Watcher-driven refresh and local CLI work | explicit lifecycle, bounded concurrency, no orphan tasks | fire-and-forget refresh jobs | start/ready/cancel/shutdown all explicit |
| 09 Environment & config | Repo-root, storage path, model settings | deterministic config precedence; safe defaults | hidden env-only runtime forks | config is validated and local-safe |
| 10 Observability | Build/query/refresh telemetry | structured logs, correlation ids, actionable failure context | silent refresh/query failures | freshness and latency are observable |
| 11 Resilience | Refresh failure recovery | fail closed on ambiguous state; recovery documented and testable | replacing last-good snapshot with partial writes | degraded mode stays queryable |
| 12 Testing | Core feature regressions | deterministic PASS/FAIL oracles and reality-check tests | manual-only verification for critical paths | every bug class has a regression test |
| 14 Security controls | Untrusted file/query inputs | validate inputs at boundary; local-only; least privilege | path traversal, raw internal errors | no secrets, no internal leakage |
| 16 Ops & governance | Docs, runbooks, feature closeout | documentation as a deliverable; explicit ownership | undocumented operator flow | quickstart and recovery guidance stay versioned |
| 17 Code patterns | New modules and public symbols | layered placement; no IO in domain; signatures first | god-modules or mixed IO/decision layers | domain/service/adapter split remains clean |

---

## LLD Decision Log

| Subject | Status | Rationale | Downstream Implication | May Tasking Proceed? |
|---------|--------|-----------|------------------------|----------------------|
| Local persistence path | Decided | `.codegraphcontext/global/db/vector-index/` is the stable repo-local home for the active collection | Tasking can target a fixed storage path and metadata sidecar | Yes |
| Parser family | Decided | Tree-sitter for Python, markdown-it-py for markdown | Extractor tasks can be concrete and repo-grounded | Yes |
| Embedding runtime | Decided | fastembed stays local and satisfies the phase-1 requirement | No external API dependency is introduced | Yes |
| Refresh trigger | Decided | watchdog is primary, post-commit is fallback | Tasking must include watcher and fallback refresh coverage | Yes |
| Runtime surface | Decided | MCP tools are primary; CLI is a thin local adapter over the same service | Tasking should keep the service reusable from both paths | Yes |
| Exact module layout | Assumed | `src/mcp_codebase/index/` for domain/service/store/extractors plus `src/mcp_codebase/indexer.py` | Tasking should use these seams unless a stronger repo contradiction appears | Conditional |

---

## Design Gaps and Repo Contradictions

### Missing Seams

- No vector-index service, extractor, store, or watcher module exists yet in `src/mcp_codebase`.
- No MCP query/status/refresh tools exist for the semantic index yet.

### Unsupported Assumptions

- The local embedding cache and model warm-up are assumed to be installable via `uv sync` without external operator setup.
- The CLI adapter is assumed to be thin and service-backed, not a second implementation path.

### Plan vs Repo Contradictions

- The feature docs now consistently say `.codegraphcontext/global/db/vector-index/`; the earlier `.codegraphcontext/db/chroma/` wording was a contradiction and has been corrected.
- The current `src/mcp_codebase` package only exposes pyright tools; the vector index will add new tools rather than modifying type/diagnostic semantics.

### Blocking Design Issues

- None remaining after the storage-path correction and the explicit service/adapter split.

---

## Design-to-Tasking Contract

Tasking must follow these rules:

- Every decomposition-ready design slice must produce at least one task unless an explicit omission rationale is recorded.
- No task may introduce scope, seams, symbols, interfaces, or artifacts absent from this sketch without explicit rationale.
- `[H]` tasks may only come from identified human/operator boundaries or explicit external dependency constraints.
- `file:symbol` annotations in tasks must trace back to symbol targets or symbol-creation notes in this sketch.
- Acceptance artifacts must derive from the verification intent and acceptance traceability in this sketch.
- Large-point tasks that require later breakdown must preserve the originating design slice and its safety invariants.

### Additional Tasking Notes

- Keep extractor logic pure and adapter IO isolated.
- Use the same service from both the MCP tool surface and the CLI wrapper.
- Treat `scripts/cgc_safe_index.sh` and `scripts/read-markdown.sh` as fallback patterns, not primary feature code.

---

## Decomposition-Ready Design Slices

### Slice 1: Domain models and index config

**Objective**  
Define the typed schema, freshness states, and repo-local index configuration before any extraction or persistence logic is built.

**Touched Files**  
- `src/mcp_codebase/index/domain.py`
- `src/mcp_codebase/index/config.py`
- `src/mcp_codebase/config.py`

**Touched Symbols**  
- `src/mcp_codebase/index/domain.py:IndexScope`
- `src/mcp_codebase/index/domain.py:IndexableContentUnit`
- `src/mcp_codebase/index/domain.py:CodeSymbol`
- `src/mcp_codebase/index/domain.py:MarkdownSection`
- `src/mcp_codebase/index/domain.py:IndexMetadata`
- `src/mcp_codebase/index/domain.py:QueryResult`
- `src/mcp_codebase/index/config.py:IndexConfig`
- `src/mcp_codebase/index/config.py:build_default_index_config`

**Likely Net-New Files**  
- `src/mcp_codebase/index/domain.py`
- `src/mcp_codebase/index/config.py`

**Primary Seam**  
Data modeling and configuration.

**Blast-Radius Neighbors**  
- `src/mcp_codebase/server.py`
- `specs/020-codebase-vector-index/data-model.md`
- `specs/020-codebase-vector-index/quickstart.md`

**Reuse / Modify / Create Classification**  
Create

**Required Public Symbols / Interfaces**  
- `IndexScope`
- `CodeSymbol`
- `MarkdownSection`
- `IndexMetadata`
- `QueryResult`
- `IndexConfig`

**Major Constraints**  
- Every field must have an explicit source of truth.
- State/freshness values must remain finite and typed.

**Dependencies on Other Slices**  
- None.

**Likely Verification / Regression Concern**  
Schema validation, deterministic ids, and freshness serialization.

### Slice 2: Python and markdown extractors

**Objective**  
Extract code symbols and markdown sections into normalized content units with provenance, content hashes, and previews.

**Touched Files**  
- `src/mcp_codebase/index/extractors/python.py`
- `src/mcp_codebase/index/extractors/markdown.py`

**Touched Symbols**  
- `src/mcp_codebase/index/extractors/python.py:extract_python_symbols`
- `src/mcp_codebase/index/extractors/markdown.py:extract_markdown_sections`

**Likely Net-New Files**  
- `src/mcp_codebase/index/extractors/python.py`
- `src/mcp_codebase/index/extractors/markdown.py`

**Primary Seam**  
Source ingestion and normalization.

**Blast-Radius Neighbors**  
- `src/mcp_codebase/security.py`
- `specs/020-codebase-vector-index/quickstart.md`
- `tests/unit/`

**Reuse / Modify / Create Classification**  
Create

**Required Public Symbols / Interfaces**  
- `extract_python_symbols`
- `extract_markdown_sections`

**Major Constraints**  
- Exclude generated artifacts and configured exclude patterns.
- Do not fail when a symbol has no docstring.

**Dependencies on Other Slices**  
- Slice 1.

**Likely Verification / Regression Concern**  
Nested headings, malformed source, and no-docstring symbols.

### Slice 3: Vector store and atomic refresh service

**Objective**  
Persist vectors and metadata on disk, implement query/status/refresh behavior, and preserve the last good snapshot on failure.

**Touched Files**  
- `src/mcp_codebase/index/store/chroma.py`
- `src/mcp_codebase/index/service.py`

**Touched Symbols**  
- `src/mcp_codebase/index/store/chroma.py:ChromaIndexStore`
- `src/mcp_codebase/index/service.py:VectorIndexService`
- `src/mcp_codebase/index/service.py:build_vector_index_service`

**Likely Net-New Files**  
- `src/mcp_codebase/index/store/chroma.py`
- `src/mcp_codebase/index/service.py`

**Primary Seam**  
Atomic persistence and lifecycle orchestration.

**Blast-Radius Neighbors**  
- `src/mcp_codebase/server.py`
- `.codegraphcontext/global/db/vector-index/`
- `tests/integration/`

**Reuse / Modify / Create Classification**  
Create

**Required Public Symbols / Interfaces**  
- `ChromaIndexStore`
- `VectorIndexService`
- `build_vector_index_service`

**Major Constraints**  
- No partial writes.
- Query must remain non-blocking while refresh runs.
- Idempotent refresh by content hash plus path/span or breadcrumb.

**Dependencies on Other Slices**  
- Slice 1.
- Slice 2.

**Likely Verification / Regression Concern**  
Interrupted refresh, stale metadata, and atomic swap correctness.

### Slice 4: MCP and CLI adapter surface

**Objective**  
Expose search/status/refresh operations through the existing MCP server and a thin local CLI wrapper without changing the existing pyright tools.

**Touched Files**  
- `src/mcp_codebase/server.py`
- `src/mcp_codebase/indexer.py`
- `src/mcp_codebase/__main__.py`

**Touched Symbols**  
- `src/mcp_codebase/server.py:register_vector_index_tools`
- `src/mcp_codebase/indexer.py:main`

**Likely Net-New Files**  
- `src/mcp_codebase/indexer.py`

**Primary Seam**  
Agent/operator tool surface.

**Blast-Radius Neighbors**  
- `src/mcp_codebase/type_tool.py`
- `src/mcp_codebase/diag_tool.py`
- `specs/020-codebase-vector-index/quickstart.md`

**Reuse / Modify / Create Classification**  
Modify / Create

**Required Public Symbols / Interfaces**  
- `register_vector_index_tools`
- `main`

**Major Constraints**  
- Keep the existing pyright tools intact.
- The adapter layer must stay thin and delegate all decisions to the service.

**Dependencies on Other Slices**  
- Slice 1.
- Slice 2.
- Slice 3.

**Likely Verification / Regression Concern**  
Tool registration, response envelopes, and CLI entry-point parity.

### Slice 5: Tests, docs, and fallback integration

**Objective**  
Lock the behavior with deterministic unit and integration coverage and update the quickstart so the final local workflow is reproducible.

**Touched Files**  
- `tests/unit/test_vector_index_*.py`
- `tests/integration/test_codebase_vector_index.py`
- `specs/020-codebase-vector-index/quickstart.md`

**Touched Symbols**  
- test functions for build/query/refresh/staleness/recovery

**Likely Net-New Files**  
- `tests/unit/test_vector_index_*.py`
- `tests/integration/test_codebase_vector_index.py`

**Primary Seam**  
Regression and operator validation.

**Blast-Radius Neighbors**  
- `scripts/read-markdown.sh`
- `scripts/cgc_safe_index.sh`
- `specs/020-codebase-vector-index/data-model.md`

**Reuse / Modify / Create Classification**  
Create / Modify

**Required Public Symbols / Interfaces**  
- deterministic fixtures and oracles only

**Major Constraints**  
- Every bug class needs a regression test.
- Tests must stay deterministic and not rely on external services.

**Dependencies on Other Slices**  
- Slice 1.
- Slice 2.
- Slice 3.
- Slice 4.

**Likely Verification / Regression Concern**  
Top-result correctness, refresh after edit, and interrupted-build preservation.

---

## Sketch Completion Summary

### Review Readiness

- [x] The solution narrative is clear
- [x] The construction strategy is coherent
- [x] Acceptance traceability is complete
- [x] Touched files and symbols are concrete enough for tasking
- [x] Reuse / modify / create choices are explicit
- [x] Manifest alignment is explicit where relevant
- [x] Human-task boundaries are explicit where relevant
- [x] Verification intent is sufficient for downstream artifact generation
- [x] Domain MUST rules are preserved
- [x] No blocking design contradiction remains unresolved

### Suggested Next Step

`/speckit.solutionreview`
