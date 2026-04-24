#!/usr/bin/env python3
"""Python entrypoint for vector-first, symbol-checked code reads."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

SOURCE_PATH = Path(__file__).resolve()
SCRIPT_DIR = SOURCE_PATH.parent
REPO_ROOT = SCRIPT_DIR.parent
CODEGRAPH_CONTEXT_DIR = REPO_ROOT / ".codegraphcontext"
CODEGRAPH_DB_DIR = CODEGRAPH_CONTEXT_DIR / "db"
VECTOR_DB_DIR = CODEGRAPH_CONTEXT_DIR / "global" / "db" / "vector-index"
VECTOR_BOOTSTRAP_COMMAND = "uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . bootstrap"

CODE_FILE_LINE_THRESHOLD = 200
READ_CODE_DEFAULT_CONTEXT_LINES = 60
READ_CODE_DEFAULT_WINDOW_LINES = 60
READ_CODE_MAX_LINES = int(os.environ.get("SPECKIT_READ_CODE_MAX_LINES", "80") or "80")
READ_CODE_CONTEXT_PRE_FRACTION = 0.1
READ_CODE_CONTEXT_PRE_CAP = 25
READ_CODE_SEMANTIC_MIN_CONFIDENCE = int(
    os.environ.get("SPECKIT_READ_CODE_SEMANTIC_MIN_CONFIDENCE", "70") or "70"
)
IGNORE_DIRS_DEFAULT = (
    "node_modules,venv,.venv,env,.env,dist,build,target,out,.git,.idea,.vscode,"
    "__pycache__,.uv-cache,logs,shadow-runs"
)
LAST_EDIT_SIGNATURE_FILE = CODEGRAPH_CONTEXT_DIR / "last-edit-signature.txt"
CODEGRAPH_LOCK_RETRY_ATTEMPTS = int(os.environ.get("SPECKIT_CODEGRAPH_LOCK_RETRY_ATTEMPTS", "2") or "2")
CODEGRAPH_LOCK_RETRY_SLEEP_SECONDS = float(
    os.environ.get("SPECKIT_CODEGRAPH_LOCK_RETRY_SLEEP_SECONDS", "0.5") or "0.5"
)
READ_CODE_ALLOW_SYMBOL_DUMP_ENV = "READ_CODE_ALLOW_SYMBOL_DUMP"
READ_CODE_PROBE_CACHE_TTL_SECONDS = float(
    os.environ.get("SPECKIT_READ_CODE_PROBE_CACHE_TTL_SECONDS", "10") or "10"
)
READ_CODE_BACKGROUND_REFRESH_DEBOUNCE_SECONDS = float(
    os.environ.get("SPECKIT_READ_CODE_BACKGROUND_REFRESH_DEBOUNCE_SECONDS", "5") or "5"
)
READ_CODE_WARN_ONCE_TTL_SECONDS = float(
    os.environ.get("SPECKIT_READ_CODE_WARN_ONCE_TTL_SECONDS", "15") or "15"
)


@dataclass(frozen=True)
class _VectorMatch:
    """Candidate vector hit plus ranking features used for anchoring."""

    line_num: int
    raw_score: float
    metadata_score: float
    confidence: int
    exact_symbol_match: bool
    symbol_type: str
    has_body: bool
    has_docstring: bool
    line_span: int
    body: str
    preview: str
    signature: str


@dataclass(frozen=True)
class _CodegraphHealthProbe:
    """Parsed health probe payload including detail and recovery command."""

    status: str
    detail: str
    recovery_command: str


@dataclass(frozen=True)
class _VectorIndexProbe:
    """Parsed vector status payload used to drive refresh branching."""

    status: str
    stale_reason: str
    stale_reason_class: str
    stale_drift_paths: tuple[str, ...]
    stale_signal_source: str
    stale_signal_available: bool
    stale_signal_error: str


@dataclass(frozen=True)
class _AnchorResolution:
    """Shared anchor resolution result for context and window read entrypoints."""

    vector_candidates: list[_VectorMatch]
    vector_match: _VectorMatch | None
    strict_status: int
    line_num: int | None


@dataclass(frozen=True)
class _ContextArgs:
    """Parsed and validated arguments for read_code_context."""

    file_path: Path
    pattern: str
    context: int
    allow_fallback: bool
    show_shortlist: bool
    inline_body: bool
    candidate_index: int


@dataclass(frozen=True)
class _WindowArgs:
    """Parsed and validated arguments for read_code_window."""

    file_path: Path
    start_line: int
    line_count: int
    pattern: str
    use_hud_fast_path: bool
    allow_fallback: bool


_VECTOR_RUNTIME_NOTE: str | None = None
_CODEGRAPH_SESSION_PROBE_DONE = False
_CODEGRAPH_SESSION_PROBE_AVAILABLE = True
_CODEGRAPH_PREFLIGHT_LAUNCHED = False
_VECTOR_PROBE_CACHE: _VectorIndexProbe | None = None
_VECTOR_PROBE_CACHE_AT = 0.0


def _set_vector_runtime_note(note: str) -> None:
    """Track why vector lookup could not be used for the current resolution attempt."""
    global _VECTOR_RUNTIME_NOTE
    if not _VECTOR_RUNTIME_NOTE:
        _VECTOR_RUNTIME_NOTE = note


def _clear_vector_runtime_note() -> None:
    """Reset per-attempt vector runtime diagnostics."""
    global _VECTOR_RUNTIME_NOTE
    _VECTOR_RUNTIME_NOTE = None


def _consume_vector_runtime_note() -> str | None:
    """Return and clear the current vector runtime diagnostic note."""
    global _VECTOR_RUNTIME_NOTE
    note = _VECTOR_RUNTIME_NOTE
    _VECTOR_RUNTIME_NOTE = None
    return note


def _read_code_session_id() -> str:
    """Return session identifier used to cache read preflight probes across helper calls."""
    configured = os.environ.get("READ_CODE_SESSION_ID", "").strip()
    if configured:
        return configured
    return str(os.getppid())


def _symbol_dump_enabled() -> bool:
    """Return whether break-glass symbol-dump mode is explicitly enabled."""
    raw = os.environ.get(READ_CODE_ALLOW_SYMBOL_DUMP_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _session_safe_key(session_id: str) -> str:
    """Return a filesystem-safe cache key derived from a session identifier."""
    safe = "".join(ch for ch in session_id if ch.isalnum() or ch in ("-", "_", "."))
    if not safe:
        safe = "default"
    return safe[:96]


def _codegraph_session_probe_cache_path(session_id: str) -> Path:
    """Return session-scoped cache file path for codegraph availability probe results."""
    return CODEGRAPH_DB_DIR / f"read-code-codegraph-probe-{_session_safe_key(session_id)}.json"


def _codegraph_preflight_launch_flag_path(session_id: str) -> Path:
    """Return session-scoped launch marker for async codegraph preflight."""
    return CODEGRAPH_DB_DIR / f"read-code-codegraph-preflight-launched-{_session_safe_key(session_id)}.flag"


def _vector_session_probe_cache_path(session_id: str) -> Path:
    """Return session-scoped cache file path for vector probe results."""
    return CODEGRAPH_DB_DIR / f"read-code-vector-probe-{_session_safe_key(session_id)}.json"


def _read_code_warn_once_cache_path(session_id: str) -> Path:
    """Return session-scoped cache path for warning suppression."""
    return CODEGRAPH_DB_DIR / f"read-code-warn-once-{_session_safe_key(session_id)}.json"


def _read_code_refresh_debounce_cache_path(session_id: str) -> Path:
    """Return session-scoped cache path for background refresh debounce state."""
    return CODEGRAPH_DB_DIR / f"read-code-refresh-debounce-{_session_safe_key(session_id)}.json"


def _load_json_object(path: Path) -> dict[str, object] | None:
    """Load a JSON object from disk, returning None on missing/invalid payloads."""
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _persist_json_object(
    path: Path,
    payload: dict[str, object],
    *,
    ensure_ascii: bool = True,
    sort_keys: bool = False,
) -> None:
    """Persist a JSON object without raising filesystem write errors."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=ensure_ascii, sort_keys=sort_keys),
            encoding="utf-8",
        )
    except OSError:
        return


