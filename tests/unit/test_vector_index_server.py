"""Unit tests for the vector-index MCP server wiring."""

from __future__ import annotations

import asyncio
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.mcp_codebase.index import CodeSymbol, IndexConfig, IndexMetadata, IndexScope, QueryResult
from src.mcp_codebase.server import CodebaseLSPServer, register_vector_index_tools


def test_register_vector_index_tools_routes_through_shared_service() -> None:
    """The new tools should call the shared service instance."""

    class FakeService:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def query(self, query_text: str, *, top_k: int = 10, scope: IndexScope | None = None):
            self.calls.append(("query", query_text, top_k, scope))
            return [
                QueryResult(
                    rank=1,
                    score=1.0,
                    content=CodeSymbol(
                        symbol_name="hello",
                        qualified_name="hello",
                        file_path=Path("src/example.py"),
                        line_start=1,
                        line_end=2,
                        signature="def hello():",
                        docstring="",
                        preview="def hello():",
                    ),
                )
            ]

        def refresh_changed_files(self, changed_paths, *, revision: str = "local"):
            self.calls.append(("refresh", list(changed_paths), revision))
            return IndexMetadata(
                source_root=Path.cwd(),
                indexed_commit=revision,
                current_commit=revision,
                indexed_at="2026-04-14T00:00:00Z",
                entry_count=1,
                is_stale=False,
                stale_reason="",
            )

        def status(self):
            self.calls.append(("status",))
            return None

    service = FakeService()
    mcp = FastMCP("vector-index-test")
    register_vector_index_tools(mcp, service)  # type: ignore[arg-type]

    tool_names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert {"search_vector_index", "refresh_vector_index", "get_vector_index_status"}.issubset(tool_names)

    asyncio.run(mcp.call_tool("search_vector_index", {"query": "hello", "top_k": 2, "scope": "code"}))
    assert service.calls[0] == ("query", "hello", 2, IndexScope.CODE)


def test_server_keeps_existing_pyright_tools_and_adds_vector_tools(tmp_path: Path) -> None:
    """The existing pyright tools should remain available alongside vector tools."""

    server = CodebaseLSPServer(project_root=tmp_path, log_base_dir=tmp_path / "logs")
    tool_names = {tool.name for tool in asyncio.run(server.mcp.list_tools())}

    assert {"get_type", "get_diagnostics", "get_graph_health"}.issubset(tool_names)
    assert {"search_vector_index", "refresh_vector_index", "get_vector_index_status"}.issubset(tool_names)
