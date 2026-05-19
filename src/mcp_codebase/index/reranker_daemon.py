"""Local Unix-socket daemon for read-code semantic query and shortlist rescoring."""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.mcp_codebase.index import IndexScope
from src.mcp_codebase.index.config import (
    DEFAULT_EMBEDDING_MODEL_NAME,
    DEFAULT_RERANKER_MODEL_NAME,
    DEFAULT_VECTOR_DB_PATH,
    IndexConfig,
    load_exclude_patterns,
)
from src.mcp_codebase.index.reranker_runtime import (
    persist_json_object,
    reranker_build_fingerprint,
    reranker_endpoint_path,
    reranker_log_path,
    reranker_pid_path,
    reranker_tcp_port,
)
from src.mcp_codebase.index.service import VectorIndexService


class ScoreRequest(BaseModel):
    """Structured score request for one query over a bounded shortlist."""

    query: str = Field(min_length=1)
    passages: list[str] = Field(default_factory=list)
    normalize: bool = True


class ScoreResponse(BaseModel):
    """Daemon response payload for shortlist reranking."""

    scores: list[float]
    model_name: str


class QueryRequest(BaseModel):
    """Structured semantic query request for the external daemon."""

    query_text: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1)
    scope: str | None = None
    file_path: str | None = None


class QueryResponse(BaseModel):
    """Daemon response payload for bounded semantic query results."""

    items: list[dict[str, Any]]


class HealthResponse(BaseModel):
    """Bounded daemon health payload for client startup checks."""

    status: str
    pid: int
    model_loaded: bool
    model_name: str
    started_at: float
    build_fingerprint: str


def _build_service(repo_root: Path, *, reranker_model: str) -> VectorIndexService:
    """Construct the vector service with the same repo-local cache and model defaults as the indexer."""
    config = IndexConfig(
        repo_root=repo_root,
        db_path=repo_root / DEFAULT_VECTOR_DB_PATH,
        embedding_model=DEFAULT_EMBEDDING_MODEL_NAME,
        reranker_model=reranker_model,
        exclude_patterns=load_exclude_patterns(),
    )
    return VectorIndexService(config)


def _serialize_query_result(result: object) -> dict[str, object]:
    """Return one JSON-safe semantic query payload for daemon clients."""
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    raise TypeError(f"unexpected query result type: {type(result)!r}")


