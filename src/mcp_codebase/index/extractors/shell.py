"""Shell script extraction for the local vector index."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from src.mcp_codebase.index.domain import CodeSymbol, IndexScope
from src.mcp_codebase.index.extractors.python import should_skip_path

_SHELL_SUFFIXES = {".sh", ".bash", ".zsh"}
_SHELL_FUNCTION_RE = re.compile(
    r"^\s*(?:function\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\))?\s*\{\s*(?:#.*)?$"
)


@dataclass(frozen=True)
class _ShellChunk:
    symbol_name: str
    symbol_type: str
    qualified_name: str
    line_start: int
    line_end: int
    signature: str
    docstring: str
    body: str
    preview: str
    content_hash: str


def extract_shell_scripts(
    file_path: str | Path,
    *,
    repo_root: str | Path | None = None,
    exclude_patterns: Sequence[str] = (),
    source_text: str | None = None,
) -> list[CodeSymbol]:
    """Extract shell scripts as semantic chunks plus top-level blocks."""

    repo_root = Path(repo_root or Path.cwd()).expanduser().resolve()
    candidate = Path(file_path)

    if should_skip_path(candidate, repo_root, exclude_patterns):
        return []

    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if candidate.suffix.lower() not in _SHELL_SUFFIXES:
        return []
    if not candidate.exists() or not candidate.is_file():
        return []

    source = source_text if source_text is not None else candidate.read_text(encoding="utf-8")
    lines = source.splitlines()
    if not lines:
        return []

    try:
        qualified_base = candidate.relative_to(repo_root).as_posix()
    except ValueError:
        qualified_base = candidate.as_posix()

    chunks = _collect_shell_chunks(lines, qualified_base, candidate.name)
    return [_chunk_to_symbol(candidate, chunk) for chunk in chunks]


def _collect_shell_chunks(lines: list[str], qualified_base: str, script_name: str) -> list[_ShellChunk]:
    function_spans = _find_shell_function_spans(lines)
    covered = [False] * len(lines)
    chunks: list[_ShellChunk] = []

    for index, (start_idx, end_idx, function_name) in enumerate(function_spans, start=1):
        for line_idx in range(start_idx, min(end_idx + 1, len(lines))):
            covered[line_idx] = True
        block_lines = lines[start_idx : end_idx + 1]
        chunks.append(
            _build_function_chunk(
                block_lines,
                qualified_base,
                script_name,
                function_name,
                index,
                start_idx,
                end_idx,
            )
        )

    block_index = 1
    cursor = 0
    while cursor < len(lines):
        if covered[cursor]:
            cursor += 1
            continue

        start_idx = cursor
        has_text = False
        while cursor < len(lines) and not covered[cursor]:
            if lines[cursor].strip():
                has_text = True
            cursor += 1

        end_idx = cursor - 1
        if not has_text:
            continue

        block_lines = lines[start_idx : end_idx + 1]
        chunks.append(
            _build_top_level_chunk(
                block_lines,
                qualified_base,
                script_name,
                block_index,
                start_idx,
                end_idx,
            )
        )
        block_index += 1

    chunks.sort(key=lambda chunk: (chunk.line_start, chunk.line_end, chunk.symbol_name))
    return chunks


def _find_shell_function_spans(lines: list[str]) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    while cursor < len(lines):
        match = _SHELL_FUNCTION_RE.match(lines[cursor])
        if match is None:
            cursor += 1
            continue

        name = match.group("name")
        start_idx = _leading_comment_block_start(lines, cursor)
        end_idx = _find_matching_brace_end(lines, cursor)
        spans.append((start_idx, end_idx, name))
        cursor = end_idx + 1
    return spans


def _leading_comment_block_start(lines: list[str], declaration_idx: int) -> int:
    cursor = declaration_idx - 1
    saw_comment = False

    while cursor >= 0:
        stripped = lines[cursor].strip()
        if not stripped:
            cursor -= 1
            continue
        if stripped.startswith("#"):
            saw_comment = True
            cursor -= 1
            continue
        break

    return cursor + 1 if saw_comment else declaration_idx


def _find_matching_brace_end(lines: list[str], declaration_idx: int) -> int:
    brace_depth = max(1, _brace_delta(lines[declaration_idx]))
    cursor = declaration_idx + 1
    while cursor < len(lines) and brace_depth > 0:
        brace_depth += _brace_delta(lines[cursor])
        cursor += 1
    return max(declaration_idx, cursor - 1)


def _brace_delta(line: str) -> int:
    stripped = line.split("#", 1)[0]
    stripped = re.sub(r"\$\{[^}]*\}", "", stripped)
    stripped = stripped.replace(r"\{", "").replace(r"\}", "")
    return stripped.count("{") - stripped.count("}")


def _build_function_chunk(
    block_lines: list[str],
    qualified_base: str,
    script_name: str,
    function_name: str,
    ordinal: int,
    start_idx: int,
    end_idx: int,
) -> _ShellChunk:
    body = "\n".join(block_lines).rstrip("\n")
    docstring = _shell_docstring(block_lines) or f"Shell function {function_name} in {script_name}."
    signature = _shell_function_signature(block_lines, function_name)
    preview = docstring.splitlines()[0].strip() if docstring else signature
    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    qualified_name = f"{qualified_base}::{function_name}"
    return _ShellChunk(
        symbol_name=function_name,
        symbol_type="script_function",
        qualified_name=qualified_name,
        line_start=start_idx + 1,
        line_end=end_idx + 1,
        signature=signature,
        docstring=docstring,
        body=body,
        preview=preview,
        content_hash=content_hash,
    )


def _build_top_level_chunk(
    block_lines: list[str],
    qualified_base: str,
    script_name: str,
    ordinal: int,
    start_idx: int,
    end_idx: int,
) -> _ShellChunk:
    body = "\n".join(block_lines).rstrip("\n")
    docstring = _shell_docstring(block_lines) or f"Top-level shell block in {script_name}."
    signature = _first_meaningful_line(block_lines) or "shell top-level block"
    preview = docstring.splitlines()[0].strip() if docstring else signature
    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    qualified_name = f"{qualified_base}::block_{ordinal}"
    return _ShellChunk(
        symbol_name=f"block_{ordinal}",
        symbol_type="script_block",
        qualified_name=qualified_name,
        line_start=start_idx + 1,
        line_end=end_idx + 1,
        signature=signature,
        docstring=docstring,
        body=body,
        preview=preview,
        content_hash=content_hash,
    )


def _shell_docstring(lines: list[str]) -> str:
    comments: list[str] = []
    seen_comment = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if index == 0 and stripped.startswith("#!"):
            continue
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


def _shell_function_signature(lines: list[str], function_name: str) -> str:
    for line in lines:
        match = _SHELL_FUNCTION_RE.match(line)
        if match and match.group("name") == function_name:
            return line.strip()
    return _first_meaningful_line(lines) or function_name


def _first_meaningful_line(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    for line in lines:
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _chunk_to_symbol(candidate: Path, chunk: _ShellChunk) -> CodeSymbol:
    return CodeSymbol(
        symbol_name=chunk.symbol_name,
        qualified_name=chunk.qualified_name,
        file_path=candidate,
        line_start=chunk.line_start,
        line_end=chunk.line_end,
        signature=chunk.signature,
        docstring=chunk.docstring,
        body=chunk.body,
        symbol_type=chunk.symbol_type,
        content_hash=chunk.content_hash,
        preview=chunk.preview,
        scope=IndexScope.CODE,
    )