def _run_command_capture(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command with deterministic capture defaults for probe/discovery flows."""
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def _parse_json_dict_payload(payload: str) -> tuple[dict[str, object] | None, bool]:
    """Parse a JSON dict payload and report whether parsing itself failed."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None, True
    return (data, False) if isinstance(data, dict) else (None, False)


def _load_string_keyed_mapping(path: Path) -> dict[str, object]:
    """Load a JSON object and keep only string-keyed entries."""
    payload = _load_json_object(path)
    if payload is None:
        return {}
    return {key: value for key, value in payload.items() if isinstance(key, str)}


def _load_session_state(path: Path) -> dict[str, float]:
    """Load a float-valued session state mapping from JSON."""
    payload = _load_string_keyed_mapping(path)
    state: dict[str, float] = {}
    for key, value in payload.items():
        if isinstance(value, (int, float)):
            state[key] = float(value)
    return state


def _persist_session_state(path: Path, state: dict[str, float]) -> None:
    """Persist a float-valued session state mapping to JSON."""
    _persist_json_object(path, dict(state))


def _scope_cache_key(scope_path: Path) -> str:
    """Return a stable cache key for a requested scope path."""
    try:
        return scope_path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(scope_path.resolve())


def _emit_session_warning_once(key: str, message: str, *, ttl_seconds: float | None = None) -> None:
    """Emit a warning once per session key within a TTL window."""
    ttl = READ_CODE_WARN_ONCE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    if ttl <= 0:
        print(message, file=sys.stderr)
        return
    session_id = _read_code_session_id()
    cache_path = _read_code_warn_once_cache_path(session_id)
    state = _load_session_state(cache_path)
    now = time.time()
    last = state.get(key, 0.0)
    if now - last < ttl:
        return
    state[key] = now
    state = {name: ts for name, ts in state.items() if now - ts <= max(ttl * 4, 60.0)}
    _persist_session_state(cache_path, state)
    print(message, file=sys.stderr)


def _should_launch_background_refresh(scope_path: Path, *, channel: str) -> bool:
    """Return whether a background refresh should start based on debounce policy."""
    debounce = READ_CODE_BACKGROUND_REFRESH_DEBOUNCE_SECONDS
    if debounce <= 0:
        return True
    session_id = _read_code_session_id()
    cache_path = _read_code_refresh_debounce_cache_path(session_id)
    state = _load_session_state(cache_path)
    key = f"{channel}:{_scope_cache_key(scope_path)}"
    now = time.time()
    last = state.get(key, 0.0)
    if now - last < debounce:
        return False
    state[key] = now
    state = {name: ts for name, ts in state.items() if now - ts <= max(debounce * 6, 60.0)}
    _persist_session_state(cache_path, state)
    return True


def _make_vector_probe(
    status: str,
    *,
    stale_reason: str = "",
    stale_reason_class: str = "none",
    stale_drift_paths: tuple[str, ...] = (),
    stale_signal_source: str = "git",
    stale_signal_available: bool = True,
    stale_signal_error: str = "",
) -> _VectorIndexProbe:
    """Construct a normalized vector probe payload with consistent defaults."""
    return _VectorIndexProbe(
        status=status,
        stale_reason=str(stale_reason or ""),
        stale_reason_class=str(stale_reason_class or "none"),
        stale_drift_paths=tuple(stale_drift_paths),
        stale_signal_source=str(stale_signal_source or "git"),
        stale_signal_available=bool(stale_signal_available),
        stale_signal_error=str(stale_signal_error or ""),
    )


def _vector_probe_from_payload(payload: object) -> _VectorIndexProbe | None:
    """Decode a cached vector probe payload when it is structurally valid."""
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    if not isinstance(status, str) or not status:
        return None
    stale_reason = payload.get("stale_reason", "")
    stale_reason_class = payload.get("stale_reason_class", "none")
    stale_signal_source = payload.get("stale_signal_source", "git")
    stale_signal_available = payload.get("stale_signal_available", True)
    stale_signal_error = payload.get("stale_signal_error", "")
    stale_drift_paths = payload.get("stale_drift_paths", [])
    return _make_vector_probe(
        status=status,
        stale_reason=stale_reason,
        stale_reason_class=stale_reason_class,
        stale_drift_paths=_normalize_vector_drift_paths(stale_drift_paths),
        stale_signal_source=stale_signal_source,
        stale_signal_available=stale_signal_available,
        stale_signal_error=stale_signal_error,
    )


def _load_vector_probe_cache(session_id: str) -> _VectorIndexProbe | None:
    """Load cached vector probe result when present and within TTL."""
    global _VECTOR_PROBE_CACHE
    global _VECTOR_PROBE_CACHE_AT
    ttl = READ_CODE_PROBE_CACHE_TTL_SECONDS
    now = time.time()
    if ttl > 0 and _VECTOR_PROBE_CACHE is not None and now - _VECTOR_PROBE_CACHE_AT <= ttl:
        return _VECTOR_PROBE_CACHE
    cache_path = _vector_session_probe_cache_path(session_id)
    if not cache_path.is_file():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    ts_raw = payload.get("cached_at")
    if not isinstance(ts_raw, (int, float)):
        return None
    cached_at = float(ts_raw)
    if ttl > 0 and now - cached_at > ttl:
        return None
    probe = _vector_probe_from_payload(payload.get("probe"))
    if probe is None:
        return None
    _VECTOR_PROBE_CACHE = probe
    _VECTOR_PROBE_CACHE_AT = cached_at
    return probe


def _remember_vector_probe(session_id: str, probe: _VectorIndexProbe) -> _VectorIndexProbe:
    """Persist and memoize vector probe results for short-lived reuse."""
    global _VECTOR_PROBE_CACHE
    global _VECTOR_PROBE_CACHE_AT
    now = time.time()
    _VECTOR_PROBE_CACHE = probe
    _VECTOR_PROBE_CACHE_AT = now
    cache_path = _vector_session_probe_cache_path(session_id)
    payload = {
        "cached_at": now,
        "probe": {
            "status": probe.status,
            "stale_reason": probe.stale_reason,
            "stale_reason_class": probe.stale_reason_class,
            "stale_drift_paths": list(probe.stale_drift_paths),
            "stale_signal_source": probe.stale_signal_source,
            "stale_signal_available": probe.stale_signal_available,
            "stale_signal_error": probe.stale_signal_error,
        },
    }
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        return probe
    return probe


def _invalidate_vector_probe_cache(session_id: str | None = None) -> None:
    """Clear in-memory and session-cached vector probe state."""
    global _VECTOR_PROBE_CACHE
    global _VECTOR_PROBE_CACHE_AT
    _VECTOR_PROBE_CACHE = None
    _VECTOR_PROBE_CACHE_AT = 0.0
    active_session = session_id or _read_code_session_id()
    cache_path = _vector_session_probe_cache_path(active_session)
    try:
        cache_path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def _load_codegraph_session_probe_cache(session_id: str) -> bool | None:
    """Load cached session probe availability when present."""
    cache_file = _codegraph_session_probe_cache_path(session_id)
    payload = _load_json_object(cache_file)
    if payload is None:
        return None
    available = payload.get("available")
    return available if isinstance(available, bool) else None


def _persist_codegraph_session_probe_cache(session_id: str, *, available: bool) -> None:
    """Persist session-scoped codegraph probe availability for subsequent helper calls."""
    cache_file = _codegraph_session_probe_cache_path(session_id)
    _persist_json_object(cache_file, {"available": available})


def _mark_codegraph_preflight_launched(session_id: str) -> bool:
    """Mark async codegraph preflight as launched once per session."""
    global _CODEGRAPH_PREFLIGHT_LAUNCHED
    if _CODEGRAPH_PREFLIGHT_LAUNCHED:
        return False
    marker = _codegraph_preflight_launch_flag_path(session_id)
    if marker.is_file():
        _CODEGRAPH_PREFLIGHT_LAUNCHED = True
        return False
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        _CODEGRAPH_PREFLIGHT_LAUNCHED = True
        return False
    _CODEGRAPH_PREFLIGHT_LAUNCHED = True
    return True


def _launch_codegraph_preflight_background(file_path: Path, session_id: str) -> bool:
    """Launch one async codegraph preflight worker for the current session."""
    if not codegraph_supports_file(file_path):
        return False
    if not _mark_codegraph_preflight_launched(session_id):
        return False
    worker_cmd = [
        sys.executable,
        str(SOURCE_PATH),
        "codegraph-preflight-worker",
        str(file_path),
        "--session-id",
        session_id,
    ]
    env = _vector_command_env()
    env["READ_CODE_SESSION_ID"] = session_id
    try:
        subprocess.Popen(
            worker_cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
    except OSError as exc:
        print(f"WARN: codegraph async preflight launch failed: {exc}", file=sys.stderr)
        return False
    return True


def run_codegraph_preflight_worker(argv: list[str]) -> int:
    """Run asynchronous codegraph preflight and one scoped refresh warm-up."""
    if not argv:
        print("ERROR: codegraph-preflight-worker requires: <scope_path> [--session-id <id>]", file=sys.stderr)
        return 1

    scope_raw = argv[0]
    session_id: str | None = None
    extras = argv[1:]
    if extras:
        if len(extras) == 2 and extras[0] == "--session-id":
            session_id = extras[1].strip() or None
        else:
            print("ERROR: invalid codegraph-preflight-worker arguments", file=sys.stderr)
            return 1

    if session_id:
        os.environ["READ_CODE_SESSION_ID"] = session_id
    active_session_id = session_id or _read_code_session_id()
    scope_path = Path(scope_raw).expanduser()
    if not scope_path.is_absolute():
        scope_path = (REPO_ROOT / scope_path).resolve()
    else:
        scope_path = scope_path.resolve()

    init_codegraph_env()
    safe_index = SCRIPT_DIR / "cgc_safe_index.sh"
    if safe_index.is_file() and os.access(safe_index, os.X_OK):
        _run_command_capture(
            [str(safe_index), str(scope_path)],
            env=_vector_command_env(),
        )

    probe = codegraph_health_probe(REPO_ROOT)
    available = probe.status in {"healthy", "stale", "locked"}
    _persist_codegraph_session_probe_cache(active_session_id, available=available)
    return 0


def _ensure_codegraph_session_available(file_path: Path) -> bool:
    """Start async codegraph preflight once per session without blocking read preflight."""
    global _CODEGRAPH_SESSION_PROBE_DONE
    global _CODEGRAPH_SESSION_PROBE_AVAILABLE
    if _CODEGRAPH_SESSION_PROBE_DONE:
        return _CODEGRAPH_SESSION_PROBE_AVAILABLE
    session_id = _read_code_session_id()
    cached = _load_codegraph_session_probe_cache(session_id)
    if cached is not None:
        _CODEGRAPH_SESSION_PROBE_DONE = True
        _CODEGRAPH_SESSION_PROBE_AVAILABLE = cached
    else:
        _CODEGRAPH_SESSION_PROBE_DONE = True
        _CODEGRAPH_SESSION_PROBE_AVAILABLE = True
        _persist_codegraph_session_probe_cache(session_id, available=True)
    if not codegraph_supports_file(file_path):
        return _CODEGRAPH_SESSION_PROBE_AVAILABLE

    _launch_codegraph_preflight_background(file_path, session_id)
    return _CODEGRAPH_SESSION_PROBE_AVAILABLE


def _emit_vector_fallback_notice(
    *,
    file_path: Path,
    pattern: str,
    vector_match: _VectorMatch | None,
    resolved_line: int | None,
) -> None:
    """Emit explicit fallback messaging when semantic anchor selection is not used."""
    if not pattern or vector_match is not None:
        _consume_vector_runtime_note()
        return

    runtime_note = _consume_vector_runtime_note()
    if resolved_line is not None:
        if runtime_note:
            print(
                f"WARN: Vector semantic anchor unavailable ({runtime_note}); using strict/local anchor for '{pattern}' in {file_path}.",
                file=sys.stderr,
            )
        else:
            print(
                f"WARN: Vector semantic anchor not found for '{pattern}' in {file_path}; using strict/local anchor.",
                file=sys.stderr,
            )
        return

    if runtime_note:
        print(
            f"WARN: Vector semantic anchor unavailable ({runtime_note}) for '{pattern}' in {file_path}.",
            file=sys.stderr,
        )


def _command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def _is_repo_local_path(file_path: Path) -> bool:
    """Return whether a target file resides under the repository root."""
    try:
        file_path.resolve().relative_to(REPO_ROOT)
        return True
    except ValueError:
        return False


def _coerce_line(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value, 10)
    return None


def _vector_command_env() -> dict[str, str]:
    """Return deterministic env for vector subprocess calls with repo-local uv cache."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from uv_env import repo_uv_env

    env = repo_uv_env()
    env.setdefault("HF_HUB_OFFLINE", "1")
    return env


def _vector_indexer_cmd(project_root: Path, action: str, *args: str) -> list[str]:
    """Build a deterministic vector indexer command for the requested action."""
    return [
        "uv",
        "run",
        "--no-sync",
        "python",
        "-m",
        "src.mcp_codebase.indexer",
        "--repo-root",
        str(project_root),
        action,
        *args,
    ]


def _normalize_vector_drift_paths(payload: object) -> tuple[str, ...]:
    """Normalize vector status drift-path payload into repo-relative POSIX paths."""
    if not isinstance(payload, list):
        return ()
    paths: list[str] = []
    for item in payload:
        if not isinstance(item, str):
            continue
        candidate = item.strip().replace("\\", "/")
        if candidate.startswith("./"):
            candidate = candidate[2:]
        if candidate:
            paths.append(candidate)
    return tuple(dict.fromkeys(paths))


def init_codegraph_env() -> None:
    """Set deterministic codegraph runtime paths for this repo."""
    repo_uv_cache = Path(os.environ.get("CGC_UV_CACHE_DIR", str(CODEGRAPH_CONTEXT_DIR / ".uv-cache")))
    CODEGRAPH_DB_DIR.mkdir(parents=True, exist_ok=True)
    repo_uv_cache.mkdir(parents=True, exist_ok=True)

    os.environ["UV_CACHE_DIR"] = str(repo_uv_cache)
    os.environ.setdefault("DEFAULT_DATABASE", "kuzudb")
    os.environ.setdefault("FALKORDB_PATH", str(CODEGRAPH_DB_DIR / "falkordb"))
    os.environ.setdefault("FALKORDB_SOCKET_PATH", str(CODEGRAPH_DB_DIR / "falkordb.sock"))
    os.environ.setdefault("KUZUDB_PATH", str(CODEGRAPH_DB_DIR / "kuzudb"))
    os.environ.setdefault("IGNORE_DIRS", IGNORE_DIRS_DEFAULT)


def codegraph_edit_signature_file(project_root: Path | None = None) -> Path:
    """Return the cached edit-signature marker path."""
    root = project_root or REPO_ROOT
    return root / ".codegraphcontext" / LAST_EDIT_SIGNATURE_FILE.name


def codegraph_cached_edit_signature(project_root: Path | None = None) -> str:
    """Read the cached edit signature if it exists."""
    marker_file = codegraph_edit_signature_file(project_root)
    if not marker_file.is_file():
        return ""
    try:
        return marker_file.read_text(encoding="utf-8").rstrip("\n")
    except OSError:
        return ""


def codegraph_current_edit_signature(project_root: Path | None = None) -> str:
    """Return the current non-ignored git status signature."""
    root = project_root or REPO_ROOT
    proc = _run_command_capture(
        [
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain",
            "--untracked-files=normal",
        ]
    )
    if proc.returncode != 0:
        return ""

    ignored_prefixes = (
        ".codegraphcontext/",
        ".speckit/",
        ".uv-cache/",
        "logs/",
        "shadow-runs/",
    )
    lines: list[str] = []
    for raw in proc.stdout.splitlines():
        if not raw.strip():
            continue
        line = raw.rstrip("\n")
        path = line[3:] if len(line) > 3 else ""
        if " -> " in path:
            candidates = [part.strip() for part in path.split(" -> ")]
        else:
            candidates = [path.strip()]
        if any(candidate.startswith(ignored_prefixes) for candidate in candidates if candidate):
            continue
        lines.append(line)

    return "\n".join(sorted(dict.fromkeys(lines)))


def _signature_paths(signature: str) -> set[str]:
    """Extract normalized relative paths from a git porcelain signature string."""
    paths: set[str] = set()
    for raw in signature.splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        if len(line) < 4:
            continue
        candidate = line[3:].strip()
        if not candidate:
            continue
        if " -> " in candidate:
            parts = [part.strip() for part in candidate.split(" -> ")]
        else:
            parts = [candidate]
        for part in parts:
            normalized = part.replace("\\", "/")
            if normalized.startswith("./"):
                normalized = normalized[2:]
            if normalized:
                paths.add(normalized)
    return paths


def _scope_needs_codegraph_refresh(scope_path: Path) -> bool:
    """Return whether stale signature drift overlaps the requested scope path."""
    current = codegraph_current_edit_signature(REPO_ROOT)
    cached = codegraph_cached_edit_signature(REPO_ROOT)
    if current == cached:
        return False

    current_paths = _signature_paths(current)
    cached_paths = _signature_paths(cached)
    drift_paths = current_paths.symmetric_difference(cached_paths)
    if not drift_paths:
        return True

    try:
        scope_abs = scope_path.resolve()
        scope_rel = scope_abs.relative_to(REPO_ROOT).as_posix().rstrip("/")
    except ValueError:
        return True

    if not scope_rel:
        return True

    scope_prefix = f"{scope_rel}/"
    for candidate in drift_paths:
        if candidate == scope_rel or candidate.startswith(scope_prefix):
            return True
    return False


def codegraph_health_status(project_root: Path | None = None) -> str:
    """Return codegraph health status string or probe-failed."""
    return codegraph_health_probe(project_root).status


def codegraph_health_probe(project_root: Path | None = None) -> _CodegraphHealthProbe:
    """Return codegraph health status plus detail and recovery hint command."""
    root = project_root or REPO_ROOT
    if not _command_exists("uv"):
        print("WARN: codegraph health probe skipped because uv is not available", file=sys.stderr)
        return _CodegraphHealthProbe(
            status="unavailable",
            detail="uv is not available",
            recovery_command=f"{SCRIPT_DIR / 'cgc_safe_index.sh'} {root}",
        )
    proc = _run_command_capture(
        [
            "uv",
            "run",
            "--no-sync",
            "python",
            "-m",
            "src.mcp_codebase.doctor",
            "--json",
            "--project-root",
            str(root),
        ],
    )

    payload = (proc.stdout or "").strip()
    status = ""
    detail = ""
    recovery_command = ""
    if payload:
        data, parse_error = _parse_json_dict_payload(payload)
        if parse_error:
            print("WARN: codegraph health probe returned non-JSON output", file=sys.stderr)
            status = ""
        elif data is not None:
            status = str(data.get("status", ""))
            detail = str(data.get("detail", "") or "")
            recovery_hint = data.get("recovery_hint")
            if isinstance(recovery_hint, dict):
                recovery_command = str(recovery_hint.get("command", "") or "")

    if not status:
        doctor_err = (proc.stderr or "").strip()
        if doctor_err:
            print(f"WARN: codegraph health probe failed: {doctor_err}", file=sys.stderr)
            detail = doctor_err
        return _CodegraphHealthProbe(
            status="probe-failed",
            detail=detail,
            recovery_command=recovery_command,
        )

    return _CodegraphHealthProbe(
        status=status or "probe-failed",
        detail=detail,
        recovery_command=recovery_command,
    )


def codegraph_refresh_if_needed(scope_path: Path | None = None) -> bool:
    """Refresh scoped codegraph index and retry lock recovery deterministically."""
    path = scope_path or REPO_ROOT
    probe = codegraph_health_probe(REPO_ROOT)
    if probe.status == "healthy":
        return True
    if probe.status == "stale" and not _scope_needs_codegraph_refresh(path):
        _emit_session_warning_once(
            key=f"codegraph-stale-nonoverlap:{_scope_cache_key(path)}",
            message=f"WARN: codegraph stale drift does not overlap requested scope ({path}); refreshing scoped index in background",
        )
        safe_index = SCRIPT_DIR / "cgc_safe_index.sh"
        if safe_index.is_file() and os.access(safe_index, os.X_OK) and _should_launch_background_refresh(
            path, channel="codegraph"
        ):
            try:
                subprocess.Popen(
                    [str(safe_index), str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError as exc:
                print(f"WARN: codegraph background refresh could not start: {exc}", file=sys.stderr)
        else:
            print(
                f"WARN: codegraph background refresh skipped: missing safe index script at {safe_index}",
                file=sys.stderr,
            )
        return True

    safe_index = SCRIPT_DIR / "cgc_safe_index.sh"
    if not (safe_index.is_file() and os.access(safe_index, os.X_OK)):
        print(f"ERROR: codegraph preflight failed: missing safe index script at {safe_index}", file=sys.stderr)
        return False

    lock_attempts = max(1, CODEGRAPH_LOCK_RETRY_ATTEMPTS)
    max_attempts = lock_attempts if probe.status == "locked" else 1
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        if probe.status == "stale":
            print(f"WARN: codegraph is stale; refreshing scoped index for {path}", file=sys.stderr)
        elif probe.status == "locked":
            reason = probe.detail or "lock marker present"
            print(f"WARN: codegraph is locked ({reason}); attempting scoped recovery for {path}", file=sys.stderr)
        else:
            reason = probe.detail or "no additional detail"
            print(
                f"ERROR: codegraph preflight failed: status is {probe.status} ({reason}). "
                f"Remediation: {safe_index} {path}",
                file=sys.stderr,
            )
            if probe.recovery_command:
                print(f"ERROR: doctor suggested: {probe.recovery_command}", file=sys.stderr)
            return False

        proc = _run_command_capture([str(safe_index), str(path)])
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            if stderr:
                print(f"ERROR: codegraph refresh failed: {stderr.splitlines()[-1]}", file=sys.stderr)
            else:
                print(f"ERROR: codegraph refresh failed with exit code {proc.returncode}", file=sys.stderr)
            print(f"ERROR: remediation: {safe_index} {path}", file=sys.stderr)
            return False

        probe = codegraph_health_probe(REPO_ROOT)
        if probe.status == "healthy":
            return True
        if probe.status == "locked" and attempt < max_attempts:
            time.sleep(max(CODEGRAPH_LOCK_RETRY_SLEEP_SECONDS, 0.0))
            continue
        break

    final_reason = probe.detail or "no additional detail"
    print(
        f"ERROR: codegraph preflight failed after refresh: status is {probe.status} ({final_reason}). "
        f"Remediation: {safe_index} {path}",
        file=sys.stderr,
    )
    if probe.recovery_command:
        print(f"ERROR: doctor suggested: {probe.recovery_command}", file=sys.stderr)
    return False


def vector_index_probe(project_root: Path | None = None) -> _VectorIndexProbe:
    """Return parsed vector freshness payload for deterministic refresh decisions."""
    root = project_root or REPO_ROOT
    session_id = _read_code_session_id()
    cached_probe = _load_vector_probe_cache(session_id)
    if cached_probe is not None:
        return cached_probe
    if not _command_exists("uv"):
        _set_vector_runtime_note("uv is not available")
        return _remember_vector_probe(
            session_id,
            _make_vector_probe(
                status="unavailable",
                stale_reason="uv is not available",
                stale_reason_class="probe-unavailable",
                stale_drift_paths=(),
                stale_signal_source="git",
                stale_signal_available=False,
                stale_signal_error="uv is not available",
            ),
        )

    cmd = _vector_indexer_cmd(root, "status")
    proc = _run_command_capture(cmd, env=_vector_command_env())
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if stderr:
            _set_vector_runtime_note(f"index status probe failed: {stderr.splitlines()[0]}")
        else:
            _set_vector_runtime_note(f"index status probe failed with exit code {proc.returncode}")
        return _remember_vector_probe(
            session_id,
            _make_vector_probe(
                status="probe-failed",
                stale_reason=stderr or f"index status probe failed with exit code {proc.returncode}",
                stale_reason_class="probe-failed",
                stale_drift_paths=(),
                stale_signal_source="git",
                stale_signal_available=False,
                stale_signal_error=stderr or f"exit code {proc.returncode}",
            ),
        )

    payload = (proc.stdout or "").strip()
    if payload in {"", "null"}:
        return _remember_vector_probe(
            session_id,
            _make_vector_probe(
                status="missing",
                stale_reason=f"index snapshot missing at {VECTOR_DB_DIR}",
                stale_reason_class="missing-index",
                stale_drift_paths=(),
                stale_signal_source="git",
                stale_signal_available=False,
                stale_signal_error="index snapshot missing",
            ),
        )

    status_payload, parse_error = _parse_json_dict_payload(payload)
    if parse_error:
        _set_vector_runtime_note("index status probe returned non-JSON output")
        return _remember_vector_probe(
            session_id,
            _make_vector_probe(
                status="probe-failed",
                stale_reason="index status probe returned non-JSON output",
                stale_reason_class="probe-failed",
                stale_drift_paths=(),
                stale_signal_source="git",
                stale_signal_available=False,
                stale_signal_error="non-json status payload",
            ),
        )
    if status_payload is None:
        _set_vector_runtime_note("index status probe returned unexpected payload shape")
        return _remember_vector_probe(
            session_id,
            _make_vector_probe(
                status="probe-failed",
                stale_reason="index status probe returned unexpected payload shape",
                stale_reason_class="probe-failed",
                stale_drift_paths=(),
                stale_signal_source="git",
                stale_signal_available=False,
                stale_signal_error="unexpected payload shape",
            ),
        )
    is_stale = bool(status_payload.get("is_stale", False))
    return _remember_vector_probe(
        session_id,
        _make_vector_probe(
            status="stale" if is_stale else "healthy",
            stale_reason=str(status_payload.get("stale_reason", "") or ""),
            stale_reason_class=str(status_payload.get("stale_reason_class", "none") or "none"),
            stale_drift_paths=_normalize_vector_drift_paths(status_payload.get("stale_drift_paths")),
            stale_signal_source=str(status_payload.get("stale_signal_source", "git") or "git"),
            stale_signal_available=bool(status_payload.get("stale_signal_available", True)),
            stale_signal_error=str(status_payload.get("stale_signal_error", "") or ""),
        ),
    )


def vector_index_status(project_root: Path | None = None) -> str:
    """Return vector index freshness state: healthy, stale, missing, unavailable, or probe-failed."""
    return vector_index_probe(project_root).status


def _scope_needs_vector_refresh(scope_path: Path, drift_paths: tuple[str, ...]) -> bool | None:
    """Return overlap decision for a requested scope against stale drift paths."""
    if not drift_paths:
        return None
    try:
        scope_abs = scope_path.resolve()
        scope_rel = scope_abs.relative_to(REPO_ROOT).as_posix().rstrip("/")
    except ValueError:
        return None

    if not scope_rel:
        return True
    scope_prefix = f"{scope_rel}/"
    for candidate in drift_paths:
        if candidate == scope_rel:
            return True
        if candidate.startswith(scope_prefix):
            return True
        if scope_rel.startswith(f"{candidate.rstrip('/')}/"):
            return True
    return False


def vector_refresh_if_needed(scope_path: Path | None = None) -> bool:
    """Require a healthy vector index with scope-aware stale refresh branching."""
    path = scope_path or REPO_ROOT
    probe = vector_index_probe(REPO_ROOT)
    status = probe.status
    if status == "healthy":
        return True
    if status in {"missing", "unavailable", "probe-failed"}:
        if status == "missing":
            _set_vector_runtime_note(
                f"index snapshot missing at {VECTOR_DB_DIR}; run `{VECTOR_BOOTSTRAP_COMMAND}`"
            )
        elif probe.stale_reason:
            _set_vector_runtime_note(probe.stale_reason)
        print(f"ERROR: vector preflight failed: status is {status}", file=sys.stderr)
        return False
    if not _command_exists("uv"):
        _set_vector_runtime_note("uv is not available")
        print("ERROR: vector preflight failed: uv is not available", file=sys.stderr)
        return False

    overlap = _scope_needs_vector_refresh(path, probe.stale_drift_paths)
    overlap_label = (
        "yes"
        if overlap is True
        else "no"
        if overlap is False
        else "unknown"
    )
    cause = probe.stale_reason_class or "none"
    detail = probe.stale_reason or "no stale reason provided"
    signal = probe.stale_signal_source or "git"
    if overlap is False:
        _emit_session_warning_once(
            key=f"vector-stale-nonoverlap:{_scope_cache_key(path)}:{cause}",
            message=(
                "WARN: vector index is stale; "
                f"cause={cause}; signal={signal}; overlap={overlap_label}; detail={detail}; "
                f"drift_paths={list(probe.stale_drift_paths)}; "
                f"proceeding without refresh because scope does not overlap request ({path})"
            ),
        )
        return True

    print(
        "WARN: vector index is stale; "
        f"cause={cause}; signal={signal}; overlap={overlap_label}; detail={detail}; "
        f"drift_paths={list(probe.stale_drift_paths)}; "
        f"refreshing targeted index for {path}",
        file=sys.stderr,
    )
    cmd = _vector_indexer_cmd(REPO_ROOT, "refresh", str(path))
    proc = _run_command_capture(cmd, env=_vector_command_env())
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if stderr:
            _set_vector_runtime_note(f"index refresh failed: {stderr.splitlines()[0]}")
        else:
            _set_vector_runtime_note(f"index refresh failed with exit code {proc.returncode}")
        print("ERROR: vector preflight failed: targeted refresh did not complete", file=sys.stderr)
        return False

    _invalidate_vector_probe_cache()
    refreshed_probe = vector_index_probe(REPO_ROOT)
    if refreshed_probe.status != "healthy":
        refreshed_overlap = _scope_needs_vector_refresh(path, refreshed_probe.stale_drift_paths)
        if refreshed_probe.status == "stale" and refreshed_overlap is False:
            _emit_session_warning_once(
                key=f"vector-post-refresh-stale-nonoverlap:{_scope_cache_key(path)}",
                message=(
                    "WARN: vector index remains stale after scoped refresh, but stale drift does not overlap "
                    f"requested scope ({path}); proceeding and refreshing in background"
                ),
            )
            if _should_launch_background_refresh(path, channel="vector"):
                followup_cmd = _vector_indexer_cmd(REPO_ROOT, "refresh", str(path))
                try:
                    subprocess.Popen(
                        followup_cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                        env=_vector_command_env(),
                    )
                except OSError as exc:
                    print(f"WARN: vector follow-up background refresh could not start: {exc}", file=sys.stderr)
            return True

        _set_vector_runtime_note(f"index status after refresh is {refreshed_probe.status}")
        print(
            f"ERROR: vector preflight failed after refresh: status is {refreshed_probe.status}",
            file=sys.stderr,
        )
        return False
    return True


def _refresh_indexes_for_read(file_path: Path) -> bool:
    """Run read preflight checks with vector hard-gate and session-scoped codegraph probe."""
    if not _is_repo_local_path(file_path):
        return True
    _ensure_codegraph_session_available(file_path)
    if not vector_refresh_if_needed(file_path):
        runtime_note = _consume_vector_runtime_note()
        if runtime_note:
            print(f"ERROR: {runtime_note}", file=sys.stderr)
        print(
            "ERROR: read-code preflight requires a healthy vector index.",
            file=sys.stderr,
        )
        return False
    return True


def codegraph_supports_file(file_path: Path) -> bool:
    """Return whether codegraph discovery should run for this extension."""
    supported_extensions = {
        ".py",
        ".pyi",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".go",
        ".ts",
        ".tsx",
        ".cpp",
        ".h",
        ".hpp",
        ".hh",
        ".rs",
        ".c",
        ".java",
        ".rb",
        ".cs",
        ".php",
        ".kt",
        ".scala",
        ".sc",
        ".swift",
        ".hs",
        ".dart",
        ".pl",
        ".pm",
        ".ex",
        ".exs",
    }
    return file_path.suffix in supported_extensions


def _tail_lines(text: str, count: int = 20) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-count:]


def codegraph_discover_or_fail(
    pattern: str,
    scope_path: Path | None = None,
    *,
    skip_preflight_refresh: bool = False,
) -> bool:
    """Run bounded codegraph discovery and self-heal index fragility once."""
    if not pattern:
        print("ERROR: codegraph discovery requires a non-empty symbol_or_pattern", file=sys.stderr)
        return False

    if not _command_exists("uv"):
        print("ERROR: uv is required for codegraph discovery (uv run cgc ...)", file=sys.stderr)
        return False

    path = scope_path or REPO_ROOT
    init_codegraph_env()
    if not skip_preflight_refresh and not codegraph_refresh_if_needed(path):
        return False

    cmd = ["uv", "run", "--no-sync", "cgc", "find", "pattern", "--", pattern]
    proc = _run_command_capture(cmd, env=_vector_command_env())
    if proc.returncode == 0:
        return True

    output = (proc.stdout or "") + (proc.stderr or "")
    safe_index = SCRIPT_DIR / "cgc_safe_index.sh"
    has_self_heal_pattern = "Database Connection Error" in output or "No index metadata" in output
    if has_self_heal_pattern and safe_index.is_file() and os.access(safe_index, os.X_OK):
        _run_command_capture([str(safe_index), str(path)])
        second = _run_command_capture(cmd)
        if second.returncode == 0:
            return True
        output = (second.stdout or "") + (second.stderr or "")

    print(f"ERROR: codegraph discovery failed for pattern: {pattern}", file=sys.stderr)
    print("Hint: run scripts/cgc_safe_index.sh <scoped-path> and retry.", file=sys.stderr)
    for line in _tail_lines(output, count=20):
        print(line, file=sys.stderr)
    return False


def normalize_symbol_pattern(raw: str) -> str:
    """Normalize common declaration prefixes and suffix delimiters."""
    normalized = raw.strip()
    for prefix in ("async def ", "def ", "class "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
    normalized = normalized.split("(", 1)[0]
    normalized = normalized.split(":", 1)[0]
    normalized = normalized.split(maxsplit=1)[0] if normalized else normalized
    return normalized


def _candidate_nested_value(item: dict[str, object], key: str) -> object | None:
    """Return candidate content[key] when a nested content mapping is present."""
    content = item.get("content")
    if isinstance(content, dict):
        return content.get(key)
    return None


def _resolve_candidate_line(item: dict[str, object]) -> int | None:
    line = _coerce_line(item.get("line_start"))
    if line is not None:
        return line
    return _coerce_line(_candidate_nested_value(item, "line_start"))


def _candidate_text(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    if isinstance(value, str):
        return value
    nested = _candidate_nested_value(item, key)
    if isinstance(nested, str):
        return nested
    return ""


def _candidate_int(item: dict[str, object], key: str) -> int | None:
    value = item.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value, 10)
    nested = _candidate_nested_value(item, key)
    if isinstance(nested, int):
        return nested
    if isinstance(nested, str) and nested.isdigit():
        return int(nested, 10)
    return None


def _candidate_string_list(item: dict[str, object], key: str) -> list[str]:
    value = item.get(key)
    if isinstance(value, list):
        return [str(part) for part in value if str(part)]
    nested = _candidate_nested_value(item, key)
    if isinstance(nested, list):
        return [str(part) for part in nested if str(part)]
    return []


def _candidate_raw_score(item: dict[str, object]) -> float:
    value = item.get("score")
    if isinstance(value, (int, float)):
        return float(value)
    nested_score = _candidate_nested_value(item, "score")
    if isinstance(nested_score, (int, float)):
        return float(nested_score)

    distance = item.get("distance")
    if isinstance(distance, (int, float)):
        return max(0.0, 1.0 - float(distance))
    nested_distance = _candidate_nested_value(item, "distance")
    if isinstance(nested_distance, (int, float)):
        return max(0.0, 1.0 - float(nested_distance))
    return 0.0


def _candidate_metadata_score(item: dict[str, object], query: str, normalized_query: str) -> tuple[float, bool]:
    symbol_name = _candidate_text(item, "symbol_name")
    qualified_name = _candidate_text(item, "qualified_name")
    signature = _candidate_text(item, "signature")
    docstring = _candidate_text(item, "docstring")
    body = _candidate_text(item, "body")
    preview = _candidate_text(item, "preview")
    heading = _candidate_text(item, "heading")
    symbol_type = _candidate_text(item, "symbol_type")
    record_type = _candidate_text(item, "record_type")
    breadcrumb = _candidate_string_list(item, "breadcrumb")
    line_start = _candidate_int(item, "line_start") or 0
    line_end = _candidate_int(item, "line_end") or 0

    exact_symbol_match = False
    for token in (query, normalized_query):
        if not token:
            continue
        lowered = token.lower()
        if lowered == symbol_name.lower() or lowered == heading.lower():
            exact_symbol_match = True
            break
        if qualified_name.lower().endswith(f".{lowered}") or qualified_name.lower().endswith(f"::{lowered}"):
            exact_symbol_match = True
            break

    score = 0.0
    if record_type == "code":
        score += 1.0
    if symbol_type in {"function", "method", "class"}:
        score += 5.0
    if symbol_name:
        score += 1.0
    if qualified_name:
        score += 1.0
    if signature:
        score += 3.5
        signature_lower = signature.lstrip().lower()
        if signature_lower.startswith(("def ", "async def ", "class ", "function ")):
            score += 2.0
        elif symbol_name and signature_lower.startswith(
            (f"{symbol_name.lower()}(", f"{symbol_name.lower()} ()", f"{symbol_name.lower()}()")
        ):
            score += 1.5
    if docstring:
        score += 4.0
    if body:
        score += 4.0
        if len(body) > 200:
            score += 1.0
    if preview:
        score += 1.0
    if heading:
        score += 0.5
    if breadcrumb:
        score += 0.5
    if line_end > line_start:
        score += 1.0

    if query:
        query_lower = query.lower()
        if query_lower == symbol_name.lower() or query_lower == heading.lower():
            score += 5.0
        elif query_lower in qualified_name.lower():
            score += 4.0
        elif query_lower in signature.lower():
            score += 3.0
        elif query_lower in docstring.lower():
            score += 2.0
        elif query_lower in body.lower() or query_lower in preview.lower():
            score += 1.5

    if normalized_query and normalized_query != query:
        normalized_lower = normalized_query.lower()
        if normalized_lower == symbol_name.lower() or normalized_lower == heading.lower():
            score += 4.0
            exact_symbol_match = True
        elif normalized_lower in qualified_name.lower():
            score += 2.5
            exact_symbol_match = True

    return score, exact_symbol_match


def _candidate_confidence(
    raw_score: float,
    metadata_score: float,
    *,
    exact_symbol_match: bool,
    has_body: bool,
    has_docstring: bool,
    line_span: int,
) -> int:
    """Normalize vector signal into a stable 0-100 confidence score."""
    score = raw_score * 50.0
    score += min(metadata_score, 20.0) * 2.5
    if exact_symbol_match:
        score += 10.0
    if has_body:
        score += 7.0
    if has_docstring:
        score += 4.0
    score -= min(float(line_span), 10.0)
    return max(0, min(100, int(round(score))))


def _vector_anchor_rank(match: _VectorMatch) -> tuple[int, int, int, int, int, float, float, int, int]:
    return (
        match.confidence,
        1 if match.exact_symbol_match else 0,
        1 if match.symbol_type in {"function", "method", "class"} else 0,
        1 if match.has_body else 0,
        1 if match.has_docstring else 0,
        match.metadata_score,
        match.raw_score,
        match.line_span,
        -match.line_num,
    )


def _vector_match_for_item(item: dict[str, object], query: str, normalized_query: str) -> _VectorMatch | None:
    line_num = _resolve_candidate_line(item)
    if line_num is None:
        return None

    raw_score = _candidate_raw_score(item)
    metadata_score, exact_symbol_match = _candidate_metadata_score(item, query, normalized_query)
    body = _candidate_text(item, "body")
    preview = _candidate_text(item, "preview")
    signature = _candidate_text(item, "signature")
    has_docstring = bool(_candidate_text(item, "docstring"))
    line_span = max(0, (_candidate_int(item, "line_end") or 0) - line_num)
    return _VectorMatch(
        line_num=line_num,
        raw_score=raw_score,
        metadata_score=metadata_score,
        confidence=_candidate_confidence(
            raw_score,
            metadata_score,
            exact_symbol_match=exact_symbol_match,
            has_body=bool(body),
            has_docstring=has_docstring,
            line_span=line_span,
        ),
        exact_symbol_match=exact_symbol_match,
        symbol_type=_candidate_text(item, "symbol_type"),
        has_body=bool(body),
        has_docstring=has_docstring,
        line_span=line_span,
        body=body,
        preview=preview,
        signature=signature,
    )


def _vector_query_candidates(
    file_path: Path,
    query: str,
    normalized_query: str,
    scope: str,
) -> list[_VectorMatch]:
    if not query or not scope:
        return []
    if not _command_exists("uv"):
        _set_vector_runtime_note("uv is not available")
        return []

    cmd = _vector_indexer_cmd(
        REPO_ROOT,
        "query",
        query,
        "--file-path",
        str(file_path.resolve()),
        "--scope",
        scope,
        "--top-k",
        "20",
    )
    proc = _run_command_capture(cmd, env=_vector_command_env())
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if stderr:
            _set_vector_runtime_note(f"indexer query failed: {stderr.splitlines()[0]}")
        else:
            _set_vector_runtime_note(f"indexer query failed with exit code {proc.returncode}")
        return []

    try:
        payload = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        _set_vector_runtime_note("indexer query returned invalid JSON")
        return []
    if not isinstance(payload, list):
        _set_vector_runtime_note("indexer query returned unexpected payload shape")
        return []

    target = file_path.resolve()
    matches: list[_VectorMatch] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        candidate = _candidate_text(item, "file_path")
        if not candidate:
            continue
        try:
            if Path(candidate).expanduser().resolve() != target:
                continue
        except Exception:
            continue
        match = _vector_match_for_item(item, query, normalized_query)
        if match is None:
            continue
        matches.append(match)

    return sorted(matches, key=_vector_anchor_rank, reverse=True)[:5]


def _vector_find_candidates(
    file_path: Path,
    raw_pattern: str,
    normalized_pattern: str,
    scope: str,
) -> list[_VectorMatch]:
    """Return the bounded shortlist for a query using raw and normalized probes."""
    _clear_vector_runtime_note()
    candidates: list[_VectorMatch] = []
    if raw_pattern:
        candidates = _vector_query_candidates(file_path, raw_pattern, normalized_pattern, scope)
    if not candidates and normalized_pattern and normalized_pattern != raw_pattern:
        candidates = _vector_query_candidates(file_path, normalized_pattern, normalized_pattern, scope)
    return candidates


def _vector_list_code_symbols(file_path: Path) -> list[dict[str, object]]:
    """Return deterministic code symbols for a file from the active vector snapshot."""
    if not _command_exists("uv"):
        _set_vector_runtime_note("uv is not available")
        return []

    cmd = _vector_indexer_cmd(REPO_ROOT, "list-file-symbols", str(file_path))
    proc = _run_command_capture(cmd)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if stderr:
            _set_vector_runtime_note(f"list-file-symbols failed: {stderr.splitlines()[0]}")
        else:
            _set_vector_runtime_note(f"list-file-symbols failed with exit code {proc.returncode}")
        return []

    try:
        payload = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        _set_vector_runtime_note("list-file-symbols returned invalid JSON")
        return []
    if not isinstance(payload, list):
        _set_vector_runtime_note("list-file-symbols returned unexpected payload shape")
        return []

    symbols: list[dict[str, object]] = []
    for item in payload:
        if isinstance(item, dict):
            symbols.append(item)
    return symbols


def _iter_literal_hits(file_path: Path, literal: str) -> Iterator[int]:
    """Yield 1-based line numbers that contain the requested literal."""
    if not literal:
        return
    with file_path.open(encoding="utf-8") as handle:
        for idx, line in enumerate(handle, start=1):
            if literal in line:
                yield idx


def _find_first_literal_line(file_path: Path, literal: str) -> int | None:
    """Return the first matching line for a literal, when one exists."""
    return next(_iter_literal_hits(file_path, literal), None)


def _find_line_num(file_path: Path, raw_pattern: str, normalized_pattern: str) -> int | None:
    line_num = _find_first_literal_line(file_path, raw_pattern) if raw_pattern else None
    if line_num is None and normalized_pattern and normalized_pattern != raw_pattern:
        line_num = _find_first_literal_line(file_path, normalized_pattern)
    if line_num is None and normalized_pattern:
        line_num = _find_first_literal_line(file_path, f"def {normalized_pattern}")
    if line_num is None and normalized_pattern:
        line_num = _find_first_literal_line(file_path, f"async def {normalized_pattern}")
    if line_num is None and normalized_pattern:
        line_num = _find_first_literal_line(file_path, f"class {normalized_pattern}")
    return line_num


def _collect_literal_hits(file_path: Path, literal: str) -> list[int]:
    """Return every matching line number for a literal within a file."""
    return list(_iter_literal_hits(file_path, literal))


def _resolve_line_num_strict(file_path: Path, raw_pattern: str, normalized_pattern: str) -> tuple[int, int | None]:
    if normalized_pattern:
        strict_hits: set[int] = set()
        for literal in [
            f"def {normalized_pattern}(",
            f"async def {normalized_pattern}(",
            f"class {normalized_pattern}",
            f"function {normalized_pattern}",
            f"{normalized_pattern}() {{",
            f"{normalized_pattern} () {{",
            f"{normalized_pattern} =",
        ]:
            strict_hits.update(_collect_literal_hits(file_path, literal))
        ordered = sorted(strict_hits)
        if len(ordered) == 1:
            return 0, ordered[0]
        if len(ordered) > 1:
            print(
                f"ERROR: Strict symbol match is ambiguous for '{normalized_pattern}' in {file_path}.",
                file=sys.stderr,
            )
            return 2, None

    raw_hits = sorted(set(_collect_literal_hits(file_path, raw_pattern)))
    if len(raw_hits) == 1:
        return 0, raw_hits[0]
    if len(raw_hits) > 1:
        print(
            f"ERROR: Strict symbol match is ambiguous for '{raw_pattern}' in {file_path}.",
            file=sys.stderr,
        )
        return 2, None

    return 1, None


def is_large_code_file(file_path: Path) -> bool:
    """Return True when file length exceeds mandatory symbol guard threshold."""
    with file_path.open(encoding="utf-8") as handle:
        line_count = sum(1 for _ in handle)
    return line_count > CODE_FILE_LINE_THRESHOLD


def _render_numbered_window(file_path: Path, start: int, end: int) -> None:
    with file_path.open(encoding="utf-8") as handle:
        for idx, line in enumerate(handle, start=1):
            if idx < start:
                continue
            if idx > end:
                break
            print(f"{idx:6}\t{line.rstrip()}")


def _split_context_window(context_lines: int) -> tuple[int, int]:
    """Split context budget into a small pre-window and larger post-window."""
    if context_lines <= 1:
        return 0, context_lines

    pre_lines = max(1, int(context_lines * READ_CODE_CONTEXT_PRE_FRACTION))
    pre_lines = min(pre_lines, READ_CODE_CONTEXT_PRE_CAP, context_lines - 1)
    post_lines = context_lines - pre_lines
    return pre_lines, post_lines


def _render_symbol_listing(symbols: list[dict[str, object]]) -> None:
    """Render a deterministic symbol list for agent anchor selection."""
    for symbol in symbols:
        symbol_name = str(symbol.get("symbol_name", "") or "")
        if not symbol_name:
            continue
        symbol_type = str(symbol.get("symbol_type", "") or "symbol")
        line_start = _coerce_line(symbol.get("line_start")) or 0
        line_end = _coerce_line(symbol.get("line_end")) or line_start
        signature = str(symbol.get("signature", "") or "")
        qualified_name = str(symbol.get("qualified_name", "") or "")
        has_body = bool(str(symbol.get("body", "") or ""))
        print(
            "\t".join(
                [
                    f"{line_start:6}",
                    f"{line_end:6}",
                    symbol_type,
                    symbol_name,
                    signature,
                    qualified_name,
                    f"has_body={'yes' if has_body else 'no'}",
                ]
            )
        )


def _render_candidate_shortlist(candidates: list[_VectorMatch], query: str) -> None:
    """Render a bounded shortlist of ranked vector candidates."""
    if not candidates:
        return
    print(f"# shortlist for: {query}")
    print(
        "# confidence\tline\tname\ttype\tbody\tdocstring\traw\tmetadata"
    )
    for candidate in candidates[:5]:
        print(
            "\t".join(
                [
                    f"{candidate.confidence:3}",
                    f"{candidate.line_num:6}",
                    candidate.signature or candidate.preview or "",
                    candidate.symbol_type or "symbol",
                    "yes" if candidate.has_body else "no",
                    "yes" if candidate.has_docstring else "no",
                    f"{candidate.raw_score:.3f}",
                    f"{candidate.metadata_score:.3f}",
                ]
            )
        )


def _render_candidate_body(candidate: _VectorMatch) -> None:
    """Render an indexed symbol body when confidence clears the body-first threshold."""
    if not candidate.body:
        return
    print("# body")
    print(candidate.body.rstrip())


def candidate_body_helper(candidates: list[_VectorMatch], index: int) -> str | None:
    """Return a non-top shortlist candidate body through a bounded lookup."""
    if index < 0 or index >= len(candidates):
        return None
    candidate = candidates[index]
    if not candidate.body:
        return None
    return candidate.body


def _select_vector_candidate(candidates: list[_VectorMatch], index: int) -> tuple[_VectorMatch | None, str | None]:
    """Select a ranked candidate index while returning actionable selection errors."""
    if index < 0:
        return None, f"candidate index must be >= 0: {index}"
    if not candidates:
        if index == 0:
            return None, None
        return None, "no ranked candidates available for requested candidate index"
    if index >= len(candidates):
        return None, f"candidate index {index} is out of range (available: 0..{len(candidates) - 1})"
    return candidates[index], None


def _select_semantic_anchor_candidate(
    candidates: list[_VectorMatch],
    index: int,
) -> tuple[_VectorMatch | None, str | None]:
    """Select the first strong semantic anchor from the requested index onward."""
    selected, error = _select_vector_candidate(candidates, index)
    if error is not None:
        return None, error
    if selected is None:
        return None, None
    if selected.confidence >= READ_CODE_SEMANTIC_MIN_CONFIDENCE:
        return selected, None

    for next_index in range(index + 1, len(candidates)):
        next_candidate = candidates[next_index]
        if next_candidate.confidence >= READ_CODE_SEMANTIC_MIN_CONFIDENCE:
            print(
                (
                    "WARN: Semantic candidate "
                    f"{index} confidence {selected.confidence} is below threshold "
                    f"{READ_CODE_SEMANTIC_MIN_CONFIDENCE}/100; using candidate {next_index} "
                    f"confidence {next_candidate.confidence}."
                ),
                file=sys.stderr,
            )
            return next_candidate, None

    _set_vector_runtime_note(
        f"semantic candidates below confidence threshold {READ_CODE_SEMANTIC_MIN_CONFIDENCE}/100"
    )
    return None, None


def _emit_strict_resolution_failure(pattern: str, strict_status: int) -> None:
    """Emit deterministic strict-resolution failure messaging."""
    if strict_status == 2:
        print(
            "ERROR: Symbol resolution ambiguous; re-run with --allow-fallback to allow bounded file-local fallback.",
            file=sys.stderr,
        )
        return
    print(
        f"ERROR: Strict symbol resolution failed for '{pattern}'. Re-run with --allow-fallback to allow bounded file-local fallback.",
        file=sys.stderr,
    )


def _query_semantic_anchor_candidate(
    file_path: Path,
    pattern: str,
    normalized_pattern: str,
    *,
    candidate_index: int,
    show_shortlist_hint: bool,
) -> tuple[list[_VectorMatch], _VectorMatch | None, bool]:
    """Query ranked candidates and select a semantic anchor with standardized error handling."""
    vector_candidates = _vector_find_candidates(file_path, pattern, normalized_pattern, "code")
    vector_match, candidate_error = _select_semantic_anchor_candidate(vector_candidates, candidate_index)
    if candidate_error is not None:
        print(f"ERROR: {candidate_error}", file=sys.stderr)
        if show_shortlist_hint and vector_candidates:
            print("Hint: re-run with --show-shortlist to inspect ranked candidates.", file=sys.stderr)
        return vector_candidates, None, False
    return vector_candidates, vector_match, True


def _resolve_pattern_anchor(
    file_path: Path,
    pattern: str,
    normalized_pattern: str,
    *,
    candidate_index: int,
    allow_fallback: bool,
    show_shortlist_hint: bool,
) -> _AnchorResolution | None:
    """Resolve pattern anchor via semantic-first and strict fallback flow."""
    vector_candidates, vector_match, selection_ok = _query_semantic_anchor_candidate(
        file_path,
        pattern,
        normalized_pattern,
        candidate_index=candidate_index,
        show_shortlist_hint=show_shortlist_hint,
    )
    if not selection_ok:
        return None

    strict_status = 1
    strict_line_num: int | None = None
    line_num: int | None = None
    if vector_match is not None:
        line_num = vector_match.line_num
    else:
        strict_status, strict_line_num = _resolve_line_num_strict(file_path, pattern, normalized_pattern)
        if strict_status == 0:
            line_num = strict_line_num
        elif allow_fallback:
            line_num = _find_line_num(file_path, pattern, normalized_pattern)

    if line_num is None and strict_status != 0:
        if codegraph_supports_file(file_path):
            discover_pattern = (
                normalized_pattern
                if normalized_pattern and normalized_pattern != pattern
                else pattern
            )
            if not codegraph_discover_or_fail(
                discover_pattern,
                file_path.parent,
                skip_preflight_refresh=True,
            ):
                return None

        refreshed_candidates, refreshed_match, selection_ok = _query_semantic_anchor_candidate(
            file_path,
            pattern,
            normalized_pattern,
            candidate_index=candidate_index,
            show_shortlist_hint=show_shortlist_hint,
        )
        if not selection_ok:
            return None
        if refreshed_candidates:
            vector_candidates = refreshed_candidates
            vector_match = refreshed_match
            if vector_match is not None:
                line_num = vector_match.line_num

        if line_num is None:
            strict_status, strict_line_num = _resolve_line_num_strict(file_path, pattern, normalized_pattern)
            if strict_status == 0:
                line_num = strict_line_num
            elif allow_fallback:
                line_num = _find_line_num(file_path, pattern, normalized_pattern)

    if line_num is not None and not vector_candidates:
        vector_candidates, vector_match, selection_ok = _query_semantic_anchor_candidate(
            file_path,
            pattern,
            normalized_pattern,
            candidate_index=candidate_index,
            show_shortlist_hint=show_shortlist_hint,
        )
        if not selection_ok:
            return None

    _emit_vector_fallback_notice(
        file_path=file_path,
        pattern=pattern,
        vector_match=vector_match,
        resolved_line=line_num,
    )
    return _AnchorResolution(
        vector_candidates=vector_candidates,
        vector_match=vector_match,
        strict_status=strict_status,
        line_num=line_num,
    )


def _validate_file_and_positive_int(
    file_arg: str,
    value_raw: str,
    *,
    value_label: str,
) -> tuple[Path, int] | None:
    """Validate an existing file path plus a positive integer argument."""
    file_path = Path(file_arg)
    if not file_path.is_file():
        print(f"ERROR: File not found: {file_arg}", file=sys.stderr)
        return None
    if not value_raw.isdigit() or int(value_raw, 10) <= 0:
        print(f"ERROR: {value_label} must be a positive integer: {value_raw}", file=sys.stderr)
        return None
    return file_path, int(value_raw, 10)


def _parse_context_args(argv: list[str]) -> _ContextArgs | None:
    """Parse and validate read_code_context arguments."""
    if len(argv) < 2:
        print(
            "ERROR: read_code_context requires: <file_path> <symbol_or_pattern> [context_lines]",
            file=sys.stderr,
        )
        return None

    file_arg = argv[0]
    pattern = argv[1]
    extra = argv[2:]

    context = READ_CODE_DEFAULT_CONTEXT_LINES
    context_set = False
    allow_fallback = False
    show_shortlist = False
    inline_body = False
    candidate_index = 0
    expect_candidate_index = False

    for token in extra:
        if expect_candidate_index:
            if not token.isdigit():
                print(f"ERROR: --candidate-index expects a non-negative integer: {token}", file=sys.stderr)
                return None
            candidate_index = int(token, 10)
            expect_candidate_index = False
        elif token == "--hud-symbol":
            continue
        elif token == "--allow-fallback":
            allow_fallback = True
        elif token == "--show-shortlist":
            show_shortlist = True
        elif token == "--inline-body":
            inline_body = True
        elif token == "--next-candidate":
            candidate_index += 1
        elif token == "--candidate-index":
            expect_candidate_index = True
        elif token.startswith("--candidate-index="):
            _, _, value = token.partition("=")
            if not value.isdigit():
                print(f"ERROR: --candidate-index expects a non-negative integer: {value}", file=sys.stderr)
                return None
            candidate_index = int(value, 10)
        elif token.isdigit() and not context_set:
            context = int(token, 10)
            context_set = True
        else:
            print(f"ERROR: Unexpected argument for context mode: {token}", file=sys.stderr)
            return None
    if expect_candidate_index:
        print("ERROR: --candidate-index requires a value", file=sys.stderr)
        return None

    validated = _validate_file_and_positive_int(file_arg, str(context), value_label="context_lines")
    if validated is None:
        return None
    file_path, context_value = validated
    if context_value > READ_CODE_MAX_LINES:
        print(f"ERROR: context_lines exceeds max ({READ_CODE_MAX_LINES}): {context_value}", file=sys.stderr)
        return None

    return _ContextArgs(
        file_path=file_path,
        pattern=pattern,
        context=context_value,
        allow_fallback=allow_fallback,
        show_shortlist=show_shortlist,
        inline_body=inline_body,
        candidate_index=candidate_index,
    )


def _parse_window_args(argv: list[str]) -> _WindowArgs | None:
    """Parse and validate read_code_window arguments."""
    if len(argv) < 2:
        print(
            "ERROR: read_code_window requires: <file_path> <start_line> [line_count]",
            file=sys.stderr,
        )
        return None

    file_arg = argv[0]
    start_line_raw = argv[1]
    extra = argv[2:]

    line_count = READ_CODE_DEFAULT_WINDOW_LINES
    line_count_set = False
    pattern = ""
    hud_flag = False
    allow_fallback = False

    for token in extra:
        if token == "--hud-symbol":
            hud_flag = True
        elif token == "--allow-fallback":
            allow_fallback = True
        elif token.isdigit() and not line_count_set:
            line_count = int(token, 10)
            line_count_set = True
        elif not pattern:
            pattern = token
        else:
            print(f"ERROR: Unexpected argument for window mode: {token}", file=sys.stderr)
            return None

    validated = _validate_file_and_positive_int(file_arg, start_line_raw, value_label="start_line")
    if validated is None:
        return None
    file_path, start_line = validated

    line_count_raw = str(line_count)
    if not line_count_raw.isdigit() or int(line_count_raw, 10) <= 0:
        print(f"ERROR: line_count must be a positive integer: {line_count}", file=sys.stderr)
        return None
    line_count_value = int(line_count_raw, 10)
    if line_count_value > READ_CODE_MAX_LINES:
        print(f"ERROR: line_count exceeds max ({READ_CODE_MAX_LINES}): {line_count_value}", file=sys.stderr)
        return None

    return _WindowArgs(
        file_path=file_path,
        start_line=start_line,
        line_count=line_count_value,
        pattern=pattern,
        use_hud_fast_path=hud_flag,
        allow_fallback=allow_fallback,
    )


def _render_resolution_extras(
    pattern: str,
    vector_candidates: list[_VectorMatch],
    vector_match: _VectorMatch | None,
    *,
    show_shortlist: bool,
    inline_body: bool,
) -> None:
    """Render optional shortlist/body output after anchor resolution."""
    if vector_candidates and show_shortlist:
        _render_candidate_shortlist(vector_candidates, pattern)
    if inline_body and vector_match is not None and vector_match.confidence >= 90:
        _render_candidate_body(vector_match)


def read_code_symbols(argv: list[str]) -> int:
    """Debug-only symbol dump for maintenance and break-glass investigation."""
    if not _symbol_dump_enabled():
        print(
            "ERROR: read_code_symbols is disabled by policy. Use semantic anchor reads via "
            "`read_code_context`/`read_code_window`. Break-glass override: "
            f"set {READ_CODE_ALLOW_SYMBOL_DUMP_ENV}=1 for maintenance/debug only.",
            file=sys.stderr,
        )
        return 1
    if len(argv) < 1:
        print("ERROR: read_code_symbols requires: <file_path>", file=sys.stderr)
        return 1
    for token in argv[1:]:
        print(f"ERROR: Unexpected argument(s) for symbols mode: {token}", file=sys.stderr)
        return 1

    file_path = Path(argv[0])
    if not file_path.is_file():
        print(f"ERROR: File not found: {argv[0]}", file=sys.stderr)
        return 1
    if not _refresh_indexes_for_read(file_path):
        return 1

    symbols = _vector_list_code_symbols(file_path)
    runtime_note = _consume_vector_runtime_note()
    if not symbols:
        if runtime_note:
            print(f"ERROR: Could not list file symbols: {runtime_note}", file=sys.stderr)
        else:
            print(f"ERROR: No code symbols found for {file_path}", file=sys.stderr)
        return 1

    print(
        "# line_start\tline_end\tsymbol_type\tsymbol_name\tsignature\tqualified_name\thas_body"
    )
    _render_symbol_listing(symbols)
    return 0


def read_code_context(argv: list[str]) -> int:
    """Resolve an anchor and print bounded context with post-anchor bias."""
    parsed = _parse_context_args(argv)
    if parsed is None:
        return 1

    if not _refresh_indexes_for_read(parsed.file_path):
        return 1
    normalized_pattern = normalize_symbol_pattern(parsed.pattern)
    resolution = _resolve_pattern_anchor(
        parsed.file_path,
        parsed.pattern,
        normalized_pattern,
        candidate_index=parsed.candidate_index,
        allow_fallback=parsed.allow_fallback,
        show_shortlist_hint=True,
    )
    if resolution is None:
        return 1
    vector_candidates = resolution.vector_candidates
    vector_match = resolution.vector_match
    strict_status = resolution.strict_status
    line_num = resolution.line_num

    if line_num is None:
        _emit_strict_resolution_failure(parsed.pattern, strict_status)
        return 1

    _render_resolution_extras(
        parsed.pattern,
        vector_candidates,
        vector_match,
        show_shortlist=parsed.show_shortlist,
        inline_body=parsed.inline_body,
    )

    pre_lines, post_lines = _split_context_window(parsed.context)
    start = max(1, line_num - pre_lines)
    end = line_num + post_lines
    _render_numbered_window(parsed.file_path, start, end)
    return 0


def read_code_window(argv: list[str]) -> int:
    """Print a numbered bounded window and ignore out-of-window semantic anchors."""
    parsed = _parse_window_args(argv)
    if parsed is None:
        return 1

    if parsed.pattern:
        if not _refresh_indexes_for_read(parsed.file_path):
            return 1
        normalized_pattern = normalize_symbol_pattern(parsed.pattern)
        resolution = _resolve_pattern_anchor(
            parsed.file_path,
            parsed.pattern,
            normalized_pattern,
            candidate_index=0,
            allow_fallback=parsed.allow_fallback,
            show_shortlist_hint=False,
        )
        if resolution is None:
            return 1
        strict_status = resolution.strict_status
        line_num = resolution.line_num

        if line_num is None:
            _emit_strict_resolution_failure(parsed.pattern, strict_status)
            return 1

    elif is_large_code_file(parsed.file_path) and not parsed.use_hud_fast_path:
        print(
            f"ERROR: symbol_or_pattern is required for files >{CODE_FILE_LINE_THRESHOLD} lines unless using HUD current-line fast-path.",
            file=sys.stderr,
        )
        print(
            "Usage: read_code_window <file> <start_line> [line_count] <symbol_or_pattern>",
            file=sys.stderr,
        )
        return 1

    end_line = parsed.start_line + parsed.line_count - 1
    _render_numbered_window(parsed.file_path, parsed.start_line, end_line)
    return 0


def _print_usage() -> None:
    print("Usage:")
    print(
        f"  read_code_context <file_path> <symbol_or_pattern> [context_lines<={READ_CODE_MAX_LINES}] [--hud-symbol] [--allow-fallback] [--show-shortlist] [--next-candidate] [--candidate-index N] [--inline-body]"
    )
    print(
        "                   (default output is resolved anchor + bounded window; semantic anchors are preferred at confidence >= "
        f"{READ_CODE_SEMANTIC_MIN_CONFIDENCE}/100 before strict fallback; semantic query is file-scoped first; shortlist is opt-in; context budget is small-before/larger-after; body is opt-in via --inline-body at confidence >= 90/100)"
    )
    print(
        f"  read_code_window  <file_path> <start_line> [line_count<={READ_CODE_MAX_LINES}] [symbol_or_pattern] [--hud-symbol] [--allow-fallback]"
    )
    print(
        "                   (when symbol_or_pattern is supplied, out-of-window anchors are treated as advisory; the requested window is returned unchanged)"
    )


def main(argv: list[str]) -> int:
    """CLI entrypoint compatible with read-code.sh mode routing."""
    if len(argv) < 2:
        _print_usage()
        return 1

    mode = argv[0]
    args = argv[1:]
    if mode == "context":
        return read_code_context(args)
    if mode == "window":
        return read_code_window(args)
    if mode == "symbols":
        print(
            "ERROR: symbols mode is debug-only. Use scripts/read_code_debug.py <file_path> "
            f"with {READ_CODE_ALLOW_SYMBOL_DUMP_ENV}=1 for maintenance/debug.",
            file=sys.stderr,
        )
        return 1
    if mode == "codegraph-preflight-worker":
        return run_codegraph_preflight_worker(args)

    print(f"ERROR: Unknown mode '{mode}'. Use: context | window", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
