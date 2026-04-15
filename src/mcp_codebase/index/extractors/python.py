"""Python symbol extraction for the local vector index."""

from __future__ import annotations

import ast
import fnmatch
import hashlib
from pathlib import Path
from typing import Iterable, Sequence

from src.mcp_codebase.index.domain import CodeSymbol, IndexScope

_BUILTIN_EXCLUDE_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".codegraphcontext",
    ".speckit",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
_BUILTIN_EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".so", ".dylib", ".dll"}


def should_skip_path(
    file_path: str | Path,
    repo_root: str | Path,
    exclude_patterns: Sequence[str] = (),
) -> bool:
    """Return True when a local path should not be indexed."""

    resolved_root = Path(repo_root).expanduser().resolve()
    candidate = Path(file_path).expanduser()
    if not candidate.is_absolute():
        candidate = (resolved_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        rel_path = candidate.relative_to(resolved_root)
    except ValueError:
        return True

    rel_posix = rel_path.as_posix()
    if any(part in _BUILTIN_EXCLUDE_DIRS for part in rel_path.parts):
        return True
    if candidate.suffix in _BUILTIN_EXCLUDE_SUFFIXES:
        return True
    if rel_posix.startswith(("build/", "dist/", "generated/")):
        return True
    if candidate.name.startswith(("generated_", "tmp_", ".")):
        return True

    for pattern in exclude_patterns:
        normalized = pattern.strip()
        if not normalized:
            continue
        if fnmatch.fnmatch(rel_posix, normalized) or fnmatch.fnmatch(
            candidate.name, normalized
        ):
            return True

    return False


def extract_python_symbols(
    file_path: str | Path,
    *,
    repo_root: str | Path | None = None,
    exclude_patterns: Sequence[str] = (),
    source_text: str | None = None,
) -> list[CodeSymbol]:
    """Extract normalized Python symbols from a local source file."""

    repo_root = Path(repo_root or Path.cwd()).expanduser().resolve()
    candidate = Path(file_path)

    if should_skip_path(candidate, repo_root, exclude_patterns):
        return []

    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if candidate.suffix not in {".py", ".pyi"}:
        return []
    if not candidate.exists() or not candidate.is_file():
        return []

    source = source_text if source_text is not None else candidate.read_text(
        encoding="utf-8"
    )
    parsed = ast.parse(source, filename=str(candidate))
    symbols: list[CodeSymbol] = []

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._qualname_stack: list[str] = []

        def _push(self, name: str) -> None:
            self._qualname_stack.append(name)

        def _pop(self) -> None:
            self._qualname_stack.pop()

        def _record(self, node: ast.AST, *, name: str, scope: IndexScope) -> None:
            segment = ast.get_source_segment(source, node) or ""
            first_line = segment.splitlines()[0].strip() if segment else ""
            if not first_line:
                line_no = getattr(node, "lineno", 1) - 1
                source_lines = source.splitlines()
                first_line = source_lines[line_no].strip() if line_no < len(source_lines) else ""
            docstring = ast.get_docstring(node, clean=False) or ""
            qualname = ".".join((*self._qualname_stack, name)) if self._qualname_stack else name
            end_lineno = getattr(node, "end_lineno", getattr(node, "lineno", 1))
            symbols.append(
                CodeSymbol(
                    symbol_name=name,
                    qualified_name=qualname,
                    file_path=candidate,
                    line_start=getattr(node, "lineno", 1),
                    line_end=end_lineno,
                    signature=first_line or name,
                    docstring=docstring,
                    content_hash=hashlib.sha256(
                        (segment or first_line or name).encode("utf-8")
                    ).hexdigest(),
                    preview=(docstring.splitlines()[0].strip() if docstring else first_line or name),
                    scope=scope,
                )
            )

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            self._record(node, name=node.name, scope=IndexScope.CODE)
            self._push(node.name)
            try:
                self.generic_visit(node)
            finally:
                self._pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self._record(node, name=node.name, scope=IndexScope.CODE)
            self._push(node.name)
            try:
                self.generic_visit(node)
            finally:
                self._pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            self._record(node, name=node.name, scope=IndexScope.CODE)
            self._push(node.name)
            try:
                self.generic_visit(node)
            finally:
                self._pop()

    _Visitor().visit(parsed)
    return symbols
