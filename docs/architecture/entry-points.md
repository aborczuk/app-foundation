# Entry Points

Status: canonical
Last reviewed: 2026-05-09
Owner: repository architecture

## Purpose

This is the task-oriented map for agents. Start here when you know what you need to change but not where the code lives.

## If You Need To Change Webhook Intake

Start with:

1. `docs/architecture/clickup-control-plane.md`
2. `src/clickup_control_plane/app.py`
3. `src/clickup_control_plane/schemas.py`
4. `src/clickup_control_plane/webhook_auth.py`

## If You Need To Change Dispatch Or QA Routing

Start with:

1. `docs/architecture/clickup-control-plane.md`
2. `src/clickup_control_plane/service.py`
3. `src/clickup_control_plane/policy.py`
4. `src/clickup_control_plane/qa_loop.py`

## If You Need To Change Semantic Code Reading Or Indexing

Start with:

1. `docs/architecture/mcp-codebase.md`
2. `src/mcp_codebase/server.py`
3. `src/mcp_codebase/index/service.py`
4. `scripts/read_code.py`

## If You Need To Change Pyright Diagnostics Or Type Lookup

Start with:

1. `docs/architecture/mcp-codebase.md`
2. `src/mcp_codebase/server.py`
3. `src/mcp_codebase/diag_tool.py`
4. `src/mcp_codebase/type_tool.py`
5. `src/mcp_codebase/pyright_client.py`

## If You Need To Change ClickUp Synchronization

Start with:

1. `docs/architecture/mcp-clickup.md`
2. `src/mcp_clickup/__main__.py`
3. `src/mcp_clickup/sync_engine.py`
4. `src/mcp_clickup/manifest.py`

## If You Need To Change Trello Synchronization

Start with:

1. `docs/architecture/mcp-trello.md`
2. `src/mcp_trello/server.py`
3. `src/mcp_trello/parser.py`
4. `src/mcp_trello/sync_engine.py`

## If You Need To Change Phase Routing Or Speckit Execution

Start with:

1. `docs/architecture/workflow-overview.md`
2. `docs/governance/pipeline-driver-readme.md`
3. `scripts/pipeline_driver.py`
4. `scripts/pipeline_driver_state.py`
5. `scripts/pipeline_driver_contracts.py`

## If You Need To Change Ledger Ordering Or Phase Rules

Start with:

1. `docs/architecture/workflow-overview.md`
2. `scripts/pipeline_ledger.py`
3. `scripts/task_ledger.py`
4. `constitution.md`

## If You Need To Change Validation Or Handoff Policy

Start with:

1. `docs/architecture/scripts-index.md`
2. `scripts/edit_code.py`
3. `scripts/pytest_guard.py`
4. `scripts/ruff_guard.py`
5. `scripts/pyright_guard.py`
6. `scripts/git_diff_guard.py`

