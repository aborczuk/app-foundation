#!/usr/bin/env python3
"""Canonical tasking finalizer with a compatibility implementation underneath."""

from __future__ import annotations

import sys

from speckit_solution_step import main as _legacy_main


def main(argv: list[str] | None = None) -> int:
    """Run the shared tasking finalizer while defaulting completion to tasking."""
    args = list(argv) if argv is not None else sys.argv[1:]
    if args and args[0] == "prepare-tasking":
        return _legacy_main(args)
    if "--phase" not in args:
        args.extend(["--phase", "tasking"])
    return _legacy_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
