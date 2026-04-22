"""Unit tests for the vector-index CLI adapter."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from src.mcp_codebase import indexer
from src.mcp_codebase.index import CodeSymbol, IndexConfig, IndexMetadata, IndexScope, QueryResult
from src.mcp_codebase.index.config import DEFAULT_VECTOR_DB_PATH


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
                indexed_at=datetime(2026, 4, 14, tzinfo=UTC),
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
                indexed_at=datetime(2026, 4, 14, tzinfo=UTC),
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


def test_indexer_list_file_symbols_routes_through_shared_service(monkeypatch, tmp_path, capsys) -> None:
    """The CLI should route file-symbol listing through the shared service."""

    class FakeService:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def list_file_code_symbols(self, file_path: str):
            self.calls.append(("list-file-symbols", file_path))
            return [
                CodeSymbol(
                    symbol_name="run_pipeline",
                    qualified_name="run_pipeline",
                    file_path=Path(file_path),
                    line_start=1,
                    line_end=3,
                    signature="def run_pipeline():",
                    docstring="",
                    preview="def run_pipeline():",
                    body="def run_pipeline():\n    return 1\n",
                )
            ]

    fake_service = FakeService()
    monkeypatch.setattr(indexer, "build_service", lambda args: fake_service)

    exit_code = indexer.main(["--repo-root", str(tmp_path), "list-file-symbols", "src/example.py"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert fake_service.calls == [("list-file-symbols", "src/example.py")]
    assert payload[0]["symbol_name"] == "run_pipeline"
    assert payload[0]["line_start"] == 1


def test_indexer_status_reports_snapshot_freshness(monkeypatch, tmp_path, capsys) -> None:
    """The CLI should surface status freshness metadata from the shared service."""

    class FakeService:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def status(self):
            self.calls.append(("status",))
            return IndexMetadata(
                source_root=tmp_path,
                indexed_commit="rev-a",
                current_commit="rev-b",
                indexed_at=datetime(2026, 4, 14, tzinfo=UTC),
                entry_count=1,
                is_stale=True,
                stale_reason="indexed commit rev-a is behind current HEAD rev-b",
            )

    fake_service = FakeService()
    monkeypatch.setattr(indexer, "build_service", lambda args: fake_service)

    exit_code = indexer.main(["--repo-root", str(tmp_path), "status"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert fake_service.calls[0] == ("status",)
    assert payload["indexed_commit"] == "rev-a"
    assert payload["current_commit"] == "rev-b"
    assert payload["is_stale"] is True


def test_indexer_build_service_uses_cli_exclude_patterns(monkeypatch, tmp_path) -> None:
    """The CLI builder should pass explicit exclude patterns into the shared config."""

    captured: dict[str, object] = {}

    def fake_build_vector_index_service(config):
        captured["config"] = config
        return config

    monkeypatch.setattr(indexer, "build_vector_index_service", fake_build_vector_index_service)

    args = argparse.Namespace(
        repo_root=tmp_path,
        db_path=DEFAULT_VECTOR_DB_PATH,
        embedding_model="local-default",
        exclude_patterns=["docs/build/**", "generated/**"],
    )

    config = indexer.build_service(args)

    assert isinstance(captured["config"], IndexConfig)
    assert config is captured["config"]
    assert captured["config"].exclude_patterns == ("docs/build/**", "generated/**")


def test_indexer_watch_command_flushes_pending_paths(monkeypatch, tmp_path) -> None:
    """Watch mode should batch local source changes into a single refresh."""

    class FakeService:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def refresh_changed_files(self, changed_paths, *, revision: str = "local"):
            self.calls.append((tuple(Path(path) for path in changed_paths), revision))
            return IndexMetadata(
                source_root=tmp_path,
                indexed_commit=revision,
                current_commit=revision,
                indexed_at=datetime(2026, 4, 14, tzinfo=UTC),
                entry_count=len(changed_paths),
                is_stale=False,
                stale_reason="",
            )

    service = FakeService()
    buffer = indexer._PendingRefreshBuffer(service, tmp_path, revision="rev-watch")
    buffer.add(tmp_path / "src" / "watched.py")
    buffer.add(tmp_path / "src" / "watched.py")
    buffer.add(tmp_path / "docs" / "notes.txt")

    metadata = buffer.flush()

    assert metadata is not None
    assert service.calls == [((tmp_path / "src" / "watched.py",), "rev-watch")]
    assert metadata.indexed_commit == "rev-watch"
    assert metadata.entry_count == 1


def test_indexer_watch_parser_exposes_watch_mode(tmp_path) -> None:
    """The CLI parser should expose the watch command and its debounce setting."""

    parser = indexer.build_parser()
    args = parser.parse_args(
        [
            "--repo-root",
            str(tmp_path),
            "watch",
            "--revision",
            "rev-watch",
            "--debounce-seconds",
            "0.25",
        ]
    )

    assert args.command == "watch"
    assert args.revision == "rev-watch"
    assert args.debounce_seconds == 0.25


def test_indexer_bootstrap_primes_model_and_builds_index(monkeypatch, tmp_path, capsys) -> None:
    """Bootstrap mode should warm the model cache and build a full snapshot."""

    class FakeService:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def ensure_embedding_model_local(self):
            self.calls.append(("ensure_embedding_model_local",))
            return {"embedding_model": "BAAI/bge-small-en-v1.5"}

        def build_full_index(self, *, revision: str = "local", source_paths=None):
            self.calls.append(("build", revision))
            return IndexMetadata(
                source_root=tmp_path,
                indexed_commit=revision,
                current_commit=revision,
                indexed_at=datetime(2026, 4, 14, tzinfo=UTC),
                entry_count=1,
                is_stale=False,
                stale_reason="",
            )

    fake_service = FakeService()
    monkeypatch.setattr(indexer, "build_service", lambda args: fake_service)

    exit_code = indexer.main(["--repo-root", str(tmp_path), "bootstrap", "--revision", "rev-bootstrap"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert fake_service.calls == [("ensure_embedding_model_local",), ("build", "rev-bootstrap")]
    assert payload["embedding_model"] == "BAAI/bge-small-en-v1.5"
    assert payload["index_metadata"]["indexed_commit"] == "rev-bootstrap"
