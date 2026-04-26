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
    source_lines = source.splitlines()
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
            node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
            *,
            name: str,
            scope: IndexScope,
            symbol_type: str,
        ) -> None:
            start_lineno = _node_start_lineno(node)
            end_lineno = getattr(node, "end_lineno", getattr(node, "lineno", 1))
            declaration_lineno = getattr(node, "lineno", start_lineno)
            segment = (ast.get_source_segment(source, node) or "").rstrip("\n")
            if start_lineno < declaration_lineno:
                decorator_lines = source_lines[start_lineno - 1 : declaration_lineno - 1]
                decorator_prefix = "\n".join(decorator_lines).rstrip("\n")
                if decorator_prefix:
                    segment = f"{decorator_prefix}\n{segment}" if segment else decorator_prefix
            first_line = ""
            declaration_index = declaration_lineno - 1
            if 0 <= declaration_index < len(source_lines):
                first_line = source_lines[declaration_index].strip()
            if not first_line:
                first_line = segment.splitlines()[0].strip() if segment else ""
            docstring = ast.get_docstring(node, clean=False) or ""
            qualname = ".".join((*self._qualname_stack, name)) if self._qualname_stack else name
            symbols.append(
                CodeSymbol(
                    symbol_name=name,
                    qualified_name=qualname,
                    file_path=candidate,
                    line_start=start_lineno,
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
    symbols.extend(_extract_python_module_units(parsed, source, candidate, repo_root))
    symbols.sort(key=lambda item: (item.line_start, item.line_end, item.symbol_type, item.symbol_name))
    return symbols


def _node_start_lineno(node: ast.AST) -> int:
    """Return the first source line owned by a node, including decorators."""
    start_lineno = getattr(node, "lineno", 1)
    for decorator in getattr(node, "decorator_list", ()):
        start_lineno = min(start_lineno, getattr(decorator, "lineno", start_lineno))
    return start_lineno


def _extract_python_module_units(
    parsed: ast.Module,
    source: str,
    candidate: Path,
    repo_root: Path,
) -> list[CodeSymbol]:
    """Extract named module-level retrieval units from a Python source file."""
    lines = source.splitlines()
    if not lines:
        return []

    try:
        qualified_base = candidate.relative_to(repo_root).as_posix()
    except Exception:
        qualified_base = candidate.as_posix()

    module_docstring = ast.get_docstring(parsed, clean=False) or ""
    units: list[CodeSymbol] = []
    grouped_nodes: list[ast.AST] = []
    grouped_name = ""
    seen_names: dict[str, int] = {}

    def flush_group() -> None:
        """Persist the current statement group as one module unit."""
        nonlocal grouped_name
        if not grouped_nodes or not grouped_name:
            return

        start_line = _node_start_lineno(grouped_nodes[0])
        end_line = getattr(grouped_nodes[-1], "end_lineno", start_line)
        block_lines = lines[start_line - 1 : end_line]
        body = "\n".join(block_lines).rstrip("\n")
        if not body.strip():
            grouped_nodes.clear()
            grouped_name = ""
            return

        symbol_name = _dedupe_module_unit_name(grouped_name, seen_names)
        docstring = module_docstring if grouped_name == "docstring" else _python_block_docstring(block_lines)
        preview = (
            docstring.splitlines()[0].strip()
            if docstring
            else _python_block_preview(block_lines)
        )
        units.append(
            CodeSymbol(
                symbol_name=symbol_name,
                qualified_name=f"{qualified_base}::module:{symbol_name}",
                file_path=candidate,
                line_start=start_line,
                line_end=end_line,
                signature=_python_block_signature(block_lines),
                docstring=docstring,
                body=body,
                symbol_type="module",
                content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
                preview=preview,
                scope=IndexScope.CODE,
            )
        )
        grouped_nodes.clear()
        grouped_name = ""

    for index, node in enumerate(parsed.body):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            flush_group()
            continue

        unit_name = _module_unit_name(node, is_first_statement=index == 0)
        if grouped_nodes and grouped_name != unit_name:
            flush_group()
        grouped_nodes.append(node)
        grouped_name = unit_name

    flush_group()
    return units


def _module_unit_name(node: ast.AST, *, is_first_statement: bool) -> str:
    """Classify one top-level statement into a stable module-unit name."""
    if is_first_statement and _is_module_docstring_statement(node):
        return "docstring"
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return "imports"

    assignment_names = _module_assignment_names(node)
    lowered_names = [name.lower() for name in assignment_names]
    if any("registry" in name for name in lowered_names):
        return "registry"
    if any("config" in name for name in lowered_names):
        return "config"
    if assignment_names and all(
        name.upper() == name and any(char.isalpha() for char in name)
        for name in assignment_names
    ):
        return "constants"
    if _is_main_guard(node):
        return "main_guard"
    return "block"


def _dedupe_module_unit_name(base_name: str, seen_names: dict[str, int]) -> str:
    """Return a stable module-unit name, suffixing repeated categories."""
    count = seen_names.get(base_name, 0) + 1
    seen_names[base_name] = count
    if count == 1:
        return base_name
    return f"{base_name}_{count}"


def _module_assignment_names(node: ast.AST) -> tuple[str, ...]:
    """Extract simple target names from one module-level assignment statement."""
    targets: Iterable[ast.AST]
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = (node.target,)
    elif isinstance(node, ast.AugAssign):
        targets = (node.target,)
    else:
        return ()

    names: list[str] = []
    for target in targets:
        names.extend(_iter_assignment_target_names(target))
    return tuple(name for name in names if name)


def _iter_assignment_target_names(target: ast.AST) -> Iterable[str]:
    """Yield simple assignment target names from a nested assignment target."""
    if isinstance(target, ast.Name):
        yield target.id
        return
    if isinstance(target, (ast.List, ast.Tuple)):
        for element in target.elts:
            yield from _iter_assignment_target_names(element)


def _is_module_docstring_statement(node: ast.AST) -> bool:
    """Return true when a top-level statement is the module docstring literal."""
    if not isinstance(node, ast.Expr):
        return False
    value = getattr(node, "value", None)
    return isinstance(value, ast.Constant) and isinstance(value.value, str)


def _is_main_guard(node: ast.AST) -> bool:
    """Return true when a top-level statement is an `if __name__ == "__main__"` guard."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq) or not isinstance(test.left, ast.Name):
        return False
    comparator = test.comparators[0]
    return test.left.id == "__name__" and isinstance(comparator, ast.Constant) and comparator.value == "__main__"


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
