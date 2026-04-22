"""YAML section extraction for the local vector index."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Sequence

from src.mcp_codebase.index.domain import CodeSymbol, IndexScope
from src.mcp_codebase.index.extractors.python import should_skip_path

_YAML_SUFFIXES = {".yaml", ".yml"}
_TOP_LEVEL_KEY_RE = re.compile(r"^(?P<key>[^\s#][^:]*):(?:\s+.*)?$")


def extract_yaml_sections(
    file_path: str | Path,
    *,
    repo_root: str | Path | None = None,
    exclude_patterns: Sequence[str] = (),
    source_text: str | None = None,
) -> list[CodeSymbol]:
    """Extract top-level YAML mapping keys as structured code symbols."""
    repo_root = Path(repo_root or Path.cwd()).expanduser().resolve()
    candidate = Path(file_path)

    if should_skip_path(candidate, repo_root, exclude_patterns):
        return []

    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if candidate.suffix.lower() not in _YAML_SUFFIXES:
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

    starts: list[tuple[int, str, str]] = []
    for line_index, line in enumerate(lines):
        if not line or line[0].isspace():
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "---", "...")):
            continue
        match = _TOP_LEVEL_KEY_RE.match(line.rstrip())
        if match is None:
            continue
        raw_key = match.group("key").strip()
        normalized_key = raw_key.strip("'\"")
        if not normalized_key:
            continue
        starts.append((line_index, normalized_key, line.rstrip()))

    if not starts:
        return []

    key_counts: dict[str, int] = {}
    symbols: list[CodeSymbol] = []
    for idx, (start_index, key_name, signature_line) in enumerate(starts):
        end_index = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        section_lines = lines[start_index:end_index]
        body = "\n".join(section_lines).rstrip("\n")
        preview = _yaml_preview(section_lines)
        key_counts[key_name] = key_counts.get(key_name, 0) + 1
        key_suffix = key_counts[key_name]
        symbol_name = key_name if key_suffix == 1 else f"{key_name}_{key_suffix}"
        content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        symbols.append(
            CodeSymbol(
                symbol_name=symbol_name,
                symbol_type="yaml_section",
                qualified_name=f"{qualified_base}::{symbol_name}",
                signature=signature_line,
                docstring=preview,
                body=body,
                preview=preview,
                content_hash=content_hash,
                file_path=candidate,
                line_start=start_index + 1,
                line_end=max(start_index + 1, end_index),
                scope=IndexScope.CODE,
            )
        )
    return symbols


def _yaml_preview(section_lines: list[str]) -> str:
    """Return a concise preview for a YAML section body."""
    for raw in section_lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:160]
    return ""

