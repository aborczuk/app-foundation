"""Vector index service orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from src.mcp_codebase.index.config import IndexConfig
from src.mcp_codebase.index.domain import CodeSymbol, IndexMetadata, IndexScope, MarkdownSection, QueryResult
from src.mcp_codebase.index.extractors import extract_markdown_sections, extract_python_symbols
from src.mcp_codebase.index.store import ChromaIndexStore


class VectorIndexService:
    """Orchestrate build, query, refresh, and status operations."""

    def __init__(self, config: IndexConfig, *, store: ChromaIndexStore | None = None) -> None:
        self._config = config
        self._store = store or ChromaIndexStore(config)

    @property
    def config(self) -> IndexConfig:
        """Return the active index configuration."""

        return self._config

    def build_full_index(
        self,
        *,
        revision: str = "local",
        source_paths: Sequence[str | Path] | None = None,
    ) -> IndexMetadata:
        """Rebuild the active snapshot from the full repository checkout."""

        content_units = self._collect_content_units(source_paths=source_paths)
        metadata = self._build_metadata(revision=revision, entry_count=len(content_units), is_stale=False, stale_reason="")
        return self._store.write_snapshot(content_units, metadata)

    def query(
        self,
        query_text: str,
        *,
        top_k: int = 10,
        scope: IndexScope | None = None,
    ) -> list[QueryResult]:
        """Query the active snapshot."""

        return self._store.query(query_text, top_k=top_k, scope=scope)

    def refresh_changed_files(
        self,
        changed_paths: Sequence[str | Path],
        *,
        revision: str = "local",
    ) -> IndexMetadata:
        """Refresh only changed content units and keep prior data queryable on failure."""

        existing = self._store.load_snapshot()
        changed_units = self._collect_content_units(changed_paths=changed_paths)

        if existing is None:
            content_units = changed_units
        else:
            _, current_units = existing
            changed_set = {_normalize_path(path, self._config.repo_root) for path in changed_paths}
            retained_units = [unit for unit in current_units if unit.file_path.resolve() not in changed_set]
            content_units = retained_units + changed_units

        metadata = self._build_metadata(revision=revision, entry_count=len(content_units), is_stale=False, stale_reason="")
        return self._store.refresh_snapshot(content_units, metadata)

    def status(self) -> IndexMetadata | None:
        """Return the active snapshot metadata."""

        return self._store.status()

    def _collect_content_units(
        self,
        *,
        source_paths: Sequence[str | Path] | None = None,
        changed_paths: Sequence[str | Path] | None = None,
    ) -> list[CodeSymbol | MarkdownSection]:
        if source_paths is not None and changed_paths is not None:
            raise ValueError("source_paths and changed_paths are mutually exclusive")

        candidate_paths = source_paths if source_paths is not None else changed_paths
        if candidate_paths is None:
            candidate_paths = self._iter_source_files()

        units: list[CodeSymbol | MarkdownSection] = []
        for raw_path in candidate_paths:
            path = _normalize_path(raw_path, self._config.repo_root)
            if path.suffix in {".py", ".pyi"}:
                units.extend(
                    extract_python_symbols(
                        path,
                        repo_root=self._config.repo_root,
                        exclude_patterns=self._config.exclude_patterns,
                    )
                )
            elif path.suffix.lower() in {".md", ".markdown", ".mdown"}:
                units.extend(
                    extract_markdown_sections(
                        path,
                        repo_root=self._config.repo_root,
                        exclude_patterns=self._config.exclude_patterns,
                    )
                )
        return units

    def _iter_source_files(self) -> list[Path]:
        repo_root = self._config.repo_root.resolve()
        files: list[Path] = []
        for path in repo_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".py", ".pyi", ".md", ".markdown", ".mdown"}:
                continue
            files.append(path)
        return files

    def _build_metadata(
        self,
        *,
        revision: str,
        entry_count: int,
        is_stale: bool,
        stale_reason: str,
    ) -> IndexMetadata:
        return IndexMetadata(
            source_root=self._config.repo_root,
            indexed_commit=revision,
            current_commit=revision,
            indexed_at=_utc_now(),
            entry_count=entry_count,
            is_stale=is_stale,
            stale_reason=stale_reason,
            scopes=self._config.default_scopes,
        )


def build_vector_index_service(config: IndexConfig) -> VectorIndexService:
    """Factory for dependency injection and adapters."""

    return VectorIndexService(config)


def _normalize_path(path: str | Path, repo_root: Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = (repo_root.resolve() / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


def _utc_now():
    from datetime import UTC, datetime

    return datetime.now(UTC)
