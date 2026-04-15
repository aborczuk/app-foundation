"""Local snapshot-backed vector store used by the index service."""

from __future__ import annotations

import json
import math
import re
import shutil
import uuid
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

from src.mcp_codebase.index.config import IndexConfig
from src.mcp_codebase.index.domain import CodeSymbol, IndexMetadata, IndexScope, MarkdownSection, QueryResult


class ChromaIndexStore:
    """Persist and query vector-index snapshots on local disk."""

    def __init__(self, config: IndexConfig) -> None:
        self._config = config
        self._db_root = config.db_path
        self._active_snapshot_path = self._db_root / "active.json"
        self._previous_snapshot_path = self._db_root / "previous.json"
        self._staging_dir = self._db_root / "staging"

    @property
    def config(self) -> IndexConfig:
        """Expose the store configuration."""

        return self._config

    def write_snapshot(
        self,
        content_units: Sequence[CodeSymbol | MarkdownSection],
        metadata: IndexMetadata,
    ) -> IndexMetadata:
        """Stage a snapshot and atomically swap it into place."""

        self._db_root.mkdir(parents=True, exist_ok=True)
        self._staging_dir.mkdir(parents=True, exist_ok=True)

        snapshot_path = self._staging_dir / f"{uuid.uuid4().hex}.json"
        snapshot_path.write_text(
            json.dumps(
                {
                    "metadata": metadata.model_dump(mode="json"),
                    "records": [self._encode_content_unit(unit) for unit in content_units],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        try:
            self._activate_snapshot(snapshot_path)
        except Exception:
            snapshot_path.unlink(missing_ok=True)
            raise
        else:
            snapshot_path.unlink(missing_ok=True)

        return metadata

    def refresh_snapshot(
        self,
        content_units: Sequence[CodeSymbol | MarkdownSection],
        metadata: IndexMetadata,
    ) -> IndexMetadata:
        """Refresh the active snapshot while preserving the previous one."""

        return self.write_snapshot(content_units, metadata)

    def load_snapshot(self) -> tuple[IndexMetadata, list[CodeSymbol | MarkdownSection]] | None:
        """Load the active snapshot if present."""

        if not self._active_snapshot_path.exists():
            return None

        payload = json.loads(self._active_snapshot_path.read_text(encoding="utf-8"))
        metadata = IndexMetadata.model_validate(payload["metadata"])
        records = [self._decode_content_unit(record) for record in payload["records"]]
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

        _, records = snapshot
        query_tokens = _tokenize(query_text)
        if not query_tokens:
            return []

        scored: list[tuple[float, CodeSymbol | MarkdownSection]] = []
        for record in records:
            if scope is not None and record.scope is not scope:
                continue
            score = _score_record(query_tokens, record)
            if score <= 0.0:
                continue
            scored.append((score, record))

        scored.sort(
            key=lambda item: (
                -item[0],
                item[1].file_path.as_posix(),
                item[1].line_start,
                item[1].line_end,
            )
        )

        return [
            QueryResult(rank=index, score=score, content=record)
            for index, (score, record) in enumerate(scored[:top_k], start=1)
        ]

    def _activate_snapshot(self, snapshot_path: Path) -> None:
        """Swap a staged snapshot into the active slot."""

        if self._active_snapshot_path.exists():
            shutil.copy2(self._active_snapshot_path, self._previous_snapshot_path)
        snapshot_path.replace(self._active_snapshot_path)

    def _encode_content_unit(self, unit: CodeSymbol | MarkdownSection) -> dict[str, object]:
        payload = unit.model_dump(mode="json")
        payload["record_type"] = "code" if isinstance(unit, CodeSymbol) else "markdown"
        return payload

    def _decode_content_unit(self, payload: dict[str, object]) -> CodeSymbol | MarkdownSection:
        record_type = payload.get("record_type")
        if record_type == "code":
            data = {key: value for key, value in payload.items() if key != "record_type"}
            return CodeSymbol.model_validate(data)
        if record_type == "markdown":
            data = {key: value for key, value in payload.items() if key != "record_type"}
            return MarkdownSection.model_validate(data)
        raise ValueError("unknown record type in snapshot payload")


def _tokenize(value: str) -> set[str]:
    return set(re.findall(r"[A-Za-z0-9_]+", value.lower()))


def _score_record(query_tokens: set[str], record: CodeSymbol | MarkdownSection) -> float:
    record_tokens = _tokenize(_record_text(record))
    if not record_tokens:
        return 0.0

    overlap = len(query_tokens & record_tokens)
    if overlap == 0:
        return 0.0

    return round(overlap / math.sqrt(len(query_tokens) * len(record_tokens)), 4)


def _record_text(record: CodeSymbol | MarkdownSection) -> str:
    parts = [
        record.file_path.as_posix(),
        record.preview,
        getattr(record, "signature", ""),
        getattr(record, "docstring", ""),
        getattr(record, "body", ""),
        getattr(record, "qualified_name", ""),
        getattr(record, "heading", ""),
        " ".join(getattr(record, "breadcrumb", ())),
    ]
    return " ".join(part for part in parts if part)
