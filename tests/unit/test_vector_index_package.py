"""Smoke test for the vector index package namespace."""

from __future__ import annotations


def test_vector_index_package_imports_cleanly() -> None:
    """The package should import without side effects."""
    import src.mcp_codebase.index as index_pkg

    assert hasattr(index_pkg, "__all__")
    assert {
        "CodeSymbol",
        "IndexConfig",
        "IndexMetadata",
        "IndexScope",
        "MarkdownSection",
        "QueryResult",
        "extract_markdown_sections",
        "extract_python_symbols",
        "should_skip_path",
    }.issubset(set(index_pkg.__all__))
