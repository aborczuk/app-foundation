#!/usr/bin/env python3
"""Deterministically update quickstart runbook notes and decision-log entries."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_QUICKSTART_TITLE = "# Quickstart"
RUNBOOK_HEADING = "## Deterministic Operator Runbook Notes"
RUNBOOK_SUBHEADING = "### Recovery Delta Validation Notes"
DECISION_LOG_HEADING = "## Decision Log"
ENTRY_MARKER_TEMPLATE = "<!-- speckit_implement_docs:entry_id={entry_id} -->"


@dataclass(frozen=True)
class UpdateRequest:
    """Input contract for deterministic quickstart documentation updates."""

    feature_dir: Path
    entry_id: str
    runbook_notes: tuple[str, ...]
    decision_log_entries: tuple[str, ...]


def _non_empty_lines(values: list[str]) -> tuple[str, ...]:
    """Normalize and keep non-empty bullet candidate lines."""
    cleaned: list[str] = []
    for raw in values:
        normalized = raw.strip()
        if normalized:
            cleaned.append(normalized)
    return tuple(cleaned)


def _load_request(args: argparse.Namespace) -> UpdateRequest:
    """Build and validate the update request from CLI flags and optional JSON payload."""
    payload: dict[str, Any] = {}
    if args.notes_json:
        notes_path = Path(args.notes_json).resolve()
        if not notes_path.exists():
            raise ValueError(f"notes_json_not_found:{notes_path}")
        loaded = json.loads(notes_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("notes_json_must_be_object")
        payload = loaded

    feature_dir = Path(args.feature_dir).resolve()
    entry_id = str(args.entry_id or payload.get("entry_id") or "").strip()
    runbook_notes = _non_empty_lines(
        list(args.runbook_note or []) + list(payload.get("runbook_notes") or [])
    )
    decision_log_entries = _non_empty_lines(
        list(args.decision_entry or []) + list(payload.get("decision_log_entries") or [])
    )

    if not feature_dir:
        raise ValueError("feature_dir_required")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", entry_id):
        raise ValueError("entry_id_invalid")
    if not runbook_notes and not decision_log_entries:
        raise ValueError("no_updates_requested")

    return UpdateRequest(
        feature_dir=feature_dir,
        entry_id=entry_id,
        runbook_notes=runbook_notes,
        decision_log_entries=decision_log_entries,
    )


def _bootstrap_quickstart(quickstart_path: Path) -> None:
    """Create a minimal quickstart skeleton with required headings when missing."""
    quickstart_path.parent.mkdir(parents=True, exist_ok=True)
    quickstart_path.write_text(
        "\n".join(
            [
                DEFAULT_QUICKSTART_TITLE,
                "",
                RUNBOOK_HEADING,
                "",
                RUNBOOK_SUBHEADING,
                "",
                DECISION_LOG_HEADING,
                "",
            ]
        ),
        encoding="utf-8",
    )


def _ensure_heading(lines: list[str], heading: str, *, after_heading: str | None = None) -> int:
    """Ensure heading exists and return its line index."""
    for idx, line in enumerate(lines):
        if line.strip() == heading:
            return idx

    insert_at = len(lines)
    if after_heading is not None:
        for idx, line in enumerate(lines):
            if line.strip() == after_heading:
                insert_at = idx + 1
                break

    block = ["", heading, ""]
    lines[insert_at:insert_at] = block
    return insert_at + 1


def _section_bounds(lines: list[str], heading_index: int) -> tuple[int, int]:
    """Return start/end indexes for section body under a heading."""
    start = heading_index + 1
    end = len(lines)
    for idx in range(start, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break
    return start, end


def _heading_index(lines: list[str], heading: str) -> int:
    """Return heading index after mutations; raise if not present."""
    for idx, line in enumerate(lines):
        if line.strip() == heading:
            return idx
    raise ValueError(f"heading_not_found:{heading}")


def _insert_marker_and_bullets(
    lines: list[str],
    *,
    heading_index: int,
    entry_id: str,
    bullets: tuple[str, ...],
) -> bool:
    """Append deterministic marker + bullets to a section unless entry already exists."""
    marker = ENTRY_MARKER_TEMPLATE.format(entry_id=entry_id)
    body_start, body_end = _section_bounds(lines, heading_index)
    section_lines = lines[body_start:body_end]
    if any(line.strip() == marker for line in section_lines):
        return False

    insertion = ["", marker]
    insertion.extend(f"- {item}" for item in bullets)
    insertion.append("")
    lines[body_end:body_end] = insertion
    return True


def apply_update(request: UpdateRequest) -> dict[str, Any]:
    """Apply deterministic documentation update and return machine-readable result."""
    quickstart_path = (request.feature_dir / "quickstart.md").resolve()
    if not quickstart_path.exists():
        _bootstrap_quickstart(quickstart_path)

    lines = quickstart_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        lines = [DEFAULT_QUICKSTART_TITLE, ""]
    if not lines[0].startswith("# "):
        lines.insert(0, DEFAULT_QUICKSTART_TITLE)
        lines.insert(1, "")

    _ensure_heading(lines, RUNBOOK_HEADING)
    _ensure_heading(
        lines,
        RUNBOOK_SUBHEADING,
        after_heading=RUNBOOK_HEADING,
    )
    _ensure_heading(lines, DECISION_LOG_HEADING)

    runbook_updated = False
    if request.runbook_notes:
        runbook_updated = _insert_marker_and_bullets(
            lines,
            heading_index=_heading_index(lines, RUNBOOK_SUBHEADING),
            entry_id=f"{request.entry_id}:runbook",
            bullets=request.runbook_notes,
        )

    decision_log_updated = False
    if request.decision_log_entries:
        decision_log_updated = _insert_marker_and_bullets(
            lines,
            heading_index=_heading_index(lines, DECISION_LOG_HEADING),
            entry_id=f"{request.entry_id}:decision_log",
            bullets=request.decision_log_entries,
        )

    changed = runbook_updated or decision_log_updated
    if changed:
        quickstart_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    reasons: list[str] = []
    if not changed:
        reasons.append("entry_already_recorded")
    if request.runbook_notes and not runbook_updated:
        reasons.append("runbook_entry_already_recorded")
    if request.decision_log_entries and not decision_log_updated:
        reasons.append("decision_log_entry_already_recorded")

    return {
        "ok": True,
        "feature_dir": str(request.feature_dir),
        "quickstart_path": str(quickstart_path),
        "entry_id": request.entry_id,
        "runbook_updated": runbook_updated,
        "decision_log_updated": decision_log_updated,
        "changed": changed,
        "reasons": reasons,
        "updated_paths": [str(quickstart_path)] if changed else [],
    }


def _build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for deterministic implement-doc updates."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-dir", required=True)
    parser.add_argument("--entry-id", default="")
    parser.add_argument("--runbook-note", action="append", default=[])
    parser.add_argument("--decision-entry", action="append", default=[])
    parser.add_argument("--notes-json", default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entrypoint for deterministic implement-doc updater."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        request = _load_request(args)
        payload = apply_update(request)
    except (ValueError, json.JSONDecodeError) as exc:
        payload = {"ok": False, "reasons": [str(exc)]}
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"status=FAIL reasons={','.join(payload['reasons'])}")
        return 2

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "PASS" if payload["ok"] else "FAIL"
        print(
            " ".join(
                [
                    f"status={status}",
                    f"changed={str(payload['changed']).lower()}",
                    f"runbook_updated={str(payload['runbook_updated']).lower()}",
                    f"decision_log_updated={str(payload['decision_log_updated']).lower()}",
                ]
            )
        )
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
