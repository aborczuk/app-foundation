"""Unit tests for the read_code reranker daemon client lifecycle."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import pytest


def _load_module(module_name: str, script_name: str):
    """Load a scripts module directly from the repo for unit testing."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


read_code = _load_module("read_code_reranker_daemon", "read_code.py")


@pytest.fixture(autouse=True)
def _reranker_runtime_env(tmp_path: Path, monkeypatch) -> None:
    """Route daemon runtime and launch-agent files into the test tmpdir."""
    monkeypatch.setenv("SPECKIT_READ_CODE_RERANKER_RUNTIME_ROOT", str(tmp_path / "runtime-root"))
    monkeypatch.setenv("SPECKIT_READ_CODE_RERANKER_LAUNCH_AGENTS_DIR", str(tmp_path / "LaunchAgents"))


def test_reranker_backend_uses_healthy_daemon_scores(tmp_path: Path, monkeypatch) -> None:
    """A ready MCP backend should supply scores without falling back to heuristic order."""
    backend = read_code._ReadCodeRerankerBackend("BAAI/bge-reranker-v2-m3", repo_root=tmp_path)
    monkeypatch.setattr(backend, "_ensure_worker_ready", lambda: {"ok": True, "pid": 123})
    monkeypatch.setattr(
        backend,
        "_worker_score",
        lambda query, passages: {"scores": [0.2, 0.9], "model_name": backend.model_name},
    )

    scores, source = backend.score_pairs("query", ["first", "second"])

    assert scores == [0.2, 0.9]
    assert source == "mcp"


def test_reranker_backend_uses_worker_query_items(tmp_path: Path, monkeypatch) -> None:
    """A ready MCP backend should supply semantic query items without local fallback."""
    backend = read_code._ReadCodeRerankerBackend("BAAI/bge-reranker-v2-m3", repo_root=tmp_path)
    monkeypatch.setattr(backend, "_ensure_worker_ready", lambda: {"ok": True, "pid": 123})
    monkeypatch.setattr(
        backend,
        "_worker_query",
        lambda **kwargs: {
            "items": [
                {
                    "file_path": "/tmp/example.py",
                    "line_start": 5,
                    "line_end": 7,
                    "score": 0.75,
                    "body": "def sample():\n    return 1",
                    "preview": "def sample(): ...",
                    "signature": "def sample()",
                    "docstring": "Sample helper.",
                    "symbol_type": "function",
                    "symbol_name": "sample",
                    "qualified_name": "sample",
                }
            ]
        },
    )

    items = backend.query_items(query="sample", top_k=5, scope="code", file_path=Path("/tmp/example.py"))

    assert items is not None
    assert items[0]["symbol_name"] == "sample"


def test_reranker_backend_query_items_fall_back_when_worker_query_fails(tmp_path: Path, monkeypatch) -> None:
    """MCP backend query failures should fail fast and allow the local fallback path."""
    backend = read_code._ReadCodeRerankerBackend("BAAI/bge-reranker-v2-m3", repo_root=tmp_path)
    monkeypatch.setattr(backend, "_ensure_worker_ready", lambda: {"ok": True, "pid": 123})
    monkeypatch.setattr(
        backend,
        "_worker_query",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("worker query failed")),
    )
    shutdown_calls: list[str] = []
    monkeypatch.setattr(backend, "_shutdown_worker", lambda: shutdown_calls.append("shutdown"))

    items = backend.query_items(query="sample", top_k=5, scope="code", file_path=Path("/tmp/example.py"))

    assert items is None
    assert shutdown_calls == ["shutdown"]


def test_reranker_backend_falls_back_to_heuristic_when_socket_health_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """An unavailable MCP backend should fail fast to heuristic ordering."""
    backend = read_code._ReadCodeRerankerBackend("BAAI/bge-reranker-v2-m3", repo_root=tmp_path)
    monkeypatch.setattr(backend, "_ensure_worker_ready", lambda: None)

    scores, source = backend.score_pairs("query", ["first", "second"])

    assert scores == []
    assert source == "heuristic"


def test_reranker_backend_falls_back_to_heuristic_when_socket_score_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """MCP backend scoring failures should fail fast instead of taking a slow secondary path."""
    backend = read_code._ReadCodeRerankerBackend("BAAI/bge-reranker-v2-m3", repo_root=tmp_path)
    monkeypatch.setattr(backend, "_ensure_worker_ready", lambda: {"ok": True, "pid": 123})
    monkeypatch.setattr(
        backend,
        "_worker_score",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("worker failed")),
    )
    shutdown_calls: list[str] = []
    monkeypatch.setattr(backend, "_shutdown_worker", lambda: shutdown_calls.append("shutdown"))

    scores, source = backend.score_pairs("query", ["first", "second"])

    assert scores == []
    assert source == "heuristic"
    assert shutdown_calls == ["shutdown"]


