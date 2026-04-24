"""Shared helpers for deterministic repo-local UV cache configuration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_UV_CACHE_DIR = REPO_ROOT / ".codegraphcontext" / ".uv-cache"


def repo_uv_cache_dir(env: Mapping[str, str] | None = None) -> Path:
    """Return the repo-local UV cache directory, creating it on demand."""
    source = env or os.environ
    cache_dir = Path(source.get("UV_CACHE_DIR", str(DEFAULT_UV_CACHE_DIR))).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def repo_uv_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a copy of env with UV_CACHE_DIR pinned to the repo-local cache."""
    merged = dict(os.environ if env is None else env)
    merged["UV_CACHE_DIR"] = str(repo_uv_cache_dir(merged))
    return merged
