"""CLI adapter for the local vector index service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from src.mcp_codebase.index import IndexConfig, IndexScope, build_vector_index_service


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for vector-index operations."""

    parser = argparse.ArgumentParser(prog="mcp-codebase-indexer")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--db-path", type=Path, default=Path(".codegraphcontext/db/vector-index"))
    parser.add_argument("--embedding-model", type=str, default="local-default")

    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build a full snapshot from the repo checkout")
    build.add_argument("--revision", default="local")

    query = subparsers.add_parser("query", help="Query the active snapshot")
    query.add_argument("query_text")
    query.add_argument("--top-k", type=int, default=10)
    query.add_argument("--scope", choices=[scope.value for scope in IndexScope], default=None)

    refresh = subparsers.add_parser("refresh", help="Refresh specific paths")
    refresh.add_argument("changed_paths", nargs="+")
    refresh.add_argument("--revision", default="local")

    subparsers.add_parser("status", help="Report the active snapshot status")

    return parser


def build_service(args: argparse.Namespace):
    """Construct the shared vector-index service from CLI arguments."""

    config = IndexConfig(
        repo_root=args.repo_root,
        db_path=args.db_path,
        embedding_model=args.embedding_model,
    )
    return build_vector_index_service(config)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the vector-index CLI adapter."""

    parser = build_parser()
    args = parser.parse_args(argv)
    service = build_service(args)

    if args.command == "build":
        metadata = service.build_full_index(revision=args.revision)
        print(json.dumps(metadata.model_dump(mode="json"), indent=2, sort_keys=True))
        return 0

    if args.command == "query":
        scope = IndexScope(args.scope) if args.scope else None
        results = service.query(args.query_text, top_k=args.top_k, scope=scope)
        print(
            json.dumps(
                [result.model_dump(mode="json") for result in results],
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

    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
