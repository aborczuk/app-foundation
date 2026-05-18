"""Integration regressions for configurable exclusions, performance slices, and feature-031 evidence."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import select
import shutil
import subprocess
import sys
from pathlib import Path
from time import perf_counter

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from src.mcp_codebase.index import IndexConfig, IndexScope
from src.mcp_codebase.index.service import VectorIndexService


def _load_script_module(module_name: str, script_name: str):
    """Load one scripts module directly from the repo for integration-style verification."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


read_code = _load_script_module("read_code_live_rerank_integration", "read_code.py")


def _persistence_artifact_path() -> Path:
    """Return the opt-in artifact path used to validate MCP persistence evidence."""
    override = os.environ.get("READ_CODE_PERSISTENCE_ARTIFACT_PATH")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[2] / ".codegraphcontext" / "read-code-persistence-probe.json"


def _mcp_read_surface_artifact_path() -> Path:
    """Return the opt-in artifact path used to validate direct MCP read-surface persistence."""
    override = os.environ.get("READ_CODE_MCP_READ_SURFACE_ARTIFACT_PATH")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[2] / ".codegraphcontext" / "read-code-mcp-read-surface-probe.json"


def _normalize_identity(identity: object) -> dict[str, object]:
    """Return one validated identity object with the expected bounded keys."""
    if not isinstance(identity, dict):
        raise AssertionError("identity snapshot must be a JSON object")
    if set(identity) != {"name", "project_root", "pid", "started_at"}:
        raise AssertionError("identity snapshot must contain name, project_root, pid, and started_at")
    return identity


