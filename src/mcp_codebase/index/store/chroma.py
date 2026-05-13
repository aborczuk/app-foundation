"""Persistent Chroma-backed vector store used by the index service."""

from __future__ import annotations

import gc
import json
import logging
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, Sequence

from src.mcp_codebase.index.config import (
    DEFAULT_EMBEDDING_MODEL_NAME,
    IndexConfig,
    embedding_model_cache_path,
)
from src.mcp_codebase.index.domain import CodeSymbol, IndexMetadata, IndexScope, MarkdownSection, QueryResult

try:  # pragma: no cover - exercised in integration/runtime verification
    import chromadb  # type: ignore[import-not-found]
    from chromadb.api.client import SharedSystemClient  # type: ignore[import-not-found]
    from chromadb.config import Settings  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - handled with a clear runtime error
    chromadb = None
    SharedSystemClient = None
    Settings = None

try:  # pragma: no cover - exercised in integration/runtime verification
    from fastembed import TextEmbedding  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - handled with a clear runtime error
    TextEmbedding = None

_EMBEDDING_MODEL_ALIASES = {"local-default": DEFAULT_EMBEDDING_MODEL_NAME}
_COSINE_COLLECTION_METADATA = {"hnsw:space": "cosine"}
_NO_OP_TELEMETRY_IMPL = "src.mcp_codebase.index.telemetry.NoOpProductTelemetry"
_UPSERT_BATCH_SIZE_FALLBACK = 1000
_EMBED_BATCH_SIZE = 256
_MAX_STAGING_DIRS = 16
_STAGING_ALERT_DIR_COUNT = 32
_STAGING_ALERT_BYTES = 8 * 1024**3
_MIN_FREE_BYTES = 5 * 1024**3
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PreparedChunk:
    """Serialized content unit plus its vector embedding."""

    record_id: str
    document: str
    metadata: dict[str, object]
    embedding: list[float]
    content: CodeSymbol | MarkdownSection


class _FastEmbedBackend:
    """Thin wrapper around fastembed so the store can own embedding lifecycle."""

    def __init__(self, model_name: str, *, cache_dir: Path) -> None:
        if TextEmbedding is None:
            raise RuntimeError(
                "fastembed is required for the vector index; run `uv sync` after adding the dependency."
            )
        self._model_name = model_name
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = TextEmbedding(model_name=model_name, cache_dir=str(cache_dir))

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = list(self._model.embed(list(texts)))
        return [[float(value) for value in vector] for vector in vectors]


