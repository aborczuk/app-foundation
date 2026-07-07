#!/usr/bin/env python3
"""Refresh the full repository CodeGraph index after owner release."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import cgc_owner
from cgc_safe_index import run_index


def _repo_root() -> Path:
    """Return the repository root inferred from this script location."""
    return Path(__file__).resolve().parents[1]


def _prepare_environment(repo_root: Path) -> None:
    """Populate the environment expected by the CodeGraph CLI."""
    codegraph_context_dir = repo_root / ".codegraphcontext"
    codegraph_db_dir = codegraph_context_dir / "db"
    repo_uv_cache = Path(os.environ.get("CGC_UV_CACHE_DIR", str(codegraph_context_dir / ".uv-cache")))
    codegraph_db_dir.mkdir(parents=True, exist_ok=True)
    repo_uv_cache.mkdir(parents=True, exist_ok=True)

    # Force child indexing work onto the target repo's own CodeGraph state.
    os.environ["UV_CACHE_DIR"] = str(repo_uv_cache)
    os.environ["DEFAULT_DATABASE"] = "kuzudb"
    os.environ["FALKORDB_PATH"] = str(codegraph_db_dir / "falkordb")
    os.environ["FALKORDB_SOCKET_PATH"] = str(codegraph_db_dir / "falkordb.sock")
    os.environ["KUZUDB_PATH"] = str(codegraph_db_dir / "kuzudb")
    os.environ["IGNORE_DIRS"] = os.environ.get(
        "IGNORE_DIRS",
        "node_modules,venv,.venv,env,.env,dist,build,target,out,.git,.idea,.vscode,__pycache__,.uv-cache,logs,shadow-runs",
    )
    os.environ["CODEGRAPH_CONTEXT_DIR"] = str(codegraph_context_dir)
    os.environ["CODEGRAPH_DB_DIR"] = str(codegraph_db_dir)


def main(argv: list[str]) -> int:
    """Run a full-repo refresh after ensuring no owner is active."""
    repo_root = _repo_root()
    _prepare_environment(repo_root)

    print(f"Indexing CodeGraphContext for: {repo_root}")
    print(f"DEFAULT_DATABASE={os.environ['DEFAULT_DATABASE']}")
    print(f"KUZUDB_PATH={os.environ['KUZUDB_PATH']}")
    print(f"IGNORE_DIRS={os.environ['IGNORE_DIRS']}")

    if os.environ.get("CGC_ALLOW_REPO_INDEX", "0") != "1":
        print("Refusing full-repo index without explicit opt-in.", file=sys.stderr)
        print("Set CGC_ALLOW_REPO_INDEX=1 when you intentionally want a full-repo rebuild.", file=sys.stderr)
        return 1

    wait_status = cgc_owner.wait_for_release()
    if wait_status != 0:
        return wait_status

    os.environ["CGC_ALLOW_REPO_INDEX"] = "1"
    return run_index(str(repo_root))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