def _load_persistence_artifact(path: Path) -> dict[str, object]:
    """Load the externally captured MCP persistence artifact from disk."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"persistence artifact must be a JSON object: {path}")
    return payload


def _assert_comparison_matches(payload: dict[str, object]) -> None:
    """Assert the artifact comparison confirms the same pid and started_at."""
    comparison = payload.get("comparison")
    if not isinstance(comparison, dict):
        raise AssertionError("persistence artifact must contain a comparison object")
    assert comparison.get("same_pid") is True
    assert comparison.get("same_started_at") is True


def _normalize_mcp_command_payload(payload: object) -> dict[str, object]:
    """Return one validated direct-MCP read-command payload."""
    if not isinstance(payload, dict):
        raise AssertionError("direct MCP read payload must be a JSON object")
    required = {"name", "pid", "started_at", "command", "argv", "exit_code", "stdout", "stderr"}
    if set(payload) != required:
        raise AssertionError(f"direct MCP read payload must contain exactly {sorted(required)}")
    if not isinstance(payload["argv"], list):
        raise AssertionError("direct MCP read payload argv must be a list")
    if not isinstance(payload["stdout"], str) or not isinstance(payload["stderr"], str):
        raise AssertionError("direct MCP read payload stdout/stderr must be strings")
    return payload


def _structured(tool_result: object) -> object:
    """Return structured content from one MCP tool result."""
    structured = getattr(tool_result, "structuredContent", None)
    if structured is None:
        raise AssertionError("MCP tool did not return structured content")
    if isinstance(structured, str):
        try:
            return json.loads(structured)
        except json.JSONDecodeError:
            return structured
    return structured


async def _exercise_live_backend_server(repo_root: Path) -> dict[str, object]:
    """Spawn one live backend server over stdio and exercise its public tools."""
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp_codebase.project_backend_server"],
        cwd=repo_root,
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}

            first_payload = _structured(await session.call_tool("get_process_identity", {}))
            second_payload = _structured(await session.call_tool("get_process_identity", {}))
            health_payload = _structured(await session.call_tool("health", {}))
            query_payload_raw = _structured(
                await session.call_tool(
                    "query",
                    {
                        "query_text": "_vector_find_candidates",
                        "top_k": 2,
                        "scope": "code",
                        "file_path": str(repo_root / "scripts" / "read_code.py"),
                    },
                )
            )
            if isinstance(query_payload_raw, dict):
                query_payload = query_payload_raw.get("items")
            elif isinstance(query_payload_raw, list):
                query_payload = query_payload_raw
            else:
                query_payload = []
            if not isinstance(query_payload, list):
                query_payload = []
            first_passage = "def _vector_find_candidates(...): ..."
            second_passage = "def _vector_query_candidates(...): ..."
            if query_payload:
                first_item = query_payload[0]
                if not isinstance(first_item, dict):
                    raise AssertionError("query tool returned a non-object result")
                second_item = query_payload[1] if len(query_payload) > 1 else first_item
                if not isinstance(second_item, dict):
                    raise AssertionError("query tool returned a non-object result")
                first_passage = first_item.get("preview") or first_item.get("body") or first_passage
                second_passage = second_item.get("preview") or second_item.get("body") or second_passage
            score_payload = _structured(
                await session.call_tool(
                    "score",
                    {
                        "query_text": "semantic rerank worker",
                        "passages": [first_passage, second_passage],
                    },
                )
            )
            read_code_context_payload = _structured(
                await session.call_tool(
                    "read_code_context",
                    {
                        "pattern": "_vector_query_candidates",
                        "file_path": str(repo_root / "scripts" / "read_code.py"),
                        "content_type": "code",
                    },
                )
            )
            read_code_find_payload = _structured(
                await session.call_tool(
                    "read_code_find",
                    {
                        "command": "name",
                        "args": ["read_code_context"],
                    },
                )
            )
            read_code_analyze_payload = _structured(
                await session.call_tool(
                    "read_code_analyze",
                    {
                        "command": "deps",
                        "args": ["src.mcp_codebase.project_backend_server"],
                    },
                )
            )
            read_code_window_payload = _structured(
                await session.call_tool(
                    "read_code_window",
                    {
                        "file_path": str(repo_root / "scripts" / "read_code.py"),
                        "start_line": 1,
                        "end_line": 3,
                    },
                )
            )

            return {
                "tool_names": tool_names,
                "identity_1": _normalize_identity(first_payload),
                "identity_2": _normalize_identity(second_payload),
                "health": health_payload,
                "query": query_payload,
                "score": score_payload,
                "read_code_context": read_code_context_payload,
                "read_code_find": read_code_find_payload,
                "read_code_analyze": read_code_analyze_payload,
                "read_code_window": read_code_window_payload,
            }


def _build_offline_vector_index_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    exclude_patterns: tuple[str, ...] = (),
) -> VectorIndexService:
    """Create a temp-repo vector index service with a seeded local embedding cache."""

    repo_root = Path(__file__).resolve().parents[2]
    source_cache = (
        repo_root / ".codegraphcontext" / "global" / "db" / "vector-index" / "fastembed-cache"
    )
    if not source_cache.exists():
        raise AssertionError(f"Missing shared fastembed cache at {source_cache}")

    target_cache = (
        tmp_path / ".codegraphcontext" / "global" / "db" / "vector-index" / "fastembed-cache"
    )
    target_cache.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_cache, target_cache, dirs_exist_ok=True)

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    return VectorIndexService(
        IndexConfig(
            repo_root=tmp_path,
            db_path=Path(".codegraphcontext/global/db/vector-index"),
            embedding_model="local-default",
            exclude_patterns=exclude_patterns,
        )
    )


def _write_python_modules(root: Path, count: int) -> list[Path]:
    """Create a deterministic batch of simple Python modules."""
    created: list[Path] = []
    src_root = root / "src" / "bulk"
    src_root.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        module = src_root / f"module_{index}.py"
        module.write_text(
            f"""
def symbol_{index}() -> str:
    return "symbol-{index}"
""".strip()
            + "\n",
            encoding="utf-8",
        )
        created.append(module)
    return created


def test_configurable_excludes_respected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configured exclude patterns should block indexing beyond built-in generated rules."""

    source = tmp_path / "src" / "live.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        """
