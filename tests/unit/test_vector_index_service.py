"""Unit tests for vector index orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

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
    assert markdown_results[0].body == "Run the index and query the doctor."
    assert markdown_results[0].content.content_hash


def test_service_indexes_shell_scripts_as_code(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "refresh.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        """#!/usr/bin/env bash
# Refresh the vector index after edits.
set -euo pipefail

require_cmd() {
  command -v "$1" >/dev/null 2>&1
}

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

    service = VectorIndexService(
        IndexConfig(
            repo_root=tmp_path,
            db_path=".codegraphcontext/db/vector-index",
            embedding_model="local-default",
        )
    )

    metadata = service.build_full_index(revision="test-rev")

    assert metadata.entry_count >= 1
    script_results = service.query("refresh vector index", scope=IndexScope.CODE, top_k=3)
    assert script_results
    assert script_results[0].content.file_path == script
    assert any(result.content.symbol_type == "script_function" and result.content.symbol_name == "run_refresh" for result in script_results)
    assert any(result.content.symbol_type == "script_block" for result in script_results)
    assert any(result.body.startswith("run_refresh()") for result in script_results if result.content.symbol_type == "script_function")


def test_refresh_embeds_only_changed_units(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_a = tmp_path / "src" / "alpha.py"
    source_a.parent.mkdir(parents=True, exist_ok=True)
    source_a.write_text(
        """
def alpha() -> str:
    return "alpha"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    source_b = tmp_path / "src" / "beta.py"
    source_b.write_text(
        """
def beta() -> str:
    return "beta"
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

    source_a.write_text(
        """
def alpha() -> str:
    return "alpha-updated"


def alpha_refresh() -> str:
    return "refresh"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    expected_changed_units = service._collect_content_units(changed_paths=[source_a])

    embed_call_sizes: list[int] = []
    original_embed = service._store._embed_texts

    def spy_embed(texts: Sequence[str]) -> list[list[float]]:
        embed_call_sizes.append(len(texts))
        return original_embed(texts)

    monkeypatch.setattr(service._store, "_embed_texts", spy_embed)

    refreshed = service.refresh_changed_files([source_a], revision="rev-b")
    assert refreshed.indexed_commit == "rev-b"
    assert embed_call_sizes == [len(expected_changed_units)]
    assert service.query("alpha_refresh", scope=IndexScope.CODE, top_k=1)
    assert service.query("beta", scope=IndexScope.CODE, top_k=1)


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
