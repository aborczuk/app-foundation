"""Unit tests for vector index orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.mcp_codebase.index import IndexConfig, IndexScope
from src.mcp_codebase.index.service import VectorIndexService


def test_service_build_query_and_status_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        """
class Greeter:
    def hello(self) -> str:
        \"\"\"Return a short hello.\"\"\"
        return "hello"
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

Run the index and query the doctor.
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

    metadata = service.build_full_index(revision="test-rev")

    assert metadata.entry_count >= 2
    assert service.status().indexed_commit == "test-rev"

    code_results = service.query("Greeter hello", scope=IndexScope.CODE, top_k=3)
    assert code_results
    assert code_results[0].content.file_path == source
    assert code_results[0].content.scope is IndexScope.CODE

    markdown_results = service.query("Usage run index", scope=IndexScope.MARKDOWN, top_k=3)
    assert markdown_results
    assert markdown_results[0].content.file_path == docs
    assert markdown_results[0].content.scope is IndexScope.MARKDOWN
    assert markdown_results[0].content.content_hash


def test_refresh_failure_preserves_previous_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    before = service.query("current_name", scope=IndexScope.CODE, top_k=1)
    assert before
    assert before[0].content.signature.startswith("def current_name")

    source.write_text(
        """
def current_name() -> str:
    return "updated"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    def boom(_: Path) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(service._store, "_activate_snapshot", boom)

    with pytest.raises(RuntimeError):
        service.refresh_changed_files([source], revision="rev-b")

    after = service.query("current_name", scope=IndexScope.CODE, top_k=1)
    assert after
    assert after[0].content.signature.startswith("def current_name")
    assert after[0].content.docstring == ""
    assert service.status().indexed_commit == "rev-a"
