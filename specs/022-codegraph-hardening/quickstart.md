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

## Doctor Flow

Check graph readiness before trusting symbol answers:

```bash
scripts/cgc_doctor.sh
scripts/cgc_doctor.sh --json
```

Doctor output is probe-only. It reports `access_mode: READ_ONLY` and one of four statuses:

| Status | Meaning | Next step |
|--------|---------|-----------|
| `healthy` | The indexed snapshot matches the current tracked sources. | Continue browsing or run the feature smoke test. |
| `stale` | Local edits are newer than the last indexed snapshot. | Run `scripts/cgc_safe_index.sh src/mcp_codebase` and retry. |
| `locked` | A stale owner or lock marker is present. | Stop the stale owner, then rerun `scripts/cgc_safe_index.sh src/mcp_codebase`. |
| `unavailable` | The snapshot is unreadable or the last index attempt failed. | Inspect `recovery_hint`, free memory if needed, and rerun the safe index wrapper. |

If the doctor reports memory pressure, treat it as a fail-fast signal instead of retrying blindly:

```bash
scripts/cgc_safe_index.sh src/mcp_codebase
```

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

## Operator Notes

- Treat `scripts/cgc_doctor.sh` as the first stop for health checks; it is a read-only probe and does not rebuild the graph.
- Use `scripts/cgc_safe_index.sh src/mcp_codebase` for recovery, not as a routine browse command.
- If the doctor says `stale`, the current working tree changed after the last refresh; reindex only the scoped path that changed.
- If the doctor says `locked`, prefer closing the stale owner cleanly before waiting for the safe-index wrapper to reclaim the lock.
- If the doctor says `unavailable`, use the recovery hint text to distinguish unreadable files from memory-pressure failures.
- Keep checkout state simple: avoid `git worktree`, detached HEADs, and scratch branches. Use `main` and explicit named branches from `main` only.

---

## Next Steps

- Read the feature spec: [spec.md](./spec.md)
- Review the implementation plan: [plan.md](./plan.md)
- Inspect the data model: [data-model.md](./data-model.md)
- If the graph still fails smoke tests, rerun `scripts/cgc_safe_index.sh src/mcp_codebase` before browsing
