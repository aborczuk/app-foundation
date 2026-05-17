"""Local Unix-socket reranker daemon for read-code shortlist rescoring."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.mcp_codebase.index.config import (
    DEFAULT_EMBEDDING_MODEL_NAME,
    DEFAULT_RERANKER_MODEL_NAME,
    DEFAULT_VECTOR_DB_PATH,
    IndexConfig,
    load_exclude_patterns,
)
from src.mcp_codebase.index.reranker_runtime import (
    READ_CODE_RERANKER_FILE_RPC_POLL_INTERVAL_SECONDS,
    persist_json_object,
    reranker_build_fingerprint,
    reranker_endpoint_path,
    reranker_file_rpc_heartbeat_path,
    reranker_file_rpc_requests_dir,
    reranker_file_rpc_responses_dir,
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


def build_app(
    *,
    repo_root: Path,
    reranker_model: str,
    pid_file: Path | None = None,
    endpoint_file: Path | None = None,
    file_rpc_requests_dir: Path | None = None,
    file_rpc_responses_dir: Path | None = None,
    file_rpc_heartbeat_path: Path | None = None,
) -> FastAPI:
    """Create the reranker daemon application with warmed model state."""
    app = FastAPI()
    service = _build_service(repo_root, reranker_model=reranker_model)
    started_at = time.time()
    build_fingerprint = reranker_build_fingerprint(repo_root, reranker_model)
    background_tasks: list[asyncio.Task[None]] = []

    def _heartbeat_payload() -> dict[str, object]:
        """Return the shared file-RPC heartbeat payload for client-side liveness checks."""
        return {
            "updated_at": time.time(),
            "pid": os.getpid(),
            "model_name": reranker_model,
            "build_fingerprint": build_fingerprint,
            "started_at": started_at,
        }

    async def _drain_file_rpc_requests_once() -> None:
        """Process the current bounded rerank requests from the shared file-RPC queue."""
        assert file_rpc_requests_dir is not None
        assert file_rpc_responses_dir is not None
        request_paths = sorted(file_rpc_requests_dir.glob("*.request.json"))
        for request_path in request_paths:
            response_path = file_rpc_responses_dir / request_path.name.replace(".request.json", ".response.json")
            try:
                payload = json.loads(request_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {"error": "invalid-request-payload"}
            query = payload.get("query")
            passages = payload.get("passages")
            if isinstance(query, str) and isinstance(passages, list) and all(isinstance(item, str) for item in passages):
                result = await asyncio.to_thread(service.rerank_scores, query, passages)
                response_payload = {
                    "scores": [float(score) for score in result["scores"]],
                    "model_name": str(result["model_name"]),
                }
            else:
                response_payload = {"error": "invalid-request-shape"}
            await asyncio.to_thread(persist_json_object, response_path, response_payload, sort_keys=True)
            try:
                request_path.unlink(missing_ok=True)
            except OSError:
                pass

    async def _heartbeat_loop() -> None:
        """Continuously refresh the shared heartbeat file and service file-RPC clients."""
        assert file_rpc_heartbeat_path is not None
        while True:
            await asyncio.to_thread(
                persist_json_object,
                file_rpc_heartbeat_path,
                _heartbeat_payload(),
                sort_keys=True,
            )
            if file_rpc_requests_dir is not None and file_rpc_responses_dir is not None:
                await _drain_file_rpc_requests_once()
            await asyncio.sleep(READ_CODE_RERANKER_FILE_RPC_POLL_INTERVAL_SECONDS)

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
        if file_rpc_requests_dir is not None:
            file_rpc_requests_dir.mkdir(parents=True, exist_ok=True)
        if file_rpc_responses_dir is not None:
            file_rpc_responses_dir.mkdir(parents=True, exist_ok=True)
        if file_rpc_heartbeat_path is not None:
            persist_json_object(file_rpc_heartbeat_path, _heartbeat_payload(), sort_keys=True)
            background_tasks.append(asyncio.create_task(_heartbeat_loop()))

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        """Remove the PID marker when the daemon exits cleanly."""
        for task in background_tasks:
            task.cancel()
        for path in (pid_file, endpoint_file, file_rpc_heartbeat_path):
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
    socket_path = args.socket_path.expanduser().resolve()
    pid_file = args.pid_file.expanduser().resolve() if args.pid_file is not None else reranker_pid_path(repo_root)
    endpoint_file = args.endpoint_file.expanduser().resolve() if args.endpoint_file is not None else reranker_endpoint_path(repo_root)
    log_file = args.log_file.expanduser().resolve() if args.log_file is not None else reranker_log_path(repo_root)
    tcp_port = int(args.tcp_port) if args.tcp_port is not None else reranker_tcp_port(repo_root)
    file_rpc_requests_dir = reranker_file_rpc_requests_dir(repo_root)
    file_rpc_responses_dir = reranker_file_rpc_responses_dir(repo_root)
    file_rpc_heartbeat_path = reranker_file_rpc_heartbeat_path(repo_root)
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
            file_rpc_requests_dir=file_rpc_requests_dir,
            file_rpc_responses_dir=file_rpc_responses_dir,
            file_rpc_heartbeat_path=file_rpc_heartbeat_path,
        )
        config = uvicorn.Config(
            app,
            uds=str(socket_path),
            log_level=args.log_level,
            access_log=False,
        )
        server = uvicorn.Server(config)
        return 0 if server.run() is None else 0
    except PermissionError:
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
            file_rpc_requests_dir=file_rpc_requests_dir,
            file_rpc_responses_dir=file_rpc_responses_dir,
            file_rpc_heartbeat_path=file_rpc_heartbeat_path,
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
