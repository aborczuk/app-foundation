#!/usr/bin/env python3
"""Create the repo-local UV cache directory from Python."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UV_CACHE_DIR = REPO_ROOT / ".codegraphcontext" / ".uv-cache"


def _repo_uv_cache_dir() -> Path:
    """Create and return the repo-local UV cache directory."""
    cache_dir = Path(os.environ.get("UV_CACHE_DIR", str(DEFAULT_UV_CACHE_DIR))).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def main() -> int:
    """Create and report the repo-local UV cache directory."""
    cache_dir = _repo_uv_cache_dir()
    print(cache_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
