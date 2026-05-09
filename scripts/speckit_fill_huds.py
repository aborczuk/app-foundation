#!/usr/bin/env python3
"""Apply section-aware HUD updates while preserving the generated scaffold."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HEADING_PREFIX = "#"
HUD_TITLE_PREFIX = "# HUD:"
FRONTMATTER_DELIMITER = "---"


@dataclass(frozen=True)
class HeadingSpan:
    """Range metadata for one markdown heading body."""

    title: str
    level: int
    heading_line_index: int
    body_start_index: int
    body_end_index: int


def _render_frontmatter_value(value: Any) -> str:
    """Render a frontmatter value using the repo's JSON-compatible scalar style."""
    return json.dumps(value)


def _find_frontmatter(lines: list[str]) -> tuple[int, int] | None:
    """Return the inclusive line bounds for the YAML frontmatter block."""
    if len(lines) < 2:
        return None
    if lines[0].strip() != FRONTMATTER_DELIMITER:
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_DELIMITER:
            return 0, index
    return None


def _update_frontmatter(lines: list[str], updates: dict[str, Any]) -> list[str]:
    """Apply frontmatter key updates while preserving the existing block shape."""
    if not updates:
        return lines
    bounds = _find_frontmatter(lines)
    if bounds is None:
        raise ValueError("hud_frontmatter_missing")
    start, end = bounds
    body = lines[start + 1 : end]
    key_to_index: dict[str, int] = {}
    for index, line in enumerate(body):
        if ":" not in line:
            continue
        key = line.split(":", 1)[0].strip()
        key_to_index[key] = index
    for key, value in updates.items():
        rendered = f"{key}: {_render_frontmatter_value(value)}\n"
        if key in key_to_index:
            body[key_to_index[key]] = rendered
        else:
            body.append(rendered)
    return lines[: start + 1] + body + lines[end:]


def _parse_heading_spans(lines: list[str]) -> dict[str, HeadingSpan]:
    """Map markdown headings to the line range covering each heading body."""
    headings: list[tuple[int, str, int]] = []
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith("##"):
            continue
        hashes, _, title = stripped.partition(" ")
        if not title:
            continue
        headings.append((index, title.strip(), len(hashes)))

    spans: dict[str, HeadingSpan] = {}
    for item_index, (line_index, title, level) in enumerate(headings):
        body_start = line_index + 1
        body_end = len(lines)
        for next_index, _, next_level in headings[item_index + 1 :]:
            if next_level <= level:
                body_end = next_index
                break
        spans[title] = HeadingSpan(
            title=title,
            level=level,
            heading_line_index=line_index,
            body_start_index=body_start,
            body_end_index=body_end,
        )
    return spans


def _normalize_section_body(body: str) -> list[str]:
    """Render a section body with stable surrounding blank lines."""
    rendered = body.strip("\n")
    if not rendered:
        return ["\n"]
    return ["\n"] + [f"{line}\n" for line in rendered.splitlines()] + ["\n"]


def _apply_section_updates(lines: list[str], sections: dict[str, str]) -> list[str]:
    """Replace the body of named sections while preserving headings and order."""
    updated_lines = list(lines)
    for title, body in sections.items():
        spans = _parse_heading_spans(updated_lines)
        span = spans.get(title)
        if span is None:
            raise ValueError(f"missing_section:{title}")
        replacement = _normalize_section_body(body)
        updated_lines = (
            updated_lines[: span.body_start_index]
            + replacement
            + updated_lines[span.body_end_index :]
        )
    return updated_lines


def _apply_title_update(lines: list[str], title: str | None) -> list[str]:
    """Replace the primary HUD title line when requested."""
    if title is None:
        return lines
    updated_lines = list(lines)
    for index, line in enumerate(updated_lines):
        if line.startswith(HUD_TITLE_PREFIX):
            updated_lines[index] = f"{title.rstrip()}\n"
            return updated_lines
    raise ValueError("missing_hud_title")


def _load_payload(payload_path: Path) -> dict[str, Any]:
    """Load a JSON payload describing HUD section updates."""
    data = json.loads(payload_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("payload_must_be_object")
    return data


def _resolve_task_updates(payload: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Return the per-task update payload from either single-task or bulk JSON."""
    tasks = payload.get("tasks")
    if isinstance(tasks, dict):
        task_payload = tasks.get(task_id)
        if not isinstance(task_payload, dict):
            raise ValueError(f"missing_task_payload:{task_id}")
        return task_payload
    return payload


def _apply_updates_to_hud(hud_path: Path, task_payload: dict[str, Any]) -> None:
    """Update one HUD file in place from structured frontmatter/title/section data."""
    text = hud_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    frontmatter = task_payload.get("frontmatter", {})
    if frontmatter and not isinstance(frontmatter, dict):
        raise ValueError("frontmatter_updates_must_be_object")
    sections = task_payload.get("sections", {})
    if sections and not isinstance(sections, dict):
        raise ValueError("section_updates_must_be_object")

    lines = _update_frontmatter(lines, dict(frontmatter))
    lines = _apply_title_update(lines, task_payload.get("title"))
    lines = _apply_section_updates(lines, {str(key): str(value) for key, value in dict(sections).items()})
    hud_path.write_text("".join(lines), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for scaffold-preserving HUD edits."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-dir", required=True, help="Feature directory containing huds/")
    parser.add_argument("--payload-file", required=True, help="JSON file with per-task HUD updates.")
    parser.add_argument("--task-id", help="Apply a single-task payload to exactly one HUD.")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Apply structured HUD updates to one or more scaffold files."""
    args = _build_parser().parse_args(argv)
    feature_dir = Path(args.feature_dir).resolve()
    payload = _load_payload(Path(args.payload_file).resolve())

    task_ids: list[str]
    if args.task_id:
        task_ids = [args.task_id]
    else:
        tasks = payload.get("tasks")
        if not isinstance(tasks, dict) or not tasks:
            raise SystemExit("bulk payloads require a non-empty tasks object")
        task_ids = [str(task_id) for task_id in tasks]

    updated: list[str] = []
    for task_id in task_ids:
        hud_path = feature_dir / "huds" / f"{task_id}.md"
        if not hud_path.exists():
            raise SystemExit(f"missing_hud:{hud_path}")
        task_payload = _resolve_task_updates(payload, task_id)
        _apply_updates_to_hud(hud_path, task_payload)
        updated.append(task_id)

    result = {"ok": True, "feature_dir": str(feature_dir), "updated_tasks": updated, "updated_count": len(updated)}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"updated={len(updated)}")
        for task_id in updated:
            print(task_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
