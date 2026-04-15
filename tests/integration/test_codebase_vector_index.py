"""Integration coverage for the vector index query contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.mcp_codebase.index import IndexConfig, IndexScope
from src.mcp_codebase.index.service import VectorIndexService


def test_code_symbol_lookup_returns_metadata(tmp_path: Path) -> None:
    """Code-symbol queries should surface direct metadata and empty-result behavior."""

    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        """
class Greeter:
    def hello(self) -> str:
        \"\"\"Return a short hello.\"\"\"
        return "hello"


def build_index() -> str:
    return "vector search"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    docs = tmp_path / "specs" / "guide.md"
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs.write_text(
        """
# Guide

## Usage

Run the index and then query the doctor.
""".strip()
        + "\n",
        encoding="utf-8",
    )

    service = VectorIndexService(
        IndexConfig(
            repo_root=tmp_path,
            db_path=".codegraphcontext/db/vector-index",
            embedding_model="local-default",
        )
    )
    service.build_full_index(revision="test-rev")

    results = service.query("vector search", scope=IndexScope.CODE, top_k=3)
    payload = [result.model_dump(mode="json") for result in results]

    assert payload
    assert payload[0]["rank"] == 1
    assert payload[0]["scope"] == "code"
    assert payload[0]["file_path"] == str(source)
    assert payload[0]["line_start"] == 7
    assert payload[0]["line_end"] >= payload[0]["line_start"]
    assert payload[0]["signature"].startswith("def build_index")
    assert "vector search" in payload[0]["body"]
    assert payload[0]["docstring"] == ""
    assert payload[0]["symbol_type"] == "function"
    assert service.query("nonsense phrase", scope=IndexScope.CODE, top_k=3) == []


def test_markdown_section_lookup_returns_breadcrumb(tmp_path: Path) -> None:
    """Markdown-topic queries should surface breadcrumb and preview metadata."""

    source = tmp_path / "specs" / "guide.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        """
# Guide

## Usage

Run the index and then query the doctor.
""".strip()
        + "\n",
        encoding="utf-8",
    )

    claude = tmp_path / ".claude" / "commands" / "indexing.md"
    claude.parent.mkdir(parents=True, exist_ok=True)
    claude.write_text(
        """
# Indexing

## Markdown

Use the local index for governance lookups.
""".strip()
        + "\n",
        encoding="utf-8",
    )

    service = VectorIndexService(
        IndexConfig(
            repo_root=tmp_path,
            db_path=".codegraphcontext/db/vector-index",
            embedding_model="local-default",
        )
    )
    service.build_full_index(revision="test-rev")

    results = service.query("markdown usage", scope=IndexScope.MARKDOWN, top_k=3)
    payload = [result.model_dump(mode="json") for result in results]

    assert payload
    assert payload[0]["scope"] == "markdown"
    assert payload[0]["file_path"] == str(source)
    assert payload[0]["breadcrumb"] == ["Guide", "Usage"]
    assert payload[0]["preview"].startswith("Run the index")


def test_incremental_refresh_preserves_last_good_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed refresh should leave the prior snapshot queryable."""

    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        """
def current_name() -> str:
    return "original"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    service = VectorIndexService(
        IndexConfig(
            repo_root=tmp_path,
            db_path=".codegraphcontext/db/vector-index",
            embedding_model="local-default",
        )
    )
    service.build_full_index(revision="rev-a")

    source.write_text(
        """
def current_name() -> str:
    return "updated"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    refreshed = service.refresh_changed_files([source], revision="rev-b")
    assert refreshed.indexed_commit == "rev-b"
    assert service.query("updated", scope=IndexScope.CODE, top_k=1)[0].body

    def boom(_: Path) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(service._store, "_activate_snapshot", boom)
    source.write_text(
        """
def current_name() -> str:
    return "broken"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError):
        service.refresh_changed_files([source], revision="rev-c")

    fallback = service.query("updated", scope=IndexScope.CODE, top_k=1)
    assert fallback
    assert fallback[0].body


def test_refresh_excludes_generated_artifacts_and_surfaces_post_edit_symbols(
    tmp_path: Path,
) -> None:
    """Generated artifacts should stay out of the index while refreshed symbols surface."""

    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        """
def live_symbol() -> str:
    return "live"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    generated = tmp_path / "generated" / "auto.py"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text(
        """
def generated_symbol() -> str:
    return "generated"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    service = VectorIndexService(
        IndexConfig(
            repo_root=tmp_path,
            db_path=".codegraphcontext/db/vector-index",
            embedding_model="local-default",
        )
    )
    service.build_full_index(revision="rev-a")

    assert service.query("generated_symbol", scope=IndexScope.CODE, top_k=1) == []
    baseline = service.query("live_symbol", scope=IndexScope.CODE, top_k=1)
    assert baseline
    assert baseline[0].file_path == source

    source.write_text(
        """
def live_symbol() -> str:
    return "live"


def refreshed_symbol() -> str:
    return "refreshed"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    refreshed = service.refresh_changed_files([source], revision="rev-b")
    assert refreshed.indexed_commit == "rev-b"

    surfacing = service.query("refreshed_symbol", scope=IndexScope.CODE, top_k=1)
    assert surfacing
    assert surfacing[0].file_path == source
    assert service.query("generated_symbol", scope=IndexScope.CODE, top_k=1) == []
