"""Shared runtime helpers for the local read-code reranker daemon."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

READ_CODE_RERANKER_DAEMON_START_TIMEOUT_SECONDS = float(
    os.environ.get("SPECKIT_READ_CODE_RERANKER_DAEMON_START_TIMEOUT_SECONDS", "15") or "15"
)
READ_CODE_RERANKER_DAEMON_HEALTH_TIMEOUT_SECONDS = float(
    os.environ.get("SPECKIT_READ_CODE_RERANKER_DAEMON_HEALTH_TIMEOUT_SECONDS", "1.5") or "1.5"
)
READ_CODE_RERANKER_DAEMON_FAILURE_COOLDOWN_SECONDS = float(
    os.environ.get("SPECKIT_READ_CODE_RERANKER_DAEMON_FAILURE_COOLDOWN_SECONDS", "10") or "10"
)
READ_CODE_RERANKER_DAEMON_HEALTH_POLL_INTERVAL_SECONDS = float(
    os.environ.get("SPECKIT_READ_CODE_RERANKER_DAEMON_HEALTH_POLL_INTERVAL_SECONDS", "0.1") or "0.1"
)


def _repo_runtime_slug(repo_root: Path) -> str:
    """Return the stable per-repo slug used for runtime and launchd isolation."""
    digest = hashlib.sha1(str(repo_root.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"{repo_root.resolve().name}-{digest}"


def reranker_runtime_root() -> Path:
    """Return the durable host-local root for reranker daemon runtime artifacts."""
    override = os.environ.get("SPECKIT_READ_CODE_RERANKER_RUNTIME_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / "Library" / "Caches" / "app-foundation" / "read-code-reranker").resolve()


def _path_can_create(path: Path) -> bool:
    """Return whether the current process can create entries under the nearest existing parent."""
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return probe.exists() and os.access(probe, os.W_OK | os.X_OK)


def reranker_runtime_dir(repo_root: Path) -> Path:
    """Return the durable per-repo runtime directory for the reranker daemon."""
    runtime_root = reranker_runtime_root()
    if _path_can_create(runtime_root):
        return runtime_root / _repo_runtime_slug(repo_root)
    return repo_root.resolve() / ".codegraphcontext" / "read-code-reranker-runtime" / _repo_runtime_slug(repo_root)


def reranker_shared_runtime_dir(repo_root: Path) -> Path:
    """Return the repo-local runtime directory shared across sandboxed and host processes."""
    return repo_root.resolve() / ".codegraphcontext" / "read-code-reranker-runtime" / _repo_runtime_slug(repo_root)


def reranker_socket_path(repo_root: Path) -> Path:
    """Return a short stable Unix socket path that stays under AF_UNIX length limits."""
    digest = hashlib.sha1(str(repo_root.resolve()).encode("utf-8")).hexdigest()[:16]
    return (Path("/private/tmp") / f"appf-rcd-{digest}.sock").resolve()


def reranker_pid_path(repo_root: Path) -> Path:
    """Return the PID marker path for the reranker daemon."""
    return reranker_runtime_dir(repo_root) / "daemon.pid"


def reranker_endpoint_path(repo_root: Path) -> Path:
    """Return the endpoint marker path for the active daemon transport."""
    return reranker_runtime_dir(repo_root) / "endpoint.json"


def reranker_startup_lock_path(repo_root: Path) -> Path:
    """Return the startup lock path for serialized daemon launches."""
    return reranker_runtime_dir(repo_root) / "startup.lock"


def reranker_failure_marker_path(repo_root: Path) -> Path:
    """Return the failure marker path for bounded restart cooldown tracking."""
    return reranker_runtime_dir(repo_root) / "startup-failure.json"


def reranker_log_path(repo_root: Path) -> Path:
    """Return the daemon log path used for detached startup diagnostics."""
    return reranker_runtime_dir(repo_root) / "daemon.log"


def reranker_build_fingerprint(repo_root: Path, model_name: str) -> str:
    """Return a bounded build fingerprint for daemon compatibility reporting."""
    digest = hashlib.sha1(
        f"{repo_root.resolve()}|{model_name}|{sys.version_info.major}.{sys.version_info.minor}".encode("utf-8")
    ).hexdigest()
    return digest[:16]


def reranker_tcp_port(repo_root: Path) -> int:
    """Return the deterministic loopback port used when UDS binds are unavailable."""
    digest = hashlib.sha1(str(repo_root.resolve()).encode("utf-8")).hexdigest()
    return 43000 + (int(digest[:4], 16) % 1000)


def reranker_launch_agents_dir() -> Path:
    """Return the user LaunchAgents directory used for managed daemon installs."""
    override = os.environ.get("SPECKIT_READ_CODE_RERANKER_LAUNCH_AGENTS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / "Library" / "LaunchAgents").resolve()


def reranker_launch_agent_label(repo_root: Path) -> str:
    """Return the stable per-repo launchd label for the managed reranker daemon."""
    digest = hashlib.sha1(str(repo_root.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"com.appfoundation.read-code-reranker.{digest}"


def reranker_launch_agent_path(repo_root: Path) -> Path:
    """Return the launchd plist path for the managed reranker daemon."""
    return reranker_launch_agents_dir() / f"{reranker_launch_agent_label(repo_root)}.plist"


def load_json_object(path: Path) -> dict[str, object] | None:
    """Load a JSON object from disk, returning None on missing or invalid payloads."""
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def persist_json_object(path: Path, payload: dict[str, object], *, sort_keys: bool = False) -> None:
    """Persist a JSON object without surfacing write errors to callers."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=sort_keys), encoding="utf-8")
    except OSError:
        return
