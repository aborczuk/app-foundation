"""Unit tests for vector index orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

import pytest

import src.mcp_codebase.index.service as vector_service_module
from src.mcp_codebase.index import CodeSymbol, IndexConfig, IndexMetadata, IndexScope
from src.mcp_codebase.index.service import VectorIndexService
from src.mcp_codebase.index.store.chroma import ChromaIndexStore


def _fake_embeddings(texts: Sequence[str]) -> list[list[float]]:
    """Return deterministic local embeddings for unit tests."""
    return [[float(len(text) % 7), float(sum(ord(char) for char in text) % 11), 1.0] for text in texts]


def test_service_build_query_and_status_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
            db_path=Path(".codegraphcontext/global/db/vector-index"),
            embedding_model="local-default",
        )
    )
    monkeypatch.setattr(service._store, "_embed_texts", _fake_embeddings)

    metadata = service.build_full_index(revision="test-rev")

    assert metadata.entry_count >= 2
    status = service.status()
    assert status is not None
    assert status.indexed_commit == "test-rev"

    code_results = service.query("Greeter hello", scope=IndexScope.CODE, top_k=3)
    assert code_results
    assert code_results[0].content.file_path == source
    assert code_results[0].content.scope is IndexScope.CODE

    file_scoped_results = service.query(
        "Greeter hello",
        scope=IndexScope.CODE,
        top_k=3,
        file_path=source,
    )
    assert file_scoped_results
    assert all(result.content.file_path == source for result in file_scoped_results)

    missing_file_results = service.query(
        "Greeter hello",
        scope=IndexScope.CODE,
        top_k=3,
        file_path=tmp_path / "src" / "missing.py",
    )
    assert missing_file_results == []

    markdown_results = service.query("Usage run index", scope=IndexScope.MARKDOWN, top_k=3)
    assert markdown_results
    assert markdown_results[0].content.file_path == docs
    assert markdown_results[0].content.scope is IndexScope.MARKDOWN
    assert markdown_results[0].body == "Run the index and query the doctor."
    assert markdown_results[0].content.content_hash


def test_status_marks_git_path_drift_stale_even_when_commit_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def alpha() -> str:\n    return 'a'\n", encoding="utf-8")

    service = VectorIndexService(
        IndexConfig(
            repo_root=tmp_path,
            db_path=Path(".codegraphcontext/global/db/vector-index"),
            embedding_model="local-default",
        )
    )
    monkeypatch.setattr(service._store, "_embed_texts", _fake_embeddings)
    monkeypatch.setattr(vector_service_module, "_resolve_current_commit", lambda _: "same-revision")
    monkeypatch.setattr(vector_service_module, "_resolve_commit_distance", lambda *_: 0)
    monkeypatch.setattr(
        vector_service_module,
        "_current_git_signature",
        lambda _: " M src/sample.py",
    )
    monkeypatch.setattr(
        vector_service_module,
        "_collect_git_indexable_drift_paths",
        lambda *args, **kwargs: (("src/sample.py",), None),
    )

    _ = service.build_full_index(revision="same-revision")
    fresh_status = service.status()

    assert fresh_status is not None
    assert fresh_status.current_commit == "same-revision"
    assert fresh_status.is_stale is True
    assert fresh_status.stale_reason_class == "git-path-drift"
    assert fresh_status.stale_drift_paths == ("src/sample.py",)
    assert fresh_status.stale_signal_source == "git"


def test_status_uses_mtime_fallback_only_when_git_signal_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def alpha() -> str:\n    return 'a'\n", encoding="utf-8")

    service = VectorIndexService(
        IndexConfig(
            repo_root=tmp_path,
            db_path=Path(".codegraphcontext/global/db/vector-index"),
            embedding_model="local-default",
        )
    )
    monkeypatch.setattr(service._store, "_embed_texts", _fake_embeddings)
    monkeypatch.setattr(vector_service_module, "_resolve_current_commit", lambda _: "same-revision")
    monkeypatch.setattr(vector_service_module, "_resolve_commit_distance", lambda *_: 0)
    monkeypatch.setattr(vector_service_module, "_current_git_signature", lambda _: None)
    monkeypatch.setattr(
        vector_service_module,
        "_collect_git_indexable_drift_paths",
        lambda *args, **kwargs: ((), "git status signature unavailable"),
    )
    monkeypatch.setattr(vector_service_module, "_latest_indexable_source_drift", lambda *args: source)

    _ = service.build_full_index(revision="same-revision")
    stale_status = service.status()

    assert stale_status is not None
    assert stale_status.is_stale is True
    assert stale_status.stale_reason_class == "mtime-fallback-drift"
    assert stale_status.stale_drift_paths == ("src/sample.py",)
    assert stale_status.stale_signal_source == "mtime-fallback"
    assert stale_status.stale_signal_available is False


def test_service_indexes_shell_scripts_as_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
            db_path=Path(".codegraphcontext/global/db/vector-index"),
            embedding_model="local-default",
        )
    )
    monkeypatch.setattr(service._store, "_embed_texts", _fake_embeddings)

    metadata = service.build_full_index(revision="test-rev")

    assert metadata.entry_count >= 1
    script_results = service.query("refresh vector index", scope=IndexScope.CODE, top_k=10)
    assert script_results
    assert script_results[0].content.file_path == script
    saw_run_refresh = False
    saw_script_block = False
    saw_function_body = False
    for result in script_results:
        content = result.content
        if isinstance(content, CodeSymbol):
            if content.symbol_type == "script_function" and content.symbol_name == "run_refresh":
                saw_run_refresh = True
            if content.symbol_type == "script_block":
                saw_script_block = True
            if content.symbol_type == "script_function" and result.body.startswith("run_refresh()"):
                saw_function_body = True
    assert saw_run_refresh
    assert saw_script_block
    assert saw_function_body


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
            db_path=Path(".codegraphcontext/global/db/vector-index"),
            embedding_model="local-default",
        )
    )
    monkeypatch.setattr(service._store, "_embed_texts", _fake_embeddings)
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
    assert refreshed is not None
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
            db_path=Path(".codegraphcontext/global/db/vector-index"),
            embedding_model="local-default",
        )
    )
    monkeypatch.setattr(service._store, "_embed_texts", _fake_embeddings)
    service.build_full_index(revision="rev-a")
    before = service.query("current_name", scope=IndexScope.CODE, top_k=1)
    assert before
    before_content = before[0].content
    assert isinstance(before_content, CodeSymbol)
    assert before_content.signature.startswith("def current_name")

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
    after_content = after[0].content
    assert isinstance(after_content, CodeSymbol)
    assert after_content.signature.startswith("def current_name")
    assert after_content.docstring == ""
    status = service.status()
    assert status is not None
    assert status.indexed_commit == "rev-a"


def test_store_write_snapshot_batches_upserts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """write_snapshot should chunk upserts to respect collection batch-size limits."""
    store = ChromaIndexStore(
        IndexConfig(
            repo_root=tmp_path,
            db_path=Path(".codegraphcontext/global/db/vector-index"),
            embedding_model="local-default",
        )
    )
    metadata = IndexMetadata(
        source_root=tmp_path,
        indexed_commit="rev-a",
        current_commit="rev-a",
        indexed_at=datetime(2026, 4, 14, tzinfo=UTC),
        entry_count=5,
        snapshot_path=str(tmp_path / "snapshot"),
        collection_name="test-collection",
    )

    chunks = [
        SimpleNamespace(
            record_id=f"record-{idx}",
            document=f"doc-{idx}",
            embedding=[float(idx), 1.0],
            metadata={"file_path": (tmp_path / "src" / f"f{idx}.py").as_posix(), "scope": IndexScope.CODE.value},
        )
        for idx in range(5)
    ]
    monkeypatch.setattr(store, "_prepare_chunks", lambda _: chunks)

    upsert_batch_sizes: list[int] = []
    activated_paths: list[Path] = []

    class _FakeClient:
        max_batch_size = 2

    class _FakeCollection:
        def __init__(self) -> None:
            self._client = _FakeClient()

        def upsert(self, *, ids, documents, embeddings, metadatas):
            upsert_batch_sizes.append(len(ids))
            assert len(ids) == len(documents) == len(embeddings) == len(metadatas)

    fake_collection = _FakeCollection()
    monkeypatch.setattr(store, "_open_collection", lambda *args, **kwargs: fake_collection)
    monkeypatch.setattr(store, "_activate_snapshot", lambda path: activated_paths.append(Path(path)))

    refreshed = store.write_snapshot([], metadata)

    assert upsert_batch_sizes == [2, 2, 1]
    assert activated_paths
    assert Path(refreshed.snapshot_path) == activated_paths[0]


def test_refresh_changed_snapshot_clones_and_patches_changed_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """refresh_changed_snapshot should clone active snapshot and patch only changed-path records."""
    store = ChromaIndexStore(
        IndexConfig(
            repo_root=tmp_path,
            db_path=Path(".codegraphcontext/global/db/vector-index"),
            embedding_model="local-default",
        )
    )
    active_snapshot = tmp_path / ".codegraphcontext" / "global" / "db" / "vector-index" / "staging" / "active"
    active_snapshot.mkdir(parents=True, exist_ok=True)
    marker_file = active_snapshot / "marker.txt"
    marker_file.write_text("active", encoding="utf-8")

    active_metadata = IndexMetadata(
        source_root=tmp_path,
        indexed_commit="rev-a",
        current_commit="rev-a",
        indexed_at=datetime(2026, 4, 14, tzinfo=UTC),
        entry_count=2,
        code_symbol_count=2,
        markdown_section_count=0,
        embedding_model="local-default",
        collection_name="active-collection",
        snapshot_path=str(active_snapshot),
    )
    store._write_manifest(active_metadata)

    refresh_metadata = IndexMetadata(
        source_root=tmp_path,
        indexed_commit="rev-b",
        current_commit="rev-b",
        indexed_at=datetime(2026, 4, 14, tzinfo=UTC),
        entry_count=2,
        code_symbol_count=2,
        markdown_section_count=0,
        embedding_model="local-default",
        collection_name="new-collection",
        snapshot_path="",
    )

    changed_file = (tmp_path / "src" / "alpha.py").resolve()
    unchanged_file = (tmp_path / "src" / "beta.py").resolve()
    changed_symbol = CodeSymbol(
        symbol_name="alpha",
        qualified_name="alpha",
        file_path=changed_file,
        line_start=1,
        line_end=2,
        signature="def alpha():",
        preview="def alpha():",
    )
    changed_chunk = SimpleNamespace(
        record_id="new-alpha",
        document="def alpha(): pass",
        embedding=[1.0, 2.0, 3.0],
        metadata={"file_path": changed_file.as_posix(), "scope": IndexScope.CODE.value},
    )
    monkeypatch.setattr(store, "_prepare_chunks", lambda units: [changed_chunk])

    delete_batches: list[list[str]] = []
    upsert_batches: list[list[str]] = []
    opened_collections: list[tuple[Path, str, bool]] = []

    class _FakeCollection:
        def get(self, *, include):
            assert include == ["metadatas"]
            return {
                "ids": ["old-alpha", "old-beta"],
                "metadatas": [
                    {"file_path": changed_file.as_posix()},
                    {"file_path": unchanged_file.as_posix()},
                ],
            }

        def delete(self, *, ids):
            delete_batches.append(list(ids))

        def upsert(self, *, ids, documents, embeddings, metadatas):
            upsert_batches.append(list(ids))
            assert len(ids) == len(documents) == len(embeddings) == len(metadatas)

    fake_collection = _FakeCollection()

    def _fake_open_collection(collection_dir: Path, collection_name: str, *, create: bool):
        opened_collections.append((Path(collection_dir), collection_name, create))
        return fake_collection

    monkeypatch.setattr(store, "_open_collection", _fake_open_collection)

    activated_paths: list[Path] = []
    monkeypatch.setattr(store, "_activate_snapshot", lambda path: activated_paths.append(Path(path)))

    refreshed = store.refresh_changed_snapshot(
        changed_paths=[changed_file],
        changed_units=[changed_symbol],
        metadata=refresh_metadata,
    )

    assert opened_collections
    opened_path, opened_name, opened_create = opened_collections[0]
    assert opened_name == "active-collection"
    assert opened_create is False
    assert delete_batches == [["old-alpha"]]
    assert upsert_batches == [["new-alpha"]]
    assert activated_paths
    assert refreshed.collection_name == "active-collection"
    assert Path(refreshed.snapshot_path) == activated_paths[0]
    assert (Path(refreshed.snapshot_path) / "marker.txt").read_text(encoding="utf-8") == "active"
    assert Path(refreshed.snapshot_path) != active_snapshot


def test_list_file_code_symbols_uses_conjunctive_chroma_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store should query Chroma with a valid conjunctive filter for file symbols."""

    store = ChromaIndexStore(
        IndexConfig(
            repo_root=tmp_path,
            db_path=Path(".codegraphcontext/global/db/vector-index"),
            embedding_model="local-default",
        )
    )
    metadata = IndexMetadata(
        source_root=tmp_path,
        indexed_commit="rev-a",
        current_commit="rev-a",
        indexed_at=datetime(2026, 4, 14, tzinfo=UTC),
        entry_count=1,
        snapshot_path=str(tmp_path / "snapshot"),
        collection_name="test-collection",
    )
    expected_file = (tmp_path / "src" / "sample.py").resolve().as_posix()
    expected_symbol = CodeSymbol(
        symbol_name="sample",
        qualified_name="sample",
        file_path=Path(expected_file),
        line_start=1,
        line_end=2,
        signature="def sample():",
        docstring="",
        preview="def sample():",
    )

    class FakeCollection:
        def __init__(self) -> None:
            self.where = None

        def get(self, *, where, include):
            self.where = where
            assert include == ["metadatas"]
            return {"metadatas": [{}]}

    fake_collection = FakeCollection()
    monkeypatch.setattr(store, "load_snapshot", lambda: (metadata, None))
    monkeypatch.setattr(store, "_open_collection", lambda *args, **kwargs: fake_collection)
    monkeypatch.setattr(store, "_decode_content_unit", lambda metadata_payload, document=None: expected_symbol)

    symbols = store.list_file_code_symbols("src/sample.py")

    assert fake_collection.where == {
        "$and": [
            {"scope": IndexScope.CODE.value},
            {"record_type": "code"},
            {"file_path": expected_file},
        ]
    }
    assert len(symbols) == 1
    assert symbols[0].symbol_name == expected_symbol.symbol_name
    assert symbols[0].file_path == expected_symbol.file_path


