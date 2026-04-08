"""MCP server for the Trello Bridge.

Exposes the sync_tasks_to_trello tool via FastMCP.

Security controls (III-b, III-e):
- Credentials loaded exclusively from env vars (TRELLO_API_KEY, TRELLO_TOKEN)
- tasks_md_path validated: must exist, be a file, have .md extension,
  have symlinks resolved, and lie within the current working tree
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.mcp_trello.parser import parse_tasks_md
from src.mcp_trello.sync_engine import SyncEngine
from src.mcp_trello.trello_client import TrelloClient

mcp = FastMCP("trello-bridge")


def _resolve_and_validate_path(tasks_md_path: str) -> Path:
    """Resolve and validate tasks_md_path against path traversal and other attacks.

    Raises:
        ValueError: If path is invalid, outside working tree, or not a .md file.
    """
    try:
        path = Path(tasks_md_path).resolve()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid path: {tasks_md_path!r}") from exc

    # Must have .md extension
    if path.suffix.lower() != ".md":
        raise ValueError(f"tasks_md_path must be a .md file, got: {path.suffix!r}")

    # Must exist and be a regular file (not a directory, symlink, etc.)
    if not path.exists():
        raise ValueError(f"tasks_md_path does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"tasks_md_path is not a regular file: {path}")

    # Path traversal guard: must be within the current working tree
    cwd = Path.cwd().resolve()
    try:
        path.relative_to(cwd)
    except ValueError:
        raise ValueError(
            f"tasks_md_path must be within the working directory ({cwd}). "
            f"Got: {path}"
        )

    return path


@mcp.tool()
async def sync_tasks_to_trello(
    tasks_md_path: str,
    board_id: str | None = None,
) -> dict[str, Any]:
    """Sync tasks from a tasks.md file to a Trello board.

    Creates one Trello list per phase and one card per task. Idempotent:
    re-running with the same inputs produces no duplicate cards.

    Args:
        tasks_md_path: Absolute path to the tasks.md file to sync.
        board_id: Trello board ID. Falls back to TRELLO_BOARD_ID env var if omitted.

    Returns:
        SyncReport dict with keys: created, updated, unchanged, errors, aborted,
        abort_reason.
    """
    # --- Credential validation (III-b) ---
    api_key = os.environ.get("TRELLO_API_KEY", "")
    token = os.environ.get("TRELLO_TOKEN", "")

    if not api_key or not token:
        return {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": [],
            "aborted": True,
            "abort_reason": "Missing credentials: TRELLO_API_KEY and TRELLO_TOKEN must be set",
        }

    # --- Board ID resolution ---
    resolved_board_id = board_id or os.environ.get("TRELLO_BOARD_ID", "")
    if not resolved_board_id:
        return {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": [],
            "aborted": True,
            "abort_reason": (
                "Missing board_id: provide it as argument or set TRELLO_BOARD_ID env var"
            ),
        }

    # --- Path validation (III-e) ---
    try:
        path = _resolve_and_validate_path(tasks_md_path)
    except ValueError as exc:
        return {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": [],
            "aborted": True,
            "abort_reason": str(exc),
        }

    # --- File reading ---
    text = path.read_text(encoding="utf-8")

    # --- Parsing ---
    try:
        phases = parse_tasks_md(text)
    except ValueError as exc:
        return {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": [],
            "aborted": True,
            "abort_reason": f"Failed to parse tasks.md: {exc}",
        }

    # --- Sync ---
    async with TrelloClient(api_key=api_key, token=token) as client:
        engine = SyncEngine(client)
        report = await engine.sync(phases, resolved_board_id)

    return {
        "created": report.created,
        "updated": report.updated,
        "unchanged": report.unchanged,
        "errors": [
            {"task_id": e.task_id, "message": e.error_message or ""}
            for e in report.errors
        ],
        "aborted": report.aborted,
        "abort_reason": report.abort_reason,
    }


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
