# Feature Specification: Codebase MCP Toolkit

**Feature Branch**: `008-codebase-mcp-toolkit`
**Status**: Canonical
**Last Updated**: 2026-05-04

## One-Line Purpose

Expose repo-aware MCP tools for type inference, diagnostics, and graph health over the local codebase.

## Consumer & Context

Codex and other MCP clients use the codebase server to inspect Python symbols, request Pyright-backed diagnostics, and query vector index health before editing code.

## Scope

- `src/mcp_codebase/server.py::CodebaseLSPServer`
- `src/mcp_codebase/type_tool.py::get_type_impl`
- `src/mcp_codebase/diag_tool.py::get_diagnostics_impl`
- `src/mcp_codebase/health.py::classify_graph_health`

## Core Behaviors

- Start a FastMCP server with `get_type`, `get_diagnostics`, and `get_graph_health`.
- Build a `PyrightClient` per server run and close it with the server lifecycle.
- Initialize the vector index service from the repository root and use it for graph-health classification.
- Emit structured JSONL logs per run so server activity is easy to inspect.

## Verification Notes

- `tests/unit/test_query_tools.py`
- `tests/unit/test_vector_index_server.py`
- `tests/unit/test_type_tool.py`
- `tests/unit/test_graph_health.py`
