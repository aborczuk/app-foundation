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

__all__ = (
    "CodeSymbol",
    "IndexConfig",
    "IndexMetadata",
    "IndexScope",
    "MarkdownSection",
    "QueryResult",
)
