"""Unit tests for vector index extractors."""

from __future__ import annotations

from pathlib import Path

from src.mcp_codebase.index import IndexScope
from src.mcp_codebase.index.extractors import (
    extract_markdown_sections,
    extract_python_symbols,
)


def test_extract_python_symbols_handles_missing_docstrings_and_hashes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "example.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        """
class Example:
    def build(self, value: int) -> int:
        return value + 1
""".strip()
        + "\n",
        encoding="utf-8",
    )

    symbols = extract_python_symbols(source, repo_root=tmp_path)

    assert [symbol.symbol_name for symbol in symbols] == ["Example", "build"]
    assert symbols[0].docstring == ""
    assert symbols[1].docstring == ""
    assert symbols[0].content_hash
    assert symbols[1].content_hash
    assert all(symbol.scope is IndexScope.CODE for symbol in symbols)


def test_extract_python_symbols_preserves_signatures_and_no_docstring_normalization(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "signature_example.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        """
def first(value: int) -> int:
    return value + 1
""".strip()
        + "\n",
        encoding="utf-8",
    )

    symbols = extract_python_symbols(source, repo_root=tmp_path)

    assert len(symbols) == 1
    assert symbols[0].signature.startswith("def first")
    assert symbols[0].docstring == ""
    assert symbols[0].preview.startswith("def first")


def test_extract_markdown_sections_builds_breadcrumbs_and_skips_generated_paths(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "specs" / "guide.md"
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs.write_text(
        """
# Guide

Intro paragraph.

## Usage

Run the indexer and then query the doctor.
""".strip()
        + "\n",
        encoding="utf-8",
    )

    sections = extract_markdown_sections(docs, repo_root=tmp_path)

    assert [section.heading for section in sections] == ["Guide", "Usage"]
    assert sections[1].breadcrumb == ("Guide", "Usage")
    assert sections[1].preview.startswith("Run the indexer")
    assert sections[1].content_hash
    assert all(section.scope is IndexScope.MARKDOWN for section in sections)

    generated = tmp_path / "build" / "generated_notes.md"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text("# Generated\n", encoding="utf-8")

    assert extract_markdown_sections(generated, repo_root=tmp_path) == []