def live_symbol() -> str:
    return "live"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    excluded = tmp_path / "docs" / "build" / "ignored.md"
    excluded.parent.mkdir(parents=True, exist_ok=True)
    excluded.write_text(
        """
# Ignored

## Hidden

Do not index this section.
""".strip()
        + "\n",
        encoding="utf-8",
    )

    service = _build_offline_vector_index_service(
        tmp_path,
        monkeypatch,
        exclude_patterns=("docs/build/**",),
    )
    service.build_full_index(revision="rev-a")

    live = service.query("live_symbol", scope=IndexScope.CODE, top_k=1)
    assert live
    assert live[0].file_path == source

    hidden = service.query("Hidden", scope=IndexScope.MARKDOWN, top_k=1)
    assert hidden == []


def test_index_build_and_refresh_meets_timing_budgets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Build and single-file refresh should stay inside the spec timing budget."""

    source_paths = _write_python_modules(tmp_path, count=40)

    service = _build_offline_vector_index_service(tmp_path, monkeypatch)

    build_started = perf_counter()
    built = service.build_full_index(revision="rev-a")
    build_seconds = perf_counter() - build_started

    assert built.code_symbol_count == 40
    assert build_seconds < 60.0

    changed = source_paths[0]
    changed.write_text(
        """
def symbol_0() -> str:
    return "symbol-0"


def refreshed_symbol() -> str:
    return "refreshed"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    refresh_started = perf_counter()
    refreshed = service.refresh_changed_files([changed], revision="rev-b")
    refresh_seconds = perf_counter() - refresh_started

    assert refreshed.indexed_commit == "rev-b"
    assert refreshed.code_symbol_count == 41
    assert refresh_seconds < 10.0

    refreshed_result = service.query("refreshed_symbol", scope=IndexScope.CODE, top_k=1)
    assert refreshed_result
    assert refreshed_result[0].file_path == changed


def test_live_project_local_mcp_server_persistence_artifact_matches_across_turns() -> None:
    """Opt-in live verification should validate externally captured MCP persistence evidence."""
    artifact_path = _persistence_artifact_path()
    if not artifact_path.exists():
        pytest.skip(f"Missing MCP persistence artifact at {artifact_path}")

    payload = _load_persistence_artifact(artifact_path)
    previous = _normalize_identity(payload.get("previous"))
    current = _normalize_identity(payload.get("current"))
    expected_repo_root = str(Path(__file__).resolve().parents[2])

    assert previous["name"] == "read-code-persistence-probe"
    assert current["name"] == "read-code-persistence-probe"
    assert previous["project_root"] == current["project_root"] == expected_repo_root
    assert previous["pid"] == current["pid"]
    assert previous["started_at"] == current["started_at"]
    assert previous["pid"] > 0
    assert isinstance(previous["started_at"], float)
    _assert_comparison_matches(payload)


def test_live_project_local_mcp_read_surface_artifact_matches_across_turns() -> None:
    """Opt-in live verification should validate externally captured direct MCP read-surface evidence."""
    artifact_path = _mcp_read_surface_artifact_path()
    if not artifact_path.exists():
        pytest.skip(f"Missing MCP read-surface artifact at {artifact_path}")

    payload = _load_persistence_artifact(artifact_path)
    previous = _normalize_identity(payload.get("previous"))
    current = _normalize_identity(payload.get("current"))
    context_payload = _normalize_mcp_command_payload(payload.get("read_code_context"))
    find_payload = _normalize_mcp_command_payload(payload.get("read_code_find"))
    analyze_payload = _normalize_mcp_command_payload(payload.get("read_code_analyze"))
    window_payload = _normalize_mcp_command_payload(payload.get("read_code_window"))

    assert previous == current
    _assert_comparison_matches(payload)

    for command_payload, command_name in (
        (context_payload, "read_code_context"),
        (find_payload, "read_code_find"),
        (analyze_payload, "read_code_analyze"),
        (window_payload, "read_code_window"),
    ):
        assert command_payload["name"] == previous["name"]
        assert command_payload["pid"] == previous["pid"]
        assert command_payload["started_at"] == previous["started_at"]
        assert command_payload["command"] == command_name
        assert command_payload["exit_code"] == 0

    assert "file_path:" in context_payload["stdout"]
    assert "ERROR:" not in context_payload["stderr"]
    assert "name: read_code_context" in find_payload["stdout"]
    assert "ERROR:" not in find_payload["stderr"]
    assert "analyze_command: deps" in analyze_payload["stdout"]
    assert "ERROR:" not in analyze_payload["stderr"]
    assert "Python entrypoint for code discovery with semantic-first anchoring." in window_payload["stdout"]
    assert "ERROR:" not in window_payload["stderr"]