def test_reranker_backend_does_not_start_daemon_on_query_path_when_unhealthy(tmp_path: Path, monkeypatch) -> None:
    """Query-time scoring should fall back immediately instead of managing daemon lifecycle."""
    backend = read_code._ReadCodeRerankerBackend("BAAI/bge-reranker-v2-m3", repo_root=tmp_path)
    monkeypatch.setattr(backend, "_health", lambda: None)
    monkeypatch.setattr(
        backend,
        "_ensure_healthy",
        lambda: (_ for _ in ()).throw(AssertionError("query path should not call _ensure_healthy")),
    )

    scores, source = backend.score_pairs("query", ["first", "second"])

    assert scores == []
    assert source == "heuristic"


def test_reranker_backend_skips_restart_during_recent_failure_cooldown(tmp_path: Path, monkeypatch) -> None:
    """A recent startup failure should suppress immediate restart thrash and fall back cleanly."""
    backend = read_code._ReadCodeRerankerBackend("BAAI/bge-reranker-v2-m3", repo_root=tmp_path)
    read_code._persist_runtime_json_object(
        backend._failure_marker_path,
        {
            "failed_at": time.time(),
            "reason": "prior startup failure",
        },
        sort_keys=True,
    )
    spawn_calls: list[str] = []
    monkeypatch.setattr(backend, "_health", lambda: None)
    monkeypatch.setattr(backend, "_spawn_daemon", lambda: spawn_calls.append("spawn"))

    scores, source = backend.score_pairs("query", ["first"])

    assert scores == []
    assert source == "heuristic"
    assert spawn_calls == []


def test_reranker_backend_starts_daemon_after_lock_when_health_recovers(tmp_path: Path, monkeypatch) -> None:
    """An unhealthy first probe should acquire the lock, spawn once, and reuse the recovered daemon."""
    backend = read_code._ReadCodeRerankerBackend("BAAI/bge-reranker-v2-m3", repo_root=tmp_path)
    health_calls = {"count": 0}
    spawn_calls: list[str] = []

    def fake_health():
        health_calls["count"] += 1
        if health_calls["count"] < 3:
            return None
        return {"status": "healthy"}

    monkeypatch.setattr(backend, "_health", fake_health)
    monkeypatch.setattr(backend, "_spawn_daemon", lambda: spawn_calls.append("spawn"))
    monkeypatch.setattr(backend, "_wait_for_ready", lambda: {"status": "healthy"})

    assert backend._ensure_healthy() == {"status": "healthy"}
    assert spawn_calls == ["spawn"]
    assert health_calls["count"] >= 2


def test_reranker_backend_removes_stale_pid_and_socket_for_dead_process(tmp_path: Path, monkeypatch) -> None:
    """Dead-process runtime artifacts should be cleared before daemon restart."""
    backend = read_code._ReadCodeRerankerBackend("BAAI/bge-reranker-v2-m3", repo_root=tmp_path)
    backend._runtime_dir.mkdir(parents=True, exist_ok=True)
    backend._socket_path.write_text("", encoding="utf-8")
    read_code._persist_runtime_json_object(backend._pid_path, {"pid": 999999}, sort_keys=True)
    monkeypatch.setattr(backend, "_process_alive", lambda pid: False)

    backend._remove_stale_artifacts()

    assert not backend._socket_path.exists()
    assert not backend._pid_path.exists()


