"""Vector index service orchestration."""

from __future__ import annotations

import logging
import subprocess
import uuid
from pathlib import Path
from typing import Sequence

from src.mcp_codebase.index.config import IndexConfig
from src.mcp_codebase.index.domain import CodeSymbol, IndexMetadata, IndexScope, MarkdownSection, QueryResult
from src.mcp_codebase.index.extractors import (
    extract_markdown_sections,
    extract_python_symbols,
    extract_shell_scripts,
)
from src.mcp_codebase.index.extractors.python import should_skip_path
from src.mcp_codebase.index.store import ChromaIndexStore

logger = logging.getLogger(__name__)


class VectorIndexService:
    """Orchestrate build, query, refresh, and status operations."""

    def __init__(self, config: IndexConfig, *, store: ChromaIndexStore | None = None) -> None:
        """Create a service bound to a specific index configuration."""
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
        logger.info("vector-index: collecting source files")
        content_units = self._collect_content_units(source_paths=source_paths)
        logger.info("vector-index: collected %d content units", len(content_units))
        code_symbol_count, markdown_section_count = _count_content_units(content_units)
        resolved_revision = _resolve_revision_label(revision, self._config.repo_root)
        metadata = self._build_metadata(
            revision=resolved_revision,
            entry_count=len(content_units),
            code_symbol_count=code_symbol_count,
            markdown_section_count=markdown_section_count,
            is_stale=False,
            stale_reason="",
        )
        logger.info("vector-index: writing snapshot")
        written = self._store.write_snapshot(content_units, metadata)
        logger.info(
            "vector-index: build complete entries=%d code=%d markdown=%d snapshot=%s",
            written.entry_count,
            written.code_symbol_count,
            written.markdown_section_count,
            written.snapshot_path,
        )
        return written

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
        logger.info("vector-index: refreshing %d changed paths", len(changed_paths))
        existing = self._store.load_snapshot()
        changed_units = self._collect_content_units(changed_paths=changed_paths)

        if existing is None:
            content_units = changed_units
        else:
            _, current_units = existing
            changed_set = {_normalize_path(path, self._config.repo_root) for path in changed_paths}
            retained_units = [unit for unit in current_units if unit.file_path.resolve() not in changed_set]
            content_units = retained_units + changed_units

        resolved_revision = _resolve_revision_label(revision, self._config.repo_root)
        code_symbol_count, markdown_section_count = _count_content_units(content_units)
        metadata = self._build_metadata(
            revision=resolved_revision,
            entry_count=len(content_units),
            code_symbol_count=code_symbol_count,
            markdown_section_count=markdown_section_count,
            is_stale=False,
            stale_reason="",
        )
        return self._store.refresh_changed_snapshot(
            changed_paths=changed_paths,
            changed_units=changed_units,
            metadata=metadata,
        )

    def status(self) -> IndexMetadata | None:
        """Return the active snapshot metadata."""
        metadata = self._store.status()
        if metadata is None:
            return None

        current_commit = _resolve_current_commit(self._config.repo_root)
        indexed_age_seconds = round(max(0.0, (_utc_now() - metadata.indexed_at).total_seconds()), 3)
        updates: dict[str, object] = {"indexed_age_seconds": indexed_age_seconds}

        if current_commit is None:
            return metadata.model_copy(update=updates)

        commits_behind_head = _resolve_commit_distance(
            self._config.repo_root,
            metadata.indexed_commit,
            current_commit,
        )
        is_stale = current_commit != metadata.indexed_commit
        stale_reason = ""
        if is_stale:
            reason_parts = [
                f"indexed commit {metadata.indexed_commit} is behind current HEAD {current_commit}",
            ]
            if commits_behind_head is not None:
                reason_parts[0] += f" by {commits_behind_head} commits"
            reason_parts.append(f"built {indexed_age_seconds} seconds ago")
            stale_reason = "; ".join(reason_parts)

        updates.update(
            {
                "current_commit": current_commit,
                "is_stale": is_stale,
                "stale_reason": stale_reason,
                "commits_behind_head": commits_behind_head,
            }
        )
        return metadata.model_copy(update=updates)

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
        candidate_paths = list(candidate_paths)
        total_candidates = len(candidate_paths)
        if total_candidates:
            logger.info("vector-index: extracting %d files", total_candidates)

        units: list[CodeSymbol | MarkdownSection] = []
        for index, raw_path in enumerate(candidate_paths, start=1):
            path = _normalize_path(raw_path, self._config.repo_root)
            suffix = path.suffix.lower()
            if suffix in {".py", ".pyi"}:
                units.extend(
                    extract_python_symbols(
                        path,
                        repo_root=self._config.repo_root,
                        exclude_patterns=self._config.exclude_patterns,
                    )
                )
            elif suffix in {".md", ".markdown", ".mdown"}:
                units.extend(
                    extract_markdown_sections(
                        path,
                        repo_root=self._config.repo_root,
                        exclude_patterns=self._config.exclude_patterns,
                    )
                )
            elif suffix in {".sh", ".bash", ".zsh"}:
                units.extend(
                    extract_shell_scripts(
                        path,
                        repo_root=self._config.repo_root,
                        exclude_patterns=self._config.exclude_patterns,
                    )
                )
            if total_candidates and (index % 50 == 0 or index == total_candidates):
                logger.info("vector-index: processed %d/%d files", index, total_candidates)
        return units

    def _iter_source_files(self) -> list[Path]:
        repo_root = self._config.repo_root.resolve()
        files: list[Path] = []
        for path in repo_root.rglob("*"):
            if not path.is_file():
                continue
            if should_skip_path(path, repo_root, self._config.exclude_patterns):
                continue
            if path.suffix.lower() not in {".py", ".pyi", ".md", ".markdown", ".mdown", ".sh", ".bash", ".zsh"}:
                continue
            files.append(path)
        return files

    def _build_metadata(
        self,
        *,
        revision: str,
        entry_count: int,
        code_symbol_count: int,
        markdown_section_count: int,
        is_stale: bool,
        stale_reason: str,
    ) -> IndexMetadata:
        return IndexMetadata(
            source_root=self._config.repo_root,
            indexed_commit=revision,
            current_commit=revision,
            indexed_at=_utc_now(),
            entry_count=entry_count,
            code_symbol_count=code_symbol_count,
            markdown_section_count=markdown_section_count,
            embedding_model=self._store.embedding_model,
            collection_name=f"{self._config.collection_name}-{uuid.uuid4().hex}",
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


def _resolve_current_commit(repo_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = completed.stdout.strip()
    return commit or None


def _resolve_revision_label(revision: str, repo_root: Path) -> str:
    if revision != "local":
        return revision
    current_commit = _resolve_current_commit(repo_root)
    return current_commit or revision


def _count_content_units(content_units: Sequence[CodeSymbol | MarkdownSection]) -> tuple[int, int]:
    code_symbol_count = sum(1 for unit in content_units if unit.scope is IndexScope.CODE)
    markdown_section_count = sum(1 for unit in content_units if unit.scope is IndexScope.MARKDOWN)
    return code_symbol_count, markdown_section_count


def _resolve_commit_distance(repo_root: Path, indexed_commit: str, current_commit: str) -> int | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-list", "--count", f"{indexed_commit}..{current_commit}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    try:
        return int(completed.stdout.strip())
    except ValueError:
        return None
