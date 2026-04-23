#!/usr/bin/env python3
"""PostToolUse hook: refresh CodeGraphContext and vector index after edits.

This script is invoked with a JSON payload on stdin after tool edits.
It extracts changed repo-local paths, refreshes codegraph for each path,
and refreshes the vector index for supported markdown/code files.
Refresh failures are fatal so the edit handoff never proceeds with stale
or missing discovery state.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.mcp_codebase.index.config import (  # noqa: E402
    DEFAULT_EMBEDDING_CACHE_DIR,
    DEFAULT_EMBEDDING_MODEL_NAME,
)

VECTOR_SUFFIXES = {".py", ".pyi", ".md", ".markdown", ".mdown", ".sh", ".bash", ".zsh"}
EMBEDDING_AVAILABILITY_CACHE_VERSION = 1


def _repo_root() -> Path:
    """Return the repository root for the current checkout."""
    return Path(__file__).resolve().parents[1]


def _repo_uv_cache_dir(root: Path) -> Path:
    """Return the repository-local uv cache directory used by refresh subprocesses."""
    return root / ".codegraphcontext" / ".uv-cache"


def _refresh_env(*, root: Path, env_overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Build a subprocess env that prefers repo-local uv cache for sandbox-safe execution."""
    env = os.environ.copy()
    if not env.get("UV_CACHE_DIR"):
        cache_dir = _repo_uv_cache_dir(root)
        cache_dir.mkdir(parents=True, exist_ok=True)
        env["UV_CACHE_DIR"] = str(cache_dir)
    if env_overrides:
        env.update(env_overrides)
    return env


def _emit_error(message: str) -> None:
    """Emit a blocking refresh error to stderr."""
    print(f"ERROR: {message}", file=sys.stderr)


def _collect_changed_paths(payload: dict) -> list[Path]:
    """Accept hook payloads with `file_path`, `path`, `file_paths`, or `paths` keys."""
    tool_input = payload.get("tool_input") or {}
    candidates: list[str] = []

    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())

    for key in ("file_paths", "paths"):
        value = tool_input.get(key)
        if isinstance(value, list):
            candidates.extend(item.strip() for item in value if isinstance(item, str) and item.strip())

    root = _repo_root()
    resolved: set[Path] = set()
    for raw in candidates:
        path = Path(raw)
        if not path.is_absolute():
            path = (root / path).resolve()
        else:
            path = path.resolve()

        try:
            path.relative_to(root)
        except ValueError:
            continue

        if path.exists():
            resolved.add(path)

    return sorted(resolved)


def _run_refresh(command: list[str], label: str, *, env_overrides: dict[str, str] | None = None) -> str | None:
    """Run a refresh command and return an error message on failure."""
    env = _refresh_env(root=_repo_root(), env_overrides=env_overrides)
    proc = subprocess.run(command, capture_output=True, text=True, env=env)
    if proc.returncode == 0:
        return None

    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()
    details = stderr or stdout or f"exit code {proc.returncode}"
    return f"{label} refresh failed: {details}"


def _refresh_codegraph(paths: Iterable[Path]) -> list[str]:
    """Refresh codegraph path-by-path through the safe wrapper."""
    script = _repo_root() / "scripts" / "cgc_safe_index.sh"
    failures: list[str] = []
    for path in paths:
        error = _run_refresh(["bash", str(script), str(path)], f"codegraph {path}")
        if error:
            failures.append(error)
    return failures


def _embedding_model_cache_dir(root: Path) -> Path:
    """Return the repo-local cache directory used for fastembed models."""
    return root / DEFAULT_EMBEDDING_CACHE_DIR


def _embedding_model_availability_cache_path(root: Path) -> Path:
    """Return the cache file for offline embedding availability checks."""
    return _repo_uv_cache_dir(root) / "hook-refresh" / "embedding-model-availability.json"


def _embedding_model_cache_signature(root: Path) -> tuple[bool, int | None]:
    """Fingerprint the embedding cache directory so stale memoized results expire."""
    cache_dir = _embedding_model_cache_dir(root)
    if not cache_dir.exists():
        return False, None
    return True, cache_dir.stat().st_mtime_ns


