#!/usr/bin/env python3
"""Run a scoped CodeGraph index while enforcing repository safety gates."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import cgc_owner

IGNORE_DIRS_DEFAULT = "node_modules,venv,.venv,env,.env,dist,build,target,out,.git,.idea,.vscode,__pycache__,.uv-cache,logs,shadow-runs"


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
    os.environ["IGNORE_DIRS"] = os.environ.get("IGNORE_DIRS", IGNORE_DIRS_DEFAULT)
    os.environ["CODEGRAPH_CONTEXT_DIR"] = str(codegraph_context_dir)
    os.environ["CODEGRAPH_DB_DIR"] = str(codegraph_db_dir)


def _is_repo_root_target(candidate: str, repo_root: Path) -> bool:
    """Return whether a target resolves to the repository root."""
    normalized = candidate.rstrip("/") or candidate
    if normalized in {".", "/", str(repo_root)}:
        return True
    path = Path(candidate)
    if path.exists() and path.is_dir():
        try:
            return path.resolve() == repo_root.resolve()
        except OSError:
            return False
    return False


def _usage() -> str:
    """Return the usage text for the safe index entrypoint."""
    return (
        "Usage:\n"
        "  scripts/cgc_safe_index.py [--force] <path>\n\n"
        "Examples:\n"
        "  scripts/cgc_safe_index.py src/clickup_control_plane\n"
        "  CGC_ALLOW_FORCE=1 scripts/cgc_safe_index.py --force src/clickup_control_plane\n"
        "  CGC_ALLOW_REPO_INDEX=1 scripts/cgc_safe_index.py .\n\n"
        "Safety:\n"
        "  - Full-repo indexing (target '.', '/', or repo root) is blocked by default.\n"
        "  - To allow non-force full-repo indexing intentionally, set CGC_ALLOW_REPO_INDEX=1.\n"
        "  - Forced indexing requires explicit opt-in: CGC_ALLOW_FORCE=1.\n"
        "  - Forced full-repo indexing is always blocked.\n"
    )


def run_index(target: str, *, force: bool = False) -> int:
    """Run a scoped CodeGraph index and return the exit status."""
    repo_root = _repo_root()
    _prepare_environment(repo_root)

    target_trimmed = target.rstrip("/") or target
    if force and _is_repo_root_target(target_trimmed, repo_root):
        print(f"Refusing unsafe full-repo force re-index: cgc index --force {target}", file=sys.stderr)
        print("Use a scoped path (example: scripts/cgc_safe_index.py --force src/clickup_control_plane).", file=sys.stderr)
        return 1

    if force and os.environ.get("CGC_ALLOW_FORCE", "0") != "1":
        print("Refusing forced index without explicit opt-in.", file=sys.stderr)
        print("Set CGC_ALLOW_FORCE=1 for a one-off scoped force re-index.", file=sys.stderr)
        return 1

    if not force and _is_repo_root_target(target_trimmed, repo_root) and os.environ.get("CGC_ALLOW_REPO_INDEX", "0") != "1":
        print(f"Refusing default full-repo index target: {target}", file=sys.stderr)
        print("Use a scoped target (recommended) or set CGC_ALLOW_REPO_INDEX=1 intentionally.", file=sys.stderr)
        return 1

    print(f"Running {'scoped force' if force else 'incremental'} index for: {target}")
    wait_status = cgc_owner.wait_for_release()
    if wait_status != 0:
        return wait_status

    cgc_owner.claim(command="scripts/cgc_safe_index.py")
    try:
        cmd = ["uv", "run", "--no-sync", "cgc", "index"]
        if force:
            cmd.append("--force")
        cmd.append(target)
        result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            cgc_owner.clear_last_error()
            cgc_owner.record_edit_signature(repo_root)
            return 0

        stderr_text = result.stderr.strip()
        if cgc_owner.error_is_memory_pressure(stderr_text):
            cgc_owner.record_last_error("memory-pressure", result.returncode, stderr_text)
            print(f"CodeGraph indexing failed due to memory pressure: {stderr_text}", file=sys.stderr)
        else:
            cgc_owner.clear_last_error()
            print(f"CodeGraph indexing failed: {stderr_text}", file=sys.stderr)
        return result.returncode
    finally:
        cgc_owner.release()


def main(argv: list[str]) -> int:
    """Parse CLI arguments and dispatch the safe index workflow."""
    if not argv or argv[0] in {"--help", "-h"}:
        print(_usage(), end="")
        return 0

    force = False
    args = list(argv)
    if args[0] == "--force":
        force = True
        args.pop(0)

    if args and args[0] in {"--help", "-h"}:
        print(_usage(), end="")
        return 0

    if len(args) != 1:
        print(_usage(), end="")
        return 2

    return run_index(args[0], force=force)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
