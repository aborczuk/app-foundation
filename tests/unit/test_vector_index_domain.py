"""Unit tests for vector index domain and config models."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.mcp_codebase.index import (
    CodeSymbol,
    IndexConfig,
    IndexMetadata,
    IndexScope,
    MarkdownSection,
    QueryResult,
)


def test_code_symbol_preserves_typed_fields() -> None:
    symbol = CodeSymbol(
        symbol_name="build_index",
        qualified_name="mcp_codebase.index.service.build_index",
        file_path="src/mcp_codebase/index/service.py",
        line_start=12,
        line_end=21,
        signature="def build_index(...):",
        docstring="Build the local vector index.",
        body="def build_index(...):\n    return True",
    )

    assert symbol.file_path == Path("src/mcp_codebase/index/service.py")
    assert symbol.line_start == 12
    assert symbol.line_end == 21
    assert symbol.scope is IndexScope.CODE
    assert symbol.docstring == "Build the local vector index."
    assert symbol.body.startswith("def build_index")


def test_markdown_section_preserves_breadcrumb_and_scope() -> None:
    section = MarkdownSection(
        heading="Quickstart",
        breadcrumb=["Codebase Vector Index", "Quickstart"],
        file_path="specs/020-codebase-vector-index/quickstart.md",
        line_start=1,
        line_end=8,
        depth=2,
        preview="Run the indexer and then query the doctor.",
    )

    assert section.file_path == Path("specs/020-codebase-vector-index/quickstart.md")
    assert section.breadcrumb == ("Codebase Vector Index", "Quickstart")
    assert section.scope is IndexScope.MARKDOWN
    assert section.preview.startswith("Run the indexer")


def test_query_result_preserves_typed_content() -> None:
    symbol = CodeSymbol(
        symbol_name="query",
        qualified_name="mcp_codebase.index.service.VectorIndexService.query",
        file_path="src/mcp_codebase/index/service.py",
        line_start=44,
        line_end=81,
        signature="def query(...):",
        docstring="Return ranked index results.",
        body="def query(...):\n    return []",
    )

    result = QueryResult(rank=1, score=0.98, content=symbol)

    assert result.rank == 1
    assert result.score == pytest.approx(0.98)
    assert isinstance(result.content, CodeSymbol)
    assert result.content.file_path == Path("src/mcp_codebase/index/service.py")
    assert result.body.startswith("def query")


def test_index_metadata_rejects_malformed_freshness_metadata() -> None:
    with pytest.raises(ValidationError):
        IndexMetadata(
            source_root=".",
            indexed_commit="abc123",
            current_commit="def456",
            indexed_at=datetime.now(UTC),
            entry_count=12,
            is_stale=False,
        )


def test_index_config_normalizes_repo_relative_db_path() -> None:
    config = IndexConfig(
        repo_root=".",
        db_path=".codegraphcontext/db/vector-index",
        embedding_model="local-default",
        exclude_patterns=("generated/", "  docs/build  "),
    )

    assert config.repo_root.is_absolute()
    assert config.db_path.is_absolute()
    assert config.db_path.is_relative_to(config.repo_root)
    assert config.default_scopes == (IndexScope.CODE, IndexScope.MARKDOWN)
    assert config.exclude_patterns == ("generated/", "docs/build")
