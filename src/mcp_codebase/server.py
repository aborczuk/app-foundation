"""FastMCP server for codebase-lsp.

Registers get_type, get_diagnostics, and get_graph_health tools. Manages
PyrightClient lifecycle and run-scoped structured logging.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.mcp_codebase import config
from src.mcp_codebase.diag_tool import get_diagnostics_impl
from src.mcp_codebase.health import classify_graph_health
from src.mcp_codebase.index import IndexScope, build_vector_index_service
from src.mcp_codebase.index.service import VectorIndexService
from src.mcp_codebase.pyright_client import PyrightClient
from src.mcp_codebase.type_tool import get_type_impl

logger = logging.getLogger(__name__)

_STANDARD_KEYS = frozenset(logging.LogRecord("", 0, "", 0, None, None, None).__dict__)


class _JsonlFormatter(logging.Formatter):
    """Emit one JSON object per line, merging ``extra`` fields."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, val in record.__dict__.items():
            if key not in _STANDARD_KEYS:
                entry[key] = val
        return json.dumps(entry)


class CodebaseLSPServer:
    """Wraps FastMCP with PyrightClient lifecycle and run-scoped logging."""

    def __init__(
        self,
        *,
        project_root: Path,
        log_base_dir: Path,
    ) -> None:
        """Initialize the instance."""
        self._project_root = project_root.resolve()
        self._log_base_dir = log_base_dir
        self._run_id = str(uuid.uuid4())[:8]
        self._pyright_client: PyrightClient | None = None
        self._vector_index_service: VectorIndexService = build_vector_index_service(
            self._build_index_config()
        )

        self.mcp = FastMCP("codebase-lsp")

        # Register tools
        self._register_tools()

        # Setup logging
        self._setup_logging()

        logger.info(
            "codebase-lsp: server created",
            extra={
                "run_id": self._run_id,
                "project_root": str(self._project_root),
                "log_path": str(self._run_log_dir / "server.jsonl"),
            },
        )

    def _register_tools(self) -> None:
        """Register MCP tool handlers."""
        server_ref = self

        @self.mcp.tool()
        async def get_type(file_path: str, line: int, column: int) -> dict:
            """Return the statically-inferred Python type at a source location.

            Args:
                file_path: Relative path to a .py file within the project.
                line: 1-based line number.
                column: 0-based column number.
            """
            return await get_type_impl(
                file_path,
                line=line,
                column=column,
                project_root=server_ref._project_root,
                pyright_client=server_ref._pyright_client,
            )

        @self.mcp.tool()
        async def get_diagnostics(file_path: str) -> list | dict:
            """Return the full pyright diagnostic list for a Python source file.

            Args:
                file_path: Relative path to a .py file within the project.
            """
            return await get_diagnostics_impl(
                file_path,
                project_root=server_ref._project_root,
            )

        @self.mcp.tool()
        async def get_graph_health() -> dict:
            """Return the current local CodeGraph readiness status."""
            health = classify_graph_health(server_ref._project_root).to_dict()
            recovery_hint = health.get("recovery_hint", {})
            logger.info(
                "codebase-lsp: graph health checked",
                extra={
                    "run_id": server_ref._run_id,
                    "status": health.get("status"),
                    "access_mode": health.get("access_mode"),
                    "recovery_hint_id": (
                        recovery_hint.get("id")
                        if isinstance(recovery_hint, dict)
                        else None
                    ),
                    "latency_ms": health.get("latency_ms"),
                },
            )
            return health

        register_vector_index_tools(self.mcp, self._vector_index_service)

    @property
    def _run_log_dir(self) -> Path:
        return self._log_base_dir / self._run_id

    def _setup_logging(self) -> None:
        """Configure run-scoped JSONL logging and latest-run pointer."""
        self._run_log_dir.mkdir(parents=True, exist_ok=True)

        log_file = self._run_log_dir / "server.jsonl"
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(_JsonlFormatter())

        root_logger = logging.getLogger("src.mcp_codebase")
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        # Write latest-run pointer
        pointer_path = self._log_base_dir / "latest-run.json"
        pointer_path.write_text(
            json.dumps({
                "run_id": self._run_id,
                "log_path": str(log_file),
            }),
            encoding="utf-8",
        )

    async def start_pyright(self) -> None:
        """Start the PyrightClient subprocess."""
        self._pyright_client = PyrightClient(self._project_root)
        await self._pyright_client.start()

    async def stop_pyright(self) -> None:
        """Shutdown the PyrightClient subprocess."""
        if self._pyright_client:
            await self._pyright_client.shutdown()
            self._pyright_client = None

    @property
    def pyright(self) -> PyrightClient | None:
        """Execute the function."""
        return self._pyright_client

    def _build_index_config(self):
        from src.mcp_codebase.index import IndexConfig
        from src.mcp_codebase.index.config import load_exclude_patterns

        return IndexConfig(
            repo_root=self._project_root,
            db_path=Path(".codegraphcontext/db/vector-index"),
            embedding_model="local-default",
            exclude_patterns=load_exclude_patterns(),
        )


def register_vector_index_tools(
    mcp: FastMCP,
    vector_service: VectorIndexService,
) -> None:
    """Register vector-index tools without changing the existing pyright tools."""

    @mcp.tool()
    async def search_vector_index(
        query: str,
        top_k: int = 10,
        scope: str | None = None,
    ) -> list[dict]:
        parsed_scope = IndexScope(scope) if scope else None
        results = vector_service.query(query, top_k=top_k, scope=parsed_scope)
        return [result.model_dump(mode="json") for result in results]

    @mcp.tool()
    async def refresh_vector_index(
        changed_paths: list[str] | None = None,
        revision: str = "local",
    ) -> dict:
        metadata = vector_service.refresh_changed_files(changed_paths or [], revision=revision)
        return metadata.model_dump(mode="json")

    @mcp.tool()
    async def get_vector_index_status() -> dict:
        metadata = vector_service.status()
        if metadata is None:
            return {
                "entry_count": 0,
                "indexed_at": None,
                "indexed_commit": "",
                "current_commit": "",
                "is_stale": True,
                "source_root": str(Path.cwd()),
                "stale_reason": "vector index has not been built yet",
                "scopes": [],
            }
        return metadata.model_dump(mode="json")


def create_server(
    *,
    project_root: Path | None = None,
    log_base_dir: Path | None = None,
) -> CodebaseLSPServer:
    """Factory function: create a CodebaseLSPServer with defaults from config."""
    return CodebaseLSPServer(
        project_root=project_root or config.PROJECT_ROOT,
        log_base_dir=log_base_dir or config.LOG_BASE_DIR,
    )


def main() -> None:
    """Run the codebase-lsp MCP server."""
    server = create_server()
    server.mcp.run()


if __name__ == "__main__":
    main()