def test_live_project_local_mcp_server_exposes_identity_health_query_and_score() -> None:
    """Opt-in live verification should exercise one real MCP backend process and read surface."""
    if os.environ.get("SPECKIT_RUN_LIVE_MCP_PERSISTENCE_TESTS") != "1":
        pytest.skip("Set SPECKIT_RUN_LIVE_MCP_PERSISTENCE_TESTS=1 to run live backend verification.")

    repo_root = Path(__file__).resolve().parents[2]
    payload = asyncio.run(_exercise_live_backend_server(repo_root))

    assert payload["tool_names"] == {
        "get_process_identity",
        "health",
        "query",
        "score",
        "read_code_context",
        "read_code_find",
        "read_code_analyze",
        "read_code_window",
    }

    identity_1 = _normalize_identity(payload["identity_1"])
    identity_2 = _normalize_identity(payload["identity_2"])
    health = payload["health"]
    query = payload["query"]
    score = payload["score"]
    read_code_context_payload = payload["read_code_context"]
    read_code_find_payload = payload["read_code_find"]
    read_code_analyze_payload = payload["read_code_analyze"]
    read_code_window_payload = payload["read_code_window"]

    assert identity_1 == identity_2
    assert identity_1["name"] == "read-code-persistence-probe"
    assert identity_1["project_root"] == str(repo_root)
    assert identity_1["pid"] > 0
    assert isinstance(identity_1["started_at"], float)
    assert isinstance(health, dict)
    assert health["pid"] == identity_1["pid"]
    assert health["started_at"] == identity_1["started_at"]
    assert health["name"] == identity_1["name"]
    assert isinstance(query, list)
    if query:
        assert query[0]["file_path"].endswith("read_code.py")
    assert isinstance(score, dict)
    assert len(score["scores"]) == 2
    assert all(isinstance(value, float) for value in score["scores"])
    assert read_code_context_payload["exit_code"] == 0
    assert "file_path:" in read_code_context_payload["stdout"]
    assert "ERROR:" not in read_code_context_payload["stderr"]
    assert read_code_find_payload["exit_code"] == 0
    assert "name: read_code_context" in read_code_find_payload["stdout"]
    assert "ERROR:" not in read_code_find_payload["stderr"]
    assert read_code_analyze_payload["exit_code"] == 0
    assert "query: src.mcp_codebase.project_backend_server" in read_code_analyze_payload["stdout"]
    assert "ERROR:" not in read_code_analyze_payload["stderr"]
    assert read_code_window_payload["exit_code"] == 0
    assert "Python entrypoint for code discovery with semantic-first anchoring." in read_code_window_payload["stdout"]
    assert "ERROR:" not in read_code_window_payload["stderr"]


def test_refresh_reindexes_changed_code_symbol_after_invalidation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changed files should invalidate the old symbol and surface the refreshed one."""

    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        """
