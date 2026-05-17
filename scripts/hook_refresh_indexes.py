#!/usr/bin/env python3
"""PostToolUse hook: refresh CodeGraphContext and vector index after edits.

This script is invoked with a JSON payload on stdin after tool edits.
It extracts changed repo-local paths, refreshes codegraph for the smallest
covering set of targets, and refreshes the vector index for supported
markdown/code files.
Refresh failures are fatal so the edit handoff never proceeds with stale
or missing discovery state.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:  # noqa: E402
    from src.mcp_codebase.index.config import (
        DEFAULT_EMBEDDING_CACHE_DIR,
        DEFAULT_EMBEDDING_MODEL_NAME,
    )
except ModuleNotFoundError as exc:  # pragma: no cover - exercised by import-isolation test
    if exc.name != "pydantic":
        raise
    # Keep the post-commit refresh hook runnable in the host git environment even when
    # repo-only Python deps are unavailable there. The hook only needs these two constants.
    DEFAULT_EMBEDDING_CACHE_DIR = Path(".codegraphcontext/global/db/vector-index/fastembed-cache")
    DEFAULT_EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

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


def _codegraph_refresh_targets(paths: Iterable[Path]) -> list[Path]:
    """Collapse changed paths to the smallest covering set of codegraph targets."""
    root = _repo_root()
    targets: list[Path] = []
    seen: set[Path] = set()

    for path in paths:
        if not path.exists():
            continue
        target = path if path.is_dir() else path.parent
        if target == root:
            target = path
        try:
            target.relative_to(root)
        except ValueError:
            continue
        if target in seen:
            continue
        seen.add(target)

        # Prefer broader ancestors when they already cover an earlier target.
        if any(target.is_relative_to(existing) for existing in targets):
            continue
        targets = [existing for existing in targets if not existing.is_relative_to(target)]
        targets.append(target)

    return sorted(targets)


def _refresh_codegraph(paths: Iterable[Path]) -> list[str]:
    """Refresh codegraph using a batched, target-minimized safe wrapper."""
    script = _repo_root() / "scripts" / "cgc_safe_index.py"
    failures: list[str] = []
    for target in _codegraph_refresh_targets(paths):
        error = _run_refresh([sys.executable, str(script), str(target)], f"codegraph {target}")
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
    vector_paths = _vector_refresh_paths(paths)
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


def _vector_refresh_paths(paths: Iterable[Path]) -> list[Path]:
    """Return the subset of changed paths that the vector indexer can ingest."""
    return [path for path in paths if path.suffix.lower() in VECTOR_SUFFIXES]


def _refresh_flags(payload: dict) -> tuple[bool, bool]:
    """Return whether codegraph/vector refreshes are enabled for this request."""
    tool_input = payload.get("tool_input") or {}
    refresh_codegraph = tool_input.get("refresh_codegraph", True)
    refresh_vector = tool_input.get("refresh_vector", True)
    return bool(refresh_codegraph), bool(refresh_vector)


def _record_refresh_side_effects(*, paths: list[Path], refreshed_vector: bool) -> None:
    """Persist shared healthy-state side effects after a successful refresh request."""
    if not refreshed_vector or not _vector_refresh_paths(paths):
        return
    from scripts import read_code_health

    read_code_health._remember_healthy_vector_probe()


def run_refresh_request(payload: dict) -> list[str]:
    """Refresh codegraph/vector indexes for the request payload and return any failures."""
    changed_paths = _collect_changed_paths(payload)
    if not changed_paths:
        return []

    refresh_codegraph, refresh_vector = _refresh_flags(payload)
    failures: list[str] = []
    if refresh_codegraph:
        failures.extend(_refresh_codegraph(changed_paths))
    vector_failures: list[str] = []
    if refresh_vector:
        vector_failures = _refresh_vector(changed_paths)
        failures.extend(vector_failures)
    if not failures:
        _record_refresh_side_effects(paths=changed_paths, refreshed_vector=refresh_vector)
    return failures


def launch_refresh_request(payload: dict) -> bool:
    """Launch a detached refresh request through this hook script."""
    root = _repo_root()
    request_dir = _repo_uv_cache_dir(root) / "hook-refresh" / "requests"
    request_path = request_dir / f"request-{time.time_ns()}.json"
    try:
        request_dir.mkdir(parents=True, exist_ok=True)
        request_path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        return False

    cmd = [sys.executable, str(Path(__file__).resolve()), "--payload-file", str(request_path)]
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=_refresh_env(root=root),
        )
    except OSError:
        try:
            request_path.unlink()
        except OSError:
            pass
        return False
    return True


def main() -> int:
    """Consume the hook payload and fan out to codegraph/vector refreshes."""
    if len(sys.argv) == 3 and sys.argv[1] == "--payload-file":
        try:
            payload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        except Exception:
            return 0
        finally:
            try:
                Path(sys.argv[2]).unlink()
            except OSError:
                pass
    else:
        try:
            payload = json.load(sys.stdin)
        except Exception:
            return 0

    failures = run_refresh_request(payload)
    if not failures:
        return 0
    for failure in failures:
        _emit_error(failure)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
