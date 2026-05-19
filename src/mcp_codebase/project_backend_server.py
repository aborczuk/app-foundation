"""FastMCP backend server that owns warm query and rerank operations."""

from __future__ import annotations

import atexit
import ctypes
import importlib.util
import io
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import asdict, is_dataclass
from pathlib import Path
from time import monotonic

from mcp.server.fastmcp import FastMCP

from src.mcp_codebase import config
from src.mcp_codebase.index import IndexScope
from src.mcp_codebase.index.config import DEFAULT_RERANKER_MODEL_NAME
from src.mcp_codebase.index.reranker_runtime import reranker_build_fingerprint
from src.mcp_codebase.index.reranker_stdio_worker import _build_service
from src.mcp_codebase.index.store import chroma as chroma_store

_SERVER_NAME = "read-code-persistence-probe"
_BACKEND_RUNTIME_DIR = "read-code-mcp-runtime"
_BACKEND_PID_FILE_PREFIX = "project_backend_server"
_WARMUP_QUERY_TEXT = "_resolve_pattern_anchor"
_WARMUP_QUERY_TOP_K = 5
_WARMUP_RERANK_PASSAGES = [
    "def _resolve_pattern_anchor(file_path, pattern, normalized_pattern):\n"
    "    vector_candidates, vector_match = _query_semantic_anchor_candidate_with_debug(\n"
    "        file_path, pattern, normalized_pattern\n"
    "    )\n"
    "    return vector_match or vector_candidates[0]\n",
    "def _resolve_pattern_anchor_with_scratchpad(session_id, pattern):\n"
    "    cached = _load_anchor_resolution(session_id, pattern)\n"
    "    if cached is not None:\n"
    "        return cached\n"
    "    return _resolve_pattern_anchor(None, pattern, pattern)\n",
    "def _query_semantic_anchor_candidate_with_debug(file_path, pattern, normalized_pattern):\n"
    "    candidates = _vector_find_candidates(pattern, file_path=file_path)\n"
    "    reranked = _rerank_semantic_candidates(pattern, candidates)\n"
    "    return reranked\n",
    "def _vector_find_candidates(query_text, *, file_path=None):\n"
    "    return _vector_query_candidates(query_text, top_k=20, file_path=file_path)\n",
    "def _rerank_semantic_candidates(query_text, passages):\n"
    "    shortlist = passages[:5]\n"
    "    return backend.score_pairs(query_text, shortlist)\n",
]


def _capture_process_identity(server_ref: "ProjectBackendServer") -> dict[str, object]:
    """Return the bounded process identity snapshot for the backend server."""
    return {
        "name": _SERVER_NAME,
        "project_root": str(server_ref._project_root),
        "pid": server_ref._pid,
        "started_at": server_ref._started_at,
    }


def _capture_torch_runtime() -> dict[str, object]:
    """Return bounded torch accelerator capability flags for this process."""
    torch_module = getattr(chroma_store, "torch", None)
    if torch_module is None:
        return {
            "torch_available": False,
            "torch_version": None,
            "mps_built": False,
            "mps_available": False,
            "cuda_available": False,
        }
    mps_backend = getattr(getattr(torch_module, "backends", None), "mps", None)
    is_mps_built = getattr(mps_backend, "is_built", None)
    is_mps_available = getattr(mps_backend, "is_available", None)
    return {
        "torch_available": True,
        "torch_version": getattr(torch_module, "__version__", None),
        "mps_built": bool(is_mps_built()) if callable(is_mps_built) else False,
        "mps_available": bool(is_mps_available()) if callable(is_mps_available) else False,
        "cuda_available": bool(torch_module.cuda.is_available()),
    }


def _mcp_process_name(owner: str) -> bytes:
    """Return one bounded process name for Activity Monitor and ps output."""
    return f"read_code_mcp_server:{owner}".encode("utf-8")[:63]


def _apply_process_name(owner: str) -> None:
    """Best-effort apply one process display name on platforms that support setprogname."""
    try:
        libc = ctypes.CDLL(None)
        setprogname = getattr(libc, "setprogname", None)
        if setprogname is None:
            return
        setprogname.argtypes = [ctypes.c_char_p]
        setprogname.restype = None
        setprogname(_mcp_process_name(owner))
    except Exception:
        return


def _warmup_query_file_path(project_root: Path) -> Path:
    """Return one stable scoped file used to prime the full context query path."""
    return project_root / "scripts" / "read_code.py"


def _backend_runtime_dir(project_root: Path) -> Path:
    """Return the runtime directory used to coordinate one MCP backend process."""
    return project_root / ".codegraphcontext" / _BACKEND_RUNTIME_DIR


def _resolve_backend_owner() -> str:
    """Return the launcher-scoped owner label used for backend singleton isolation."""
    explicit = os.environ.get("READ_CODE_MCP_INSTANCE_OWNER")
    if explicit:
        return explicit
    return f"ppid-{os.getppid()}"


