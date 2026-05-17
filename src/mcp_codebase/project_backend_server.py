"""FastMCP backend server that owns warm query and rerank operations."""

from __future__ import annotations

import os
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.mcp_codebase import config
from src.mcp_codebase.index import IndexScope
from src.mcp_codebase.index.config import DEFAULT_RERANKER_MODEL_NAME
from src.mcp_codebase.index.reranker_runtime import reranker_build_fingerprint
from src.mcp_codebase.index.reranker_stdio_worker import _build_service

_SERVER_NAME = "read-code-persistence-probe"


def _capture_process_identity(server_ref: "ProjectBackendServer") -> dict[str, object]:
    """Return the bounded process identity snapshot for the backend server."""
    return {
        "name": _SERVER_NAME,
        "project_root": str(server_ref._project_root),
        "pid": server_ref._pid,
        "started_at": server_ref._started_at,
    }


def _serialize_query_result(result: object) -> dict[str, object]:
    """Return one JSON-safe query result payload."""
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    raise TypeError(f"unexpected query result type: {type(result)!r}")


class ProjectBackendServer:
    """Expose bounded MCP tools for identity, health, query, and rerank."""

    def __init__(
        self,
        *,
        project_root: Path | None = None,
        reranker_model: str = DEFAULT_RERANKER_MODEL_NAME,
    ) -> None:
        """Capture one process identity and build one warm vector service."""
        self._project_root = (project_root or config.PROJECT_ROOT).resolve()
        self._pid = os.getpid()
        self._started_at = time.time()
        self._reranker_model = reranker_model
        self._build_fingerprint = reranker_build_fingerprint(self._project_root, reranker_model)
        self._vector_index_service = _build_service(self._project_root, reranker_model=reranker_model)
        self._vector_index_service.build_full_index(revision="local")
        self.mcp = FastMCP(_SERVER_NAME)
        self._register_tools()

    def _ensure_vector_index_ready(self) -> None:
        """Build the local vector index once when the backend first needs it."""
        if self._vector_index_service.status() is None:
            self._vector_index_service.build_full_index(revision="local")

    def _register_tools(self) -> None:
        """Register the backend MCP tools once."""

        @self.mcp.tool()
        async def get_process_identity() -> dict[str, object]:
            """Return the current server process identity for persistence checks."""
            return _capture_process_identity(self)

        @self.mcp.tool()
        async def health() -> dict[str, object]:
            """Return the warmed reranker cache state and process identity."""
            payload = self._vector_index_service.ensure_reranker_model_local()
            payload.update(
                {
                    "name": _SERVER_NAME,
                    "project_root": str(self._project_root),
                    "pid": self._pid,
                    "started_at": self._started_at,
                    "build_fingerprint": self._build_fingerprint,
                }
            )
            return payload

        @self.mcp.tool()
        async def query(
            query_text: str,
            top_k: int = 10,
            scope: str | None = None,
            file_path: str | None = None,
        ) -> list[dict[str, object]]:
            """Return semantic query results from the warm vector index."""
            self._ensure_vector_index_ready()
            parsed_scope = IndexScope(scope) if scope else None
            results = self._vector_index_service.query(
                query_text,
                top_k=top_k,
                scope=parsed_scope,
                file_path=Path(file_path).resolve() if file_path else None,
            )
            return [_serialize_query_result(result) for result in results]

        @self.mcp.tool()
        async def score(query_text: str, passages: list[str]) -> dict[str, object]:
            """Return reranker scores for one query and bounded passage shortlist."""
            self._ensure_vector_index_ready()
            return self._vector_index_service.rerank_scores(query_text, passages)


def create_server(
    *,
    project_root: Path | None = None,
    reranker_model: str = DEFAULT_RERANKER_MODEL_NAME,
) -> ProjectBackendServer:
    """Create the project-local MCP backend server."""
    return ProjectBackendServer(project_root=project_root, reranker_model=reranker_model)


def main() -> None:
    """Run the project-local MCP backend server over stdio."""
    create_server().mcp.run()


if __name__ == "__main__":
    main()
