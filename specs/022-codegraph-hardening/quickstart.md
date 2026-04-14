# Quickstart: CodeGraph Reliability Hardening

Get the local CodeGraph/Kuzu health path running and verified in about 10 minutes.

---

## Prerequisites

| Requirement | Check | Notes |
|-------------|-------|-------|
| Python env | `uv sync` | Installs the repo dependencies into the local environment. |
| Repo-local cache | `echo "$UV_CACHE_DIR"` | Should point at the repo-local `.uv-cache` path, not a stale home-directory path. |
| Kuzu graph state | `.codegraphcontext/db/kuzudb` exists or is rebuildable | The feature assumes local graph state is available or can be refreshed safely. |

---

## Installation

### 1. Set up the environment

```bash
cd /Users/andreborczuk/app-foundation
uv sync
```

### 2. Confirm the local cache path

```bash
echo "$UV_CACHE_DIR"
# Expected: /Users/andreborczuk/app-foundation/.uv-cache
```

### 3. Refresh codegraph discovery if needed

```bash
scripts/cgc_safe_index.sh src/mcp_codebase
```

---

## Run the Feature

### Start the codebase MCP server

```bash
uv run python -m src.mcp_codebase
```

### Start the CodeGraph MCP server

```bash
uv run cgc mcp start
```

The feature is healthy when both surfaces can start without lock contention or stale-session errors.

---

## Smoke Test

Verify the graph hardening path is working:

```bash
scripts/validate_doc_graph.sh
```

Expected outcome:

```text
Doc graph validation PASSED.
```

If the graph looks stale or locked, try a scoped safe refresh:

```bash
scripts/cgc_safe_index.sh src/mcp_codebase
```

---

## Common Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| Stale UV cache path | `uv` tries to use a home-directory cache from an older workspace | Repoint `UV_CACHE_DIR` to `/Users/andreborczuk/app-foundation/.uv-cache`. |
| Locked Kuzu DB | Doctor/health check reports `locked` | Stop the stale process, then rerun `scripts/cgc_safe_index.sh src/mcp_codebase`. |
| Unhealthy graph snapshot | Browsing falls back to direct file reads | Refresh the graph with the safe index wrapper and rerun the smoke test. |

---

## Next Steps

- Read the feature spec: [spec.md](./spec.md)
- Review the implementation plan: [plan.md](./plan.md)
- Inspect the data model: [data-model.md](./data-model.md)
- If the graph still fails smoke tests, rerun `scripts/cgc_safe_index.sh src/mcp_codebase` before browsing
