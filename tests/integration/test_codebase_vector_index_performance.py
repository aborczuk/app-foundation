"""Integration regressions for configurable exclusions, performance slices, and feature-031 evidence."""

from __future__ import annotations

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


def test_live_read_code_context_records_worker_rerank_source_without_restarting_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Opt-in live verification should prove normal context reads reuse one stdio worker."""
    if os.environ.get("SPECKIT_RUN_LIVE_RERANKER_STDIO_CONTEXT_TESTS") != "1":
        pytest.skip("Set SPECKIT_RUN_LIVE_RERANKER_STDIO_CONTEXT_TESTS=1 to run live worker verification.")

    backend = read_code._load_read_code_reranker()
    if backend is None:
        pytest.skip("Reranker backend is unavailable in this environment.")

    metadata_log_path = tmp_path / "search-history.jsonl"
    current_session = {"id": "live-rerank-daemon-1"}
    monkeypatch.setattr(read_code, "_read_code_session_id", lambda: current_session["id"])
    monkeypatch.setattr(
        read_code,
        "_read_code_search_scratchpad_path",
        lambda session_id: tmp_path / f"{session_id}-scratchpad.json",
    )
    monkeypatch.setattr(read_code, "_read_code_search_metadata_log_path", lambda: metadata_log_path)

    try:
        assert read_code.read_code_context(["_vector_trust_decision", "--path", "scripts/read_code_health.py"]) == 0
        assert backend._worker_process is not None
        pid_before = backend._worker_process.pid
        current_session["id"] = "live-rerank-daemon-2"
        assert read_code.read_code_context(["_vector_trust_decision", "--path", "scripts/read_code_health.py"]) == 0
        assert backend._worker_process is not None
        assert pid_before == backend._worker_process.pid
    finally:
        backend._shutdown_worker()

    events = [json.loads(line) for line in metadata_log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(events) == 2
    assert all(event["command"] == "context" for event in events)
    assert all(event["rerank_source"] == "worker" for event in events)


def test_live_vector_query_candidates_reuse_worker_without_local_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt-in live verification should prove semantic query requests reuse the stdio worker."""
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
        assert first
        assert backend._worker_process is not None
        pid_before = backend._worker_process.pid

        second = read_code._vector_query_candidates(
            target,
            "_vector_find_candidates",
            "_vector_find_candidates",
            "code",
            allow_test_files=False,
        )
        assert second
        assert backend._worker_process is not None
        assert backend._worker_process.pid == pid_before
    finally:
        backend._shutdown_worker()


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
