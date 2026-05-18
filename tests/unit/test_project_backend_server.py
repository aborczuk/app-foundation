"""Unit tests for the MCP-native project backend server."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

import src.mcp_codebase.project_backend_server as backend_server


class _FakeQueryResult:
    """Provide one minimal model_dump-compatible query result."""

    def __init__(self, payload: dict[str, object]) -> None:
        """Store one fixed payload for later model_dump calls."""
        self._payload = dict(payload)

    def model_dump(self, *, mode: str = "json") -> dict[str, object]:
        """Return the stored JSON-safe payload."""
        assert mode == "json"
        return dict(self._payload)


class _FakeVectorIndexService:
    """Keep project-backend unit tests off the real vector runtime."""

    class _FakeStore:
        """Expose the cheap active-metadata seam used by MCP readiness checks."""

        def _load_active_metadata(self) -> dict[str, object]:
            """Return one truthy fake active-manifest payload."""
            return {"snapshot_path": "/tmp/fake-snapshot"}

    def __init__(self) -> None:
        """Attach one fake store with an active metadata loader."""
        self._store = self._FakeStore()
        self.ensure_reranker_calls = 0
        self.rerank_calls = 0

    def status(self) -> dict[str, object]:
        """Return one healthy fake status payload."""
        return {"healthy": True}

    def build_full_index(self, revision: str = "local") -> None:
        """Accept the one-time warm-up call without side effects."""
        _ = revision

    def ensure_reranker_model_local(self) -> dict[str, object]:
        """Return a bounded fake health payload."""
        self.ensure_reranker_calls += 1
        return {"model_loaded": True, "model_name": "fake-model"}

    def query(
        self,
        query_text: str,
        *,
        top_k: int,
        scope: object,
        file_path: Path | None,
    ) -> list[_FakeQueryResult]:
        """Return one deterministic query row for tests."""
        _ = top_k
        _ = scope
        resolved = file_path.resolve() if file_path is not None else Path("/tmp/example.py")
        return [
            _FakeQueryResult(
                {
                    "file_path": str(resolved),
                    "line_start": 1,
                    "line_end": 3,
                    "score": 0.75,
                    "body": f"def {query_text}():\n    return 1",
                    "preview": f"def {query_text}(): ...",
                    "signature": f"def {query_text}()",
                    "docstring": "Fake query result.",
                    "symbol_type": "function",
                    "symbol_name": query_text,
                    "qualified_name": query_text,
                }
            )
        ]

    def rerank_scores(self, query_text: str, passages: list[str]) -> dict[str, object]:
        """Return bounded float scores for fake rerank requests."""
        self.rerank_calls += 1
        _ = query_text
        return {
            "scores": [float(index + 1) for index, _ in enumerate(passages)],
            "model_name": "fake-model",
        }


def _extract_tool_payload(tool_result: object) -> dict[str, object]:
    """Extract the structured JSON payload returned by one MCP tool call."""
    if isinstance(tool_result, tuple) and len(tool_result) == 2 and isinstance(tool_result[1], dict):
        return tool_result[1]

    structured = getattr(tool_result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    content = getattr(tool_result, "content", None)
    if content and getattr(content[0], "text", None):
        import json

        payload = json.loads(content[0].text)
        if isinstance(payload, dict):
            return payload

    raise AssertionError("tool did not return a JSON object")


@pytest.fixture()
def server(monkeypatch: pytest.MonkeyPatch) -> backend_server.ProjectBackendServer:
    """Create one backend server with a fake in-memory vector service."""
    monkeypatch.setattr(backend_server, "_build_service", lambda *_args, **_kwargs: _FakeVectorIndexService())
    return backend_server.create_server(project_root=Path.cwd())


def test_create_server_registers_mcp_native_read_code_tools(
    server: backend_server.ProjectBackendServer,
) -> None:
    """The backend server should expose both warm backend and MCP-native read_code tools."""
    tool_names = {tool.name for tool in asyncio.run(server.mcp.list_tools())}

    assert tool_names == {
        "get_process_identity",
        "get_runtime_capabilities",
        "warmup",
        "health",
        "score_probe",
        "query",
        "score",
        "read_code_context",
        "read_code_find",
        "read_code_analyze",
        "read_code_window",
    }


def test_run_read_code_command_injects_local_backend_and_restores_session(
    server: backend_server.ProjectBackendServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shared read_code execution should see the warm in-process backend and bounded session id."""
    calls: list[tuple[list[str], bool, str | None]] = []
    previous = os.environ.get("READ_CODE_SESSION_ID")

    class _FakeReadCodeModule:
        _READ_CODE_RERANKER_BACKEND = "before-backend"
        _READ_CODE_VECTOR_QUERY_SERVICE = "before-service"

        def read_code_context(self, argv: list[str], *, verbose: bool = False) -> int:
            calls.append((list(argv), verbose, os.environ.get("READ_CODE_SESSION_ID")))
            assert self._READ_CODE_RERANKER_BACKEND is server._read_code_backend
            assert self._READ_CODE_VECTOR_QUERY_SERVICE is server._vector_index_service
            print("context stdout")
            print("context stderr", file=sys.stderr)
            return 0

    fake_module = _FakeReadCodeModule()
    monkeypatch.setattr(server, "_read_code_module", fake_module)

    payload = server._run_read_code_command(
        "read_code_context",
        ["symbol", "--path", str(Path.cwd() / "scripts" / "read_code.py")],
        session_id="unit-session",
        verbose=True,
    )

    assert calls == [
        (
            ["symbol", "--path", str(Path.cwd() / "scripts" / "read_code.py")],
            True,
            "unit-session",
        )
    ]
    assert payload["exit_code"] == 0
    assert payload["stdout"] == "context stdout\n"
    assert payload["stderr"] == "context stderr\n"
    assert fake_module._READ_CODE_RERANKER_BACKEND == "before-backend"
    assert fake_module._READ_CODE_VECTOR_QUERY_SERVICE == "before-service"
    assert os.environ.get("READ_CODE_SESSION_ID") == previous


