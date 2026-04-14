# Quickstart: Codebase Vector Index

Get the local semantic index running in a repo checkout.

---

## Prerequisites

- Python 3.12 via `uv`: run `uv --version`
- Repo dependencies installed: run `uv sync`
- Local disk space for the index under `.codegraphcontext/db/`
- A checked-out repo with `src/`, `tests/`, `specs/`, and `.claude/` content

---

## Installation

### 1. Sync dependencies

```bash
uv sync
```

### 2. Confirm the repo-local storage home exists

```bash
mkdir -p .codegraphcontext/db
```

### 3. Warm the local embedding/runtime path

```bash
UV_CACHE_DIR=/tmp/app-foundation-uv-cache uv run python -c "import chromadb, fastembed, watchdog, markdown_it"
```

---

## Run the Feature

The first implementation should expose the index through the existing `src/mcp_codebase` package. Expected entry points:

```bash
# Build or refresh the index
UV_CACHE_DIR=/tmp/app-foundation-uv-cache uv run python -m src.mcp_codebase.indexer build

# Start watcher mode for incremental refresh
UV_CACHE_DIR=/tmp/app-foundation-uv-cache uv run python -m src.mcp_codebase.indexer watch

# Query for context
UV_CACHE_DIR=/tmp/app-foundation-uv-cache uv run python -m src.mcp_codebase.indexer query "webhook deduplication"
```

If the implementation is exposed as MCP tools only, the equivalent flow is to start the `codebase` MCP server and call the search/update/staleness tools from the agent runtime.

---

## Smoke Test

Verify the workflow contracts are still wired correctly:

```bash
bash .specify/scripts/test-plan.sh feature_id=020
```

For the feature itself, the implementation should eventually provide a deterministic test that:

```bash
# Build index
# Query a known symbol
# Confirm the top result includes file path + line range
# Edit one file and confirm the refresh path updates the result
```

---

## Common Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| Missing local index dependencies | Import or startup failure | Run `uv sync` and rebuild the environment. |
| Stale results after editing files | Query returns old line ranges | Confirm the watcher is running or invoke the manual refresh command. |
| Index storage missing | Query reports no active snapshot | Rebuild the index from the repo root and verify `.codegraphcontext/db/chroma/` exists. |
| Embedding runtime unavailable | Refresh fails early | Confirm the local embedding package is installed and reachable in the `uv` environment. |

---

## Next Steps

- Read [Feature Specification](./spec.md)
- Read [Research Notes](./research.md)
- Run the plan review step: `/speckit.planreview`
