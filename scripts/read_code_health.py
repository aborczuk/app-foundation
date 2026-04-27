#!/usr/bin/env python3
"""Health, preflight, and probe logic for read_code vector/codegraph dependencies."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = _SCRIPT_DIR.parent
CODEGRAPH_CONTEXT_DIR = REPO_ROOT / ".codegraphcontext"
CODEGRAPH_DB_DIR = CODEGRAPH_CONTEXT_DIR / "db"
VECTOR_DB_DIR = CODEGRAPH_CONTEXT_DIR / "global" / "db" / "vector-index"
VECTOR_BOOTSTRAP_COMMAND = "uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . bootstrap"

IGNORE_DIRS_DEFAULT = (
    "node_modules,venv,.venv,env,.env,dist,build,target,out,.git,.idea,.vscode,"
    "__pycache__,.uv-cache,logs,shadow-runs"
)
LAST_EDIT_SIGNATURE_FILE = CODEGRAPH_CONTEXT_DIR / "last-edit-signature.txt"
CODEGRAPH_LOCK_RETRY_ATTEMPTS = int(os.environ.get("SPECKIT_CODEGRAPH_LOCK_RETRY_ATTEMPTS", "2") or "2")
CODEGRAPH_LOCK_RETRY_SLEEP_SECONDS = float(
    os.environ.get("SPECKIT_CODEGRAPH_LOCK_RETRY_SLEEP_SECONDS", "0.5") or "0.5"
)
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


def _command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def _is_repo_local_path(file_path: Path) -> bool:
    """Return whether a target file resides under the repository root."""
    try:
        file_path.resolve().relative_to(REPO_ROOT)
        return True
    except ValueError:
        return False


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
    root = project_root or REPO_ROOT
    probe_status = codegraph_health_probe(root).status
    if probe_status != "healthy":
        return probe_status
    current = codegraph_current_edit_signature(root)
    cached = codegraph_cached_edit_signature(root)
    if current and cached and current != cached:
        print("marking codegraph stale: edit signature drift detected", file=sys.stderr)
        return "stale"
    if not cached and current:
        print("marking codegraph stale: no cached signature", file=sys.stderr)
        return "stale"
    return probe_status


def codegraph_health_probe(project_root: Path | None = None) -> _CodegraphHealthProbe:
    """Return codegraph health status plus detail and recovery hint command."""
    root = project_root or REPO_ROOT
    if not _command_exists("uv"):
        print("WARN: codegraph health probe skipped because uv is not available", file=sys.stderr)
        return _CodegraphHealthProbe(
            status="unavailable",
            detail="uv is not available",
            recovery_command=f"{_SCRIPT_DIR / 'cgc_safe_index.sh'} {root}",
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
            message=f"WARN: codegraph is stale; refreshing scoped index for {path}",
        )
        safe_index = _SCRIPT_DIR / "cgc_safe_index.sh"
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

    safe_index = _SCRIPT_DIR / "cgc_safe_index.sh"
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
                f"proceeding without blocking refresh; launching async scoped refresh for ({path})"
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
            except OSError:
                pass
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


def _launch_codegraph_preflight_background(file_path: Path, session_id: str) -> bool:
    """Launch one async codegraph preflight worker for the current session."""
    if not codegraph_supports_file(file_path):
        return False
    if not _mark_codegraph_preflight_launched(session_id):
        return False
    worker_cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
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
    safe_index = _SCRIPT_DIR / "cgc_safe_index.sh"
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


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv and argv[0] == "codegraph-preflight-worker":
        raise SystemExit(run_codegraph_preflight_worker(argv[1:]))
    print(f"ERROR: unknown mode: {argv[0] if argv else '(none)'}", file=sys.stderr)
    raise SystemExit(1)
