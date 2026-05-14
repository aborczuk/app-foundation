"""Integration regressions for configurable exclusions and performance slices."""

from __future__ import annotations

import shutil
from pathlib import Path
from time import perf_counter

import pytest

from src.mcp_codebase.index import IndexConfig, IndexScope
from src.mcp_codebase.index.service import VectorIndexService


def _build_offline_vector_index_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    exclude_patterns: tuple[str, ...] = (),
) -> VectorIndexService:
    """Create a temp-repo vector index service with a seeded local embedding cache."""

    repo_root = Path(__file__).resolve().parents[2]
    source_cache = (
        repo_root / ".codegraphcontext" / "global" / "db" / "vector-index" / "fastembed-cache"
    )
    if not source_cache.exists():
        raise AssertionError(f"Missing shared fastembed cache at {source_cache}")

    target_cache = (
        tmp_path / ".codegraphcontext" / "global" / "db" / "vector-index" / "fastembed-cache"
    )
    target_cache.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_cache, target_cache, dirs_exist_ok=True)

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    return VectorIndexService(
        IndexConfig(
            repo_root=tmp_path,
            db_path=Path(".codegraphcontext/global/db/vector-index"),
            embedding_model="local-default",
            exclude_patterns=exclude_patterns,
        )
    )


def _write_python_modules(root: Path, count: int) -> list[Path]:
    """Create a deterministic batch of simple Python modules."""
    created: list[Path] = []
    src_root = root / "src" / "bulk"
    src_root.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        module = src_root / f"module_{index}.py"
        module.write_text(
            f"""
def symbol_{index}() -> str:
    return "symbol-{index}"
""".strip()
            + "\n",
            encoding="utf-8",
        )
        created.append(module)
    return created


def test_configurable_excludes_respected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configured exclude patterns should block indexing beyond built-in generated rules."""

    source = tmp_path / "src" / "live.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        """
def live_symbol() -> str:
    return "live"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    excluded = tmp_path / "docs" / "build" / "ignored.md"
    excluded.parent.mkdir(parents=True, exist_ok=True)
    excluded.write_text(
        """
# Ignored

## Hidden

Do not index this section.
""".strip()
        + "\n",
        encoding="utf-8",
    )

    service = _build_offline_vector_index_service(
        tmp_path,
        monkeypatch,
        exclude_patterns=("docs/build/**",),
    )
    service.build_full_index(revision="rev-a")

    live = service.query("live_symbol", scope=IndexScope.CODE, top_k=1)
    assert live
    assert live[0].file_path == source

    hidden = service.query("Hidden", scope=IndexScope.MARKDOWN, top_k=1)
    assert hidden == []


def test_index_build_and_refresh_meets_timing_budgets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Build and single-file refresh should stay inside the spec timing budget."""

    source_paths = _write_python_modules(tmp_path, count=40)

    service = _build_offline_vector_index_service(tmp_path, monkeypatch)

    build_started = perf_counter()
    built = service.build_full_index(revision="rev-a")
    build_seconds = perf_counter() - build_started

    assert built.code_symbol_count == 40
    assert build_seconds < 60.0

    changed = source_paths[0]
    changed.write_text(
        """
def symbol_0() -> str:
    return "symbol-0"


def refreshed_symbol() -> str:
    return "refreshed"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    refresh_started = perf_counter()
    refreshed = service.refresh_changed_files([changed], revision="rev-b")
    refresh_seconds = perf_counter() - refresh_started

    assert refreshed.indexed_commit == "rev-b"
    assert refreshed.code_symbol_count == 41
    assert refresh_seconds < 10.0

    refreshed_result = service.query("refreshed_symbol", scope=IndexScope.CODE, top_k=1)
    assert refreshed_result
    assert refreshed_result[0].file_path == changed


def test_refresh_reindexes_changed_code_symbol_after_invalidation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changed files should invalidate the old symbol and surface the refreshed one."""

    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        """
def stale_symbol() -> str:
    return "stale"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    service = _build_offline_vector_index_service(tmp_path, monkeypatch)
    service.build_full_index(revision="rev-a")

    initial = service.query("stale_symbol", scope=IndexScope.CODE, top_k=1)
    assert initial
    assert initial[0].file_path == source
    assert initial[0].signature.startswith("def stale_symbol")

    source.write_text(
        """
def refreshed_symbol() -> str:
    return "fresh"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    refreshed = service.refresh_changed_files([source], revision="rev-b")
    assert refreshed.indexed_commit == "rev-b"

    stale = service.query("stale_symbol", scope=IndexScope.CODE, top_k=1)
    assert stale
    assert stale[0].signature.startswith("def refreshed_symbol")

    updated = service.query("refreshed_symbol", scope=IndexScope.CODE, top_k=1)
    assert updated
    assert updated[0].file_path == source
    assert updated[0].signature.startswith("def refreshed_symbol")


def test_index_handles_max_volume_without_oom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A larger local checkout should remain buildable without memory failure."""

    source_paths = _write_python_modules(tmp_path, count=240)

    docs_root = tmp_path / "specs"
    docs_root.mkdir(parents=True, exist_ok=True)
    for index in range(40):
        doc = docs_root / f"topic_{index}.md"
        doc.write_text(
            f"""
# Topic {index}

## Section {index}

This is document {index}.
""".strip()
            + "\n",
            encoding="utf-8",
        )

    service = _build_offline_vector_index_service(tmp_path, monkeypatch)

    built = service.build_full_index(revision="rev-a")

    assert built.code_symbol_count == len(source_paths)
    assert built.markdown_section_count == 80
    assert built.entry_count > len(source_paths)
    assert service.query("symbol_239", scope=IndexScope.CODE, top_k=1)
