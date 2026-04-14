# CodeGraph Reliability Hardening

This feature hardens the local CodeGraph/Kuzu path so stale sessions, lock contention, unreadable state, malformed query input, and query failures fail gracefully instead of blocking discovery.

## What Changed

- Added a shared graph-health seam in `src/mcp_codebase/health.py`.
- Added the operator-facing doctor command and shared MCP health tool.
- Added health, recovery, and query-failure tests.
- Added a real feature E2E pipeline in `scripts/e2e_022_codegraph_hardening.sh`.
- Replaced the scaffolded E2E plan in `specs/022-codegraph-hardening/e2e.md` with the actual recovery matrix.

## Current Coverage

- `tests/unit/test_health.py`
- `tests/unit/test_query_tools.py`
- `tests/integration/test_codegraph_health.py`
- `tests/integration/test_codegraph_recovery.py`
- `.speckit/acceptance-tests/story-1.py`
- `.speckit/acceptance-tests/story-2.py`
- `.speckit/acceptance-tests/story-3.py`

## How To Run

```bash
scripts/e2e_022_codegraph_hardening.sh full .codegraphcontext/config.yaml
```

The E2E script now:

1. Runs a preflight health smoke check.
2. Runs the developer health story checks.
3. Runs the lock/recovery and query-failure checks.
4. Runs the refresh/rebuild recovery checks.
5. Refreshes the touched codegraph scopes.
6. Verifies the doctor command reports `healthy`.
7. Runs the full regression suite.
8. Validates the task ledger and task-file format.

## Closeout

After the full E2E pipeline passes, the feature is closed with the manual `feature_closed` pipeline event. That event is separate from the E2E run itself.
