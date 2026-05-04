# Behavior Map: Codebase MCP Toolkit

This file maps the runtime behavior of the codebase MCP server to the modules that own it.

## Scope

- Runtime mode: FastMCP service (`uv run python -m src.mcp_codebase`)
- Tools: `get_type`, `get_diagnostics`, `get_graph_health`

## How To Read

- `Entrypoint`: first function or module that owns the behavior.
- `Observe`: visible signal that the behavior is active.
- `Tests`: fastest file to inspect when changing the behavior.

## Behavior Catalog

| Behavior | Entrypoint | Core Code Path | Observe | Tests |
|---|---|---|---|---|
| Server bootstrap and tool registration | `src/mcp_codebase/server.py::CodebaseLSPServer.__init__` | Builds the FastMCP app, registers tools, and wires run-scoped logging | Server startup log with `run_id` and `project_root` | `tests/unit/test_vector_index_server.py` |
| Type inference tool | `src/mcp_codebase/type_tool.py::get_type_impl` | Uses Pyright-backed inference for symbol locations and hover-style type resolution | Tool response returns the inferred type at the requested location | `tests/unit/test_query_tools.py` |
| Diagnostics tool | `src/mcp_codebase/diag_tool.py::get_diagnostics_impl` | Runs Pyright diagnostics and normalizes the output for MCP clients | Tool response returns diagnostics grouped by path and severity | `tests/unit/test_query_tools.py` |
| Graph-health classification | `src/mcp_codebase/health.py::classify_graph_health` | Evaluates vector-index freshness and health state | Health tool returns a stable status payload | `tests/unit/test_graph_health.py` |
| Vector index service initialization | `src/mcp_codebase/index/service.py::build_vector_index_service` | Creates the repository-scoped vector index service used by health checks and discovery | Index bootstrap logs and health classifications | `tests/unit/test_vector_index_server.py` |

## Maintenance Rule

When changing the server surface or its health/index behavior, update one row in this file in the same PR.
