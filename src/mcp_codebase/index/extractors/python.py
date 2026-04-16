"""Python symbol extraction for the local vector index."""

from __future__ import annotations

import ast
import fnmatch
import hashlib
from pathlib import Path
from typing import Iterable, Sequence

from src.mcp_codebase.index.domain import CodeSymbol, IndexScope

_BUILTIN_EXCLUDE_DIRS = {
    ".idea",
    ".git",
    ".uv-cache",
    ".vscode",
    ".env",
    "env",
    "logs",
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
    "out",
    "node_modules",
    "shadow-runs",
    "target",
    "venv",
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

        def _record(
            self,
            node: ast.AST,
            *,
            name: str,
            scope: IndexScope,
            symbol_type: str,
        ) -> None:
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
                    body=segment or "",
                    symbol_type=symbol_type,
                    content_hash=hashlib.sha256(
                        (segment or first_line or name).encode("utf-8")
                    ).hexdigest(),
                    preview=(docstring.splitlines()[0].strip() if docstring else first_line or name),
                    scope=scope,
                )
            )

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            self._record(
                node,
                name=node.name,
                scope=IndexScope.CODE,
                symbol_type="class",
            )
            self._push(node.name)
            try:
                self.generic_visit(node)
            finally:
                self._pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self._record(
                node,
                name=node.name,
                scope=IndexScope.CODE,
                symbol_type="function",
            )
            self._push(node.name)
            try:
                self.generic_visit(node)
            finally:
                self._pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            self._record(
                node,
                name=node.name,
                scope=IndexScope.CODE,
                symbol_type="async_function",
            )
            self._push(node.name)
            try:
                self.generic_visit(node)
            finally:
                self._pop()

    _Visitor().visit(parsed)
    symbols.extend(_extract_python_module_blocks(parsed, source, candidate, repo_root))
    symbols.sort(key=lambda item: (item.line_start, item.line_end, item.symbol_type, item.symbol_name))
    return symbols


def _extract_python_module_blocks(
    parsed: ast.Module,
    source: str,
    candidate: Path,
    repo_root: Path,
) -> list[CodeSymbol]:
    lines = source.splitlines()
    if not lines:
        return []

    covered = [False] * len(lines)
    for node in parsed.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            start = max(0, getattr(node, "lineno", 1) - 1)
            end = max(start, getattr(node, "end_lineno", getattr(node, "lineno", 1)) - 1)
            for line_no in range(start, min(end + 1, len(lines))):
                covered[line_no] = True

    try:
        qualified_base = candidate.relative_to(repo_root).as_posix()
    except Exception:
        qualified_base = candidate.as_posix()

    module_docstring = ast.get_docstring(parsed, clean=False) or ""
    blocks: list[CodeSymbol] = []
    block_index = 1
    cursor = 0
    while cursor < len(lines):
        if covered[cursor]:
            cursor += 1
            continue

        start = cursor
        has_text = False
        while cursor < len(lines) and not covered[cursor]:
            if lines[cursor].strip():
                has_text = True
            cursor += 1

        end = cursor - 1
        if not has_text:
            continue

        block_lines = lines[start : end + 1]
        body = "\n".join(block_lines).rstrip("\n")
        preview = _python_block_preview(block_lines, module_docstring if start == 0 else "")
        docstring = _python_block_docstring(block_lines, module_docstring if start == 0 else "")
        signature = _python_block_signature(block_lines)
        content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        blocks.append(
            CodeSymbol(
                symbol_name=f"module_block_{block_index}",
                qualified_name=f"{qualified_base}::module_block_{block_index}",
                file_path=candidate,
                line_start=start + 1,
                line_end=end + 1,
                signature=signature,
                docstring=docstring,
                body=body,
                symbol_type="module_block",
                content_hash=content_hash,
                preview=preview,
                scope=IndexScope.CODE,
            )
        )
        block_index += 1

    return blocks


def _python_block_docstring(lines: list[str], fallback: str = "") -> str:
    leading_comments = _leading_comment_block(lines)
    if leading_comments:
        return leading_comments
    return fallback


def _python_block_signature(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return "module block"


def _python_block_preview(lines: list[str], fallback: str = "") -> str:
    docstring = _leading_comment_block(lines)
    if docstring:
        return docstring.splitlines()[0].strip()
    if fallback:
        return fallback.splitlines()[0].strip()
    return _python_block_signature(lines)


def _leading_comment_block(lines: list[str]) -> str:
    comments: list[str] = []
    seen_comment = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if index == 0 and stripped.startswith('"""'):
            return stripped.strip('"')
        if not stripped:
            if seen_comment:
                comments.append("")
            continue
        if stripped.startswith("#"):
            seen_comment = True
            comments.append(stripped.lstrip("#").strip())
            continue
        break
    return "\n".join(comments).strip()