def _embedding_model_available_offline(root: Path) -> tuple[bool, str]:
    """Probe whether the embedding model can be loaded in offline mode."""
    command = [
        "uv",
        "run",
        "--no-sync",
        "python",
        "-m",
        "src.mcp_codebase.indexer",
        "--repo-root",
        str(root),
        "bootstrap",
        "--skip-build",
    ]
    env = _refresh_env(root=root, env_overrides={"HF_HUB_OFFLINE": "1"})
    proc = subprocess.run(command, capture_output=True, text=True, env=env)
    if proc.returncode == 0:
        return True, ""

    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()
    details = stderr or stdout or f"exit code {proc.returncode}"
    return False, details


def _read_cached_embedding_model_availability(root: Path) -> tuple[bool, str] | None:
    """Return a cached availability result when the embedding cache state matches."""
    cache_path = _embedding_model_availability_cache_path(root)
    if not cache_path.exists():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("version") != EMBEDDING_AVAILABILITY_CACHE_VERSION:
        return None
    if payload.get("model_name") != DEFAULT_EMBEDDING_MODEL_NAME:
        return None

    cache_exists, cache_mtime_ns = _embedding_model_cache_signature(root)
    if payload.get("cache_dir_exists") != cache_exists:
        return None
    if payload.get("cache_dir_mtime_ns") != cache_mtime_ns:
        return None

    available = payload.get("available")
    details = payload.get("details", "")
    if not isinstance(available, bool):
        return None
    if not isinstance(details, str):
        details = ""
    return available, details


def _write_cached_embedding_model_availability(root: Path, *, available: bool, details: str) -> None:
    """Persist the latest availability check for reuse across edit-refresh invocations."""
    cache_path = _embedding_model_availability_cache_path(root)
    cache_exists, cache_mtime_ns = _embedding_model_cache_signature(root)
    payload = {
        "version": EMBEDDING_AVAILABILITY_CACHE_VERSION,
        "model_name": DEFAULT_EMBEDDING_MODEL_NAME,
        "cache_dir_exists": cache_exists,
        "cache_dir_mtime_ns": cache_mtime_ns,
        "available": available,
        "details": details,
    }

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        # Refreshing the cache should never block the actual refresh path.
        return


def _resolve_embedding_model_availability(root: Path) -> tuple[bool, str]:
    """Return a memoized embedding-model availability result when the cache is fresh."""
    cached = _read_cached_embedding_model_availability(root)
    if cached is not None:
        return cached

    available, details = _embedding_model_available_offline(root)
    _write_cached_embedding_model_availability(root, available=available, details=details)
    return available, details


def _refresh_vector(paths: Iterable[Path]) -> list[str]:
    """Refresh vector embeddings only for file types the indexer can ingest."""
    vector_paths = [path for path in paths if path.suffix.lower() in VECTOR_SUFFIXES]
    if not vector_paths:
        return []

    root = _repo_root()
    cache_dir = _embedding_model_cache_dir(root)
    model_available, availability_details = _resolve_embedding_model_availability(root)
    if not model_available:
        return [
            "vector index refresh blocked: embedding model cache for "
            f"{DEFAULT_EMBEDDING_MODEL_NAME} is not available offline at {cache_dir} "
            f"({availability_details}); "
            "run `uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . bootstrap` first"
        ]

    command = [
        "uv",
        "run",
        "--no-sync",
        "python",
        "-m",
        "src.mcp_codebase.indexer",
        "--repo-root",
        str(root),
        "refresh",
        *[str(path) for path in vector_paths],
    ]
    error = _run_refresh(command, "vector index", env_overrides={"HF_HUB_OFFLINE": "1"})
    return [error] if error else []


def main() -> int:
    """Consume the hook payload and fan out to codegraph/vector refreshes."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    # Non-JSON payloads are ignored so the hook stays non-blocking in callers.
    changed_paths = _collect_changed_paths(payload)
    if not changed_paths:
        return 0

    # Codegraph refresh runs for every changed path; vector refresh runs for supported text/code files.
    failures = _refresh_codegraph(changed_paths)
    failures.extend(_refresh_vector(changed_paths))
    if failures:
        for failure in failures:
            _emit_error(failure)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
