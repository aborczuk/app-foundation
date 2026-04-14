# Research: Codebase Vector Index

Investigation of prior art, integration patterns, and reusable code/packages that can reduce scope.

---

## Zero-Custom-Server Assessment

What no-server integration options exist? For each, which FRs does it cover?

| Option | FRs covered | How it works | Gap (uncovered FRs) |
|--------|-------------|--------------|---------------------|
| Local embedded index pipeline | FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, FR-011, FR-012, FR-013, FR-014 | Keep parsing, embeddings, storage, query, staleness, and refresh logic local to the repo using embedded libraries plus a local vector DB. | Still needs repo-specific glue for exact parser selection, atomic update semantics, and the final query/reporting surface. |

---

## Repo Assembly Map

Assemble pieces from multiple repositories to cover all FRs. Each row = one repo/file that covers one or more FRs.

| Source (owner/repo) | File(s) to copy/adapt | FRs covered | Notes |
|---------------------|----------------------|-------------|-------|
| [st3v3nmw/sourcerer-mcp](https://github.com/st3v3nmw/sourcerer-mcp) | `README.md`, `cmd/sourcerer/`, `internal/` | FR-001, FR-003, FR-004, FR-006, FR-009, FR-010, FR-012, FR-013 | Best repo-level match for local symbol extraction, watched reindexing, persistent vector storage, and metadata-rich results. Reuse the Tree-sitter chunking/reindex loop, then extend symbol records to carry the exact body/signature/line metadata the spec wants. Maintenance signal: 111 stars; last-push timestamp not surfaced in the repo page snapshot. |
| [continuedev/continue](https://github.com/continuedev/continue) | `core/indexing/CodebaseIndexer.ts`, `core/indexing/LanceDbIndex.ts`, `docs/` | FR-003, FR-004, FR-008, FR-009, FR-011, FR-012 | Strong orchestration reference for large-scale indexing, progress tracking, incremental refresh flow, and staleness-aware maintenance. Not markdown-first, but useful for batching and index lifecycle management. Maintenance signal: 30.9k stars; updated Nov 18, 2025. |
| [run-llama/llama_index](https://github.com/run-llama/llama_index) | `llama-index-core/llama_index/core/node_parser/file/markdown.py`, `llama-index-core/llama_index/core/node_parser/relational/markdown_element.py`, `docs/docs/getting_started/reading.md` | FR-003, FR-004, FR-006, FR-007 | Best file-level match for markdown section parsing plus vector-store persist/load flow. Adapt its breadcrumb/section logic to this repo’s `specs/` and `.claude/` docs. Maintenance signal: 48.6k stars; updated Jan 5, 2026. |
| [supabase/headless-vector-search](https://github.com/supabase/headless-vector-search) | `README.md`, `supabase/`, `supabase/functions/vector-search`, GitHub Action `supabase-vector-embeddings` | FR-003, FR-004, FR-006 | Good docs-style ingestion pattern for markdown-fed vector search. Swap the docs-only ingest step for code + section ingestion while keeping the database-backed search surface. Maintenance signal: 193 stars; last-push timestamp not surfaced in the repo page snapshot. |
| [elastic/semantic-code-search-indexer](https://github.com/elastic/semantic-code-search-indexer) | `README.md`, `src/index.ts`, `src/commands/`, `src/languages/`, `src/utils/` | FR-001, FR-003, FR-004, FR-009, FR-010, FR-013 | Strong scan -> queue -> index flow and watch-based refresh reference. Useful if the implementation leans toward an indexer-style pipeline instead of a one-shot script. Maintenance signal: 16 stars; last-push timestamp not surfaced in the repo page snapshot. |
| [osinmv/function-lookup-mcp](https://github.com/osinmv/function-lookup-mcp) | `README.md`, `main.py`, `run.sh`, `apis/*.ctags` | FR-001, FR-004, FR-011 | Precise match for declaration/signature lookup and line-oriented symbol discovery. Best used as a focused symbol indexer, then paired with semantic search for broader natural-language queries. Maintenance signal: 3 stars; latest visible release Nov 10, 2025. |

**After assembly**: which FRs remain uncovered and require net-new code?
- FR-005: one query API that cleanly applies a code/markdown/both scope filter still needs repo-local orchestration.
- FR-008: the exact index metadata record shape and write point still need repo-local definition even where indexers already persist state.
- FR-011: explicit HEAD-vs-last-build staleness reporting in the repo’s required format is only partially covered by existing patterns.
- FR-012: atomic prior-index retention on interrupted update remains implementation-specific glue for the chosen storage backend.

---

## Package Adoption Options

Installable packages only (verified via `pip index versions`, `npm view`, or `gh api repos/`). Unverified entries belong in Repo Assembly Map.

| Package | Version | FRs covered | Integration effort | Installability check |
|---------|---------|-------------|-------------------|---------------------|
| [chromadb](https://pypi.org/project/chromadb/) | 1.5.7 | FR-003, FR-004, FR-008, FR-011, FR-012 | 2 | `pip index versions chromadb` verified on PyPI |
| [libcst](https://pypi.org/project/libcst/) | 1.8.6 | FR-001, FR-002, FR-014 | 3 | `pip index versions libcst` verified on PyPI |
| [tree-sitter](https://pypi.org/project/tree-sitter/) | 0.23.2 | FR-001, FR-013, FR-014 | 3 | `pip index versions tree-sitter` verified on PyPI |
| [markdown-it-py](https://pypi.org/project/markdown-it-py/) | 3.0.0 | FR-006, FR-007 | 2 | `pip index versions markdown-it-py` verified on PyPI |
| [fastembed](https://pypi.org/project/fastembed/) | 0.7.4 | FR-002, FR-007 | 2 | `pip index versions fastembed` verified on PyPI |
| [sentence-transformers](https://pypi.org/project/sentence-transformers/) | 5.1.2 | FR-002, FR-007 | 3 | `pip index versions sentence-transformers` verified on PyPI |
| [watchfiles](https://pypi.org/project/watchfiles/) | 1.1.1 | FR-009, FR-010 | 1 | `pip index versions watchfiles` verified on PyPI |
| [watchdog](https://pypi.org/project/watchdog/) | 6.0.0 | FR-009, FR-010 | 1 | `pip index versions watchdog` verified on PyPI |

---

## Conceptual Patterns

Non-code synthesis from web research. Standard approaches, common patterns, known mistakes.

- **Pattern**: Tree-sitter incremental symbol indexing — standard embedded parsing approach for symbol extraction and selective reparsing — covers: FR-001, FR-009, FR-013, FR-014 — requires custom server: no
  - Source: https://tree-sitter.github.io/tree-sitter/index.html
  - Source: https://tree-sitter.github.io/py-tree-sitter/classes/tree_sitter.Tree.html
- **Pattern**: Markdown token-stream sectioning — parse headings into breadcrumbed sections before embedding — covers: FR-005, FR-006, FR-007 — requires custom server: no
  - Source: https://markdown-it-py.readthedocs.io/en/latest/architecture.html
  - Source: https://markdown-it-py.readthedocs.io/en/latest/api/markdown_it.tree.html
- **Pattern**: Persistent local vector store with metadata filters — local on-disk vectors plus query-time metadata slicing — covers: FR-003, FR-004, FR-005, FR-008 — requires custom server: no
  - Source: https://docs.trychroma.com/docs/overview/introduction
  - Source: https://docs.trychroma.com/reference/python/client
  - Source: https://docs.trychroma.com/docs/querying-collections/metadata-filtering
- **Pattern**: Filesystem watcher plus Git hook refresh trigger — update on file events, keep commit hooks as a fallback — covers: FR-009, FR-010, FR-012 — requires custom server: no
  - Source: https://github.com/gorakhargosh/watchdog
  - Source: https://git-scm.com/docs/githooks
- **Pattern**: HEAD-hash staleness check with diff-based invalidation — persist the last successful build commit hash and compare it to current HEAD — covers: FR-008, FR-011, FR-012 — requires custom server: no
  - Source: https://git-scm.com/docs/git-rev-parse/2.45.3
  - Source: https://git-scm.com/docs/git-diff.html

---

## Search Tools Used

Log which tools and queries ran. Used to diagnose shallow results in future debugging.

- Agent A (Code Discovery): GitHub MCP search plus web searches for `sourcerer-mcp`, `Continue`, `llama_index`, `headless-vector-search`, `semantic-code-search-indexer`, and `function-lookup-mcp`; then web opens on the selected repo pages and source references.
- Agent B (Package Discovery): `pip index versions` for `chromadb`, `libcst`, `tree-sitter`, `markdown-it-py`, `fastembed`, `sentence-transformers`, `watchfiles`, and `watchdog`.
- Agent C (Conceptual Patterns): `web.search_query`, `web.open`, and `web.find` against Tree-sitter, markdown-it-py, Chroma, watchdog, and git hook docs.
- Local context mapping: `sed` reads of `specs/020-codebase-vector-index/spec.md` and `.claude/commands/speckit.research.md`.

---

## Unanswered Questions

Anything still unknown after all research. These become [NEEDS CLARIFICATION] in plan.md.

- Which code extraction parser should the plan standardize on first: `libcst` or `tree-sitter`?
- Which local embedding runtime should the plan prioritize first: `fastembed` or `sentence-transformers`?
- Which persistence path should the on-disk Chroma collection use, and how should migrations or cleanup work?