def test_store_query_uses_conjunctive_filter_for_scope_and_file_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store should combine scope + file constraints in a single Chroma where clause."""
    store = ChromaIndexStore(
        IndexConfig(
            repo_root=tmp_path,
            db_path=Path(".codegraphcontext/global/db/vector-index"),
            embedding_model="local-default",
        )
    )
    metadata = IndexMetadata(
        source_root=tmp_path,
        indexed_commit="rev-a",
        current_commit="rev-a",
        indexed_at=datetime(2026, 4, 14, tzinfo=UTC),
        entry_count=1,
        snapshot_path=str(tmp_path / "snapshot"),
        collection_name="test-collection",
    )
    expected_file = (tmp_path / "src" / "sample.py").resolve().as_posix()
    expected_symbol = CodeSymbol(
        symbol_name="sample",
        qualified_name="sample",
        file_path=Path(expected_file),
        line_start=1,
        line_end=2,
        signature="def sample():",
        docstring="",
        preview="def sample():",
        body="def sample():\n    return 1\n",
    )

    class FakeCollection:
        def __init__(self) -> None:
            self.where = None

        def query(self, *, query_embeddings, n_results, where, include):
            self.where = where
            assert query_embeddings
            assert n_results == 12
            assert include == ["distances", "metadatas", "documents"]
            return {
                "distances": [[0.0]],
                "documents": [["def sample():\n    return 1\n"]],
                "metadatas": [[{}]],
            }

    fake_collection = FakeCollection()
    monkeypatch.setattr(store, "load_snapshot", lambda: (metadata, []))
    monkeypatch.setattr(store, "_open_collection", lambda *args, **kwargs: fake_collection)
    monkeypatch.setattr(store, "_embed_texts", lambda texts: [[0.1, 0.2, 0.3]])
    monkeypatch.setattr(store, "_decode_content_unit", lambda metadata_payload, document=None: expected_symbol)

    results = store.query("sample", top_k=3, scope=IndexScope.CODE, file_path="src/sample.py")

    assert fake_collection.where == {
        "$and": [
            {"scope": IndexScope.CODE.value},
            {"file_path": expected_file},
        ]
    }
    assert len(results) == 1
    assert results[0].content.file_path == expected_symbol.file_path
