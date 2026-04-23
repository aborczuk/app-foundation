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

FORBIDDEN_PROCEDURE_MARKERS = (
    "speckit_gate_status.py",
    "speckit_prepare_ignores.py",
    "task gate and ledger flow",
    "append_pipeline_success_event",
)

REQUIRED_COMMAND_DOC_IDS: tuple[str, ...] = (
    "speckit.run",
    "speckit.tasking",
    "speckit.implement",
)


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


def _compact_contract_body(markdown_file: Path) -> str:
    """Return the body text that belongs to the compact contract section."""
    lines = markdown_file.read_text(encoding="utf-8").splitlines()
    compact_heading = "## Compact Contract (Load First)"
    collecting = False
    compact_lines: list[str] = []

    for line in lines:
        if line.strip() == compact_heading:
            collecting = True
            continue
        if collecting and re.match(r"^##\s+.+$", line):
            break
        if collecting:
            compact_lines.append(line)

    return "\n".join(compact_lines)


def _find_forbidden_procedure_markers(text: str) -> list[str]:
    """Return executable gate/append markers embedded in a command doc."""
    lower_text = text.lower()
    return [marker for marker in FORBIDDEN_PROCEDURE_MARKERS if marker in lower_text]


def _resolve_repo_root(markdown_file: Path, repo_root: Path | None) -> Path:
    """Resolve repository root for required command-doc checks."""
    if repo_root is not None:
        return repo_root.resolve()
    for candidate in [markdown_file.resolve(), *markdown_file.resolve().parents]:
        if (candidate / "command-manifest.yaml").exists():
            return candidate
    return Path.cwd().resolve()


def _validate_required_command_docs(repo_root: Path) -> dict[str, Any]:
    """Validate required command-doc shape and compact-contract marker hygiene."""
    command_dir = repo_root / ".claude" / "commands"
    missing_docs: list[str] = []
    shape_failures: list[str] = []
    marker_failures: list[dict[str, Any]] = []
    validated_docs: list[str] = []

    for command_id in REQUIRED_COMMAND_DOC_IDS:
        doc_path = command_dir / f"{command_id}.md"
        if not doc_path.exists():
            missing_docs.append(command_id)
            continue
        validated_docs.append(command_id)
        headings = _top_level_headings(doc_path)
        if not _shape_matches(headings, KNOWN_SHAPES["compact_expanded"]):
            shape_failures.append(command_id)
            continue
        forbidden_markers = _find_forbidden_procedure_markers(_compact_contract_body(doc_path))
        if forbidden_markers:
            marker_failures.append(
                {
                    "command_id": command_id,
                    "forbidden_markers": forbidden_markers,
                }
            )

    return {
        "missing_docs": missing_docs,
        "shape_failures": shape_failures,
        "marker_failures": marker_failures,
        "validated_docs": validated_docs,
    }


def validate_markdown_doc_shape(
    *,
    markdown_file: Path,
    shape: str = "auto",
    enforce_required_command_set: bool = False,
    repo_root: Path | None = None,
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
    forbidden_markers: list[str] = []
    required_command_docs: dict[str, Any] | None = None

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
        else:
            forbidden_markers = _find_forbidden_procedure_markers(_compact_contract_body(markdown_file))
            if forbidden_markers:
                reasons.append("executable_procedures_detected")

    if enforce_required_command_set:
        required_command_docs = _validate_required_command_docs(
            _resolve_repo_root(markdown_file, repo_root)
        )
        if required_command_docs["missing_docs"]:
            reasons.append("required_command_docs_missing")
        if required_command_docs["shape_failures"]:
            reasons.append("required_command_doc_shape_mismatch")
        if required_command_docs["marker_failures"]:
            reasons.append("required_command_doc_executable_procedures_detected")

    payload = {
        "markdown_file": str(markdown_file),
        "shape": shape,
        "ok": len(reasons) == 0,
        "reasons": reasons,
        "headings": headings,
        "matched_shape": matched_shape,
        "forbidden_markers": forbidden_markers,
        "available_shapes": sorted(KNOWN_SHAPES),
        "required_command_docs": required_command_docs,
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
    parser.add_argument(
        "--enforce-required-command-set",
        action="store_true",
        help="Also validate required migrated command docs in the repository.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Optional repository root override used with --enforce-required-command-set.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate markdown heading shapes and return an exit status."""
    args = _build_parser().parse_args(argv)
    payload = validate_markdown_doc_shape(
        markdown_file=Path(args.file).resolve(),
        shape=args.shape,
        enforce_required_command_set=bool(args.enforce_required_command_set),
        repo_root=Path(args.repo_root).resolve() if args.repo_root else None,
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
