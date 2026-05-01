#!/usr/bin/env python3
"""General session bootstrap for Codex-facing repo workflows."""

# ruff: noqa: E402, I001

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WARM_SCOPES = ("scripts", "src", "tests", "specs")

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from read_code_health import codegraph_health_probe  # noqa: E402
from uv_env import repo_uv_env  # noqa: E402


def bootstrap_session(scope_path: Path | None = None) -> dict[str, Any]:
    """Pin the UV cache and warm the repo-local codegraph state."""
    env = repo_uv_env()
    os.environ.update(env)

    scope = scope_path or REPO_ROOT
    before = codegraph_health_probe(scope)
    refreshed = before.status == "healthy"
    warmed_scopes: list[str] = []
    safe_index = SCRIPT_DIR / "cgc_safe_index.py"
    if safe_index.is_file():
        for relative_scope in WARM_SCOPES:
            scope_dir = REPO_ROOT / relative_scope
            if not scope_dir.is_dir():
                continue
            proc = subprocess.run(
                [sys.executable, str(safe_index), str(scope_dir)],
                cwd=REPO_ROOT,
                env=os.environ.copy(),
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                warmed_scopes.append(relative_scope)
                refreshed = True
                continue
            refreshed = False
    after = codegraph_health_probe(scope)

    return {
        "uv_cache_dir": env["UV_CACHE_DIR"],
        "scope_path": str(scope),
        "codegraph_before": before.status,
        "codegraph_after": after.status,
        "codegraph_detail": after.detail or before.detail,
        "codegraph_refreshed": refreshed,
        "warmed_scopes": warmed_scopes,
        "bootstrap_ok": refreshed and after.status in {"healthy", "stale", "locked"},
    }


def main(argv: list[str]) -> int:
    """Run the session bootstrap and report the resulting state."""
    parser = argparse.ArgumentParser(description="Bootstrap Codex-facing repo workflow state")
    parser.add_argument(
        "--scope",
        default=str(REPO_ROOT),
        help="Scope path to warm with codegraph preflight (default: repo root).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON summary")
    args = parser.parse_args(argv)

    summary = bootstrap_session(Path(args.scope).expanduser())
    if not summary["bootstrap_ok"]:
        message = summary["codegraph_detail"] or "codegraph bootstrap failed"
        print(f"ERROR: {message}", file=sys.stderr)
        if args.json:
            print(json.dumps(summary, separators=(",", ":")))
        return 1

    if args.json:
        print(json.dumps(summary, separators=(",", ":")))
        return 0

    print(f"UV_CACHE_DIR={summary['uv_cache_dir']}")
    print(f"CODEGRAPH_BEFORE={summary['codegraph_before']}")
    print(f"CODEGRAPH_AFTER={summary['codegraph_after']}")
    print(f"CODEGRAPH_REFRESHED={summary['codegraph_refreshed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
