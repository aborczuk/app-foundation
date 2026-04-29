"""Unit tests for vector-index store progress logging."""

from __future__ import annotations

import logging
from pathlib import Path

from src.mcp_codebase.index import CodeSymbol, IndexConfig
from src.mcp_codebase.index.store import chroma as chroma_store


def test_embed_texts_logs_batch_progress(monkeypatch, tmp_path, caplog) -> None:
    """Embedding should log bounded batch progress for long runs."""

    class FakeBackend:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def embed_texts(self, texts):
            batch = list(texts)
            self.calls.append(batch)
            return [[float(len(batch))] for _ in batch]

    config = IndexConfig(repo_root=tmp_path, db_path=tmp_path / "vector-index", embedding_model="local")
    store = chroma_store.ChromaIndexStore(config)
    backend = FakeBackend()

    monkeypatch.setattr(store, "_ensure_embedding_backend", lambda: backend)
    monkeypatch.setattr(chroma_store, "_EMBED_BATCH_SIZE", 2)
    caplog.set_level(logging.INFO)

    vectors = store._embed_texts(["one", "two", "three"])

    assert backend.calls == [["one", "two"], ["three"]]
    assert vectors == [[2.0], [2.0], [1.0]]
    assert "vector-index: embedding 3 texts in batches of 2" in caplog.text
    assert "vector-index: embedded 2/3 texts" in caplog.text
    assert "vector-index: embedded 3/3 texts" in caplog.text
    assert "vector-index: embedding backend returned 3 vectors" in caplog.text


def test_upsert_chunks_logs_batch_progress(monkeypatch, tmp_path, caplog) -> None:
    """Upserting should log bounded batch progress for long runs."""

    class FakeCollection:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def upsert(self, *, ids, documents, metadatas, embeddings):
            self.calls.append(list(ids))

    config = IndexConfig(repo_root=tmp_path, db_path=tmp_path / "vector-index", embedding_model="local")
    store = chroma_store.ChromaIndexStore(config)
    collection = FakeCollection()
    chunks = [
        chroma_store._PreparedChunk(
            record_id="one",
            document="doc-one",
            metadata={"record_id": "one"},
            embedding=[1.0],
            content=CodeSymbol(
                symbol_name="one",
                qualified_name="one",
                file_path=Path("src/one.py"),
                line_start=1,
                line_end=2,
                signature="def one():",
                docstring="",
                preview="def one():",
            ),
        ),
        chroma_store._PreparedChunk(
            record_id="two",
            document="doc-two",
            metadata={"record_id": "two"},
            embedding=[2.0],
            content=CodeSymbol(
                symbol_name="two",
                qualified_name="two",
                file_path=Path("src/two.py"),
                line_start=1,
                line_end=2,
                signature="def two():",
                docstring="",
                preview="def two():",
            ),
        ),
        chroma_store._PreparedChunk(
            record_id="three",
            document="doc-three",
            metadata={"record_id": "three"},
            embedding=[3.0],
            content=CodeSymbol(
                symbol_name="three",
                qualified_name="three",
                file_path=Path("src/three.py"),
                line_start=1,
                line_end=2,
                signature="def three():",
                docstring="",
                preview="def three():",
            ),
        ),
    ]

    monkeypatch.setattr(store, "_collection_batch_size", lambda collection: 2)
    caplog.set_level(logging.INFO)

    store._upsert_chunks_in_batches(collection, chunks)

    assert collection.calls == [["one", "two"], ["three"]]
    assert "vector-index: upserting 3 chunks in batches of 2" in caplog.text
    assert "vector-index: upserted 2/3 chunks" in caplog.text
    assert "vector-index: upserted 3/3 chunks" in caplog.text
