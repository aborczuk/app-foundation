"""FastMCP backend server that owns warm query and rerank operations."""

from __future__ import annotations

import importlib.util
import io
import os
import sys
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout
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


def _load_read_code_module(project_root: Path):
    """Load the repo-local read_code script as one reusable Python module."""
    module_name = "_project_backend_read_code_bridge"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached

    script_path = project_root / "scripts" / "read_code.py"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load read_code bridge from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _DirectReadCodeBackend:
    """Serve read_code semantic query and rerank requests from the local warm service."""

    def __init__(self, server_ref: "ProjectBackendServer") -> None:
        """Bind the adapter to one already-warm project backend server."""
        self._server_ref = server_ref
        self.model_name = server_ref._reranker_model

    def score_pairs(self, query: str, passages: list[str]) -> tuple[list[float], str]:
        """Return local warm reranker scores in the same shape as read_code expects."""
        self._server_ref._ensure_vector_index_ready()
        payload = self._server_ref._vector_index_service.rerank_scores(query, passages)
        scores = payload.get("scores")
        if not isinstance(scores, list) or not all(isinstance(value, (int, float)) for value in scores):
            return [], "heuristic"
        return [float(value) for value in scores], "mcp"

    def query_items(
        self,
        *,
        query: str,
        top_k: int,
        scope: str,
        file_path: Path | None,
    ) -> list[dict[str, object]] | None:
        """Return local warm semantic query items in the same shape as read_code expects."""
        self._server_ref._ensure_vector_index_ready()
        try:
            parsed_scope = IndexScope(scope)
        except ValueError:
            return []
        results = self._server_ref._vector_index_service.query(
            query,
            top_k=top_k,
            scope=parsed_scope,
            file_path=file_path.resolve() if file_path is not None else None,
        )
        return [_serialize_query_result(result) for result in results]


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
        self._read_code_module = _load_read_code_module(self._project_root)
        self._read_code_backend = _DirectReadCodeBackend(self)
        self._vector_index_ready = False
        self.mcp = FastMCP(_SERVER_NAME)
        self._register_tools()

    def _ensure_vector_index_ready(self) -> None:
        """Build the local vector index once using the active manifest, not stale diagnostics."""
        if self._vector_index_ready:
            return
        store = getattr(self._vector_index_service, "_store", None)
        load_active_metadata = getattr(store, "_load_active_metadata", None)
        active_metadata = load_active_metadata() if callable(load_active_metadata) else None
        if active_metadata is None and not callable(load_active_metadata):
            active_metadata = self._vector_index_service.status()
        if active_metadata is None:
            self._vector_index_service.build_full_index(revision="local")
        self._vector_index_ready = True

    @contextmanager
    def _read_code_session(self, session_id: str | None):
        """Temporarily bind one explicit read_code session id when provided."""
        if session_id is None:
            yield
            return
        previous = os.environ.get("READ_CODE_SESSION_ID")
        os.environ["READ_CODE_SESSION_ID"] = session_id
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("READ_CODE_SESSION_ID", None)
            else:
                os.environ["READ_CODE_SESSION_ID"] = previous

    @contextmanager
    def _patched_read_code_runtime(self):
        """Route read_code's local backend globals to this warm server instance."""
        module = self._read_code_module
        previous_backend = getattr(module, "_READ_CODE_RERANKER_BACKEND", None)
        previous_service = getattr(module, "_READ_CODE_VECTOR_QUERY_SERVICE", None)
        module._READ_CODE_RERANKER_BACKEND = self._read_code_backend
        module._READ_CODE_VECTOR_QUERY_SERVICE = self._vector_index_service
        try:
            yield module
        finally:
            module._READ_CODE_RERANKER_BACKEND = previous_backend
            module._READ_CODE_VECTOR_QUERY_SERVICE = previous_service

    def _run_read_code_command(
        self,
        command_name: str,
        argv: list[str],
        *,
        session_id: str | None = None,
        verbose: bool = False,
    ) -> dict[str, object]:
        """Execute one shared read_code command against the warm in-process backend."""
        stdout = io.StringIO()
        stderr = io.StringIO()
        with self._patched_read_code_runtime() as module, self._read_code_session(session_id):
            command = getattr(module, command_name)
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = command(argv, verbose=verbose)
        return {
            "name": _SERVER_NAME,
            "pid": self._pid,
            "started_at": self._started_at,
            "command": command_name,
            "argv": list(argv),
            "exit_code": int(exit_code),
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
        }

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

        @self.mcp.tool()
        async def read_code_context(
            pattern: str,
            file_path: str | None = None,
            context_lines: int | None = None,
            allow_fallback: bool = False,
            show_shortlist: bool = False,
            show_rerank: bool = False,
            inline_body: bool = False,
            next_candidate: bool = False,
            candidate_index: int | None = None,
            content_type: str | None = None,
            session_id: str | None = None,
            verbose: bool = False,
        ) -> dict[str, object]:
            """Execute the shared read_code context path directly inside the warm MCP server."""
            argv = [pattern]
            if file_path is not None:
                argv.extend(["--path", file_path])
            if context_lines is not None:
                argv.append(str(context_lines))
            if allow_fallback:
                argv.append("--allow-fallback")
            if show_shortlist:
                argv.append("--show-shortlist")
            if show_rerank:
                argv.append("--show-rerank")
            if inline_body:
                argv.append("--inline-body")
            if next_candidate:
                argv.append("--next-candidate")
            if candidate_index is not None:
                argv.extend(["--candidate-index", str(candidate_index)])
            if content_type is not None:
                argv.extend(["--content-type", content_type])
            return self._run_read_code_command(
                "read_code_context",
                argv,
                session_id=session_id,
                verbose=verbose,
            )

        @self.mcp.tool()
        async def read_code_find(
            command: str,
            args: list[str],
            candidate_index: int | None = None,
            next_candidate: bool = False,
            show_shortlist: bool = False,
            session_id: str | None = None,
            verbose: bool = False,
        ) -> dict[str, object]:
            """Execute the shared read_code find path directly inside the warm MCP server."""
            argv = [command, *args]
            if show_shortlist:
                argv.append("--show-shortlist")
            if next_candidate:
                argv.append("--next-candidate")
            if candidate_index is not None:
                argv.extend(["--candidate-index", str(candidate_index)])
            return self._run_read_code_command(
                "read_code_find",
                argv,
                session_id=session_id,
                verbose=verbose,
            )

        @self.mcp.tool()
        async def read_code_analyze(
            command: str,
            args: list[str],
            candidate_index: int | None = None,
            next_candidate: bool = False,
            show_shortlist: bool = False,
            session_id: str | None = None,
            verbose: bool = False,
        ) -> dict[str, object]:
            """Execute the shared read_code analyze path directly inside the warm MCP server."""
            argv = [command, *args]
            if show_shortlist:
                argv.append("--show-shortlist")
            if next_candidate:
                argv.append("--next-candidate")
            if candidate_index is not None:
                argv.extend(["--candidate-index", str(candidate_index)])
            return self._run_read_code_command(
                "read_code_analyze",
                argv,
                session_id=session_id,
                verbose=verbose,
            )

        @self.mcp.tool()
        async def read_code_window(
            file_path: str,
            start_line: int,
            end_line: int,
            pattern: str | None = None,
            hud_symbol: bool = False,
            allow_fallback: bool = False,
            session_id: str | None = None,
            verbose: bool = False,
        ) -> dict[str, object]:
            """Execute the shared read_code window path directly inside the warm MCP server."""
            argv = [file_path, str(start_line), str(end_line)]
            if hud_symbol:
                argv.append("--hud-symbol")
            if allow_fallback:
                argv.append("--allow-fallback")
            if pattern:
                argv.append(pattern)
            return self._run_read_code_command(
                "read_code_window",
                argv,
                session_id=session_id,
                verbose=verbose,
            )


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
