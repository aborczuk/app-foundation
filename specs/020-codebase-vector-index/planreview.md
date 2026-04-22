# Plan Review — Codebase Vector Index

_Date: 2026-04-14_  
_Feature: `020-codebase-vector-index`_  
_Review Artifact: `planreview.md`_

## Executive Summary

**Review Status:** `PASS WITH NOTES`  
**Questions Asked:** `0`  
**Open Feasibility Questions:** `0`

### Summary

The plan is technically precise enough to proceed to sketch. The main plan-level ambiguities were already resolved in `plan.md` (parser family, embedding runtime, local on-disk persistence path, and watcher-first refresh model), and there are no blocking feasibility questions remaining.

---

## Catalog Cross-Reference

No external service nodes appear in the Architecture Flow, so `catalog.yaml` is not materially in scope for this feature.

### Catalog Notes

- Local vector-index storage and refresh are repo-local concerns rather than catalogued external services.
- No new catalog-entry task is required at this stage.

---

## Ambiguity Findings

| Finding ID | Category | Severity | Location | Question / Gap | Recommended Resolution | Story Point Impact | Status |
|------------|----------|----------|----------|----------------|------------------------|-------------------|--------|
| PR-001 | Behavior Map | LOW | `plan.md` Behavior Map Sync Gate | The repository-local storage target in the behavior map still referenced the older `.codegraphcontext/db/chroma/` path while the Technical Context and Handoff Contract use `.codegraphcontext/global/db/vector-index/`. | Update the behavior-map target to `.codegraphcontext/global/db/vector-index/` so the plan is internally consistent. | +0 pts | Resolved |

---

## Domain Coverage

| Domain | Touched | Core Principles Addressed | Gaps Found |
|--------|---------|---------------------------|------------|
| 01 API & integration | No | N/A | None |
| 02 Data modeling | Yes | ✅ | None |
| 03 Data storage | Yes | ✅ | None |
| 04 Caching & performance | Yes | ✅ | None |
| 05 Client/UI | No | N/A | None |
| 06 Edge & delivery | No | N/A | None |
| 07 Compute & orchestration | Yes | ✅ | None |
| 08 Networking | No | N/A | None |
| 09 Environment & config | Yes | ✅ | None |
| 10 Observability | Yes | ⚠️ | The plan does not yet spell out structured logging/latency/error/throughput expectations for the query and refresh paths. |
| 11 Resilience | Yes | ✅ | None |
| 12 Testing | Yes | ✅ | None |
| 13 Identity & access | No | N/A | None |
| 14 Security controls | Yes | ✅ | None |
| 15 Build & deployment | No | N/A | None |
| 16 Ops & governance | Yes | ✅ | None |
| 17 Code patterns | Yes | ✅ | None |

### Domain Coverage Notes

- No hard-block domain issues remain.
- Observability is a deferred risk to capture in sketch/tasking rather than a plan blocker.

---

## Pipeline Architecture Review

### Repeated Architectural Unit Recognition

**Status:** `PASS`  
**Assessment:** The recurring `IndexableContentUnit` abstraction is clearly defined and stable enough for tasking.

### Pipeline Architecture Model

**Status:** `PASS`  
**Assessment:** Stage boundaries, ownership, and event flow are explicit enough to support deterministic task decomposition.

### Artifact / Event Contract Architecture

**Status:** `PASS`  
**Assessment:** Producers, consumers, templates, and emitted events are clear enough for downstream command ownership.

### Architecture Review Notes

- The storage-path mismatch in the behavior-map gate was resolved in-place during review.
- The plan already commits to local-only, repo-scoped state with watcher-first refresh and atomic swaps.

---

## Handoff-to-Sketch Review

### Status

`PASS WITH NOTES`

### Settled by Plan

- The index is local-only and repo-scoped.
- Tree-sitter is the phase-1 parser for Python symbols.
- `markdown-it-py` is the phase-1 parser for markdown sections.
- `fastembed` provides local embeddings.
- Chroma persists on disk under the repo-local codegraph home.
- Watchdog is the default refresh trigger, with post-commit as fallback.

### Sketch Must Preserve

- The local-only trust boundary.
- The on-disk persistence model.
- The metadata-rich query result contract.
- The watcher-first refresh behavior.
- The atomic no-partial-write requirement.

### Sketch May Extend

- Exact module names inside `src/mcp_codebase`.
- Exact query tool names and CLI entry points.
- The precise metadata sidecar file format.
- Fixture layout and test split.

### Handoff Gaps

- Structured observability expectations are implied but not yet spelled out in enough detail for the sketch to treat them as a hard contract.

---

## Resolved Clarifications

| Clarification ID | Question | Accepted Answer | Files Updated | Impact |
|------------------|----------|-----------------|--------------|--------|
| C-001 | Should the index persist on disk or in memory? | Persist on disk in the repo-local codegraph home. | `plan.md`, `research.md` | Makes refresh and restart behavior deterministic. |
| C-002 | Which parser families should phase 1 standardize on? | Tree-sitter for Python and markdown-it-py for markdown. | `plan.md`, `research.md` | Locks the extraction model for tasking. |
| C-003 | Which refresh trigger should be primary? | Watchdog filesystem watcher, with post-commit fallback. | `plan.md`, `research.md` | Defines the lifecycle model for incremental refresh. |

---

## Open Feasibility Questions

### Status

`Empty`

### Count

`0`

---

## Final Status

### Files Updated

- `specs/020-codebase-vector-index/plan.md`
- `specs/020-codebase-vector-index/planreview.md`

### Deferred Items

- Structured observability expectations for the query/refresh paths.

### Risks to Sketch / Task Generation

- Observability details may need to be made explicit in sketch or tasking so runtime logs/metrics remain traceable.

### Recommended Next Step

- `/speckit.solution`
