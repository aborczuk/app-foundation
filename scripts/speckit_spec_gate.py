#!/usr/bin/env python3
"""Deterministic checks for /speckit.specify gates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

from spec_routing import load_spec_routing_contract

CHECKBOX_RE = re.compile(r"^\s*-\s*\[(?P<state>[ xX])\]")
NEEDS_CLARIFICATION_RE = re.compile(r"\[NEEDS CLARIFICATION:\s*(?P<text>[^\]]+)\]")
QUESTION_HEADER_RE = re.compile(r"^\s*##\s+Question\s+(?P<num>\d+)\s*:\s*(?P<title>.+?)\s*$")

REQUIRED_CHECKLIST_HEADINGS = (
    "## Content Quality",
    "## Requirement Completeness",
    "## Feature Readiness",
)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="subcommand", required=True)

    checklist = sub.add_parser(
        "checklist-status", help="Validate requirements checklist presence and completion."
    )
    checklist.add_argument("--feature-dir", required=True)
    checklist.add_argument("--json", action="store_true")

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

    routing_check = sub.add_parser(
        "validate-routing", help="Validate the machine-readable routing contract in spec.md."
    )
    routing_check.add_argument("--spec-file", required=True)
    routing_check.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"ok={payload.get('ok')} mode={payload.get('mode')}")
    for reason in payload.get("reasons", []):
        print(f"- {reason}")


def _checklist_status(feature_dir: Path) -> tuple[int, dict[str, Any]]:
    checklists_dir = feature_dir / "checklists"
    requirements = checklists_dir / "requirements.md"
    reasons: list[str] = []
    entries: list[dict[str, Any]] = []
    incomplete_total = 0

    if not checklists_dir.is_dir():
        reasons.append("missing_checklists_dir")
    if not requirements.exists():
        reasons.append("missing_requirements_checklist")

    for checklist in sorted(checklists_dir.glob("*.md")) if checklists_dir.is_dir() else []:
        total = 0
        completed = 0
        incomplete = 0
        for line in checklist.read_text(encoding="utf-8").splitlines():
            match = CHECKBOX_RE.match(line)
            if not match:
                continue
            total += 1
            if match.group("state").lower() == "x":
                completed += 1
            else:
                incomplete += 1
        incomplete_total += incomplete
        entries.append(
            {
                "name": checklist.name,
                "path": str(checklist),
                "total": total,
                "completed": completed,
                "incomplete": incomplete,
                "status": "PASS" if incomplete == 0 else "FAIL",
            }
        )

    if requirements.exists():
        requirements_text = requirements.read_text(encoding="utf-8")
        for heading in REQUIRED_CHECKLIST_HEADINGS:
            if heading not in requirements_text:
                reasons.append(f"requirements_missing_heading:{heading}")
    if incomplete_total > 0:
        reasons.append("incomplete_checklist_items")

    payload = {
        "mode": "checklist_status",
        "feature_dir": str(feature_dir),
        "requirements_path": str(requirements),
        "entries": entries,
        "incomplete_total": incomplete_total,
        "reasons": reasons,
        "ok": len(reasons) == 0,
    }
    return (0 if payload["ok"] else 2, payload)


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


def _validate_routing(spec_file: Path) -> tuple[int, dict[str, Any]]:
    """Validate that spec.md contains a parseable routing contract."""
    contract, reasons = load_spec_routing_contract(spec_file)
    payload: dict[str, Any] = {
        "mode": "validate_routing",
        "spec_file": str(spec_file),
        "routing": contract.get("routing") if contract is not None else None,
        "risk": contract.get("risk") if contract is not None else None,
        "reasons": reasons,
        "ok": len(reasons) == 0,
    }
    return (0 if payload["ok"] else 2, payload)


def main(argv: Sequence[str] | None = None) -> int:
    """Run selected /speckit.specify deterministic gate check."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.subcommand == "checklist-status":
        exit_code, payload = _checklist_status(Path(args.feature_dir).resolve())
    elif args.subcommand == "extract-clarifications":
        exit_code, payload = _extract_clarifications(Path(args.spec_file).resolve())
    elif args.subcommand == "validate-clarification-questions":
        exit_code, payload = _validate_clarification_questions(
            Path(args.markdown_file).resolve()
        )
    elif args.subcommand == "validate-routing":
        exit_code, payload = _validate_routing(Path(args.spec_file).resolve())
    else:
        return 2

    _emit(payload, as_json=bool(args.json))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
