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

import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from time import monotonic
from typing import Any, Iterable


class GraphHealthStatus(str, Enum):
    """Typed readiness vocabulary for the local code graph."""

    HEALTHY = "healthy"
    STALE = "stale"
    LOCKED = "locked"
    UNAVAILABLE = "unavailable"


class GraphAccessMode(str, Enum):
    """Access-mode vocabulary for the probe vs refresh contract."""

    READ_ONLY = "READ_ONLY"
    READ_WRITE = "READ_WRITE"


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
    access_mode: GraphAccessMode
    detail: str
    checked_at: str
    source: str
    recovery_hint: GraphRecoveryHint
    latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dictionary."""
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["access_mode"] = self.access_mode.value
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
_LAST_EDIT_SIGNATURE_FILE = ".codegraphcontext/last-edit-signature.txt"
_LAST_INDEX_ERROR_FILE = ".codegraphcontext/last-index-error.txt"


def classify_graph_health(project_root: Path) -> GraphHealthResult:
    """Classify the current graph-readiness state from local filesystem cues."""
    start = monotonic()
    repo_root = project_root.resolve()
    last_index_error = _read_last_index_error(repo_root)
    if last_index_error is not None:
        # Keep last-failure context visible until a successful refresh clears it.
        status, detail = last_index_error
    else:
        status, detail = _classify_state(repo_root)
        # Deliberately avoid git-status drift reclassification here; non-indexed
        # metadata edits should not force graph health to stale.
    recovery_hint = build_recovery_hint(status, repo_root=repo_root, detail=detail)
    checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    latency_ms = round((monotonic() - start) * 1000.0, 1)
    return GraphHealthResult(
        status=status,
        access_mode=GraphAccessMode.READ_ONLY,
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

    if status is GraphHealthStatus.UNAVAILABLE and _is_memory_pressure_detail(detail):
        return GraphRecoveryHint(
            id="fail-fast-memory-pressure",
            action="retry",
            summary=(
                "Memory pressure blocked indexing; free memory or reduce the "
                "indexed scope before retrying."
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


def _read_last_index_error(repo_root: Path) -> tuple[GraphHealthStatus, str] | None:
    error_path = repo_root / _LAST_INDEX_ERROR_FILE
    if not error_path.exists():
        return None

    try:
        lines = error_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    fields: dict[str, str] = {}
    for line in lines:
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        fields[key.strip()] = value.strip()

    detail = fields.get("detail", "last index attempt failed")
    if fields.get("type") == "memory-pressure":
        return (
            GraphHealthStatus.UNAVAILABLE,
            f"last index attempt failed due to memory pressure: {detail}",
        )

    return GraphHealthStatus.UNAVAILABLE, detail


def _read_edit_drift(repo_root: Path) -> tuple[GraphHealthStatus, str] | None:
    current_signature = _current_edit_signature(repo_root)
    cached_signature = _read_cached_edit_signature(repo_root)

    if current_signature == cached_signature:
        return None

    current_preview = _preview_edit_signature(current_signature)
    cached_preview = _preview_edit_signature(cached_signature)
    return (
        GraphHealthStatus.STALE,
        (
            "working tree edits changed since the last indexed snapshot; "
            f"current={current_preview or 'clean'}, cached={cached_preview or 'clean'}"
        ),
    )


def _read_cached_edit_signature(repo_root: Path) -> str:
    marker_path = repo_root / _LAST_EDIT_SIGNATURE_FILE
    if not marker_path.exists():
        return ""

    try:
        return marker_path.read_text(encoding="utf-8").rstrip("\n")
    except OSError:
        return ""


def _current_edit_signature(repo_root: Path) -> str:
    if not repo_root.exists() or not repo_root.is_dir():
        return ""

    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "status",
                "--porcelain",
                "--untracked-files=normal",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return ""

    lines: list[str] = []
    for raw in proc.stdout.splitlines():
        if not raw.strip():
            continue
        line = raw.rstrip("\n")
        path = line[3:] if len(line) > 3 else ""
        if " -> " in path:
            candidates = [part.strip() for part in path.split(" -> ")]
        else:
            candidates = [path.strip()]
        if any(_is_ignored_edit_path(candidate) for candidate in candidates if candidate):
            continue
        lines.append(line)

    return "\n".join(sorted(dict.fromkeys(lines)))


def _is_ignored_edit_path(relative_path: str) -> bool:
    ignored_prefixes = (
        ".codegraphcontext/",
        ".speckit/",
        ".uv-cache/",
        "logs/",
        "shadow-runs/",
    )
    normalized = relative_path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.startswith(ignored_prefixes)


def _preview_edit_signature(signature: str) -> str:
    if not signature:
        return ""
    first_line = signature.splitlines()[0].strip()
    return first_line[:120]


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


def _is_memory_pressure_detail(detail: str) -> bool:
    normalized = detail.lower()
    return any(
        marker in normalized
        for marker in (
            "buffer pool",
            "out of memory",
            "memory pressure",
            "memory exhausted",
            "cannot allocate",
            "allocation failed",
        )
    )
