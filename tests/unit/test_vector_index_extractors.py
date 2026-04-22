"""Unit tests for vector index extractors."""

from __future__ import annotations

from pathlib import Path

from src.mcp_codebase.index import IndexScope
from src.mcp_codebase.index.extractors import (
    extract_markdown_sections,
    extract_python_symbols,
    extract_shell_scripts,
    extract_yaml_sections,
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
    assert symbols[0].body.startswith("class Example")
    assert symbols[1].body.startswith("def build")
    assert [symbol.symbol_type for symbol in symbols] == ["class", "function"]
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
    assert sections[1].body == "Run the indexer and then query the doctor."
    assert sections[1].preview.startswith("Run the indexer")
    assert sections[1].content_hash
    assert all(section.scope is IndexScope.MARKDOWN for section in sections)

    generated = tmp_path / "build" / "generated_notes.md"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text("# Generated\n", encoding="utf-8")

    assert extract_markdown_sections(generated, repo_root=tmp_path) == []


def test_extract_markdown_sections_preserves_nested_breadcrumbs_and_preview(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "specs" / "guide.md"
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs.write_text(
        """
# Guide

## Usage

### Querying

Run the indexer before querying the doctor.
""".strip()
        + "\n",
        encoding="utf-8",
    )

    sections = extract_markdown_sections(docs, repo_root=tmp_path)

    assert [section.heading for section in sections] == ["Guide", "Usage", "Querying"]
    assert sections[-1].breadcrumb == ("Guide", "Usage", "Querying")
    assert sections[-1].body == "Run the indexer before querying the doctor."
    assert sections[-1].preview.startswith("Run the indexer")


def test_extract_python_symbols_includes_module_level_blocks(tmp_path: Path) -> None:
    source = tmp_path / "src" / "module_example.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        '''
"""Module docstring."""

from pathlib import Path

SETTING = 1

def work() -> int:
    return SETTING

if __name__ == "__main__":
    print(Path.cwd())
'''.strip()
        + "\n",
        encoding="utf-8",
    )

    symbols = extract_python_symbols(source, repo_root=tmp_path)

    assert any(symbol.symbol_name == "work" and symbol.symbol_type == "function" for symbol in symbols)
    module_blocks = [symbol for symbol in symbols if symbol.symbol_type == "module_block"]
    assert module_blocks
    assert any("SETTING = 1" in symbol.body for symbol in module_blocks)
    assert any("if __name__ == \"__main__\"" in symbol.body for symbol in module_blocks)


def test_extract_shell_scripts_uses_header_comment_and_full_body(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "refresh.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        """#!/usr/bin/env bash
# Refresh the vector index after a repo change.
#
# This keeps the script discoverable in the vector store.
set -euo pipefail

# Check whether a command exists.
require_cmd() {
  command -v "$1" >/dev/null 2>&1
}

# Run the refresh action.
run_refresh() {
  echo refresh
}

case "${1:-}" in
  refresh)
    run_refresh
    ;;
esac
""",
        encoding="utf-8",
    )

    scripts = extract_shell_scripts(script, repo_root=tmp_path)

    function_symbols = [symbol for symbol in scripts if symbol.symbol_type == "script_function"]
    block_symbols = [symbol for symbol in scripts if symbol.symbol_type == "script_block"]

    assert {symbol.symbol_name for symbol in function_symbols} == {"require_cmd", "run_refresh"}
    assert block_symbols
    assert all(symbol.docstring for symbol in function_symbols)
    assert any(symbol.symbol_name == "require_cmd" and "command -v" in symbol.body for symbol in function_symbols)
    assert any(symbol.symbol_name == "run_refresh" and "run_refresh()" in symbol.body for symbol in function_symbols)
    assert any("case \"${1:-}\"" in symbol.body for symbol in block_symbols)
    assert any(symbol.docstring == "Check whether a command exists." for symbol in function_symbols)
    assert any(symbol.docstring == "Run the refresh action." for symbol in function_symbols)
    assert scripts[0].scope is IndexScope.CODE


def test_extract_yaml_sections_builds_top_level_structured_chunks(tmp_path: Path) -> None:
    manifest = tmp_path / "command-manifest.yaml"
    manifest.write_text(
        """
version: 1
commands:
  read-code:
    script: scripts/read-code.sh
domains:
  - security
  - observability
""".strip()
        + "\n",
        encoding="utf-8",
    )

    sections = extract_yaml_sections(manifest, repo_root=tmp_path)

    assert [section.symbol_name for section in sections] == ["version", "commands", "domains"]
    assert all(section.symbol_type == "yaml_section" for section in sections)
    assert sections[1].preview.startswith("commands:")
    assert sections[2].content_hash
    assert all(section.scope is IndexScope.CODE for section in sections)
