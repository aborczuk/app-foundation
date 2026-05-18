"""Unit tests for vector-index store progress logging."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

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


def test_activate_snapshot_promotes_active_and_previous(tmp_path: Path) -> None:
    """Activation should move staging into active and rotate the former active into previous."""
    config = IndexConfig(repo_root=tmp_path, db_path=tmp_path / "vector-index", embedding_model="local")
    store = chroma_store.ChromaIndexStore(config)
    store._db_root.mkdir(parents=True, exist_ok=True)

    previous_dir = store._previous_collection_path
    previous_dir.mkdir(parents=True, exist_ok=True)
    (previous_dir / "marker.txt").write_text("old-previous", encoding="utf-8")

    active_dir = store._active_collection_path
    active_dir.mkdir(parents=True, exist_ok=True)
    (active_dir / "marker.txt").write_text("old-active", encoding="utf-8")

    staging_dir = store._staging_root / "incoming"
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "marker.txt").write_text("new-active", encoding="utf-8")

    store._activate_snapshot(staging_dir)

    assert not staging_dir.exists()
    assert (store._active_collection_path / "marker.txt").read_text(encoding="utf-8") == "new-active"
    assert (store._previous_collection_path / "marker.txt").read_text(encoding="utf-8") == "old-active"


def test_apply_staging_guardrails_prunes_oldest_dirs(tmp_path: Path, monkeypatch) -> None:
    """Guardrails should keep only the configured number of orphaned staging dirs."""
    config = IndexConfig(repo_root=tmp_path, db_path=tmp_path / "vector-index", embedding_model="local")
    store = chroma_store.ChromaIndexStore(config)
    store._staging_root.mkdir(parents=True, exist_ok=True)

    for index in range(chroma_store._MAX_STAGING_DIRS + 3):
        stage_dir = store._staging_root / f"stage-{index:02d}"
        stage_dir.mkdir()
        (stage_dir / "marker.txt").write_text(str(index), encoding="utf-8")
        mtime = index + 1
        os.utime(stage_dir, (mtime, mtime))

    monkeypatch.setattr(store, "_available_free_bytes", lambda: chroma_store._MIN_FREE_BYTES + 1)

    store._apply_staging_guardrails()

    remaining = sorted(path.name for path in store._staging_root.iterdir() if path.is_dir())
    assert len(remaining) == chroma_store._MAX_STAGING_DIRS
    assert remaining == [f"stage-{index:02d}" for index in range(3, chroma_store._MAX_STAGING_DIRS + 3)]


def test_select_torch_device_prefers_mps_when_cuda_is_unavailable(monkeypatch) -> None:
    """Device selection should prefer Apple MPS before falling back to CPU."""

    class _FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return False

    class _FakeMps:
        @staticmethod
        def is_available() -> bool:
            return True

    class _FakeBackends:
        mps = _FakeMps()

    class _FakeTorch:
        cuda = _FakeCuda()
        backends = _FakeBackends()

    monkeypatch.setattr(chroma_store, "torch", _FakeTorch())

    assert chroma_store._select_torch_device() == "mps"


def test_local_sequence_reranker_backend_moves_model_to_mps_without_half_precision(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """MPS rerankers should use the accelerator without forcing the CUDA-only half path."""

    class _FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return False

    class _FakeMps:
        @staticmethod
        def is_available() -> bool:
            return True

    class _FakeBackends:
        mps = _FakeMps()

    class _FakeTorch:
        cuda = _FakeCuda()
        backends = _FakeBackends()

    class _FakeTokenizer:
        pass

    class _FakeTokenizerLoader:
        @staticmethod
        def from_pretrained(*_args, **_kwargs) -> _FakeTokenizer:
            return _FakeTokenizer()

    class _FakeModel:
        def __init__(self) -> None:
            self.half_called = False
            self.moved_to: str | None = None
            self.eval_called = False

        def half(self) -> "_FakeModel":
            self.half_called = True
            return self

        def to(self, device: str) -> "_FakeModel":
            self.moved_to = device
            return self

        def eval(self) -> "_FakeModel":
            self.eval_called = True
            return self

    fake_model = _FakeModel()

    class _FakeModelLoader:
        @staticmethod
        def from_pretrained(*_args, **_kwargs) -> _FakeModel:
            return fake_model

    monkeypatch.setattr(chroma_store, "torch", _FakeTorch())
    monkeypatch.setattr(chroma_store, "AutoTokenizer", _FakeTokenizerLoader)
    monkeypatch.setattr(chroma_store, "AutoModelForSequenceClassification", _FakeModelLoader)

    backend = chroma_store._LocalSequenceRerankerBackend(
        "fake-model",
        cache_dir=tmp_path / "reranker-cache",
        local_files_only=True,
    )

    assert backend._device == "mps"
    assert fake_model.half_called is False
    assert fake_model.moved_to == "mps"
    assert fake_model.eval_called is True


def test_apply_staging_guardrails_raises_on_low_disk(tmp_path: Path, monkeypatch) -> None:
    """Guardrails should fail loudly before staging when free space is critically low."""
    config = IndexConfig(repo_root=tmp_path, db_path=tmp_path / "vector-index", embedding_model="local")
    store = chroma_store.ChromaIndexStore(config)
    monkeypatch.setattr(store, "_available_free_bytes", lambda: chroma_store._MIN_FREE_BYTES - 1)

    with pytest.raises(RuntimeError, match="staging capacity critically low"):
        store._apply_staging_guardrails()


def test_ensure_reranker_model_local_primes_cache(monkeypatch, tmp_path: Path) -> None:
    """Bootstrap should report the local reranker cache after a warmup score pass."""

    class FakeRerankerBackend:
        def __init__(self, cache_path: Path) -> None:
            self.model_name = "BAAI/bge-reranker-v2-m3"
            self.cache_path = cache_path
            self.calls: list[tuple[str, tuple[str, ...]]] = []

        def rerank_scores(self, query: str, passages):
            self.calls.append((query, tuple(passages)))
            self.cache_path.mkdir(parents=True, exist_ok=True)
            return [1.0]

    config = IndexConfig(repo_root=tmp_path, db_path=tmp_path / "vector-index", embedding_model="local")
    store = chroma_store.ChromaIndexStore(config)
    cache_path = store.reranker_cache_dir / "models--BAAI--bge-reranker-v2-m3"
    backend = FakeRerankerBackend(cache_path)

    monkeypatch.setattr(store, "_ensure_reranker_backend", lambda: backend)

    payload = store.ensure_reranker_model_local()

    assert backend.calls == [("vector-index-bootstrap", ("vector-index-bootstrap",))]
    assert payload["reranker_model"] == "BAAI/bge-reranker-v2-m3"
    assert payload["reranker_model_cache_path"] == str(cache_path)
    assert payload["reranker_model_cache_present"] is True
