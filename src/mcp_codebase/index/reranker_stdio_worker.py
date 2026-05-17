"""Persistent stdio worker for reranker scoring experiments."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import IO, Sequence

from src.mcp_codebase.index.config import (
    DEFAULT_EMBEDDING_MODEL_NAME,
    DEFAULT_RERANKER_MODEL_NAME,
    DEFAULT_VECTOR_DB_PATH,
    IndexConfig,
    load_exclude_patterns,
)
from src.mcp_codebase.index.domain import IndexScope
from src.mcp_codebase.index.reranker_runtime import reranker_build_fingerprint
from src.mcp_codebase.index.service import VectorIndexService


def _build_service(repo_root: Path, *, reranker_model: str) -> VectorIndexService:
    """Construct the vector service with the same local model defaults as the daemon."""
    config = IndexConfig(
        repo_root=repo_root,
        db_path=repo_root / DEFAULT_VECTOR_DB_PATH,
        embedding_model=DEFAULT_EMBEDDING_MODEL_NAME,
        reranker_model=reranker_model,
        exclude_patterns=load_exclude_patterns(),
    )
    return VectorIndexService(config)


def _emit_json_line(stdout: IO[str], payload: dict[str, object]) -> None:
    """Write one newline-delimited JSON payload and flush immediately."""
    stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    stdout.flush()


def _query_items_payload(
    service: VectorIndexService,
    *,
    query: str,
    top_k: int,
    scope: str,
    file_path: str | None,
) -> list[dict[str, object]]:
    """Return serialized semantic query results for stdio transport."""
    results = service.query(
        query,
        top_k=top_k,
        scope=IndexScope(scope),
        file_path=Path(file_path).resolve() if file_path else None,
    )
    return [
        {
            "file_path": str(result.file_path),
            "line_start": result.line_start,
            "line_end": result.line_end,
            "score": result.score,
            "body": result.body,
            "preview": result.preview,
            "signature": result.signature,
            "docstring": result.docstring,
            "symbol_type": result.symbol_type,
            "symbol_name": getattr(result.content, "symbol_name", ""),
            "qualified_name": getattr(result.content, "qualified_name", ""),
        }
        for result in results
    ]


def run_stdio_worker(
    *,
    stdin: IO[str],
    stdout: IO[str],
    service: VectorIndexService,
    reranker_model: str,
    repo_root: Path,
) -> int:
    """Serve health and score requests over newline-delimited JSON on stdio."""
    started_at = time.time()
    pid = os.getpid()
    build_fingerprint = reranker_build_fingerprint(repo_root, reranker_model)
    try:
        service.ensure_reranker_model_local()
        service.rerank_scores("__warmup__", ["__warmup__"])
    except Exception as exc:
        _emit_json_line(
            stdout,
            {
                "op": "ready",
                "ok": False,
                "error": f"worker startup failed: {exc}",
            },
        )
        return 1

    _emit_json_line(
        stdout,
        {
            "op": "ready",
            "ok": True,
            "pid": pid,
            "started_at": started_at,
            "model_name": reranker_model,
            "build_fingerprint": build_fingerprint,
        },
    )

    for raw_line in stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            _emit_json_line(stdout, {"ok": False, "error": f"invalid-json: {exc.msg}"})
            continue
        if not isinstance(payload, dict):
            _emit_json_line(stdout, {"ok": False, "error": "invalid-request-shape"})
            continue
        op = payload.get("op")
        if op == "health":
            _emit_json_line(
                stdout,
                {
                    "op": "health",
                    "ok": True,
                    "pid": pid,
                    "started_at": started_at,
                    "model_name": reranker_model,
                    "build_fingerprint": build_fingerprint,
                },
            )
            continue
        if op == "score":
            query = payload.get("query")
            passages = payload.get("passages")
            if not isinstance(query, str) or not isinstance(passages, list) or not all(
                isinstance(item, str) for item in passages
            ):
                _emit_json_line(stdout, {"op": "score", "ok": False, "error": "invalid-score-request"})
                continue
            started = time.perf_counter()
            try:
                result = service.rerank_scores(query, passages)
            except Exception as exc:
                _emit_json_line(stdout, {"op": "score", "ok": False, "error": f"score-failed: {exc}"})
                continue
            _emit_json_line(
                stdout,
                {
                    "op": "score",
                    "ok": True,
                    "pid": pid,
                    "started_at": started_at,
                    "model_name": str(result["model_name"]),
                    "scores": [float(score) for score in result["scores"]],
                    "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
                },
            )
            continue
        if op == "query":
            query = payload.get("query")
            top_k = payload.get("top_k")
            scope = payload.get("scope")
            file_path = payload.get("file_path")
            if (
                not isinstance(query, str)
                or not isinstance(top_k, int)
                or top_k <= 0
                or not isinstance(scope, str)
                or (file_path is not None and not isinstance(file_path, str))
            ):
                _emit_json_line(stdout, {"op": "query", "ok": False, "error": "invalid-query-request"})
                continue
            started = time.perf_counter()
            try:
                items = _query_items_payload(
                    service,
                    query=query,
                    top_k=top_k,
                    scope=scope,
                    file_path=file_path,
                )
            except Exception as exc:
                _emit_json_line(stdout, {"op": "query", "ok": False, "error": f"query-failed: {exc}"})
                continue
            _emit_json_line(
                stdout,
                {
                    "op": "query",
                    "ok": True,
                    "pid": pid,
                    "started_at": started_at,
                    "item_count": len(items),
                    "items": items,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
                },
            )
            continue
        if op == "shutdown":
            _emit_json_line(stdout, {"op": "shutdown", "ok": True, "pid": pid})
            return 0
        _emit_json_line(stdout, {"ok": False, "error": f"unsupported-op: {op}"})
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the stdio worker spike."""
    parser = argparse.ArgumentParser(description="Run the read-code reranker stdio worker.")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--reranker-model", default=DEFAULT_RERANKER_MODEL_NAME)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Start the stdio reranker worker using the real repo-local vector service."""
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = args.repo_root.expanduser().resolve()
    service = _build_service(repo_root, reranker_model=args.reranker_model)
    return run_stdio_worker(
        stdin=sys.stdin,
        stdout=sys.stdout,
        service=service,
        reranker_model=args.reranker_model,
        repo_root=repo_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
