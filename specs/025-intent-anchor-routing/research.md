# Research: Read-Code Anchor Output Simplification

Investigation of prior art, integration patterns, and reusable code/packages that can reduce scope.

---

## Zero-Custom-Server Assessment

The feature can stay inside the existing repo and reuse the current read-code helper plus the vector index. No new custom server is required for the narrowed scope.

| Option | FRs covered | How it works | Gap (uncovered FRs) |
|--------|-------------|--------------|---------------------|
| Existing read-code helper + AGENTS guidance + local vector index | FR-001, FR-002, FR-003, FR-004, FR-005 | Agents consult `AGENTS.md`, use `scripts/read-code.sh`/`scripts/read_code.py`, and consume indexed symbol metadata from the local vector store. | Needs the documented 5-item shortlist, one bounded expansion rule, and body-first preference made explicit. Current helper still returns one best anchor by default. |

---

## Repo Assembly Map

Assemble pieces from the current repository to cover the feature.

| Source (owner/repo) | File(s) to copy/adapt | FRs covered | Notes |
|---------------------|----------------------|-------------|-------|
| `aborczuk/app-foundation` | `AGENTS.md`, `scripts/read-code.sh` | FR-001, FR-005 | `AGENTS.md` already defines code-file read efficiency, bounded reads, and the rule to use `read_code_context`/`read_code_window` before seam anchoring. Last upstream commit on `main`: `2026-04-20`; public repo. |
| `aborczuk/app-foundation` | `scripts/read_code.py` | FR-002, FR-003, FR-004, FR-005 | Existing logic already ranks vector hits, enforces bounded windows, and consults the local vector index with `--top-k 5`; needs shortlist/expansion semantics and body-first preference surfaced to the agent. |
| `aborczuk/app-foundation` | `src/mcp_codebase/index/domain.py` | FR-003 | `CodeSymbol.body` and `QueryResult.body` already carry full body text, so body-return can reuse existing indexed data instead of introducing a new storage shape. |
| `aborczuk/app-foundation` | `src/mcp_codebase/indexer.py` | FR-004 | The indexer already exposes query top-k controls and defaults; the read-code path can widen retrieval without changing index storage. |

**After assembly**: which FRs remain uncovered and require net-new code?
- FR-001: needs explicit AGENTS-facing read-code guidance wording for the new shortlist/body-first contract.
- FR-002: needs multi-candidate return instead of a single best anchor.
- FR-003: needs a first-class body-return path and documentation that it is preferred when confident body text is available.
- FR-004: needs the read-code retrieval default raised to a bounded `top_k = 20`.
- FR-005: needs documentation of the first 5-candidate shortlist and one bounded follow-up expansion step.

---

## Package Adoption Options

No external package adoption is needed for this feature. The current implementation can reuse the existing in-repo vector index and read-code helper without introducing a new third-party dependency.

| Package | Version | FRs covered | Integration effort | Installability check |
|---------|---------|-------------|-------------------|---------------------|
| None | n/a | n/a | n/a | Not applicable; no new package is required for the narrowed scope. |

---

## Conceptual Patterns

- **Pattern**: Two-stage retrieval + rerank — retrieve more candidates than you return, then rerank a bounded shortlist — covers: FR-002, FR-004, FR-005 — requires custom server: no
  - Source: https://docs.topk.io/concepts/reranking
- **Pattern**: Query `topk` plus rerank with `topk_multiple` — retrieve `2x` the final count, rerank, and return a bounded top set — covers: FR-002, FR-004, FR-005 — requires custom server: no
  - Source: https://docs.topk.io/documents/query
- **Pattern**: Standard two-stage retrieval with reranking in RAG systems — retrieve a larger pool, rerank it, and expose only the top `N` to the caller — covers: FR-002, FR-005 — requires custom server: no
  - Source: https://www.pinecone.io/learn/series/rag/rerankers/
- **Pattern**: Passage retrieval from indexed content — store full content passages and retrieve the body directly when the passage is the right answer unit — covers: FR-003 — requires custom server: no
  - Source: https://docs.coveo.com/en/oaod5329/passage-retrieval-cpr-content-requirements-and-best-practices

---

## Search Tools Used

- Code Discovery: `uv run cgc find pattern -- "read_code_context"`, `uv run cgc find pattern -- "body"`, `uv run cgc find pattern -- "AGENTS.md"`, `uv run cgc find pattern -- "top_k"`
- Package Discovery: Not applicable; no external package adoption candidate was identified for this scope.
- Conceptual Patterns: WebSearch queries `retrieval reranking top k confidence standard pattern documentation` and `full passage vs snippet retrieval best practices documentation`; Web results reviewed from TopK, Pinecone, and Coveo.
- Local Context Mapping: `AGENTS.md`, `scripts/read-code.sh`, `scripts/read_code.py`, `src/mcp_codebase/index/domain.py`, `src/mcp_codebase/indexer.py`, `specs/025-intent-anchor-routing/spec.md`
- Repo Metadata: GitHub connector repo lookup for `aborczuk/app-foundation`; local `git log origin/main -1 --format=%cs`

---

## Unanswered Questions

- What numeric confidence threshold should trigger body-first output for a symbol hit?
- Should the one-time extra candidate batch always be a fixed 5 results, or should it be configurable within a hard cap?
