"""Unit tests for the reranker stdio worker protocol."""

from __future__ import annotations

import io
import json
from pathlib import Path

from src.mcp_codebase.index.domain import IndexScope
from src.mcp_codebase.index.reranker_stdio_worker import run_stdio_worker


class _FakeService:
    """Small fake service for protocol verification without model startup."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def ensure_reranker_model_local(self) -> dict[str, object]:
        """Record model warmup and return a bounded fake payload."""
        self.calls.append(("ensure_reranker_model_local", None))
        return {"model_name": "fake-reranker"}

    def rerank_scores(self, query: str, passages: list[str]) -> dict[str, object]:
        """Return deterministic fake scores for the worker protocol test."""
        self.calls.append(("rerank_scores", (query, tuple(passages))))
        return {"model_name": "fake-reranker", "scores": [0.25 for _ in passages]}

    def query(
        self,
        query_text: str,
        *,
        top_k: int = 10,
        scope=None,
        file_path=None,
    ) -> list[object]:
        """Return one deterministic fake semantic result for worker protocol tests."""
        self.calls.append(("query", (query_text, top_k, scope, file_path)))

        class _Content:
            symbol_name = "fake_symbol"
            qualified_name = "fake.module.fake_symbol"

        class _Result:
            file_path = Path("/tmp/example.py")
            line_start = 11
            line_end = 15
            score = 0.75
            body = "def fake_symbol():\n    return 1"
            preview = "def fake_symbol(): ..."
            signature = "def fake_symbol()"
            docstring = "Return a fake value."
            symbol_type = "function"
            content = _Content()

        return [_Result()]


def test_stdio_worker_serves_health_score_and_shutdown() -> None:
    """One worker should answer multiple requests over the same stdio session."""
    service = _FakeService()
    stdin = io.StringIO(
        "\n".join(
            [
                json.dumps({"op": "health"}),
                json.dumps({"op": "score", "query": "what", "passages": ["one", "two"]}),
                json.dumps({"op": "shutdown"}),
            ]
        )
        + "\n"
    )
    stdout = io.StringIO()

    code = run_stdio_worker(
        stdin=stdin,
        stdout=stdout,
        service=service,  # type: ignore[arg-type]
        reranker_model="fake-reranker",
        repo_root=Path.cwd(),
    )

    assert code == 0
    responses = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert responses[0]["op"] == "ready"
    assert responses[0]["ok"] is True
    assert responses[1]["op"] == "health"
    assert responses[1]["ok"] is True
    assert responses[1]["pid"] == responses[0]["pid"]
    assert responses[1]["started_at"] == responses[0]["started_at"]
    assert responses[2]["op"] == "score"
    assert responses[2]["ok"] is True
    assert responses[2]["scores"] == [0.25, 0.25]
    assert responses[2]["pid"] == responses[0]["pid"]
    assert responses[2]["started_at"] == responses[0]["started_at"]
    assert responses[3]["op"] == "shutdown"
    assert responses[3]["ok"] is True
    assert service.calls == [
        ("ensure_reranker_model_local", None),
        ("rerank_scores", ("__warmup__", ("__warmup__",))),
        ("rerank_scores", ("what", ("one", "two"))),
    ]


def test_stdio_worker_serves_query_requests() -> None:
    """One worker should serialize semantic query responses over the same stdio session."""
    service = _FakeService()
    stdin = io.StringIO(
        "\n".join(
            [
                json.dumps(
                    {
                        "op": "query",
                        "query": "what",
                        "top_k": 3,
                        "scope": "code",
                        "file_path": "/tmp/example.py",
                    }
                ),
                json.dumps({"op": "shutdown"}),
            ]
        )
        + "\n"
    )
    stdout = io.StringIO()

    code = run_stdio_worker(
        stdin=stdin,
        stdout=stdout,
        service=service,  # type: ignore[arg-type]
        reranker_model="fake-reranker",
        repo_root=Path.cwd(),
    )

    assert code == 0
    responses = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert responses[0]["op"] == "ready"
    assert responses[1]["op"] == "query"
    assert responses[1]["ok"] is True
    assert responses[1]["item_count"] == 1
    assert responses[1]["items"][0]["symbol_name"] == "fake_symbol"
    assert responses[2]["op"] == "shutdown"
    assert service.calls == [
        ("ensure_reranker_model_local", None),
        ("rerank_scores", ("__warmup__", ("__warmup__",))),
        ("query", ("what", 3, IndexScope.CODE, Path("/tmp/example.py").resolve())),
    ]
