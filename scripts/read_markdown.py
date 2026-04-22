#!/usr/bin/env python3
"""Python entrypoint for markdown discovery and bounded section reads with vector-first anchoring.

Markdown file read-efficiency contract:
- Use this helper for markdown files.
- Prefer the helper over raw file reads so the read stays bounded.
- List markdown headings first when you need discovery, then resolve the target
  section semantically before falling back to exact heading matching.
- The companion shell entrypoint is ``scripts/read-markdown.sh``; source it
  when you need the shell function form.
- If you need only the smallest bounded window, pass the specific section
  heading rather than scanning the whole file.

How to use:
1. Source ``scripts/read-markdown.sh`` or invoke the Python entrypoint.
2. Call ``read_markdown_headings <file>`` when you need discovery.
3. Call ``read_markdown_section <file> <section_heading>`` once you know the exact heading.
4. Let the helper anchor the section and print only the relevant window.

Validation:
- If the section does not resolve, the helper prints a clear not-found error
  and shows nearby headings.
- The helper keeps the read window bounded.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SOURCE_PATH = Path(__file__).resolve()
SCRIPT_DIR = SOURCE_PATH.parent
REPO_ROOT = SCRIPT_DIR.parent


VECTOR_BOOTSTRAP_COMMAND = "uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . bootstrap"


@dataclass(frozen=True)
class _VectorIndexProbe:
    """Parsed vector status payload used to drive refresh branching."""

    status: str
    stale_reason: str
    stale_reason_class: str
    stale_drift_paths: tuple[str, ...]
    stale_signal_source: str
    stale_signal_available: bool
    stale_signal_error: str


def _command_exists(name: str) -> bool:
    """Return whether a shell command is available on PATH."""
    return shutil.which(name) is not None


def _is_repo_local_path(file_path: Path) -> bool:
    """Return whether a target file resides under the repository root."""
    try:
        file_path.resolve().relative_to(REPO_ROOT)
        return True
    except ValueError:
        return False


def _vector_command_env() -> dict[str, str]:
    """Return deterministic env for vector subprocess calls with repo-local uv cache."""
    env = os.environ.copy()
    cache_dir = Path(env.get("UV_CACHE_DIR", str(REPO_ROOT / ".codegraphcontext" / ".uv-cache"))).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    env["UV_CACHE_DIR"] = str(cache_dir)
    env.setdefault("HF_HUB_OFFLINE", "1")
    return env


def _normalize_vector_drift_paths(payload: object) -> tuple[str, ...]:
    """Normalize vector status drift-path payload into repo-relative POSIX paths."""
    if not isinstance(payload, list):
        return ()
    paths: list[str] = []
    for item in payload:
        if not isinstance(item, str):
            continue
        candidate = item.strip().replace("\\", "/")
        if candidate.startswith("./"):
            candidate = candidate[2:]
        if candidate:
            paths.append(candidate)
    return tuple(dict.fromkeys(paths))


def _vector_index_probe(project_root: Path | None = None) -> _VectorIndexProbe:
    """Return parsed vector freshness payload for deterministic refresh decisions."""
    root = project_root or REPO_ROOT
    if not _command_exists("uv"):
        return _VectorIndexProbe(
            status="unavailable",
            stale_reason="uv is not available",
            stale_reason_class="probe-unavailable",
            stale_drift_paths=(),
            stale_signal_source="git",
            stale_signal_available=False,
            stale_signal_error="uv is not available",
        )

    cmd = [
        "uv",
        "run",
        "--no-sync",
        "python",
        "-m",
        "src.mcp_codebase.indexer",
        "--repo-root",
        str(root),
        "status",
    ]
    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        env=_vector_command_env(),
    )
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip() or f"index status probe failed with exit code {proc.returncode}"
        return _VectorIndexProbe(
            status="probe-failed",
            stale_reason=detail,
            stale_reason_class="probe-failed",
            stale_drift_paths=(),
            stale_signal_source="git",
            stale_signal_available=False,
            stale_signal_error=detail,
        )

    payload = (proc.stdout or "").strip()
    if payload in {"", "null"}:
        return _VectorIndexProbe(
            status="missing",
            stale_reason="index snapshot missing",
            stale_reason_class="missing-index",
            stale_drift_paths=(),
            stale_signal_source="git",
            stale_signal_available=False,
            stale_signal_error="index snapshot missing",
        )

    try:
        status_payload = json.loads(payload)
    except json.JSONDecodeError:
        return _VectorIndexProbe(
            status="probe-failed",
            stale_reason="index status probe returned non-JSON output",
            stale_reason_class="probe-failed",
            stale_drift_paths=(),
            stale_signal_source="git",
            stale_signal_available=False,
            stale_signal_error="non-json status payload",
        )
    if not isinstance(status_payload, dict):
        return _VectorIndexProbe(
            status="probe-failed",
            stale_reason="index status probe returned unexpected payload shape",
            stale_reason_class="probe-failed",
            stale_drift_paths=(),
            stale_signal_source="git",
            stale_signal_available=False,
            stale_signal_error="unexpected payload shape",
        )
    is_stale = bool(status_payload.get("is_stale", False))
    return _VectorIndexProbe(
        status="stale" if is_stale else "healthy",
        stale_reason=str(status_payload.get("stale_reason", "") or ""),
        stale_reason_class=str(status_payload.get("stale_reason_class", "none") or "none"),
        stale_drift_paths=_normalize_vector_drift_paths(status_payload.get("stale_drift_paths")),
        stale_signal_source=str(status_payload.get("stale_signal_source", "git") or "git"),
        stale_signal_available=bool(status_payload.get("stale_signal_available", True)),
        stale_signal_error=str(status_payload.get("stale_signal_error", "") or ""),
    )


def _vector_index_status(project_root: Path | None = None) -> str:
    """Return vector index freshness state: healthy, stale, missing, unavailable, or probe-failed."""
    return _vector_index_probe(project_root).status


def _scope_needs_vector_refresh(scope_path: Path, drift_paths: tuple[str, ...]) -> bool | None:
    """Return overlap decision for a requested scope against stale drift paths."""
    if not drift_paths:
        return None
    try:
        scope_abs = scope_path.resolve()
        scope_rel = scope_abs.relative_to(REPO_ROOT).as_posix().rstrip("/")
    except ValueError:
        return None

    if not scope_rel:
        return True
    scope_prefix = f"{scope_rel}/"
    for candidate in drift_paths:
        if candidate == scope_rel:
            return True
        if candidate.startswith(scope_prefix):
            return True
        if scope_rel.startswith(f"{candidate.rstrip('/')}/"):
            return True
    return False


def _vector_refresh_if_needed(scope_path: Path | None = None) -> bool:
    """Require a healthy vector index with scope-aware stale refresh branching."""
    path = scope_path or REPO_ROOT
    probe = _vector_index_probe(REPO_ROOT)
    status = probe.status
    if status == "healthy":
        return True
    if status in {"missing", "unavailable", "probe-failed"}:
        print(f"ERROR: vector preflight failed: status is {status}", file=sys.stderr)
        return False
    if not _command_exists("uv"):
        print("ERROR: vector preflight failed: uv is not available", file=sys.stderr)
        return False

    overlap = _scope_needs_vector_refresh(path, probe.stale_drift_paths)
    overlap_label = (
        "yes"
        if overlap is True
        else "no"
        if overlap is False
        else "unknown"
    )
    cause = probe.stale_reason_class or "none"
    detail = probe.stale_reason or "no stale reason provided"
    signal = probe.stale_signal_source or "git"
    if overlap is False:
        print(
            "WARN: vector index is stale; "
            f"cause={cause}; signal={signal}; overlap={overlap_label}; detail={detail}; "
            f"drift_paths={list(probe.stale_drift_paths)}; "
            f"refreshing scoped index in background for {path}",
            file=sys.stderr,
        )
        refresh_cmd = [
            "uv",
            "run",
            "--no-sync",
            "python",
            "-m",
            "src.mcp_codebase.indexer",
            "--repo-root",
            str(REPO_ROOT),
            "refresh",
            str(path),
        ]
        try:
            subprocess.Popen(
                refresh_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=_vector_command_env(),
            )
        except OSError as exc:
            print(f"WARN: vector background refresh could not start: {exc}", file=sys.stderr)
        return True

    print(
        "WARN: vector index is stale; "
        f"cause={cause}; signal={signal}; overlap={overlap_label}; detail={detail}; "
        f"drift_paths={list(probe.stale_drift_paths)}; "
        f"refreshing targeted index for {path}",
        file=sys.stderr,
    )
    cmd = [
        "uv",
        "run",
        "--no-sync",
        "python",
        "-m",
        "src.mcp_codebase.indexer",
        "--repo-root",
        str(REPO_ROOT),
        "refresh",
        str(path),
    ]
    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        env=_vector_command_env(),
    )
    if proc.returncode != 0:
        print("ERROR: vector preflight failed: targeted refresh did not complete", file=sys.stderr)
        return False

    refreshed_probe = _vector_index_probe(REPO_ROOT)
    if refreshed_probe.status != "healthy":
        refreshed_overlap = _scope_needs_vector_refresh(path, refreshed_probe.stale_drift_paths)
        if refreshed_probe.status == "stale" and refreshed_overlap is False:
            print(
                "WARN: vector index remains stale after scoped refresh, but stale drift does not overlap "
                f"requested scope ({path}); proceeding and refreshing in background",
                file=sys.stderr,
            )
            followup_cmd = [
                "uv",
                "run",
                "--no-sync",
                "python",
                "-m",
                "src.mcp_codebase.indexer",
                "--repo-root",
                str(REPO_ROOT),
                "refresh",
                str(path),
            ]
            try:
                subprocess.Popen(
                    followup_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env=_vector_command_env(),
                )
            except OSError as exc:
                print(f"WARN: vector follow-up background refresh could not start: {exc}", file=sys.stderr)
            return True

        print(
            f"ERROR: vector preflight failed after refresh: status is {refreshed_probe.status}",
            file=sys.stderr,
        )
        return False
    return True


def _refresh_indexes_for_read(file_path: Path) -> bool:
    """Run strict preflight checks for repo-local markdown reads."""
    if not _is_repo_local_path(file_path):
        return True
    if _vector_refresh_if_needed(file_path):
        return True
    print(
        "ERROR: read-markdown preflight requires a healthy vector index; run "
        f"`{VECTOR_BOOTSTRAP_COMMAND}`",
        file=sys.stderr,
    )
    return False


def _resolve_file(item: dict[str, object]) -> str | None:
    """Resolve the file path from a vector hit payload."""
    candidate = item.get("file_path")
    if isinstance(candidate, str) and candidate:
        return candidate

    content = item.get("content")
    if isinstance(content, dict):
        nested = content.get("file_path")
        if isinstance(nested, str) and nested:
            return nested
    return None


def _resolve_line(item: dict[str, object]) -> int | None:
    """Resolve the first line number from a vector hit payload."""
    line = item.get("line_start")
    if isinstance(line, int):
        return line
    if isinstance(line, str) and line.isdigit():
        return int(line, 10)

    content = item.get("content")
    if isinstance(content, dict):
        nested = content.get("line_start")
        if isinstance(nested, int):
            return nested
        if isinstance(nested, str) and nested.isdigit():
            return int(nested, 10)
    return None


def _resolve_heading(item: dict[str, object]) -> str | None:
    """Resolve the heading text from a vector hit payload."""
    heading = item.get("heading")
    if isinstance(heading, str) and heading:
        return heading

    content = item.get("content")
    if isinstance(content, dict):
        nested = content.get("heading")
        if isinstance(nested, str) and nested:
            return nested
    return None


def _resolve_breadcrumb_tail(item: dict[str, object]) -> str | None:
    """Resolve the last breadcrumb element from a vector hit payload."""
    breadcrumb = item.get("breadcrumb")
    if isinstance(breadcrumb, list) and breadcrumb:
        last = breadcrumb[-1]
        if isinstance(last, str) and last:
            return last

    content = item.get("content")
    if isinstance(content, dict):
        nested = content.get("breadcrumb")
        if isinstance(nested, list) and nested:
            last = nested[-1]
            if isinstance(last, str) and last:
                return last
    return None


def _resolve_breadcrumb_depth(item: dict[str, object]) -> int:
    """Resolve the breadcrumb depth from a vector hit payload."""
    breadcrumb = item.get("breadcrumb")
    if isinstance(breadcrumb, list):
        return len(breadcrumb)

    content = item.get("content")
    if isinstance(content, dict):
        nested = content.get("breadcrumb")
        if isinstance(nested, list):
            return len(nested)
    return 0


def _normalize_heading_text(text: str) -> str:
    """Normalize heading text for fuzzy comparisons."""
    return re.sub(r"\s+", " ", text.strip().lstrip("#").strip()).rstrip(":").lower()


def _markdown_heading_lines(target_file: Path) -> list[tuple[int, str]]:
    """Collect markdown heading lines in file order."""
    headings: list[tuple[int, str]] = []
    heading_pattern = re.compile(r"^(#{1,6})\s+.+$")
    with target_file.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            stripped = line.rstrip("\n")
            if heading_pattern.match(stripped):
                headings.append((index, stripped))
    return headings


def _format_heading_hint(headings: list[tuple[int, str]], *, limit: int = 8) -> str:
    """Render a compact heading hint for not-found errors."""
    if not headings:
        return "no markdown headings found"
    rendered = [f"{line}\t{heading}" for line, heading in headings[:limit]]
    if len(headings) > limit:
        rendered.append("...")
    return "; ".join(rendered)


def _section_matches_query(section: str, candidate: str | None) -> bool:
    """Return whether a query and candidate heading are close enough to match."""
    if not section or not candidate:
        return False
    section_norm = _normalize_heading_text(section)
    candidate_norm = _normalize_heading_text(candidate)
    if not section_norm or not candidate_norm:
        return False
    return (
        candidate_norm == section_norm
        or candidate_norm.startswith(f"{section_norm}:")
        or candidate_norm.startswith(f"{section_norm} -")
        or candidate_norm.startswith(f"{section_norm} ")
    )


def _score_markdown_match(
    section: str,
    heading: str | None,
    breadcrumb_tail: str | None,
    *,
    breadcrumb_depth: int = 0,
) -> int | None:
    """Score a markdown hit so more specific same-file matches win."""
    if not _section_matches_query(section, heading) and not _section_matches_query(section, breadcrumb_tail):
        return None

    section_norm = _normalize_heading_text(section)
    heading_norm = _normalize_heading_text(heading or "")
    breadcrumb_norm = _normalize_heading_text(breadcrumb_tail or "")

    score = 0
    if heading_norm == section_norm:
        score = 100
    elif breadcrumb_norm == section_norm:
        score = 98
    elif heading_norm.startswith(section_norm):
        score = 88
    elif breadcrumb_norm.startswith(section_norm):
        score = 86
    elif section_norm.startswith(heading_norm) and heading_norm:
        score = 72
    elif section_norm.startswith(breadcrumb_norm) and breadcrumb_norm:
        score = 70
    elif section_norm in heading_norm:
        score = 60
    elif section_norm in breadcrumb_norm:
        score = 58
    else:
        score = 50

    return score + min(max(breadcrumb_depth, 0), 10)


def _vector_markdown_line_num(target_file: Path, section: str) -> int | None:
    """Use vector lookup to resolve a markdown section line number."""
    if not target_file or not section:
        return None

    try:
        subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            check=True,
            text=True,
            env=_vector_command_env(),
        )
    except Exception:
        return None

    cmd = [
        "uv",
        "run",
        "--no-sync",
        "python",
        "-m",
        "src.mcp_codebase.indexer",
        "--repo-root",
        str(REPO_ROOT),
        "query",
        section,
        "--scope",
        "markdown",
        "--top-k",
        "5",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=_vector_command_env())
    if proc.returncode != 0:
        return None

    try:
        payload = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None

    best_match: tuple[int, int, int] | None = None

    for raw_item in payload:
        if not isinstance(raw_item, dict):
            continue
        candidate = _resolve_file(raw_item)
        if not candidate:
            continue
        try:
            if Path(candidate).expanduser().resolve() != target_file:
                continue
        except Exception:
            continue

        heading = _resolve_heading(raw_item)
        breadcrumb_tail = _resolve_breadcrumb_tail(raw_item)
        score = _score_markdown_match(
            section,
            heading,
            breadcrumb_tail,
            breadcrumb_depth=_resolve_breadcrumb_depth(raw_item),
        )
        if score is None:
            continue
        line = _resolve_line(raw_item)
        if line is not None:
            candidate_match = (score, _resolve_breadcrumb_depth(raw_item), -line)
            if best_match is None or candidate_match > best_match:
                best_match = candidate_match

    if best_match is not None:
        return -best_match[2]

    return None


def _fallback_heading_line_num(target_file: Path, section: str) -> int | None:
    """Fall back to matching any markdown heading level when vector lookup is unavailable."""
    with target_file.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            stripped = line.rstrip("\n")
            if not re.match(r"^(#{1,6})\s+.+$", stripped):
                continue
            heading = stripped.lstrip("#").strip()
            if _section_matches_query(section, heading):
                return index
    return None


def read_markdown_section(file_path: str, section: str) -> int:
    """Render a bounded line window for a markdown heading section."""
    if not file_path or not section:
        print(
            "ERROR: read_markdown_section requires two arguments: <file> <section_heading>",
            file=sys.stderr,
        )
        return 1

    target_file = Path(file_path)
    if not target_file.is_file():
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        return 1

    resolved_file = target_file.resolve()
    if not _refresh_indexes_for_read(resolved_file):
        return 1
    line_num = _vector_markdown_line_num(resolved_file, section)
    if line_num is None:
        line_num = _fallback_heading_line_num(resolved_file, section)

    if line_num is None:
        heading_hint = _format_heading_hint(_markdown_heading_lines(resolved_file))
        print(
            (
                f"ERROR: Section '## {section}' not found in {file_path}. "
                f"Use read_markdown_headings {file_path} to inspect headings. "
                f"Available headings: {heading_hint}"
            ),
            file=sys.stderr,
        )
        return 1

    window_size = 50
    content = resolved_file.read_text(encoding="utf-8").split("\n")
    start_idx = max(line_num - 1, 0)
    end_idx = min(start_idx + window_size, len(content))
    for index in range(start_idx, end_idx):
        print(f"{index + 1}\t{content[index]}")
    return 0


def read_markdown_headings(file_path: str) -> int:
    """Render the markdown headings discovery list for a file."""
    if not file_path:
        print("ERROR: read_markdown_headings requires one argument: <file>", file=sys.stderr)
        return 1

    target_file = Path(file_path)
    if not target_file.is_file():
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        return 1

    resolved_file = target_file.resolve()
    if not _refresh_indexes_for_read(resolved_file):
        return 1
    for line_num, heading in _markdown_heading_lines(resolved_file):
        print(f"{line_num}\t{heading}")
    return 0


def main(argv: list[str]) -> int:
    """CLI entrypoint compatible with read-markdown.sh wrapper semantics."""
    if len(argv) > 0 and argv[0] == "--headings":
        file_path = argv[1] if len(argv) > 1 else ""
        return read_markdown_headings(file_path)
    file_path = argv[0] if len(argv) > 0 else ""
    section = argv[1] if len(argv) > 1 else ""
    return read_markdown_section(file_path, section)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
