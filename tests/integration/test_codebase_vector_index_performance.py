"""Integration regressions for configurable exclusions and performance slices."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from src.mcp_codebase.index import IndexConfig, IndexScope
from src.mcp_codebase.index.service import VectorIndexService


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


def test_configurable_excludes_respected(tmp_path: Path) -> None:
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

    service = VectorIndexService(
        IndexConfig(
            repo_root=tmp_path,
            db_path=Path(".codegraphcontext/db/vector-index"),
            embedding_model="local-default",
            exclude_patterns=("docs/build/**",),
        )
    )
    service.build_full_index(revision="rev-a")

    live = service.query("live_symbol", scope=IndexScope.CODE, top_k=1)
    assert live
    assert live[0].file_path == source

    hidden = service.query("Hidden", scope=IndexScope.MARKDOWN, top_k=1)
    assert hidden == []


def test_index_build_and_refresh_meets_timing_budgets(tmp_path: Path) -> None:
    """Build and single-file refresh should stay inside the spec timing budget."""

    source_paths = _write_python_modules(tmp_path, count=40)

    service = VectorIndexService(
        IndexConfig(
            repo_root=tmp_path,
            db_path=Path(".codegraphcontext/db/vector-index"),
            embedding_model="local-default",
        )
    )

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


def test_index_handles_max_volume_without_oom(tmp_path: Path) -> None:
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

    service = VectorIndexService(
        IndexConfig(
            repo_root=tmp_path,
            db_path=Path(".codegraphcontext/db/vector-index"),
            embedding_model="local-default",
        )
    )

    built = service.build_full_index(revision="rev-a")

    assert built.code_symbol_count == len(source_paths)
    assert built.markdown_section_count == 80
    assert built.entry_count > len(source_paths)
    assert service.query("symbol_239", scope=IndexScope.CODE, top_k=1)
