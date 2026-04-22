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
    extract_shell_scripts,
    extract_yaml_sections,
    should_skip_path,
)
from src.mcp_codebase.index.service import VectorIndexService, build_vector_index_service

__all__ = (
    "CodeSymbol",
    "IndexConfig",
    "IndexMetadata",
    "IndexScope",
    "MarkdownSection",
    "QueryResult",
    "VectorIndexService",
    "build_vector_index_service",
    "extract_markdown_sections",
    "extract_python_symbols",
    "extract_shell_scripts",
    "extract_yaml_sections",
    "should_skip_path",
)
