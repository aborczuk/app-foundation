#!/usr/bin/env python3
"""Validate that markdown docs follow one of the known command-doc heading shapes."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

KNOWN_SHAPES: dict[str, list[str]] = {
    "compact_expanded": [
        "User Input",
        "Compact Contract (Load First)",
        "Expanded Guidance (Load On Demand)",
        "Behavior rules",
    ],
    "legacy_outline": [
        "User Input",
        "Purpose",
        "Outline",
        "Behavior rules",
    ],
}


def _top_level_headings(markdown_file: Path) -> list[str]:
    """Return the top-level markdown headings in file order."""
    headings: list[str] = []
    for line in markdown_file.read_text(encoding="utf-8").splitlines():
        if re.match(r"^##\s+.+$", line):
            headings.append(re.sub(r"^##\s+", "", line).strip())
    return headings


def _shape_matches(headings: list[str], expected: list[str]) -> bool:
    """Return whether the file headings match the expected shape exactly."""
    return headings == expected


def validate_markdown_doc_shape(
    *,
    markdown_file: Path,
    shape: str = "auto",
) -> dict[str, Any]:
    """Validate a markdown doc against a known heading shape."""
    if not markdown_file.exists():
        return {
            "markdown_file": str(markdown_file),
            "shape": shape,
            "ok": False,
            "reasons": ["missing_markdown_file"],
            "headings": [],
            "matched_shape": None,
            "available_shapes": sorted(KNOWN_SHAPES),
        }

    headings = _top_level_headings(markdown_file)
    reasons: list[str] = []
    matched_shape: str | None = None

    if shape != "auto" and shape not in KNOWN_SHAPES:
        reasons.append(f"unknown_shape:{shape}")
    else:
        shapes_to_check = [shape] if shape != "auto" else sorted(KNOWN_SHAPES)
        for candidate in shapes_to_check:
            if candidate in KNOWN_SHAPES and _shape_matches(headings, KNOWN_SHAPES[candidate]):
                matched_shape = candidate
                break
        if matched_shape is None:
            reasons.append("shape_mismatch")

    payload = {
        "markdown_file": str(markdown_file),
        "shape": shape,
        "ok": len(reasons) == 0,
        "reasons": reasons,
        "headings": headings,
        "matched_shape": matched_shape,
        "available_shapes": sorted(KNOWN_SHAPES),
    }
    return payload


def _build_parser() -> argparse.ArgumentParser:
    """Build the markdown shape validation CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="Path to the markdown file to validate.")
    parser.add_argument(
        "--shape",
        default="auto",
        help="Expected shape name, or auto to detect from known shapes.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate markdown heading shapes and return an exit status."""
    args = _build_parser().parse_args(argv)
    payload = validate_markdown_doc_shape(
        markdown_file=Path(args.file).resolve(),
        shape=args.shape,
    )

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "PASS" if payload["ok"] else "FAIL"
        print(f"status={status}")
        print(f"shape={payload['shape']}")
        if payload["matched_shape"]:
            print(f"matched_shape={payload['matched_shape']}")
        if payload["reasons"]:
            print("reasons=" + ",".join(payload["reasons"]))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
