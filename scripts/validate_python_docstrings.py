#!/usr/bin/env python3
"""Validate that Python functions have docstrings, including private helpers."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def _iter_python_files(paths: list[str]) -> list[Path]:
    """Expand input paths into the Python files that should be validated."""
    files: list[Path] = []
    for raw_path in paths or ["."]:
        path = Path(raw_path)
        if path.is_dir():
            files.extend(sorted(candidate for candidate in path.rglob("*.py") if "__pycache__" not in candidate.parts))
        elif path.suffix == ".py" and path.exists():
            files.append(path)
    return files


def _docstring_failures(path: Path) -> list[str]:
    """Return docstring validation failures for a single Python file."""
    failures: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"{path}:{exc.lineno}:{exc.offset}: syntax_error:{exc.msg}"]

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if ast.get_docstring(node, clean=False):
            continue
        failures.append(f"{path}:{node.lineno}: missing_docstring:{node.name}")
    return failures


def main(argv: list[str]) -> int:
    """Validate docstrings for the supplied Python file paths."""
    failures: list[str] = []
    for path in _iter_python_files(argv):
        failures.extend(_docstring_failures(path))

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
