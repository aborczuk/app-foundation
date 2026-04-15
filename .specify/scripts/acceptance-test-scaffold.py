#!/usr/bin/env python3
"""Scaffold story acceptance tests from tasks.md.

This helper turns the tasking contract into clean, syntax-valid pytest modules.
It intentionally produces red-first skeletons with story-specific context so
the implementation phase can fill in deterministic PASS/FAIL oracles without
repeating boilerplate by hand.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


STORY_HEADER_RE = re.compile(
    r"^## Phase\s+\d+:\s+User Story\s+(?P<num>\d+)\s*-\s*(?P<title>.+?)\s*\(Priority:.*$",
    re.MULTILINE,
)
INDEPENDENT_TEST_RE = re.compile(
    r"^\*\*Independent Test\*\*:\s*(?P<text>.+)$", re.MULTILINE
)
ACCEPTANCE_LINE_RE = re.compile(r"^\|\s*\d+\s*\|\s*(?P<given>.+?)\s*\|\s*(?P<when>.+?)\s*\|\s*(?P<then>.+?)\s*\|$", re.MULTILINE)


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "story"


def extract_story_sections(tasks_text: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    matches = list(STORY_HEADER_RE.finditer(tasks_text))
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(tasks_text)
        block = tasks_text[start:end]
        independent_test_match = INDEPENDENT_TEST_RE.search(block)
        independent_test = independent_test_match.group("text").strip() if independent_test_match else ""
        scenarios = ACCEPTANCE_LINE_RE.findall(block)
        sections.append(
            {
                "num": match.group("num"),
                "title": match.group("title").strip(),
                "independent_test": independent_test,
                "scenarios": [
                    " | ".join(part.strip() for part in row)
                    for row in scenarios
                ],
            }
        )
    return sections


def render_story_test(story: dict[str, str]) -> str:
    story_num = story["num"]
    title = story["title"]
    slug = slugify(title)
    independent_test = story["independent_test"] or "Story-specific acceptance criteria from tasks.md."
    scenarios = story["scenarios"]
    scenario_lines = "\n".join(f"    # - {scenario}" for scenario in scenarios) if scenarios else "    # - TODO: fill in acceptance scenarios from tasks.md"

    return f'''from pathlib import Path


def test_story{story_num}_{slug}(tmp_path: Path) -> None:
    """US{story_num}: {title}."""
    # Independent Test: {independent_test}
{scenario_lines}
    raise AssertionError("TODO: replace scaffold with a deterministic PASS/FAIL oracle")
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold acceptance tests from tasks.md")
    parser.add_argument("--tasks-file", required=True, help="Path to tasks.md")
    parser.add_argument(
        "--output-dir",
        default=".speckit/acceptance-tests",
        help="Directory to write story-N.py files into",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    tasks_path = Path(args.tasks_file)
    if not tasks_path.exists():
        print(f"ERROR: tasks file not found: {tasks_path}", file=sys.stderr)
        return 1

    stories = extract_story_sections(tasks_path.read_text())
    if not stories:
        print(f"ERROR: no user stories found in {tasks_path}", file=sys.stderr)
        return 1

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    skipped = 0
    for story in stories:
        out_path = out_dir / f"story-{story['num']}.py"
        if out_path.exists() and not args.force:
            print(f"[acceptance-test-scaffold] Skipping (exists): {out_path}", file=sys.stderr)
            skipped += 1
            continue
        out_path.write_text(render_story_test(story))
        print(f"[acceptance-test-scaffold] Created: {out_path}", file=sys.stderr)
        created += 1

    print(
        f"[acceptance-test-scaffold] Done — Created: {created}, Skipped: {skipped}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
