"""Persistent Chroma-backed vector store used by the index service."""

from __future__ import annotations

import gc
import logging
import json
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from time import monotonic

from src.mcp_codebase.index.config import IndexConfig
from src.mcp_codebase.index.domain import CodeSymbol, IndexMetadata, IndexScope, MarkdownSection, QueryResult

try:  # pragma: no cover - exercised in integration/runtime verification
    import chromadb  # type: ignore[import-not-found]
    from chromadb.config import Settings  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - handled with a clear runtime error
    chromadb = None
    Settings = None

try:  # pragma: no cover - exercised in integration/runtime verification
    from fastembed import TextEmbedding  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - handled with a clear runtime error
    TextEmbedding = None

_DEFAULT_FASTEMBED_MODEL = "BAAI/bge-small-en-v1.5"
_EMBEDDING_MODEL_ALIASES = {"local-default": _DEFAULT_FASTEMBED_MODEL}
_COSINE_COLLECTION_METADATA = {"hnsw:space": "cosine"}
_NO_OP_TELEMETRY_IMPL = "src.mcp_codebase.index.telemetry.NoOpProductTelemetry"
_MIN_QUERY_SCORE = 0.55
_HIGH_CONFIDENCE_QUERY_SCORE = 0.8
_MARKDOWN_COMMAND_DOC_PENALTY = 0.25
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

    def __init__(self, model_name: str) -> None:
        if TextEmbedding is None:
            raise RuntimeError(
                "fastembed is required for the vector index; run `uv sync` after adding the dependency."
            )
        self._model_name = model_name
        self._model = TextEmbedding(model_name=model_name)

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

    def write_snapshot(
        self,
        content_units: Sequence[CodeSymbol | MarkdownSection],
        metadata: IndexMetadata,
    ) -> IndexMetadata:
        """Stage a snapshot and atomically swap it into place."""
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
                collection.upsert(
                    ids=[chunk.record_id for chunk in chunks],
                    documents=[chunk.document for chunk in chunks],
                    embeddings=[chunk.embedding for chunk in chunks],
                    metadatas=[chunk.metadata for chunk in chunks],
                )
                del collection
                gc.collect()
                logger.info(
                    "vector-index: upsert complete in %.2fs",
                    monotonic() - upsert_start,
                )

            activate_start = monotonic()
            logger.info("vector-index: activating snapshot")
            self._activate_snapshot(staging_run_dir)
            self._write_manifest(metadata.model_copy(update={"snapshot_path": str(staging_run_dir)}))
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
        return metadata.model_copy(update={"snapshot_path": str(staging_run_dir)})

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
        """Refresh changed paths while reusing unchanged embeddings from the active snapshot."""
        snapshot = self.load_snapshot()
        if snapshot is None:
            return self.write_snapshot(changed_units, metadata)

        active_metadata, _ = snapshot
        active_snapshot_path = Path(active_metadata.snapshot_path)
        active_collection = self._open_collection(active_snapshot_path, active_metadata.collection_name, create=False)
        payload = active_collection.get(include=["metadatas", "documents", "embeddings"])

        changed_path_set = {
            _normalize_index_path(path, self._config.repo_root)
            for path in changed_paths
        }
        ids = _payload_sequence(payload, "ids")
        metadatas = _payload_sequence(payload, "metadatas")
        documents = _payload_sequence(payload, "documents")
        embeddings = _payload_sequence(payload, "embeddings")

        retained_ids: list[str] = []
        retained_metadatas: list[dict[str, object]] = []
        retained_documents: list[str] = []
        retained_embeddings: list[list[float]] = []

        for index, record_id in enumerate(ids):
            metadata_payload = metadatas[index] if index < len(metadatas) else None
            if not isinstance(metadata_payload, dict):
                continue
            file_path = str(metadata_payload.get("file_path", ""))
            if file_path in changed_path_set:
                continue

            retained_ids.append(str(record_id))
            retained_metadatas.append(metadata_payload)

            document = documents[index] if index < len(documents) else ""
            retained_documents.append(str(document or ""))

            embedding_vector = embeddings[index] if index < len(embeddings) else None
            if embedding_vector is None:
                embedding_vector = self._embed_texts([retained_documents[-1]])[0]
            retained_embeddings.append([float(value) for value in embedding_vector])

        logger.info(
            "vector-index: reusing %d unchanged embeddings; embedding %d changed texts",
            len(retained_ids),
            len(changed_units),
        )
        changed_chunks = self._prepare_chunks(changed_units)

        staging_run_dir = self._staging_root / uuid.uuid4().hex
        self._db_root.mkdir(parents=True, exist_ok=True)
        staging_run_dir.mkdir(parents=True, exist_ok=False)
        try:
            start = monotonic()
            total_entries = len(retained_ids) + len(changed_chunks)
            logger.info(
                "vector-index: staging snapshot entries=%d target=%s",
                total_entries,
                staging_run_dir,
            )
            collection = self._open_collection(staging_run_dir, metadata.collection_name, create=True)
            if retained_ids:
                upsert_start = monotonic()
                logger.info("vector-index: upserting %d reused chunks", len(retained_ids))
                collection.upsert(
                    ids=retained_ids,
                    documents=retained_documents,
                    embeddings=retained_embeddings,
                    metadatas=retained_metadatas,
                )
                logger.info(
                    "vector-index: reused chunk upsert complete in %.2fs",
                    monotonic() - upsert_start,
                )
            if changed_chunks:
                upsert_start = monotonic()
                logger.info("vector-index: upserting %d changed chunks", len(changed_chunks))
                collection.upsert(
                    ids=[chunk.record_id for chunk in changed_chunks],
                    documents=[chunk.document for chunk in changed_chunks],
                    embeddings=[chunk.embedding for chunk in changed_chunks],
                    metadatas=[chunk.metadata for chunk in changed_chunks],
                )
                logger.info(
                    "vector-index: changed chunk upsert complete in %.2fs",
                    monotonic() - upsert_start,
                )
            del collection
            gc.collect()

            activate_start = monotonic()
            logger.info("vector-index: activating snapshot")
            self._activate_snapshot(staging_run_dir)
            self._write_manifest(metadata.model_copy(update={"snapshot_path": str(staging_run_dir)}))
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
        return metadata.model_copy(update={"snapshot_path": str(staging_run_dir)})

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
        payload = collection.get(include=["metadatas", "documents"])
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
    ) -> list[QueryResult]:
        """Return ranked query results from the active snapshot."""
        snapshot = self.load_snapshot()
        if snapshot is None or not query_text.strip():
            return []

        metadata, _ = snapshot
        collection = self._open_collection(Path(metadata.snapshot_path), metadata.collection_name, create=False)
        query_embedding = self._embed_texts([query_text])[0]
        where = {"scope": scope.value} if scope is not None else None
        candidate_count = max(top_k * 4, top_k)
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=candidate_count,
            where=where,
            include=["distances", "metadatas", "documents"],
        )

        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        if not metadatas:
            return []

        ranked: list[QueryResult] = []
        for rank, metadata_payload in enumerate(metadatas, start=1):
            content = self._decode_content_unit(metadata_payload, documents[rank - 1] if rank - 1 < len(documents) else None)
            distance = distances[rank - 1] if rank - 1 < len(distances) else None
            score = _score_query_result(_distance_to_score(distance), query_text, content)
            if score < _MIN_QUERY_SCORE:
                continue
            ranked.append(
                QueryResult(
                    rank=rank,
                    score=score,
                    content=content,
                )
            )
        ranked.sort(key=lambda item: (-item.score, item.file_path.as_posix(), item.line_start, item.line_end))
        return [item.model_copy(update={"rank": index}) for index, item in enumerate(ranked[:top_k], start=1)]

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
        embed_start = monotonic()
        vectors = backend.embed_texts(texts)
        logger.info("vector-index: embedding backend returned %d vectors in %.2fs", len(vectors), monotonic() - embed_start)
        return vectors

    def _ensure_embedding_backend(self) -> _FastEmbedBackend:
        if self._embedding_backend is None:
            self._embedding_backend = _FastEmbedBackend(self.embedding_model)
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

    def _activate_snapshot(self, staging_run_dir: Path) -> None:
        return None

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


def _score_query_result(score: float, query_text: str, content: CodeSymbol | MarkdownSection) -> float:
    overlap_count = _token_overlap_count(query_text, content)
    if overlap_count == 0 and score < _HIGH_CONFIDENCE_QUERY_SCORE:
        return 0.0
    if content.scope is IndexScope.MARKDOWN and ".claude" in content.file_path.parts and "commands" in content.file_path.parts:
        score -= _MARKDOWN_COMMAND_DOC_PENALTY
    if overlap_count:
        query_token_count = max(1, len(_tokenize_text(query_text)))
        score += 0.15 * (overlap_count / query_token_count)
    return round(min(1.0, max(0.0, score)), 4)


def _token_overlap_count(query_text: str, content: CodeSymbol | MarkdownSection) -> int:
    query_tokens = set(_tokenize_text(query_text))
    if not query_tokens:
        return 0
    content_tokens = set(_tokenize_text(_embedding_text(content)))
    return len(query_tokens & content_tokens)


def _tokenize_text(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_]+", text.lower())


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