def build_app(
    *,
    repo_root: Path,
    reranker_model: str,
    pid_file: Path | None = None,
    endpoint_file: Path | None = None,
) -> FastAPI:
    """Create the daemon application with warmed rerank and semantic-query state."""
    app = FastAPI()
    service = _build_service(repo_root, reranker_model=reranker_model)
    started_at = time.time()
    build_fingerprint = reranker_build_fingerprint(repo_root, reranker_model)
    vector_index_ready = False

    def _ensure_query_ready() -> None:
        """Build the vector index once before serving semantic query requests."""
        nonlocal vector_index_ready
        if vector_index_ready:
            return
        store = getattr(service, "_store", None)
        load_active_metadata = getattr(store, "_load_active_metadata", None)
        active_metadata = load_active_metadata() if callable(load_active_metadata) else None
        if active_metadata is None and not callable(load_active_metadata):
            active_metadata = service.status()
        if active_metadata is None:
            service.build_full_index(revision="local")
        vector_index_ready = True

    @app.on_event("startup")
    async def _startup() -> None:
        """Warm the reranker cache and publish runtime metadata before serving requests."""
        await asyncio.to_thread(service.ensure_reranker_model_local)
        await asyncio.to_thread(service.rerank_scores, "__warmup__", ["__warmup__"])
        if pid_file is not None:
            persist_json_object(
                pid_file,
                {"pid": os.getpid(), "updated_at": time.time()},
                sort_keys=True,
            )

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        """Remove the PID marker when the daemon exits cleanly."""
        for path in (pid_file, endpoint_file):
            if path is None:
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue

    @app.get("/health", response_model=HealthResponse)
    async def _health() -> HealthResponse:
        """Report daemon liveness and warmed model state."""
        return HealthResponse(
            status="healthy",
            pid=os.getpid(),
            model_loaded=True,
            model_name=reranker_model,
            started_at=started_at,
            build_fingerprint=build_fingerprint,
        )

    @app.post("/score", response_model=ScoreResponse)
    async def _score(request: ScoreRequest) -> ScoreResponse:
        """Return normalized reranker scores for one query over a bounded shortlist."""
        payload = await asyncio.to_thread(service.rerank_scores, request.query, request.passages)
        return ScoreResponse(
            scores=[float(score) for score in payload["scores"]],
            model_name=str(payload["model_name"]),
        )

    @app.post("/query", response_model=QueryResponse)
    async def _query(request: QueryRequest) -> QueryResponse:
        """Return serialized semantic query results from the daemon-owned vector service."""
        await asyncio.to_thread(_ensure_query_ready)
        try:
            parsed_scope = IndexScope(request.scope) if request.scope else None
        except ValueError:
            return QueryResponse(items=[])
        file_path = Path(request.file_path).resolve() if request.file_path else None
        results = await asyncio.to_thread(
            service.query,
            request.query_text,
            top_k=request.top_k,
            scope=parsed_scope,
            file_path=file_path,
        )
        return QueryResponse(items=[_serialize_query_result(result) for result in results])

    return app


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the local reranker daemon."""
    parser = argparse.ArgumentParser(description="Run the local read-code reranker daemon.")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--socket-path", type=Path, required=True)
    parser.add_argument("--pid-file", type=Path)
    parser.add_argument("--endpoint-file", type=Path)
    parser.add_argument("--log-file", type=Path)
    parser.add_argument("--tcp-port", type=int)
    parser.add_argument("--log-level", default="warning")
    parser.add_argument("--reranker-model", default=DEFAULT_RERANKER_MODEL_NAME)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the reranker daemon over a local Unix domain socket."""
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = args.repo_root.expanduser().resolve()
    socket_path = args.socket_path.expanduser()
    pid_file = args.pid_file.expanduser().resolve() if args.pid_file is not None else reranker_pid_path(repo_root)
    endpoint_file = args.endpoint_file.expanduser().resolve() if args.endpoint_file is not None else reranker_endpoint_path(repo_root)
    log_file = args.log_file.expanduser().resolve() if args.log_file is not None else reranker_log_path(repo_root)
    tcp_port = int(args.tcp_port) if args.tcp_port is not None else reranker_tcp_port(repo_root)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        socket_path.unlink(missing_ok=True)
    except OSError:
        pass
    persist_json_object(
        endpoint_file,
        {
            "transport": "uds",
            "socket_path": str(socket_path),
        },
        sort_keys=True,
    )
    try:
        app = build_app(
            repo_root=repo_root,
            reranker_model=args.reranker_model,
            pid_file=pid_file,
            endpoint_file=endpoint_file,
        )
        config = uvicorn.Config(
            app,
            uds=str(socket_path),
            log_level=args.log_level,
            access_log=False,
        )
        server = uvicorn.Server(config)
        return 0 if server.run() is None else 0
    except OSError:
        persist_json_object(
            endpoint_file,
            {
                "transport": "tcp",
                "host": "127.0.0.1",
                "port": tcp_port,
            },
            sort_keys=True,
        )
        app = build_app(
            repo_root=repo_root,
            reranker_model=args.reranker_model,
            pid_file=pid_file,
            endpoint_file=endpoint_file,
        )
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=tcp_port,
            log_level=args.log_level,
            access_log=False,
        )
        server = uvicorn.Server(config)
        return 0 if server.run() is None else 0


if __name__ == "__main__":
    raise SystemExit(main())
