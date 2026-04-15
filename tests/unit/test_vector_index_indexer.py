"""Unit tests for the vector-index CLI adapter."""

from __future__ import annotations

from pathlib import Path

from src.mcp_codebase.index import CodeSymbol, IndexMetadata, IndexScope, QueryResult
from src.mcp_codebase import indexer


def test_indexer_query_routes_through_shared_service(monkeypatch, tmp_path, capsys) -> None:
    """The CLI should delegate query handling to the shared service."""

    class FakeService:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def query(self, query_text: str, *, top_k: int = 10, scope: IndexScope | None = None):
            self.calls.append(("query", query_text, top_k, scope))
            return [
                QueryResult(
                    rank=1,
                    score=1.0,
                    content=CodeSymbol(
                        symbol_name="query",
                        qualified_name="query",
                        file_path=Path("src/example.py"),
                        line_start=1,
                        line_end=2,
                        signature="def query():",
                        docstring="",
                        preview="def query():",
                    ),
                )
            ]

        def build_full_index(self, *, revision: str = "local", source_paths=None):
            self.calls.append(("build", revision, source_paths))
            return IndexMetadata(
                source_root=tmp_path,
                indexed_commit=revision,
                current_commit=revision,
                indexed_at="2026-04-14T00:00:00Z",
                entry_count=1,
                is_stale=False,
                stale_reason="",
            )

        def refresh_changed_files(self, changed_paths, *, revision: str = "local"):
            self.calls.append(("refresh", list(changed_paths), revision))
            return IndexMetadata(
                source_root=tmp_path,
                indexed_commit=revision,
                current_commit=revision,
                indexed_at="2026-04-14T00:00:00Z",
                entry_count=1,
                is_stale=False,
                stale_reason="",
            )

        def status(self):
            self.calls.append(("status",))
            return None

    fake_service = FakeService()
    monkeypatch.setattr(indexer, "build_service", lambda args: fake_service)

    exit_code = indexer.main(["--repo-root", str(tmp_path), "query", "hello"])

    assert exit_code == 0
    assert fake_service.calls[0] == ("query", "hello", 10, None)
    assert "\"rank\": 1" in capsys.readouterr().out