def test_read_code_daemon_status_renders_health_snapshot(monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Daemon status should print the bounded health/runtime snapshot."""

    class FakeBackend:
        def status(self):
            return read_code._DaemonStatus(
                healthy=True,
                managed=True,
                launch_agent_loaded=True,
                launch_agent_label="com.appfoundation.read-code-reranker.test",
                launch_agent_path=Path("/tmp/com.appfoundation.read-code-reranker.test.plist"),
                transport="tcp",
                endpoint="127.0.0.1:43210",
                pid=12345,
                model_loaded=True,
                model_name="BAAI/bge-reranker-v2-m3",
                startup_timestamp=1700000000.0,
                build_fingerprint="abc123",
                failure_reason=None,
                failure_age_seconds=None,
                cooldown_active=False,
                log_path=Path("/tmp/daemon.log"),
            )

    monkeypatch.setattr(read_code, "_load_read_code_reranker", lambda: FakeBackend())

    assert read_code.read_code_daemon(["status"]) == 0
    output = capsys.readouterr().out
    assert "daemon_command: status" in output
    assert "healthy: true" in output
    assert "managed: true" in output
    assert "transport: tcp" in output
    assert "endpoint: 127.0.0.1:43210" in output


def test_read_code_daemon_start_stop_and_logs(monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Daemon control commands should delegate to backend lifecycle helpers."""
    seen: list[tuple[str, object]] = []

    class FakeBackend:
        def __init__(self) -> None:
            self._status = read_code._DaemonStatus(
                healthy=False,
                managed=False,
                launch_agent_loaded=False,
                launch_agent_label="com.appfoundation.read-code-reranker.test",
                launch_agent_path=Path("/tmp/com.appfoundation.read-code-reranker.test.plist"),
                transport="uds",
                endpoint="/tmp/example.sock",
                pid=None,
                model_loaded=False,
                model_name="BAAI/bge-reranker-v2-m3",
                startup_timestamp=None,
                build_fingerprint=None,
                failure_reason="startup failed",
                failure_age_seconds=2.5,
                cooldown_active=True,
                log_path=Path("/tmp/daemon.log"),
            )

        def status(self):
            seen.append(("status", None))
            return self._status

        def start(self, *, force: bool = False):
            seen.append(("start", force))
            return self._status

        def stop(self):
            seen.append(("stop", None))
            return True

        def log_tail(self, *, limit: int):
            seen.append(("logs", limit))
            return ["line one", "line two"]

    monkeypatch.setattr(read_code, "_load_read_code_reranker", lambda: FakeBackend())

    assert read_code.read_code_daemon(["start", "--force"]) == 0
    start_output = capsys.readouterr().out
    assert "cooldown_active: true" in start_output

    assert read_code.read_code_daemon(["stop"]) == 0
    stop_output = capsys.readouterr().out
    assert "stopped: true" in stop_output

    assert read_code.read_code_daemon(["logs", "2"]) == 0
    log_output = capsys.readouterr().out
    assert "line_count: 2" in log_output
    assert "line one" in log_output

    assert seen == [
        ("start", True),
        ("stop", None),
        ("status", None),
        ("logs", 2),
    ]


def test_reranker_backend_install_writes_launch_agent_and_bootstraps(tmp_path: Path, monkeypatch) -> None:
    """Managed install should write the plist and route startup through launchctl."""
    backend = read_code._ReadCodeRerankerBackend("BAAI/bge-reranker-v2-m3", repo_root=tmp_path)
    commands: list[list[str]] = []

    def fake_run_launchctl(args: list[str]):
        commands.append(args)
        if args[:1] == ["print"]:
            return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(backend, "_run_launchctl", fake_run_launchctl)
    monkeypatch.setattr(backend, "_launchctl_path", lambda: "/bin/launchctl")
    monkeypatch.setattr(backend, "_wait_for_ready", lambda: {
        "status": "healthy",
        "pid": 123,
        "model_loaded": True,
        "model_name": backend.model_name,
        "build_fingerprint": backend._build_fingerprint,
        "started_at": time.time(),
    })
    monkeypatch.setattr(backend, "_health", lambda: None)

    status = backend.install_managed_service(force=True)

    assert status.managed is True
    assert backend._launch_agent_path.is_file()
    assert any(args[:1] == ["bootstrap"] for args in commands)
    assert any(args[:2] == ["kickstart", "-k"] for args in commands)


def test_reranker_backend_uninstall_boots_out_and_removes_plist(tmp_path: Path, monkeypatch) -> None:
    """Managed uninstall should stop launchd ownership and remove the plist."""
    backend = read_code._ReadCodeRerankerBackend("BAAI/bge-reranker-v2-m3", repo_root=tmp_path)
    backend._write_launch_agent_plist()
    commands: list[list[str]] = []

    def fake_run_launchctl(args: list[str]):
        commands.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(backend, "_run_launchctl", fake_run_launchctl)
    monkeypatch.setattr(backend, "_launchctl_path", lambda: "/bin/launchctl")

    removed = backend.uninstall_managed_service()

    assert removed is True
    assert not backend._launch_agent_path.exists()
    assert any(args[:1] == ["bootout"] for args in commands)
