"""Integration coverage for the vector index query contract."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.mcp_codebase.index import IndexConfig, IndexScope
from src.mcp_codebase.index import service as index_service
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
            db_path=Path(".codegraphcontext/global/db/vector-index"),
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
            db_path=Path(".codegraphcontext/global/db/vector-index"),
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
            db_path=Path(".codegraphcontext/global/db/vector-index"),
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
            db_path=Path(".codegraphcontext/global/db/vector-index"),
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


def test_staleness_reports_commit_delta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Status should report when the active snapshot lags behind the current HEAD."""

    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        """
def stable_symbol() -> str:
    return "stable"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    build_time = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)
    status_time = datetime(2026, 4, 14, 13, 0, tzinfo=UTC)
    monkeypatch.setattr(index_service, "_utc_now", lambda: build_time)

    service = VectorIndexService(
        IndexConfig(
            repo_root=tmp_path,
            db_path=Path(".codegraphcontext/global/db/vector-index"),
            embedding_model="local-default",
        )
    )
    service.build_full_index(revision="rev-a")

    monkeypatch.setattr(index_service, "_resolve_current_commit", lambda repo_root: "rev-b")
    monkeypatch.setattr(index_service, "_resolve_commit_distance", lambda repo_root, indexed, current: 7)
    monkeypatch.setattr(index_service, "_utc_now", lambda: status_time)

    status = service.status()

    assert status is not None
    assert status.indexed_commit == "rev-a"
    assert status.current_commit == "rev-b"
    assert status.is_stale is True
    assert status.commits_behind_head == 7
    assert status.indexed_age_seconds == 3600.0
    assert "rev-a" in status.stale_reason
    assert "rev-b" in status.stale_reason
    assert "7 commits" in status.stale_reason
    assert "built 3600.0 seconds ago" in status.stale_reason
