"""Integration coverage for the vector index query contract."""

from __future__ import annotations

from pathlib import Path

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
