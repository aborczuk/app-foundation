"""Shared graph-readiness health classification for codegraph tooling.

The health seam keeps the doctor CLI and the MCP server aligned on a single
read-only vocabulary:

- healthy
- stale
- locked
- unavailable

The implementation intentionally uses local repository state only. The current
checkout is authoritative; local edits invalidate freshness until the indexed
snapshot is refreshed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from time import monotonic
from typing import Any, Iterable
import os


class GraphHealthStatus(str, Enum):
    """Typed readiness vocabulary for the local code graph."""

    HEALTHY = "healthy"
    STALE = "stale"
    LOCKED = "locked"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class GraphRecoveryHint:
    """Stable recovery guidance for both CLI and MCP adapters."""

    id: str
    action: str
    summary: str
    command: str
    preserves_last_good: bool


@dataclass(frozen=True)
class GraphHealthResult:
    """Canonical graph-health result."""

    status: GraphHealthStatus
    detail: str
    checked_at: str
    source: str
    recovery_hint: GraphRecoveryHint
    latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dictionary."""

        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


_IGNORED_DIRS = {
    ".codegraphcontext",
    ".git",
    ".idea",
    ".speckit",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "env",
    "logs",
    "node_modules",
    "out",
    "shadow-runs",
    "target",
    "venv",
    ".vscode",
}

_SOURCE_ROOTS = ("src", "scripts", "tests")
_LOCK_MARKERS = (
    ".codegraphcontext/db/kuzudb.lock",
    ".codegraphcontext/db/falkordb.lock",
    ".codegraphcontext/db/.lock",
    ".codegraphcontext/.lock",
)


def classify_graph_health(project_root: Path) -> GraphHealthResult:
    """Classify the current graph-readiness state from local filesystem cues."""

    start = monotonic()
    repo_root = project_root.resolve()
    status, detail = _classify_state(repo_root)
    recovery_hint = build_recovery_hint(status, repo_root=repo_root, detail=detail)
    checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    latency_ms = round((monotonic() - start) * 1000.0, 1)
    return GraphHealthResult(
        status=status,
        detail=detail,
        checked_at=checked_at,
        source="filesystem-freshness",
        recovery_hint=recovery_hint,
        latency_ms=latency_ms,
    )


async def get_graph_health_impl(project_root: Path) -> dict[str, Any]:
    """Return a JSON-friendly graph-health payload for adapter callers."""

    return classify_graph_health(project_root).to_dict()


def build_recovery_hint(
    status: GraphHealthStatus,
    *,
    repo_root: Path,
    detail: str = "",
) -> GraphRecoveryHint:
    """Map a health status to a stable next-action hint."""

    repo_display = str(repo_root)

    if status is GraphHealthStatus.HEALTHY:
        return GraphRecoveryHint(
            id="continue",
            action="continue",
            summary="Graph is healthy; continue using codegraph.",
            command="",
            preserves_last_good=True,
        )

    if status is GraphHealthStatus.STALE:
        return GraphRecoveryHint(
            id="refresh-scoped-index",
            action="refresh",
            summary=(
                "Local edits are newer than the indexed snapshot; refresh the "
                "scoped graph before trusting symbol answers."
            ),
            command=f"scripts/cgc_safe_index.sh {repo_display}",
            preserves_last_good=True,
        )

    if status is GraphHealthStatus.LOCKED:
        return GraphRecoveryHint(
            id="retry-after-close",
            action="retry",
            summary=(
                "Graph access is blocked by a lock marker; close the stale "
                "session or wait for the owner, then retry."
            ),
            command=f"scripts/cgc_safe_index.sh {repo_display}",
            preserves_last_good=True,
        )

    return GraphRecoveryHint(
        id="fallback-to-files",
        action="fallback",
        summary=(
            "Graph state is unavailable or unreadable; fall back to direct "
            "file reads and reindex once the backend is healthy."
        ),
        command="scripts/read-code.sh <file> <symbol> --allow-fallback",
        preserves_last_good=False,
    )


def _classify_state(repo_root: Path) -> tuple[GraphHealthStatus, str]:
    if not repo_root.exists() or not repo_root.is_dir():
        return (
            GraphHealthStatus.UNAVAILABLE,
            "project root is missing or not a directory",
        )

    db_path = repo_root / ".codegraphcontext" / "db" / "kuzudb"
    lock_marker = _first_existing_path(repo_root, _LOCK_MARKERS)
    if lock_marker is not None:
        return (
            GraphHealthStatus.LOCKED,
            f"lock marker present at {lock_marker.relative_to(repo_root)}",
        )

    if not db_path.exists():
        return (
            GraphHealthStatus.STALE,
            "graph snapshot is missing; refresh the scoped index before trusting symbol answers",
        )

    if not db_path.is_file():
        return (
            GraphHealthStatus.UNAVAILABLE,
            "graph snapshot path is not a regular file",
        )

    if not os.access(db_path, os.R_OK):
        return (
            GraphHealthStatus.UNAVAILABLE,
            "graph snapshot exists but is not readable",
        )

    latest_source_mtime, newest_source = _latest_source_mtime(repo_root)
    if latest_source_mtime is None:
        return (
            GraphHealthStatus.HEALTHY,
            "graph snapshot is present and no tracked source files were found",
        )

    db_mtime = db_path.stat().st_mtime
    if latest_source_mtime > db_mtime:
        newest_rel = newest_source.relative_to(repo_root) if newest_source is not None else None
        if newest_rel is not None:
            detail = (
                f"working tree changed after the indexed snapshot: {newest_rel}"
            )
        else:
            detail = "working tree changed after the indexed snapshot"
        return GraphHealthStatus.STALE, detail

    return (
        GraphHealthStatus.HEALTHY,
        "graph snapshot is current with tracked source files",
    )


def _first_existing_path(root: Path, candidates: Iterable[str]) -> Path | None:
    for relative in candidates:
        candidate = root / relative
        if candidate.exists():
            return candidate
    return None


def _latest_source_mtime(repo_root: Path) -> tuple[float | None, Path | None]:
    latest_mtime: float | None = None
    latest_path: Path | None = None

    def maybe_update(path: Path) -> None:
        nonlocal latest_mtime, latest_path
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return
        if latest_mtime is None or mtime > latest_mtime:
            latest_mtime = mtime
            latest_path = path

    for relative_dir in _SOURCE_ROOTS:
        root = repo_root / relative_dir
        if not root.exists():
            continue
        for current_root, dirs, files in os.walk(root):
            current_path = Path(current_root)
            dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]
            if current_path.name in _IGNORED_DIRS:
                dirs[:] = []
                continue
            for filename in files:
                maybe_update(current_path / filename)

    for top_level in ("AGENTS.md", "CLAUDE.md", "constitution.md", "catalog.yaml", "pyproject.toml"):
        candidate = repo_root / top_level
        if candidate.exists():
            maybe_update(candidate)

    return latest_mtime, latest_path
