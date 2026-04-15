"""Vector index namespace for codebase-lsp."""

from __future__ import annotations

from src.mcp_codebase.index.config import IndexConfig
from src.mcp_codebase.index.domain import (
    CodeSymbol,
    IndexMetadata,
    IndexScope,
    MarkdownSection,
    QueryResult,
)
from src.mcp_codebase.index.extractors import (
    extract_markdown_sections,
    extract_python_symbols,
    should_skip_path,
)

__all__ = (
    "CodeSymbol",
    "IndexConfig",
    "IndexMetadata",
    "IndexScope",
    "MarkdownSection",
    "QueryResult",
    "extract_markdown_sections",
    "extract_python_symbols",
    "should_skip_path",
)