class ChromaIndexStore:
    """Persist and query vector-index snapshots on local disk."""

    def __init__(self, config: IndexConfig) -> None:
        """Create a store rooted at the configured database path."""
        self._config = config
        self._db_root = config.db_path
        self._active_manifest_path = self._db_root / "active.json"
        self._previous_manifest_path = self._db_root / "previous.json"
        self._active_collection_path = self._db_root / "active"
        self._previous_collection_path = self._db_root / "previous"
        self._staging_root = self._db_root / "staging"
        self._embedding_backend: _FastEmbedBackend | None = None

    @property
    def config(self) -> IndexConfig:
        """Expose the store configuration."""
        return self._config

    @property
    def embedding_model(self) -> str:
        """Return the resolved embedding model name."""
        return _resolve_embedding_model_name(self._config.embedding_model)

    @property
    def embedding_cache_dir(self) -> Path:
        """Return the repo-local cache directory for embedding models."""
        return self._config.embedding_cache_dir

    def ensure_embedding_model_local(self) -> dict[str, object]:
        """Prime the configured embedding model cache and return local cache details."""
        backend = self._ensure_embedding_backend()
        # Trigger a real embedding pass so missing model weights are downloaded eagerly.
        backend.embed_texts(["vector-index-bootstrap"])
        model_cache_path = embedding_model_cache_path(self.embedding_cache_dir, backend.model_name)
        if not model_cache_path.exists():
            fallback_candidates = sorted(self.embedding_cache_dir.glob("models--*"))
            if fallback_candidates:
                model_cache_path = fallback_candidates[0]
        return {
            "embedding_model": backend.model_name,
            "embedding_cache_dir": str(self.embedding_cache_dir),
            "embedding_model_cache_path": str(model_cache_path),
            "embedding_model_cache_present": model_cache_path.exists(),
        }

    def write_snapshot(
        self,
        content_units: Sequence[CodeSymbol | MarkdownSection],
        metadata: IndexMetadata,
    ) -> IndexMetadata:
        """Stage a snapshot and atomically swap it into place."""
        self._apply_staging_guardrails()
        staging_run_dir = self._staging_root / uuid.uuid4().hex
        self._db_root.mkdir(parents=True, exist_ok=True)
        staging_run_dir.mkdir(parents=True, exist_ok=False)

        try:
            start = monotonic()
            logger.info(
                "vector-index: staging snapshot entries=%d target=%s",
                len(content_units),
                staging_run_dir,
            )
            chunks = self._prepare_chunks(content_units)
            logger.info(
                "vector-index: prepared %d chunks in %.2fs",
                len(chunks),
                monotonic() - start,
            )
            collection = self._open_collection(staging_run_dir, metadata.collection_name, create=True)
            if chunks:
                upsert_start = monotonic()
                logger.info("vector-index: upserting %d chunks", len(chunks))
                self._upsert_chunks_in_batches(collection, chunks)
                logger.info(
                    "vector-index: upsert complete in %.2fs",
                    monotonic() - upsert_start,
                )
            self._close_collection(collection)
            del collection
            gc.collect()

            activate_start = monotonic()
            logger.info("vector-index: activating snapshot")
            self._activate_snapshot(staging_run_dir)
            active_metadata = metadata.model_copy(
                update={"snapshot_path": str(self._active_collection_path)}
            )
            self._write_manifest(active_metadata)
            logger.info(
                "vector-index: snapshot activated in %.2fs",
                monotonic() - activate_start,
            )
        except Exception:
            shutil.rmtree(staging_run_dir, ignore_errors=True)
            raise

        logger.info(
            "vector-index: staged snapshot complete in %.2fs",
            monotonic() - start,
        )
        return active_metadata

    def refresh_snapshot(
        self,
        content_units: Sequence[CodeSymbol | MarkdownSection],
        metadata: IndexMetadata,
    ) -> IndexMetadata:
        """Refresh the active snapshot while preserving the previous one."""
        return self.write_snapshot(content_units, metadata)

    def refresh_changed_snapshot(
        self,
        *,
        changed_paths: Sequence[str | Path],
        changed_units: Sequence[CodeSymbol | MarkdownSection],
        metadata: IndexMetadata,
    ) -> IndexMetadata:
        """Refresh changed paths by cloning active snapshot and patching changed records only."""
        active_metadata = self._load_active_metadata()
        if active_metadata is None:
            return self.write_snapshot(changed_units, metadata)

        self._apply_staging_guardrails()
        active_snapshot_path = Path(active_metadata.snapshot_path)
        changed_path_set = {
            _normalize_index_path(path, self._config.repo_root)
            for path in changed_paths
        }

        staging_run_dir = self._staging_root / uuid.uuid4().hex
        self._db_root.mkdir(parents=True, exist_ok=True)
        try:
            start = monotonic()
            logger.info(
                "vector-index: cloning active snapshot source=%s target=%s",
                active_snapshot_path,
                staging_run_dir,
            )
            shutil.copytree(active_snapshot_path, staging_run_dir, dirs_exist_ok=False)

            collection = self._open_collection(
                staging_run_dir,
                active_metadata.collection_name,
                create=False,
            )
            payload = collection.get(include=["metadatas"])
            ids = _payload_sequence(payload, "ids")
            metadatas = _payload_sequence(payload, "metadatas")
            delete_ids: list[str] = []
            for index, record_id in enumerate(ids):
                metadata_payload = metadatas[index] if index < len(metadatas) else None
                if not isinstance(metadata_payload, dict):
                    continue
                file_path = str(metadata_payload.get("file_path", ""))
                if file_path in changed_path_set:
                    delete_ids.append(str(record_id))
            if delete_ids:
                logger.info("vector-index: deleting %d changed-path chunks", len(delete_ids))
                self._delete_ids_in_batches(collection, delete_ids)

            changed_chunks = self._prepare_chunks(changed_units)
            if changed_chunks:
                upsert_start = monotonic()
                logger.info("vector-index: upserting %d changed chunks", len(changed_chunks))
                self._upsert_chunks_in_batches(collection, changed_chunks)
                logger.info(
                    "vector-index: changed chunk upsert complete in %.2fs",
                    monotonic() - upsert_start,
                )
            self._close_collection(collection)
            del collection
            gc.collect()

            activate_start = monotonic()
            logger.info("vector-index: activating snapshot")
            self._activate_snapshot(staging_run_dir)
            next_metadata = metadata.model_copy(
                update={
                    "snapshot_path": str(self._active_collection_path),
                    "collection_name": active_metadata.collection_name,
                }
            )
            self._write_manifest(next_metadata)
            logger.info(
                "vector-index: snapshot activated in %.2fs",
                monotonic() - activate_start,
            )
        except Exception:
            shutil.rmtree(staging_run_dir, ignore_errors=True)
            raise

        logger.info(
            "vector-index: staged snapshot complete in %.2fs",
            monotonic() - start,
        )
        return next_metadata

    def _load_active_metadata(self) -> IndexMetadata | None:
        """Return active snapshot metadata without decoding full collection contents."""
        if not self._active_manifest_path.exists():
            return None
        metadata = IndexMetadata.model_validate(
            json.loads(self._active_manifest_path.read_text(encoding="utf-8"))
        )
        if not Path(metadata.snapshot_path).exists():
            return None
        return metadata

    def load_snapshot(self) -> tuple[IndexMetadata, list[CodeSymbol | MarkdownSection]] | None:
        """Load the active snapshot if present."""
        if not self._active_manifest_path.exists():
            return None

        metadata = IndexMetadata.model_validate(
            json.loads(self._active_manifest_path.read_text(encoding="utf-8"))
        )
        snapshot_path = Path(metadata.snapshot_path)
        if not snapshot_path.exists():
            return None

        collection = self._open_collection(snapshot_path, metadata.collection_name, create=False)
        try:
            payload = collection.get(include=["metadatas", "documents"])
        finally:
            self._close_collection(collection)
            del collection
            gc.collect()
        metadatas = payload.get("metadatas") or []
        documents = payload.get("documents") or []
        if not metadatas:
            return metadata, []

        records = [
            self._decode_content_unit(item, documents[index] if index < len(documents) else None)
            for index, item in enumerate(metadatas)
            if item
        ]
        return metadata, records

    def status(self) -> IndexMetadata | None:
        """Return the active snapshot metadata if the index exists."""
        snapshot = self.load_snapshot()
        if snapshot is None:
            return None
        metadata, _ = snapshot
        return metadata

    def query(
        self,
        query_text: str,
        *,
        top_k: int = 10,
        scope: IndexScope | None = None,
        file_path: str | Path | None = None,
    ) -> list[QueryResult]:
        """Return ranked query results from the active snapshot."""
        snapshot = self.load_snapshot()
        if snapshot is None or not query_text.strip():
            return []

        metadata, _ = snapshot
        collection = self._open_collection(Path(metadata.snapshot_path), metadata.collection_name, create=False)
        try:
            query_embedding = self._embed_texts([query_text])[0]
            where_filters: list[dict[str, object]] = []
            if scope is not None:
                where_filters.append({"scope": scope.value})
            if file_path is not None:
                where_filters.append({"file_path": _normalize_index_path(file_path, self._config.repo_root)})
            if len(where_filters) > 1:
                where: dict[str, object] | None = {"$and": where_filters}
            elif where_filters:
                where = where_filters[0]
            else:
                where = None
            candidate_count = max(top_k * 4, top_k)
            result = collection.query(
                query_embeddings=[query_embedding],
                n_results=candidate_count,
                where=where,
                include=["distances", "metadatas", "documents"],
            )
        finally:
            self._close_collection(collection)
            del collection
            gc.collect()

        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        if not metadatas:
            return []

        ranked: list[QueryResult] = []
        for rank, metadata_payload in enumerate(metadatas, start=1):
            content = self._decode_content_unit(metadata_payload, documents[rank - 1] if rank - 1 < len(documents) else None)
            distance = distances[rank - 1] if rank - 1 < len(distances) else None
            score = _distance_to_score(distance)
            ranked.append(
                QueryResult(
                    rank=rank,
                    score=score,
                    content=content,
                )
            )
        ranked.sort(key=lambda item: (-item.score, item.file_path.as_posix(), item.line_start, item.line_end))
        return [item.model_copy(update={"rank": index}) for index, item in enumerate(ranked[:top_k], start=1)]

    def list_file_code_symbols(self, file_path: str | Path) -> list[CodeSymbol]:
        """Return deterministic code symbols for a single file from the active snapshot."""
        snapshot = self.load_snapshot()
        if snapshot is None:
            return []

        metadata, _ = snapshot
        normalized_file = _normalize_index_path(file_path, self._config.repo_root)
        collection = self._open_collection(
            Path(metadata.snapshot_path),
            metadata.collection_name,
            create=False,
        )
        try:
            payload = collection.get(
                where={
                    "$and": [
                        {"scope": IndexScope.CODE.value},
                        {"record_type": "code"},
                        {"file_path": normalized_file},
                    ]
                },
                include=["metadatas"],
            )
        finally:
            self._close_collection(collection)
            del collection
            gc.collect()
        metadatas = _payload_sequence(payload, "metadatas")

        symbols: list[CodeSymbol] = []
        for metadata_payload in metadatas:
            if not isinstance(metadata_payload, dict):
                continue
            content = self._decode_content_unit(metadata_payload)
            if isinstance(content, CodeSymbol):
                symbols.append(content)

        symbols.sort(
            key=lambda item: (
                item.line_start,
                item.line_end,
                item.symbol_type,
                item.symbol_name,
                item.qualified_name,
            )
        )
        return symbols

    def _prepare_chunks(self, content_units: Sequence[CodeSymbol | MarkdownSection]) -> list[_PreparedChunk]:
        embedding_inputs = [_embedding_text(unit) for unit in content_units]
        logger.info("vector-index: embedding %d texts", len(embedding_inputs))
        embed_start = monotonic()
        embeddings = self._embed_texts(embedding_inputs)
        logger.info("vector-index: embedded %d texts in %.2fs", len(embedding_inputs), monotonic() - embed_start)
        chunks: list[_PreparedChunk] = []
        for unit, embedding in zip(content_units, embeddings, strict=True):
            metadata = _record_metadata(unit)
            chunks.append(
                _PreparedChunk(
                    record_id=_record_id(unit),
                    document=_embedding_text(unit),
                    metadata=metadata,
                    embedding=embedding,
                    content=unit,
                )
            )
        return chunks

    def _embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        backend = self._ensure_embedding_backend()
        total = len(texts)
        if total == 0:
            return []

        batch_size = min(_EMBED_BATCH_SIZE, total)
        vectors: list[list[float]] = []
        embed_start = monotonic()
        logger.info("vector-index: embedding %d texts in batches of %d", total, batch_size)
        for start in range(0, total, batch_size):
            batch = list(texts[start : start + batch_size])
            batch_start = monotonic()
            batch_vectors = backend.embed_texts(batch)
            vectors.extend(batch_vectors)
            logger.info(
                "vector-index: embedded %d/%d texts in %.2fs",
                min(start + len(batch), total),
                total,
                monotonic() - batch_start,
            )
        logger.info("vector-index: embedding backend returned %d vectors in %.2fs", len(vectors), monotonic() - embed_start)
        return vectors

    def _ensure_embedding_backend(self) -> _FastEmbedBackend:
        if self._embedding_backend is None:
            self._embedding_backend = _FastEmbedBackend(
                self.embedding_model,
                cache_dir=self.embedding_cache_dir,
            )
        return self._embedding_backend

    def _open_collection(self, collection_dir: Path, collection_name: str, *, create: bool) -> Any:
        if chromadb is None:
            raise RuntimeError(
                "chromadb is required for the vector index; run `uv sync` after adding the dependency."
            )

        collection_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(collection_dir), settings=_chroma_settings(collection_dir))
        if create:
            return client.get_or_create_collection(
                name=collection_name,
                metadata=_COSINE_COLLECTION_METADATA,
            )
        try:
            return client.get_collection(name=collection_name)
        except Exception as exc:  # pragma: no cover - safety net for partially initialized collections
            raise RuntimeError(f"Vector index collection is not available at {collection_dir}") from exc

    def _close_collection(self, collection: Any) -> None:
        """Best-effort shutdown for the Chroma client behind a collection handle."""
        client = getattr(collection, "_client", None)
        system = getattr(client, "_system", None)
        stop = getattr(system, "stop", None)
        if callable(stop):
            stop()
        if SharedSystemClient is not None:
            SharedSystemClient.clear_system_cache()

    def _collection_batch_size(self, collection: Any) -> int:
        """Return the largest safe per-call mutation batch size for the active Chroma client."""
        for candidate in (
            getattr(collection, "max_batch_size", None),
            getattr(getattr(collection, "_client", None), "max_batch_size", None),
        ):
            value = candidate() if callable(candidate) else candidate
            if isinstance(value, int) and value > 0:
                return value
        return _UPSERT_BATCH_SIZE_FALLBACK

    def _delete_ids_in_batches(self, collection: Any, ids: Sequence[str]) -> None:
        """Delete record ids in bounded batches to avoid backend mutation limits."""
        if not ids:
            return
        batch_size = self._collection_batch_size(collection)
        for start in range(0, len(ids), batch_size):
            batch_ids = list(ids[start : start + batch_size])
            collection.delete(ids=batch_ids)

    def _upsert_chunks_in_batches(self, collection: Any, chunks: Sequence[_PreparedChunk]) -> None:
        """Upsert prepared chunks in bounded batches to avoid backend mutation limits."""
        if not chunks:
            return
        batch_size = self._collection_batch_size(collection)
        logger.info("vector-index: upserting %d chunks in batches of %d", len(chunks), batch_size)
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            batch_start = monotonic()
            collection.upsert(
                ids=[chunk.record_id for chunk in batch],
                documents=[chunk.document for chunk in batch],
                embeddings=[chunk.embedding for chunk in batch],
                metadatas=[chunk.metadata for chunk in batch],
            )
            logger.info(
                "vector-index: upserted %d/%d chunks in %.2fs",
                min(start + len(batch), len(chunks)),
                len(chunks),
                monotonic() - batch_start,
            )

    def _activate_snapshot(self, staging_run_dir: Path) -> None:
        """Promote a completed staging snapshot into active/previous collection paths."""
        self._staging_root.mkdir(parents=True, exist_ok=True)
        if self._previous_collection_path.exists():
            shutil.rmtree(self._previous_collection_path, ignore_errors=True)
        if self._active_collection_path.exists():
            shutil.move(str(self._active_collection_path), str(self._previous_collection_path))
        shutil.move(str(staging_run_dir), str(self._active_collection_path))

    def _apply_staging_guardrails(self) -> None:
        """Prune orphaned staging snapshots and fail fast when disk headroom is too low."""
        self._staging_root.mkdir(parents=True, exist_ok=True)
        self._prune_orphaned_staging_dirs()
        staging_dirs = self._list_staging_dirs()
        staging_bytes = sum(self._dir_size_bytes(path) for path in staging_dirs)
        if len(staging_dirs) >= _STAGING_ALERT_DIR_COUNT or staging_bytes >= _STAGING_ALERT_BYTES:
            logger.warning(
                "vector-index: excessive staging retention count=%d bytes=%d root=%s",
                len(staging_dirs),
                staging_bytes,
                self._staging_root,
            )
        free_bytes = self._available_free_bytes()
        if free_bytes < _MIN_FREE_BYTES:
            raise RuntimeError(
                "vector-index staging capacity critically low: "
                f"free_bytes={free_bytes} staging_root={self._staging_root}"
            )

    def _prune_orphaned_staging_dirs(self) -> None:
        """Keep only a bounded number of orphaned staging snapshots on disk."""
        staging_dirs = self._list_staging_dirs()
        stale_dirs = staging_dirs[:-_MAX_STAGING_DIRS]
        if not stale_dirs:
            return
        for stale_dir in stale_dirs:
            shutil.rmtree(stale_dir, ignore_errors=True)
        logger.warning(
            "vector-index: pruned %d orphaned staging snapshots under %s",
            len(stale_dirs),
            self._staging_root,
        )

    def _list_staging_dirs(self) -> list[Path]:
        """Return staging directories ordered from oldest to newest."""
        if not self._staging_root.exists():
            return []
        return sorted(
            (path for path in self._staging_root.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
        )

    def _available_free_bytes(self) -> int:
        """Return available free bytes for the vector-index filesystem."""
        return shutil.disk_usage(self._db_root).free

    def _dir_size_bytes(self, directory: Path) -> int:
        """Return the recursive size of a directory for staging telemetry."""
        total = 0
        for child in directory.rglob("*"):
            if child.is_file():
                total += child.stat().st_size
        return total

    def _write_manifest(self, metadata: IndexMetadata) -> None:
        if self._active_manifest_path.exists():
            self._previous_manifest_path.write_text(
                self._active_manifest_path.read_text(encoding="utf-8"), encoding="utf-8"
            )
        self._active_manifest_path.write_text(
            json.dumps(metadata.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _decode_content_unit(
        self,
        payload: dict[str, Any],
        document: str | None = None,
    ) -> CodeSymbol | MarkdownSection:
        record_type = str(payload.get("record_type", ""))
        if record_type == "code":
            return CodeSymbol(
                symbol_name=str(payload.get("symbol_name", "")),
                symbol_type=str(payload.get("symbol_type", "symbol")),
                qualified_name=str(payload.get("qualified_name", "")),
                signature=str(payload.get("signature", "")),
                docstring=str(payload.get("docstring", "")),
                body=str(payload.get("body", "")) or (document or ""),
                file_path=Path(str(payload.get("file_path", "."))),
                line_start=int(payload.get("line_start", 1)),
                line_end=int(payload.get("line_end", 1)),
                preview=str(payload.get("preview", "")),
                content_hash=str(payload.get("content_hash", "")),
                scope=IndexScope(str(payload.get("scope", IndexScope.CODE.value))),
            )
        if record_type == "markdown":
            breadcrumb = json.loads(str(payload.get("breadcrumb_json", "[]")))
            return MarkdownSection(
                heading=str(payload.get("heading", "")),
                symbol_type=str(payload.get("symbol_type", "section")),
                body=str(payload.get("body", "")) or (document or ""),
                breadcrumb=tuple(str(item) for item in breadcrumb),
                depth=int(payload.get("depth", 1)),
                file_path=Path(str(payload.get("file_path", "."))),
                line_start=int(payload.get("line_start", 1)),
                line_end=int(payload.get("line_end", 1)),
                preview=str(payload.get("preview", "")),
                content_hash=str(payload.get("content_hash", "")),
                scope=IndexScope(str(payload.get("scope", IndexScope.MARKDOWN.value))),
            )
        raise ValueError("unknown record type in vector payload")


def _embedding_text(unit: CodeSymbol | MarkdownSection) -> str:
    if isinstance(unit, CodeSymbol):
        parts = [unit.qualified_name, unit.symbol_name, unit.signature, unit.docstring, unit.body]
    else:
        parts = [unit.heading, unit.body, unit.preview]
    return "\n\n".join(part for part in parts if part)


def _record_id(unit: CodeSymbol | MarkdownSection) -> str:
    return f"{unit.scope.value}:{unit.file_path.as_posix()}:{unit.line_start}:{unit.line_end}:{unit.content_hash}"


def _record_metadata(unit: CodeSymbol | MarkdownSection) -> dict[str, object]:
    common: dict[str, object] = {
        "record_type": "code" if isinstance(unit, CodeSymbol) else "markdown",
        "file_path": unit.file_path.as_posix(),
        "line_start": unit.line_start,
        "line_end": unit.line_end,
        "scope": unit.scope.value,
        "content_hash": unit.content_hash,
        "preview": unit.preview,
        "symbol_type": unit.symbol_type,
    }
    if isinstance(unit, CodeSymbol):
        common.update(
            {
                "symbol_name": unit.symbol_name,
                "qualified_name": unit.qualified_name,
                "signature": unit.signature,
                "docstring": unit.docstring,
                "body": unit.body,
                "breadcrumb_json": "[]",
                "heading": "",
                "depth": 0,
            }
        )
    else:
        common.update(
            {
                "symbol_name": "",
                "qualified_name": "",
                "signature": "",
                "docstring": "",
                "body": unit.body,
                "breadcrumb_json": json.dumps(list(unit.breadcrumb)),
                "heading": unit.heading,
                "depth": unit.depth,
            }
        )
    return common


def _normalize_index_path(file_path: str | Path, repo_root: str | Path) -> str:
    root = Path(repo_root).expanduser().resolve()
    candidate = Path(file_path).expanduser()
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate.as_posix()


def _payload_sequence(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if value is None:
        return []
    return list(value)


def _distance_to_score(distance: float | None) -> float:
    if distance is None:
        return 0.0
    return round(max(0.0, 1.0 - float(distance)), 4)


def _resolve_embedding_model_name(configured_model: str) -> str:
    return _EMBEDDING_MODEL_ALIASES.get(configured_model, configured_model)


def _chroma_settings(collection_dir: Path) -> Any:
    if Settings is None:
        raise RuntimeError("chromadb settings are unavailable; run `uv sync`.")
    return Settings(
        is_persistent=True,
        persist_directory=str(collection_dir),
        anonymized_telemetry=False,
        chroma_product_telemetry_impl=_NO_OP_TELEMETRY_IMPL,
        chroma_telemetry_impl=_NO_OP_TELEMETRY_IMPL,
    )
