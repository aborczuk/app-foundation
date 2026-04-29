#!/usr/bin/env python3
"""Read markdown headings or anchored sections from a local file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _is_heading(line: str) -> bool:
    """Return whether a line is a markdown heading."""
    return line.lstrip().startswith("#")


def read_markdown_headings(file_path: str) -> list[str]:
    """Return markdown headings as numbered lines."""
    path = Path(file_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        f"{line_number}\t{line}"
        for line_number, line in enumerate(lines, 1)
        if _is_heading(line)
    ]


def _heading_text(line: str) -> str:
    """Return the visible text for a markdown heading line."""
    return line.lstrip("#").strip()


def _find_heading_index(lines: list[str], section_heading: str) -> int | None:
    """Locate the best heading index for the requested section."""
    exact = section_heading.strip()
    candidates: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        if not _is_heading(line):
            continue
        heading_text = _heading_text(line)
        if heading_text == exact:
            return index
        if heading_text.endswith(exact):
            candidates.append((len(heading_text), index))
        elif exact in heading_text:
            candidates.append((len(heading_text), index))
    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][1]
    return None


def read_markdown_section(file_path: str, section_heading: str) -> list[str]:
    """Return a 50-line numbered window anchored at a markdown section."""
    path = Path(file_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    index = _find_heading_index(lines, section_heading)
    if index is None:
        headings = read_markdown_headings(file_path)
        available = "\n".join(headings)
        raise ValueError(
            f"ERROR: Section '## {section_heading}' not found in {path}\n"
            f"Use read_markdown.py --headings {path} to inspect headings.\n"
            f"Available headings:\n{available}"
        )

    window = lines[index : index + 50]
    return [f"{line_number}\t{line}" for line_number, line in enumerate(window, start=index + 1)]


def _build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for the markdown helper."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--headings", action="store_true", dest="headings")
    parser.add_argument("--help", "-h", action="store_true", dest="help")
    parser.add_argument("file_path", nargs="?")
    parser.add_argument("section_heading", nargs="?")
    return parser


def main(argv: list[str]) -> int:
    """Dispatch the markdown helper CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.help:
        print(
            "Usage: scripts/read_markdown.py [--headings] <file> [section_heading]\n\n"
            "Without --headings, the script prints a 50-line numbered window anchored at the\n"
            "first matching markdown heading.\n"
            "With --headings, it prints all headings in the file.\n"
        )
        return 0

    if args.headings:
        if not args.file_path or args.section_heading:
            print("ERROR: read_markdown_headings requires one argument: <file>", file=sys.stderr)
            return 1
        for line in read_markdown_headings(args.file_path):
            print(line)
        return 0

    if not args.file_path or not args.section_heading:
        print("ERROR: read_markdown_section requires two arguments: <file> <section_heading>", file=sys.stderr)
        return 1

    try:
        for line in read_markdown_section(args.file_path, args.section_heading):
            print(line)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
