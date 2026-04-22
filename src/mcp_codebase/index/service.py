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
    extract_yaml_sections,
)
from src.mcp_codebase.index.extractors.python import should_skip_path
from src.mcp_codebase.index.store import ChromaIndexStore

logger = logging.getLogger(__name__)
INDEXABLE_SUFFIXES = {
    ".py",
    ".pyi",
    ".md",
    ".markdown",
    ".mdown",
    ".sh",
    ".bash",
    ".zsh",
    ".yaml",
    ".yml",
}


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

    def list_file_code_symbols(self, file_path: str | Path) -> list[CodeSymbol]:
        """Return deterministic symbols for a file from the active vector snapshot."""
        return self._store.list_file_code_symbols(file_path)

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
        """Return snapshot metadata with git-primary stale diagnostics and mtime fallback."""
        metadata = self._store.status()
        if metadata is None:
            return None

        current_commit = _resolve_current_commit(self._config.repo_root)
        current_signature = _current_git_signature(self._config.repo_root)
        indexed_age_seconds = round(max(0.0, (_utc_now() - metadata.indexed_at).total_seconds()), 3)
        updates: dict[str, object] = {"indexed_age_seconds": indexed_age_seconds}
        stale_reasons: list[str] = []
        stale_reason_class = "none"
        stale_drift_paths: tuple[str, ...] = ()
        stale_signal_source = "git"
        stale_signal_available = True
        stale_signal_error = ""
        commits_behind_head: int | None = None

        if current_commit is not None:
            commits_behind_head = _resolve_commit_distance(
                self._config.repo_root,
                metadata.indexed_commit,
                current_commit,
            )
            updates["current_commit"] = current_commit

            if current_commit != metadata.indexed_commit:
                commit_reason = f"indexed commit {metadata.indexed_commit} is behind current HEAD {current_commit}"
                if commits_behind_head is not None:
                    commit_reason += f" by {commits_behind_head} commits"
                stale_reasons.append(commit_reason)
                stale_reason_class = "commit-drift"

            git_drift_paths, git_probe_error = _collect_git_indexable_drift_paths(
                self._config.repo_root,
                self._config.exclude_patterns,
                metadata.indexed_commit,
                current_commit,
                metadata.indexed_worktree_signature,
                current_signature,
            )
            if git_probe_error:
                stale_signal_source = "mtime-fallback"
                stale_signal_available = False
                stale_signal_error = git_probe_error
            else:
                stale_drift_paths = git_drift_paths
                if git_drift_paths:
                    joined = ", ".join(git_drift_paths[:8])
                    if len(git_drift_paths) > 8:
                        joined += ", ..."
                    stale_reasons.append(f"indexable git drift paths: {joined}")
                    if stale_reason_class == "none":
                        stale_reason_class = "git-path-drift"
                    elif stale_reason_class == "commit-drift":
                        stale_reason_class = "commit-and-git-path-drift"
        else:
            stale_signal_source = "mtime-fallback"
            stale_signal_available = False
            stale_signal_error = "could not resolve current git HEAD"
        if current_signature is None:
            stale_signal_source = "mtime-fallback"
            stale_signal_available = False
            stale_signal_error = "could not resolve current git status signature"

        if not stale_signal_available:
            drift_path = _latest_indexable_source_drift(
                self._config.repo_root,
                self._config.exclude_patterns,
                metadata.indexed_at.timestamp(),
            )
            if drift_path is not None:
                relative_path = drift_path.relative_to(self._config.repo_root.resolve()).as_posix()
                stale_drift_paths = (relative_path,)
                stale_reasons.append(f"indexable path {relative_path} changed after last embedding refresh")
                if stale_reason_class == "none":
                    stale_reason_class = "mtime-fallback-drift"
                elif stale_reason_class == "commit-drift":
                    stale_reason_class = "commit-and-mtime-fallback-drift"

        is_stale = bool(stale_reasons)
        stale_reason = ""
        if is_stale:
            stale_reasons.append(f"built {indexed_age_seconds} seconds ago")
            stale_reason = "; ".join(stale_reasons)
        else:
            stale_reason_class = "none"
            stale_drift_paths = ()

        updates.update(
            {
                "is_stale": is_stale,
                "stale_reason": stale_reason,
                "stale_reason_class": stale_reason_class,
                "stale_drift_paths": stale_drift_paths,
                "stale_signal_source": stale_signal_source,
                "stale_signal_available": stale_signal_available,
                "stale_signal_error": stale_signal_error,
                "commits_behind_head": commits_behind_head,
            }
        )
        return metadata.model_copy(update=updates)

    def ensure_embedding_model_local(self) -> dict[str, object]:
        """Prime and report the local embedding cache used by vector indexing."""
        return self._store.ensure_embedding_model_local()

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
            elif suffix in {".yaml", ".yml"}:
                units.extend(
                    extract_yaml_sections(
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
            if path.suffix.lower() not in INDEXABLE_SUFFIXES:
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
        indexed_signature = _current_git_signature(self._config.repo_root) or ""
        return IndexMetadata(
            source_root=self._config.repo_root,
            indexed_commit=revision,
            current_commit=revision,
            indexed_worktree_signature=indexed_signature,
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


def _current_git_signature(repo_root: Path) -> str | None:
    """Return a stable git status signature string for stale-drift comparisons."""
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root.resolve()),
            "status",
            "--porcelain",
            "--untracked-files=normal",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None

    ignored_prefixes = (
        ".codegraphcontext/",
        ".speckit/",
        ".uv-cache/",
        "logs/",
        "shadow-runs/",
    )
    lines: list[str] = []
    for raw in completed.stdout.splitlines():
        if not raw.strip():
            continue
        path_text = raw[3:].strip() if len(raw) > 3 else ""
        if not path_text:
            continue
        if " -> " in path_text:
            candidates = [part.strip() for part in path_text.split(" -> ")]
        else:
            candidates = [path_text]
        if any(candidate.startswith(ignored_prefixes) for candidate in candidates if candidate):
            continue
        lines.append(raw.rstrip("\n"))
    return "\n".join(sorted(dict.fromkeys(lines)))


def _signature_paths(signature: str) -> set[str]:
    """Extract normalized relative paths from a git porcelain signature string."""
    paths: set[str] = set()
    for raw in signature.splitlines():
        line = raw.rstrip("\n")
        if not line.strip() or len(line) < 4:
            continue
        candidate = line[3:].strip()
        if not candidate:
            continue
        if " -> " in candidate:
            parts = [part.strip() for part in candidate.split(" -> ")]
        else:
            parts = [candidate]
        for part in parts:
            normalized = part.strip().strip('"').replace("\\", "/")
            if normalized.startswith("./"):
                normalized = normalized[2:]
            if normalized:
                paths.add(normalized)
    return paths


def _collect_git_indexable_drift_paths(
    repo_root: Path,
    exclude_patterns: Sequence[str],
    indexed_commit: str,
    current_commit: str,
    indexed_signature: str,
    current_signature: str | None,
) -> tuple[tuple[str, ...], str | None]:
    """Collect indexable changed paths from commit and worktree signature drift."""
    root = repo_root.resolve()
    paths: set[str] = set()

    if current_signature is None:
        return (), "git status signature unavailable"

    if indexed_commit != current_commit:
        diff_proc = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "diff",
                "--name-only",
                "--diff-filter=ACDMRTUXB",
                f"{indexed_commit}..{current_commit}",
                "--",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if diff_proc.returncode != 0:
            detail = (diff_proc.stderr or "").strip() or "git diff failed"
            return (), detail
        for line in diff_proc.stdout.splitlines():
            _add_indexable_drift_path(paths, line, root, exclude_patterns)

    if indexed_signature != current_signature:
        indexed_paths = _signature_paths(indexed_signature)
        current_paths = _signature_paths(current_signature)
        for candidate in indexed_paths.symmetric_difference(current_paths):
            _add_indexable_drift_path(paths, candidate, root, exclude_patterns)

    return tuple(sorted(paths)), None


def _add_indexable_drift_path(
    paths: set[str],
    raw_path: str,
    repo_root: Path,
    exclude_patterns: Sequence[str],
) -> None:
    """Normalize and record an indexable repo-local drift path."""
    normalized = raw_path.strip().strip('"').replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        return
    if Path(normalized).suffix.lower() not in INDEXABLE_SUFFIXES:
        return
    if should_skip_path(repo_root / normalized, repo_root, exclude_patterns):
        return
    paths.add(normalized)


def _latest_indexable_source_drift(
    repo_root: Path,
    exclude_patterns: Sequence[str],
    indexed_at_timestamp: float,
) -> Path | None:
    """Return the latest indexable path by mtime when git drift probing is unavailable."""
    root = repo_root.resolve()
    latest_path: Path | None = None
    latest_mtime = indexed_at_timestamp
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if should_skip_path(path, root, exclude_patterns):
            continue
        if path.suffix.lower() not in INDEXABLE_SUFFIXES:
            continue
        try:
            modified_at = path.stat().st_mtime
        except OSError:
            continue
        if modified_at > latest_mtime:
            latest_mtime = modified_at
            latest_path = path
    return latest_path
