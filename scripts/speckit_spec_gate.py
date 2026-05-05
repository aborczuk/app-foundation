#!/usr/bin/env python3
"""Deterministic checks for /speckit.specify gates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

NEEDS_CLARIFICATION_RE = re.compile(r"\[NEEDS CLARIFICATION:\s*(?P<text>[^\]]+)\]")
QUESTION_HEADER_RE = re.compile(r"^\s*##\s+Question\s+(?P<num>\d+)\s*:\s*(?P<title>.+?)\s*$")


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="subcommand", required=True)

    clarifications = sub.add_parser(
        "extract-clarifications", help="Extract [NEEDS CLARIFICATION: ...] markers from spec.md."
    )
    clarifications.add_argument("--spec-file", required=True)
    clarifications.add_argument("--json", action="store_true")

    format_check = sub.add_parser(
        "validate-clarification-questions",
        help="Validate clarification question markdown table formatting.",
    )
    format_check.add_argument("--markdown-file", required=True)
    format_check.add_argument("--json", action="store_true")

    return parser.parse_args(argv)


def _emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"ok={payload.get('ok')} mode={payload.get('mode')}")
    for reason in payload.get("reasons", []):
        print(f"- {reason}")


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = value.strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


def _extract_clarifications(spec_file: Path) -> tuple[int, dict[str, Any]]:
    if not spec_file.exists():
        payload = {
            "mode": "extract_clarifications",
            "spec_file": str(spec_file),
            "marker_count": 0,
            "markers": [],
            "reasons": ["missing_spec_file"],
            "ok": False,
        }
        return (2, payload)

    text = spec_file.read_text(encoding="utf-8")
    markers = _dedupe_keep_order([m.group("text").strip() for m in NEEDS_CLARIFICATION_RE.finditer(text)])
    reasons: list[str] = []
    if len(markers) > 3:
        reasons.append("too_many_clarifications")

    payload = {
        "mode": "extract_clarifications",
        "spec_file": str(spec_file),
        "marker_count": len(markers),
        "markers": markers,
        "reasons": reasons,
        "ok": len(reasons) == 0,
    }
    return (0 if payload["ok"] else 2, payload)


def _split_sections(lines: list[str]) -> list[tuple[int, int]]:
    headers: list[int] = []
    for idx, line in enumerate(lines):
        if QUESTION_HEADER_RE.match(line):
            headers.append(idx)
    windows: list[tuple[int, int]] = []
    for i, start in enumerate(headers):
        end = headers[i + 1] if i + 1 < len(headers) else len(lines)
        windows.append((start, end))
    return windows


def _section_has_option_row(section_lines: list[str], label: str) -> bool:
    row_re = re.compile(rf"^\|\s*{re.escape(label)}\s*\|", re.IGNORECASE)
    return any(row_re.search(line) for line in section_lines)


def _validate_clarification_questions(markdown_file: Path) -> tuple[int, dict[str, Any]]:
    if not markdown_file.exists():
        payload = {
            "mode": "validate_clarification_questions",
            "markdown_file": str(markdown_file),
            "reasons": ["missing_markdown_file"],
            "ok": False,
        }
        return (2, payload)

    lines = markdown_file.read_text(encoding="utf-8").splitlines()
    windows = _split_sections(lines)
    reasons: list[str] = []

    if not windows:
        reasons.append("no_question_sections")

    expected_num = 1
    for start, end in windows:
        section = lines[start:end]
        header = QUESTION_HEADER_RE.match(lines[start])
        if not header:
            reasons.append(f"invalid_question_header_line:{start + 1}")
            continue

        number = int(header.group("num"))
        if number != expected_num:
            reasons.append(f"question_number_not_sequential:{number}")
        expected_num += 1

        joined = "\n".join(section)
        if "| Option | Answer | Implications |" not in joined:
            reasons.append(f"missing_table_header:Q{number}")
        if not _section_has_option_row(section, "A"):
            reasons.append(f"missing_option_A:Q{number}")
        if not _section_has_option_row(section, "B"):
            reasons.append(f"missing_option_B:Q{number}")
        if not _section_has_option_row(section, "C"):
            reasons.append(f"missing_option_C:Q{number}")
        if not _section_has_option_row(section, "Custom"):
            reasons.append(f"missing_option_Custom:Q{number}")
        if not any("**Your choice**" in line for line in section):
            reasons.append(f"missing_your_choice_prompt:Q{number}")

    payload = {
        "mode": "validate_clarification_questions",
        "markdown_file": str(markdown_file),
        "question_count": len(windows),
        "reasons": reasons,
        "ok": len(reasons) == 0,
    }
    return (0 if payload["ok"] else 2, payload)


def main(argv: Sequence[str] | None = None) -> int:
    """Run selected /speckit.specify deterministic gate check."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.subcommand == "extract-clarifications":
        exit_code, payload = _extract_clarifications(Path(args.spec_file).resolve())
    elif args.subcommand == "validate-clarification-questions":
        exit_code, payload = _validate_clarification_questions(
            Path(args.markdown_file).resolve()
        )
    else:
        return 2

    _emit(payload, as_json=bool(args.json))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