def _backend_pid_path(project_root: Path, owner: str) -> Path:
    """Return the pid file path used by the MCP backend singleton guard."""
    safe_owner = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in owner)
    return _backend_runtime_dir(project_root) / f"{_BACKEND_PID_FILE_PREFIX}.{safe_owner}.pid"


def _read_backend_pid(path: Path) -> int | None:
    """Return the recorded backend pid when a valid pid file exists."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _backend_command_for_pid(pid: int) -> str:
    """Return the recorded command line for one pid when it is still visible."""
    completed = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _pid_matches_backend_server(pid: int) -> bool:
    """Return True when the pid still belongs to this backend entrypoint."""
    command = _backend_command_for_pid(pid)
    return "src.mcp_codebase.project_backend_server" in command


def _pid_is_running(pid: int) -> bool:
    """Return True when the current user can still signal the given pid."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _wait_for_pid_exit(pid: int, *, timeout_seconds: float) -> bool:
    """Wait a bounded interval for a pid to disappear after a termination signal."""
    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        if not _pid_is_running(pid):
            return True
        time.sleep(0.05)
    return not _pid_is_running(pid)


def _terminate_backend_pid(pid: int) -> None:
    """Best-effort terminate one older backend pid before starting a replacement."""
    if not _pid_is_running(pid):
        return
    for sig, timeout_seconds in ((signal.SIGTERM, 2.0), (signal.SIGKILL, 0.5)):
        try:
            os.kill(pid, sig)
        except OSError:
            return
        if _wait_for_pid_exit(pid, timeout_seconds=timeout_seconds):
            return


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
    """Serve read_code semantic queries locally and rerank through the persistent daemon."""

    def __init__(self, server_ref: "ProjectBackendServer") -> None:
        """Bind the adapter to one already-warm project backend server."""
        self._server_ref = server_ref
        self.model_name = server_ref._reranker_model

    def score_pairs(self, query: str, passages: list[str]) -> tuple[list[float], str]:
        """Return daemon-backed scores in the same shape as read_code expects."""
        payload = self._server_ref._daemon_score_payload(query, passages)
        if payload is None:
            return [], "heuristic"
        scores = payload.get("scores")
        if not isinstance(scores, list) or not all(isinstance(value, (int, float)) for value in scores):
            return [], "heuristic"
        return [float(value) for value in scores], "daemon"

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
        self._instance_owner = _resolve_backend_owner()
        _apply_process_name(self._instance_owner)
        self._pid = os.getpid()
        self._started_at = time.time()
        self._reranker_model = reranker_model
        self._build_fingerprint = reranker_build_fingerprint(self._project_root, reranker_model)
        self._vector_index_service = _build_service(self._project_root, reranker_model=reranker_model)
        self._read_code_module = _load_read_code_module(self._project_root)
        self._daemon_backend = self._load_daemon_backend()
        self._read_code_backend = _DirectReadCodeBackend(self)
        self._vector_index_ready = False
        self._reranker_warmed = False
        self.mcp = FastMCP(_SERVER_NAME)
        self._register_tools()

    def _load_daemon_backend(self):
        """Return the shared daemon-backed reranker client exposed by read_code.py."""
        loader = getattr(self._read_code_module, "_load_read_code_reranker", None)
        if not callable(loader):
            raise RuntimeError("read_code daemon backend loader is unavailable")
        return loader()

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

    def _current_reranker_device(self) -> str | None:
        """Return the device advertised by the external daemon when healthy."""
        payload = self._daemon_health_payload()
        device = payload.get("selected_device")
        return str(device) if isinstance(device, str) else None

    def _daemon_status(self, *, start: bool = False) -> object:
        """Return the shared daemon status, optionally ensuring the daemon is started first."""
        command = getattr(self._daemon_backend, "start" if start else "status", None)
        if not callable(command):
            raise RuntimeError("daemon backend status API is unavailable")
        return command()

    def _serialize_daemon_status(self, status: object) -> dict[str, object]:
        """Return one bounded JSON-safe snapshot of the daemon status object."""
        payload = asdict(status) if is_dataclass(status) else {}
        if not payload:
            payload = {
                key: getattr(status, key)
                for key in (
                    "healthy",
                    "transport",
                    "endpoint",
                    "pid",
                    "model_loaded",
                    "model_name",
                    "startup_timestamp",
                    "build_fingerprint",
                    "failure_reason",
                    "failure_age_seconds",
                    "cooldown_active",
                    "log_path",
                    "managed",
                    "launch_agent_loaded",
                    "launch_agent_label",
                    "launch_agent_path",
                )
                if hasattr(status, key)
            }
        for key in ("log_path", "launch_agent_path"):
            value = payload.get(key)
            if isinstance(value, Path):
                payload[key] = str(value)
        return dict(payload)

    def _daemon_health_payload(self) -> dict[str, object]:
        """Return the daemon health payload when the external daemon is reachable and healthy."""
        health = getattr(self._daemon_backend, "_health", None)
        if not callable(health):
            return {}
        payload = health()
        return dict(payload) if isinstance(payload, dict) else {}

    def _daemon_runtime_report(self, *, ensure_started: bool = False) -> dict[str, object]:
        """Return one bounded combined report for the shim process and external daemon."""
        status = self._daemon_status(start=ensure_started)
        return {
            **_capture_process_identity(self),
            "shim_pid": self._pid,
            "shim_started_at": self._started_at,
            "daemon": self._serialize_daemon_status(status),
            "active_rerank_path": "daemon"
            if bool(self._serialize_daemon_status(status).get("healthy"))
            else "heuristic",
        }

    def _daemon_score_payload(self, query: str, passages: list[str], *, ensure_started: bool = False) -> dict[str, object] | None:
        """Return daemon score payload when healthy, otherwise None for heuristic fallback."""
        status_payload = self._serialize_daemon_status(self._daemon_status(start=ensure_started))
        if not bool(status_payload.get("healthy")):
            return None
        score = getattr(self._daemon_backend, "_score", None)
        if not callable(score):
            return None
        payload = score(query, passages)
        return dict(payload) if isinstance(payload, dict) else None

    def _warmup_reranker_runtime(self) -> dict[str, object]:
        """Prime the daemon-backed reranker plus one representative local query path."""
        self._ensure_vector_index_ready()
        started = monotonic()
        if not self._reranker_warmed:
            self._daemon_status(start=True)
            self._vector_index_service.query(
                _WARMUP_QUERY_TEXT,
                top_k=_WARMUP_QUERY_TOP_K,
                scope=None,
                file_path=_warmup_query_file_path(self._project_root),
            )
            self._daemon_score_payload(
                _WARMUP_QUERY_TEXT,
                list(_WARMUP_RERANK_PASSAGES),
                ensure_started=False,
            )
            self._reranker_warmed = True
        return {
            **self._daemon_runtime_report(ensure_started=False),
            "warmup_completed": self._reranker_warmed,
            "elapsed_ms": round((monotonic() - started) * 1000, 3),
        }

    def _prepare_stdio_runtime(self) -> Path:
        """Reap the previously tracked backend pid and record this process as the active server."""
        pid_path = _backend_pid_path(self._project_root, self._instance_owner)
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        previous_pid = _read_backend_pid(pid_path)
        if previous_pid is not None and previous_pid != self._pid and _pid_matches_backend_server(previous_pid):
            _terminate_backend_pid(previous_pid)
        pid_path.write_text(f"{self._pid}\n", encoding="utf-8")

        def _cleanup() -> None:
            current_pid = _read_backend_pid(pid_path)
            if current_pid == self._pid:
                try:
                    pid_path.unlink()
                except FileNotFoundError:
                    return

        atexit.register(_cleanup)
        return pid_path

    def _register_tools(self) -> None:
        """Register the backend MCP tools once."""

        @self.mcp.tool()
        async def get_process_identity() -> dict[str, object]:
            """Return the current server process identity for persistence checks."""
            return _capture_process_identity(self)

        @self.mcp.tool()
        async def get_runtime_capabilities() -> dict[str, object]:
            """Return bounded torch runtime capability flags for this MCP process."""
            payload = _capture_process_identity(self)
            payload.update(_capture_torch_runtime())
            return payload

        @self.mcp.tool()
        async def warmup() -> dict[str, object]:
            """Prime the local reranker and accelerator path before the first real read."""
            return self._warmup_reranker_runtime()

        @self.mcp.tool()
        async def health() -> dict[str, object]:
            """Return the external daemon health plus shim identity for the spike path."""
            payload = self._daemon_runtime_report(ensure_started=False)
            payload["warmup_completed"] = self._reranker_warmed
            return payload

        @self.mcp.tool()
        async def daemon_runtime_report() -> dict[str, object]:
            """Return one bounded runtime report for shim-vs-daemon ownership evidence."""
            payload = self._daemon_runtime_report(ensure_started=False)
            payload["warmup_completed"] = self._reranker_warmed
            return payload

        @self.mcp.tool()
        async def score_probe(query_text: str, passages: list[str]) -> dict[str, object]:
            """Return one bounded rerank timing probe through the external daemon."""
            started = monotonic()
            payload = self._daemon_score_payload(query_text, passages, ensure_started=True)
            elapsed_ms = round((monotonic() - started) * 1000, 3)
            scores = payload.get("scores") if isinstance(payload, dict) else None
            score_count = len(scores) if isinstance(scores, list) else 0
            return {
                **self._daemon_runtime_report(ensure_started=False),
                "elapsed_ms": elapsed_ms,
                "score_count": score_count,
                "model_name": payload.get("model_name") if isinstance(payload, dict) else None,
                "rerank_source": "daemon" if isinstance(payload, dict) else "heuristic",
                "selected_device": self._current_reranker_device(),
            }

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
            """Return reranker scores from the external daemon or an empty heuristic payload."""
            payload = self._daemon_score_payload(query_text, passages, ensure_started=True)
            if payload is not None:
                return payload
            return {"scores": [], "model_name": None, "rerank_source": "heuristic"}

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
    server = create_server()
    server._prepare_stdio_runtime()
    server.mcp.run()


if __name__ == "__main__":
    main()