def stale_symbol() -> str:
    return "stale"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    service = _build_offline_vector_index_service(tmp_path, monkeypatch)
    service.build_full_index(revision="rev-a")

    initial = service.query("stale_symbol", scope=IndexScope.CODE, top_k=1)
    assert initial
    assert initial[0].file_path == source
    assert initial[0].signature.startswith("def stale_symbol")

    source.write_text(
        """
def refreshed_symbol() -> str:
    return "fresh"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    refreshed = service.refresh_changed_files([source], revision="rev-b")
    assert refreshed.indexed_commit == "rev-b"

    stale = service.query("stale_symbol", scope=IndexScope.CODE, top_k=1)
    assert stale
    assert stale[0].signature.startswith("def refreshed_symbol")

    updated = service.query("refreshed_symbol", scope=IndexScope.CODE, top_k=1)
    assert updated
    assert updated[0].file_path == source
    assert updated[0].signature.startswith("def refreshed_symbol")


def test_index_handles_max_volume_without_oom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A larger local checkout should remain buildable without memory failure."""

    source_paths = _write_python_modules(tmp_path, count=240)

    docs_root = tmp_path / "specs"
    docs_root.mkdir(parents=True, exist_ok=True)
    for index in range(40):
        doc = docs_root / f"topic_{index}.md"
        doc.write_text(
            f"""
# Topic {index}

## Section {index}

This is document {index}.
""".strip()
            + "\n",
            encoding="utf-8",
        )

    service = _build_offline_vector_index_service(tmp_path, monkeypatch)

    built = service.build_full_index(revision="rev-a")

    assert built.code_symbol_count == len(source_paths)
    assert built.markdown_section_count == 80
    assert built.entry_count > len(source_paths)
    assert service.query("symbol_239", scope=IndexScope.CODE, top_k=1)


def test_live_read_code_context_records_worker_rerank_source_without_restarting_worker() -> None:
    """Opt-in live verification should prove rerank scoring reuses one MCP backend session."""
    if os.environ.get("SPECKIT_RUN_LIVE_RERANKER_STDIO_CONTEXT_TESTS") != "1":
        pytest.skip("Set SPECKIT_RUN_LIVE_RERANKER_STDIO_CONTEXT_TESTS=1 to run live MCP verification.")

    backend = read_code._load_read_code_reranker()
    if backend is None:
        pytest.skip("Reranker backend is unavailable in this environment.")

    try:
        backend._shutdown_backend()
        scores_1, source_1 = backend.score_pairs(
            "semantic rerank worker",
            ["def _vector_find_candidates(...): ...", "def _vector_query_candidates(...): ..."],
        )
        assert backend._backend_identity is not None
        pid_before = backend._backend_identity["pid"]
        scores_2, source_2 = backend.score_pairs(
            "semantic rerank worker",
            ["def _vector_anchor_rank(...): ...", "def _rerank_semantic_candidates(...): ..."],
        )
        assert backend._backend_identity is not None
        assert pid_before == backend._backend_identity["pid"]
    finally:
        backend._shutdown_backend()

    assert source_1 == "mcp"
    assert source_2 == "mcp"
    assert len(scores_1) == 2
    assert len(scores_2) == 2
    assert all(isinstance(value, float) for value in scores_1 + scores_2)


def test_live_vector_query_candidates_reuse_worker_without_local_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt-in live verification should prove semantic query requests reuse the MCP backend session."""
    if os.environ.get("SPECKIT_RUN_LIVE_RERANKER_STDIO_CONTEXT_TESTS") != "1":
        pytest.skip("Set SPECKIT_RUN_LIVE_RERANKER_STDIO_CONTEXT_TESTS=1 to run live worker verification.")

    backend = read_code._load_read_code_reranker()
    if backend is None:
        pytest.skip("Reranker backend is unavailable in this environment.")

    repo_root = Path(__file__).resolve().parents[2]
    target = repo_root / "scripts" / "read_code.py"
    monkeypatch.setattr(
        read_code,
        "_load_read_code_vector_query_service",
        lambda: (_ for _ in ()).throw(AssertionError("semantic query should use the stdio worker first")),
    )

    try:
        backend._shutdown_worker()
        first = read_code._vector_query_candidates(
            target,
            "_vector_query_candidates",
            "_vector_query_candidates",
            "code",
            allow_test_files=False,
        )
        assert isinstance(first, list)
        assert backend._backend_identity is not None
        pid_before = backend._backend_identity["pid"]

        second = read_code._vector_query_candidates(
            target,
            "_vector_find_candidates",
            "_vector_find_candidates",
            "code",
            allow_test_files=False,
        )
        assert isinstance(second, list)
        assert backend._backend_identity is not None
        assert backend._backend_identity["pid"] == pid_before
    finally:
        backend._shutdown_backend()


def _read_json_line(process: subprocess.Popen[str], *, timeout: float) -> dict[str, object]:
    """Read one JSON line from a live stdio worker with a bounded timeout."""
    assert process.stdout is not None
    ready, _, _ = select.select([process.stdout], [], [], timeout)
    if not ready:
        raise TimeoutError(f"stdio worker did not produce output within {timeout} seconds")
    line = process.stdout.readline()
    if not line:
        stderr = process.stderr.read() if process.stderr is not None else ""
        raise AssertionError(f"stdio worker closed stdout unexpectedly: {stderr}")
    payload = json.loads(line)
    assert isinstance(payload, dict)
    return payload


def _write_json_line(process: subprocess.Popen[str], payload: dict[str, object]) -> None:
    """Write one JSON line to the live stdio worker and flush immediately."""
    assert process.stdin is not None
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.flush()


def test_live_reranker_stdio_worker_reuses_one_process_for_multiple_requests() -> None:
    """Opt-in live verification should prove stdio worker reuse without sockets or file RPC."""
    if os.environ.get("SPECKIT_RUN_LIVE_RERANKER_STDIO_TESTS") != "1":
        pytest.skip("Set SPECKIT_RUN_LIVE_RERANKER_STDIO_TESTS=1 to run live stdio worker verification.")

    repo_root = Path(__file__).resolve().parents[2]
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "src.mcp_codebase.index.reranker_stdio_worker",
            "--repo-root",
            str(repo_root),
        ],
        cwd=repo_root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        ready = _read_json_line(process, timeout=120.0)
        assert ready["op"] == "ready"
        assert ready["ok"] is True

        _write_json_line(process, {"op": "health"})
        health = _read_json_line(process, timeout=10.0)
        assert health["op"] == "health"
        assert health["ok"] is True
        assert health["pid"] == ready["pid"]
        assert health["started_at"] == ready["started_at"]

        _write_json_line(
            process,
            {
                "op": "score",
                "query": "vector trust decision fallback",
                "passages": [
                    "Return daemon scores only when the daemon is already healthy.",
                    "Remove the startup failure marker after a healthy daemon handshake.",
                ],
            },
        )
        score_one = _read_json_line(process, timeout=30.0)
        assert score_one["op"] == "score"
        assert score_one["ok"] is True
        assert score_one["pid"] == ready["pid"]
        assert score_one["started_at"] == ready["started_at"]
        assert len(score_one["scores"]) == 2

        _write_json_line(
            process,
            {
                "op": "score",
                "query": "vector trust decision fallback",
                "passages": [
                    "Return daemon scores only when the daemon is already healthy.",
                    "Remove the startup failure marker after a healthy daemon handshake.",
                ],
            },
        )
        score_two = _read_json_line(process, timeout=30.0)
        assert score_two["op"] == "score"
        assert score_two["ok"] is True
        assert score_two["pid"] == ready["pid"]
        assert score_two["started_at"] == ready["started_at"]
        assert len(score_two["scores"]) == 2

        _write_json_line(process, {"op": "shutdown"})
        shutdown = _read_json_line(process, timeout=10.0)
        assert shutdown["op"] == "shutdown"
        assert shutdown["ok"] is True
        assert shutdown["pid"] == ready["pid"]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10.0)
