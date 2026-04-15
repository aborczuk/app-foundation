"""Markdown section extraction for the local vector index."""

from __future__ import annotations

import fnmatch
import hashlib
import re
from pathlib import Path
from typing import Sequence

from src.mcp_codebase.index.domain import IndexScope, MarkdownSection
from src.mcp_codebase.index.extractors.python import should_skip_path

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def extract_markdown_sections(
    file_path: str | Path,
    *,
    repo_root: str | Path | None = None,
    exclude_patterns: Sequence[str] = (),
    source_text: str | None = None,
) -> list[MarkdownSection]:
    """Extract normalized markdown sections with breadcrumbs and previews."""

    repo_root = Path(repo_root or Path.cwd()).expanduser().resolve()
    candidate = Path(file_path)

    if should_skip_path(candidate, repo_root, exclude_patterns):
        return []

    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if candidate.suffix.lower() not in {".md", ".markdown", ".mdown"}:
        return []
    if not candidate.exists() or not candidate.is_file():
        return []

    text = source_text if source_text is not None else candidate.read_text(
        encoding="utf-8"
    )
    lines = text.splitlines()
    headings: list[tuple[int, int, str]] = []
    for line_no, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match:
            headings.append((line_no, len(match.group(1)), match.group(2).strip()))

    sections: list[MarkdownSection] = []
    breadcrumb_stack: list[tuple[int, str]] = []

    for index, (start_line_no, depth, heading) in enumerate(headings):
        while breadcrumb_stack and breadcrumb_stack[-1][0] >= depth:
            breadcrumb_stack.pop()

        breadcrumb = (*[title for _, title in breadcrumb_stack], heading)
        next_line_no = (
            headings[index + 1][0] if index + 1 < len(headings) else len(lines)
        )
        section_lines = lines[start_line_no + 1 : next_line_no]
        preview = _section_preview(section_lines)
        content_hash = hashlib.sha256(
            "\n".join([heading, *section_lines]).encode("utf-8")
        ).hexdigest()

        sections.append(
            MarkdownSection(
                heading=heading,
                breadcrumb=breadcrumb,
                file_path=candidate,
                line_start=start_line_no + 1,
                line_end=max(start_line_no + 1, next_line_no),
                depth=depth,
                preview=preview,
                content_hash=content_hash,
                scope=IndexScope.MARKDOWN,
            )
        )
        breadcrumb_stack.append((depth, heading))

    return sections


def _section_preview(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped:
            return stripped[:160]
    return ""
