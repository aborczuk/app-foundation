#!/usr/bin/env python3
"""Explicit break-glass entrypoint for read_code_symbols maintenance use."""

# ruff: noqa: E402,I001

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from read_code import READ_CODE_ALLOW_SYMBOL_DUMP_ENV, read_code_symbols
from uv_env import repo_uv_env


def _print_usage() -> None:
    """Print the debug-only usage string."""
    print("Usage:")
    print(
        f"  read_code_debug.py <file_path> [--allow-repeat] (sets {READ_CODE_ALLOW_SYMBOL_DUMP_ENV}=1)"
    )
    print("                   (break-glass maintenance/debug only)")


def main(argv: Sequence[str] | None = None) -> int:
    """Enable the break-glass symbol-dump path and delegate to read_code_symbols."""
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        _print_usage()
        return 1

    os.environ.update(repo_uv_env())
    os.environ[READ_CODE_ALLOW_SYMBOL_DUMP_ENV] = "1"
    return read_code_symbols(args)


if __name__ == "__main__":
    raise SystemExit(main())
