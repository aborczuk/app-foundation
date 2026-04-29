#!/usr/bin/env python3
"""Run the CodeGraph doctor entrypoint."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    """Return the repository root inferred from this script location."""
    return Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    """Execute the CodeGraph doctor module through uv."""
    repo_root = _repo_root()
    result = subprocess.run(
        ["uv", "run", "python", "-m", "src.mcp_codebase.doctor", *argv],
        cwd=repo_root,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
