"""CLI adapter for the local vector index service."""

from __future__ import annotations

import argparse
import json
import logging
import threading
import time
from pathlib import Path
from typing import Sequence

from src.mcp_codebase.index import IndexConfig, IndexScope, build_vector_index_service
from src.mcp_codebase.index.config import DEFAULT_VECTOR_DB_PATH, load_exclude_patterns
from src.mcp_codebase.index.extractors.python import should_skip_path

try:  # pragma: no cover - exercised in runtime verification
    from watchdog.events import FileSystemEventHandler  # type: ignore[import-not-found]
    from watchdog.observers import Observer  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - handled with a clear runtime error
    class FileSystemEventHandler:  # type: ignore[override]
        """Fallback base class used when watchdog is unavailable."""

        pass

    Observer = None

_WATCHABLE_SUFFIXES = {
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

def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for vector-index operations."""
    parser = argparse.ArgumentParser(prog="mcp-codebase-indexer")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--db-path", type=Path, default=DEFAULT_VECTOR_DB_PATH)
    parser.add_argument("--embedding-model", type=str, default="local-default")
    parser.add_argument(
        "--exclude-pattern",
        action="append",
        dest="exclude_patterns",
        default=None,
        help="Exclude matching paths from indexing; can be repeated.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build a full snapshot from the repo checkout")
    build.add_argument("--revision", default="local")

    query = subparsers.add_parser("query", help="Query the active snapshot")
    query.add_argument("query_text")
    query.add_argument("--top-k", type=int, default=10)
    query.add_argument("--scope", choices=[scope.value for scope in IndexScope], default=None)
    query.add_argument(
        "--file-path",
        default=None,
        help="Optional file path filter for file-local semantic retrieval.",
    )

    symbols = subparsers.add_parser(
        "list-file-symbols",
        help="List deterministic code symbols for a single file from the active snapshot",
    )
    symbols.add_argument("file_path")

    refresh = subparsers.add_parser("refresh", help="Refresh specific paths")
    refresh.add_argument("changed_paths", nargs="+")
    refresh.add_argument("--revision", default="local")

    status = subparsers.add_parser("status", help="Report the active snapshot status")
    status.set_defaults(command="status")

    watch = subparsers.add_parser("watch", help="Watch for local file changes and refresh incrementally")
    watch.add_argument("--revision", default="local")
    watch.add_argument(
        "--debounce-seconds",
        type=float,
        default=0.5,
        help="Wait this long after the most recent change before refreshing.",
    )

    bootstrap = subparsers.add_parser(
        "bootstrap",
        help="Ensure the embedding model is cached locally and optionally build a full snapshot",
    )
    bootstrap.add_argument("--revision", default="local")
    bootstrap.add_argument(
        "--skip-build",
        action="store_true",
        help="Only prime/check the embedding model cache without building embeddings.",
    )

    return parser


def build_service(args: argparse.Namespace):
    """Construct the shared vector-index service from CLI arguments."""
    cli_patterns = tuple(args.exclude_patterns or ())
    env_patterns = load_exclude_patterns()
    config = IndexConfig(
        repo_root=args.repo_root,
        db_path=args.db_path,
        embedding_model=args.embedding_model,
        exclude_patterns=cli_patterns or env_patterns,
    )
    return build_vector_index_service(config)


class _PendingRefreshBuffer:
    """Collect file paths until the watcher has been quiet long enough."""

    def __init__(self, service, repo_root: Path, *, revision: str) -> None:
        self._service = service
        self._repo_root = repo_root.expanduser().resolve()
        self._revision = revision
        self._pending_paths: set[Path] = set()
        self._lock = threading.Lock()

    def add(self, raw_path: str | Path) -> None:
        candidate = Path(raw_path)
        if should_skip_path(candidate, self._repo_root):
            return

        if not candidate.is_absolute():
            candidate = (self._repo_root / candidate).resolve()
        else:
            candidate = candidate.resolve()

        if candidate.suffix.lower() not in _WATCHABLE_SUFFIXES:
            return

        with self._lock:
            self._pending_paths.add(candidate)

    def flush(self):
        with self._lock:
            if not self._pending_paths:
                return None
            changed_paths = sorted(self._pending_paths)
            self._pending_paths.clear()
        return self._service.refresh_changed_files(changed_paths, revision=self._revision)


class _WatchEventHandler(FileSystemEventHandler):
    """Watchdog event handler that batches local file changes."""

    def __init__(self, buffer: _PendingRefreshBuffer, trigger: threading.Event) -> None:
        self._buffer = buffer
        self._trigger = trigger

    def on_any_event(self, event) -> None:  # pragma: no cover - watchdog callback wiring
        if getattr(event, "is_directory", False):
            return
        self._buffer.add(getattr(event, "src_path", ""))
        if getattr(event, "event_type", "") == "moved":
            self._buffer.add(getattr(event, "dest_path", ""))
        self._trigger.set()


def _run_watch(service, *, repo_root: Path, revision: str, debounce_seconds: float) -> int:
    if Observer is None:
        raise RuntimeError("watchdog is required for watch mode; run `uv sync` first.")

    trigger = threading.Event()
    buffer = _PendingRefreshBuffer(service, repo_root, revision=revision)
    handler = _WatchEventHandler(buffer, trigger)
    observer = Observer()
    observer.schedule(handler, str(repo_root), recursive=True)  # type: ignore[arg-type]
    observer.start()
    print(f"Watching {repo_root} for local changes. Press Ctrl-C to stop.")

    try:
        while True:
            trigger.wait()
            trigger.clear()
            time.sleep(debounce_seconds)
            while trigger.is_set():
                trigger.clear()
                time.sleep(debounce_seconds)
            metadata = buffer.flush()
            if metadata is not None:
                print(json.dumps(metadata.model_dump(mode="json"), indent=2, sort_keys=True))
    except KeyboardInterrupt:
        return 0
    finally:
        observer.stop()
        observer.join()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the vector-index CLI adapter."""
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    service = build_service(args)

    if args.command == "build":
        metadata = service.build_full_index(revision=args.revision)
        print(json.dumps(metadata.model_dump(mode="json"), indent=2, sort_keys=True))
        return 0

    if args.command == "query":
        scope = IndexScope(args.scope) if args.scope else None
        results = service.query(
            args.query_text,
            top_k=args.top_k,
            scope=scope,
            file_path=args.file_path,
        )
        print(
            json.dumps(
                [result.model_dump(mode="json") for result in results],
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "list-file-symbols":
        symbols = service.list_file_code_symbols(args.file_path)
        print(
            json.dumps(
                [symbol.model_dump(mode="json") for symbol in symbols],
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "refresh":
        metadata = service.refresh_changed_files(args.changed_paths, revision=args.revision)
        print(json.dumps(metadata.model_dump(mode="json"), indent=2, sort_keys=True))
        return 0

    if args.command == "status":
        metadata = service.status()
        print(
            json.dumps(
                metadata.model_dump(mode="json") if metadata else None,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "watch":
        return _run_watch(
            service,
            repo_root=args.repo_root,
            revision=args.revision,
            debounce_seconds=args.debounce_seconds,
        )

    if args.command == "bootstrap":
        bootstrap_payload = service.ensure_embedding_model_local()
        if args.skip_build:
            print(json.dumps(bootstrap_payload, indent=2, sort_keys=True))
            return 0
        metadata = service.build_full_index(revision=args.revision)
        print(
            json.dumps(
                {
                    **bootstrap_payload,
                    "index_metadata": metadata.model_dump(mode="json"),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