def test_read_code_window_tool_returns_bounded_output(server: backend_server.ProjectBackendServer) -> None:
    """The MCP-native window tool should reuse the shared read_code window renderer."""
    payload = _extract_tool_payload(
        asyncio.run(
            server.mcp.call_tool(
                "read_code_window",
                {
                    "file_path": str(Path(__file__).resolve()),
                    "start_line": 1,
                    "end_line": 3,
                },
            )
        )
    )

    assert payload["exit_code"] == 0
    assert '"""Unit tests for the MCP-native project backend server."""' in payload["stdout"]
    assert payload["stderr"] == ""
    assert payload["pid"] > 0


def test_runtime_capabilities_tool_returns_bounded_probe_payload(
    server: backend_server.ProjectBackendServer,
) -> None:
    """The MCP runtime probe should return bounded accelerator capability flags."""
    payload = _extract_tool_payload(asyncio.run(server.mcp.call_tool("get_runtime_capabilities", {})))

    assert payload["name"] == "read-code-persistence-probe"
    assert payload["pid"] > 0
    assert payload["project_root"] == str(Path.cwd())
    assert isinstance(payload["torch_available"], bool)
    assert isinstance(payload["mps_built"], bool)
    assert isinstance(payload["mps_available"], bool)
    assert isinstance(payload["cuda_available"], bool)


def test_warmup_tool_primes_reranker_once(server: backend_server.ProjectBackendServer) -> None:
    """The explicit warmup tool should prime reranker init and first forward once per server."""
    first = _extract_tool_payload(asyncio.run(server.mcp.call_tool("warmup", {})))
    second = _extract_tool_payload(asyncio.run(server.mcp.call_tool("warmup", {})))

    assert first["warmup_completed"] is True
    assert second["warmup_completed"] is True
    assert second["elapsed_ms"] <= first["elapsed_ms"]
    assert server._vector_index_service.ensure_reranker_calls == 1
    assert server._vector_index_service.rerank_calls == 1


def test_score_probe_tool_reports_elapsed_time_and_score_count(
    server: backend_server.ProjectBackendServer,
) -> None:
    """The rerank timing probe should return bounded score metadata."""
    payload = _extract_tool_payload(
        asyncio.run(
            server.mcp.call_tool(
                "score_probe",
                {
                    "query_text": "vector trust decision",
                    "passages": ["one", "two", "three"],
                },
            )
        )
    )

    assert payload["name"] == "read-code-persistence-probe"
    assert payload["score_count"] == 3
    assert payload["elapsed_ms"] >= 0
    assert payload["selected_device"] is None


def test_ensure_vector_index_ready_uses_store_metadata_without_service_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MCP readiness should use active snapshot metadata instead of full service status diagnostics."""

    class _StatusShouldNotRunService(_FakeVectorIndexService):
        def status(self) -> dict[str, object]:
            """Fail loudly if the heavy service status path is touched."""
            raise AssertionError("service.status() should not run for MCP readiness")

    monkeypatch.setattr(
        backend_server,
        "_build_service",
        lambda *_args, **_kwargs: _StatusShouldNotRunService(),
    )
    server = backend_server.create_server(project_root=Path.cwd())

    server._ensure_vector_index_ready()
    server._ensure_vector_index_ready()

    assert server._vector_index_ready is True


def test_prepare_stdio_runtime_reaps_previous_backend_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Starting a new backend server should reap the previously tracked backend pid once."""
    monkeypatch.setenv("READ_CODE_MCP_INSTANCE_OWNER", "unit-owner")
    monkeypatch.setattr(backend_server, "_build_service", lambda *_args, **_kwargs: _FakeVectorIndexService())
    server = backend_server.create_server(project_root=tmp_path)
    pid_path = backend_server._backend_pid_path(tmp_path, "unit-owner")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("4242\n", encoding="utf-8")

    terminated: list[int] = []
    monkeypatch.setattr(backend_server, "_pid_matches_backend_server", lambda pid: pid == 4242)
    monkeypatch.setattr(backend_server, "_terminate_backend_pid", lambda pid: terminated.append(pid))

    written_path = server._prepare_stdio_runtime()

    assert written_path == pid_path
    assert terminated == [4242]
    assert pid_path.read_text(encoding="utf-8").strip() == str(server._pid)


def test_prepare_stdio_runtime_leaves_unrelated_pid_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The singleton guard should not terminate unrelated pids recorded in the pid file."""
    monkeypatch.setenv("READ_CODE_MCP_INSTANCE_OWNER", "unit-owner")
    monkeypatch.setattr(backend_server, "_build_service", lambda *_args, **_kwargs: _FakeVectorIndexService())
    server = backend_server.create_server(project_root=tmp_path)
    pid_path = backend_server._backend_pid_path(tmp_path, "unit-owner")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("5151\n", encoding="utf-8")

    terminated: list[int] = []
    monkeypatch.setattr(backend_server, "_pid_matches_backend_server", lambda _pid: False)
    monkeypatch.setattr(backend_server, "_terminate_backend_pid", lambda pid: terminated.append(pid))

    server._prepare_stdio_runtime()

    assert terminated == []
    assert pid_path.read_text(encoding="utf-8").strip() == str(server._pid)
