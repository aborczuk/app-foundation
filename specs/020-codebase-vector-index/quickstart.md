# Quickstart: Codebase Vector Index

Get the local semantic index running in a repo checkout.

---

## What Exists Now

This feature now ships a local Chroma-backed vector index with embeddings. It
stores its data on disk under `.codegraphcontext/global/db/vector-index/`, so the
index stays tied to the repository checkout and does not require a remote
database.

The main implementation pieces are:

- `src/mcp_codebase/index/domain.py` - typed models for symbols, markdown
  sections, metadata, and query results
- `src/mcp_codebase/index/config.py` - repo-local configuration and configurable
  exclude-pattern loading
- `src/mcp_codebase/index/extractors/` - Python and markdown chunk extraction
- `src/mcp_codebase/index/store/chroma.py` - Chroma persistence, embeddings,
  queries, and snapshot swaps
- `src/mcp_codebase/index/service.py` - build/query/refresh/status orchestration
- `src/mcp_codebase/indexer.py` - CLI entrypoint
- `src/mcp_codebase/server.py` - MCP tool registration
- `src/mcp_codebase/index/telemetry.py` - local no-op telemetry client to keep
  Chroma quiet during runs

## Prerequisites

- Python 3.12 via `uv`: run `uv --version`
- Repo dependencies installed: run `uv sync`
- Local disk space for the index under `.codegraphcontext/global/db/vector-index/`
- A checked-out repo with `src/`, `tests/`, `specs/`, and `.claude/` content

---

## Installation

### 1. Sync dependencies

```bash
uv sync
```

### 2. Confirm the shared vector storage home exists

```bash
mkdir -p .codegraphcontext/global/db/vector-index
```

### 3. Warm the local embedding/runtime path

```bash
uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . bootstrap --skip-build
```

---

## Run the Feature

The index is exposed through the existing `src/mcp_codebase` package. Expected entry points:

```bash
# Ensure the local embedding model is available (and optionally build immediately)
uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . bootstrap --skip-build

# Build or refresh the index
uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . build

# Build while excluding configured paths
MCP_CODEBASE_INDEX_EXCLUDE_PATTERNS="docs/build/**" \
  uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . --exclude-pattern docs/build/** build

# Check whether the active snapshot is stale relative to HEAD
uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . status

# Start watcher mode for incremental refresh
uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . watch

# Query for context
uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . query "webhook deduplication"
```

If the implementation is exposed as MCP tools only, the equivalent flow is to start the `codebase` MCP server and call the search/update/staleness tools from the agent runtime.

---

## Keeping It Up To Date

Use this as the normal local workflow:

```bash
# Build the initial snapshot
uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . build

# Check freshness before trusting results
uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . status

# Query the index
uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . query "webhook deduplication"

# Refresh a changed file or a short list of changed files
uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . refresh src/mcp_codebase/index/service.py

# Keep the snapshot current while you edit
uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . watch
```

The watcher listens for local edits and calls the incremental refresh path for
changed Python and markdown files. If you only need a one-off update, use
`refresh`; if you want the snapshot to stay current while you work, use `watch`.

You can inspect the stored snapshot directly on disk under
`.codegraphcontext/global/db/vector-index/`:

- `active.json` records the active snapshot metadata
- the active snapshot directory stores the Chroma collection and chunk data

What is stored in each chunk:

- code chunks keep the full source body, signature, docstring, line span, and
  content hash
- markdown chunks keep the section heading, breadcrumb, preview, line span, and
  content hash
- query results surface those fields so you can jump straight into
  `read_code_context` or `read_markdown_section`

The supported ways to view the indexed content are:

- `status` for build freshness and commit delta
- `query` for ranked semantic results
- direct file inspection of the snapshot directory if you need to debug storage

## How It Feeds Read Helpers

The index is the discovery step, not the reader itself.

Use this sequence when you know the concept but do not know the exact file:

1. Query the vector index with the concept phrase.
2. If the top result is code, call `read_code_context` with the returned file
   path and line span.
3. If the top result is markdown, call `read_markdown_section` with the
   returned file path and heading/breadcrumb.
4. Only fall back to broad grep or manual scanning if the index returns no
   useful hit.

That keeps the tool flow semantic-first instead of “grep everything first.”

---

## Smoke Test

Verify the workflow contracts are still wired correctly:

```bash
bash .specify/scripts/test-plan.sh feature_id=020
```

For the feature itself, the implementation should eventually provide a deterministic test that:

```bash
# Build index
# Confirm status reports the current HEAD as fresh and includes build age
# Edit one file, then confirm status reports the snapshot as stale with commit delta and age
# Query a known symbol
# Confirm the top result includes file path + line range
# Edit one file and confirm the refresh path updates the result
```

The current test coverage for this workflow lives in:

- [`tests/integration/test_codebase_vector_index.py`](../../tests/integration/test_codebase_vector_index.py)
- [`tests/integration/test_codebase_vector_index_performance.py`](../../tests/integration/test_codebase_vector_index_performance.py)

---

## Common Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| Missing local index dependencies | Import or startup failure | Run `uv sync` and rebuild the environment. |
| Stale results after editing files | Query returns old line ranges | Confirm the watcher is running or invoke the manual refresh command. |
| Stale snapshot after new commits | Status reports `is_stale: true` plus commit delta and age | Rebuild or refresh the index so `current_commit` matches the repository HEAD again. |
| Configured paths still appear in results | Query returns files you intended to skip | Confirm `MCP_CODEBASE_INDEX_EXCLUDE_PATTERNS` or `--exclude-pattern` was supplied before the build or refresh. |
| Index storage missing | Query reports no active snapshot | Rebuild the index from the repo root and verify `.codegraphcontext/global/db/vector-index/` exists. |
| Embedding runtime unavailable | Refresh fails early | Confirm the local embedding package is installed and reachable in the `uv` environment. |

---

## Next Steps

- Read [Feature Specification](./spec.md)
- Read [Research Notes](./research.md)
- Run the plan review step: `/speckit.planreview`
