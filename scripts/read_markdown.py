#!/usr/bin/env python3
"""Python entrypoint for markdown section reads with vector-first anchoring."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def _repo_root_from_cwd() -> Path:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=True,
            text=True,
        )
        return Path(proc.stdout.strip() or ".").resolve()
    except Exception:
        return Path.cwd().resolve()


def _resolve_file(item: dict[str, object]) -> str | None:
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


def _normalize_heading_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lstrip("#").strip()).rstrip(":").lower()


def _section_matches_query(section: str, candidate: str | None) -> bool:
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


def _vector_markdown_line_num(target_file: Path, section: str) -> int | None:
    if not target_file or not section:
        return None

    try:
        subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            check=True,
            text=True,
        )
    except Exception:
        return None

    repo_root = _repo_root_from_cwd()
    cmd = [
        "uv",
        "run",
        "--no-sync",
        "python",
        "-m",
        "src.mcp_codebase.indexer",
        "--repo-root",
        str(repo_root),
        "query",
        section,
        "--scope",
        "markdown",
        "--top-k",
        "5",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return None

    try:
        payload = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None

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
        if not _section_matches_query(section, heading) and not _section_matches_query(section, breadcrumb_tail):
            continue

        line = _resolve_line(raw_item)
        if line is not None:
            return line

    return None


def _fallback_heading_line_num(target_file: Path, section: str) -> int | None:
    with target_file.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            stripped = line.rstrip("\n")
            if not stripped.startswith("## "):
                continue
            heading = stripped[3:]
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
    line_num = _vector_markdown_line_num(resolved_file, section)
    if line_num is None:
        line_num = _fallback_heading_line_num(resolved_file, section)

    if line_num is None:
        print(f"ERROR: Section '## {section}' not found in {file_path}", file=sys.stderr)
        return 1

    window_size = 50
    content = resolved_file.read_text(encoding="utf-8").split("\n")
    start_idx = max(line_num - 1, 0)
    end_idx = min(start_idx + window_size, len(content))
    for index in range(start_idx, end_idx):
        print(f"{index + 1}\t{content[index]}")
    return 0


def main(argv: list[str]) -> int:
    """CLI entrypoint compatible with read-markdown.sh wrapper semantics."""
    file_path = argv[0] if len(argv) > 0 else ""
    section = argv[1] if len(argv) > 1 else ""
    return read_markdown_section(file_path, section)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
