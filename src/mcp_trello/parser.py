"""tasks.md parser for the MCP Trello Bridge.

Parses a tasks.md file into a list of Phase objects, each containing Task objects.
Validates task ID uniqueness, non-empty titles, and unique phase names.
"""

from __future__ import annotations

import re

from src.mcp_trello import Phase, Task

# Matches task checkbox lines: - [ ] or - [X] or - [x]
_TASK_LINE = re.compile(
    r"^-\s+\[(?P<done>[Xx ])\]\s+"
    r"(?P<id>T\d+)\s+"
    r"(?P<rest>.+)$"
)

# Matches phase headings: ## Phase N: Name or ## Section Name
_PHASE_HEADING = re.compile(r"^#{1,3}\s+(?P<name>.+)$")

# Bracket markers appearing BEFORE the title: [P], [US1], [P1], [P2], [P3], etc.
_BRACKET_MARKER = re.compile(r"\[(?P<marker>[^\]]+)\]")

_PRIORITY_PATTERN = re.compile(r"^P[123]$")
_USER_STORY_PATTERN = re.compile(r"^US\d+$")


def _parse_task_line(line: str, phase_name: str) -> Task | None:
    """Parse a single task line into a Task, or return None if not a task line."""
    m = _TASK_LINE.match(line.strip())
    if not m:
        return None

    # Skip completed tasks
    if m.group("done") in ("X", "x"):
        return None

    task_id = m.group("id")
    rest = m.group("rest").strip()

    # Extract bracket markers before the title text
    parallel = False
    user_story: str | None = None
    priority: str | None = None
    consumed_spans: list[tuple[int, int]] = []

    for marker_match in _BRACKET_MARKER.finditer(rest):
        marker = marker_match.group("marker")
        if marker == "P":
            parallel = True
            consumed_spans.append((marker_match.start(), marker_match.end()))
        elif _USER_STORY_PATTERN.match(marker):
            user_story = marker
            consumed_spans.append((marker_match.start(), marker_match.end()))
        elif _PRIORITY_PATTERN.match(marker):
            priority = marker
            consumed_spans.append((marker_match.start(), marker_match.end()))
        else:
            # Unknown bracket — stop extracting markers; the rest is title
            break

    # Remove consumed bracket markers from rest to get title
    title = rest
    for start, end in sorted(consumed_spans, reverse=True):
        title = title[:start] + title[end:]
    title = title.strip()

    return Task(
        id=task_id,
        title=title,
        phase_name=phase_name,
        user_story=user_story,
        priority=priority,
        parallel=parallel,
    )


def parse_tasks_md(text: str) -> list[Phase]:
    """Parse tasks.md content into a list of Phase objects.

    Args:
        text: Full content of a tasks.md file.

    Returns:
        Ordered list of Phase objects, each containing Task objects.

    Raises:
        ValueError: If text is empty, contains duplicate phase names,
                    duplicate task IDs, or tasks with empty titles.
    """
    if not text or not text.strip():
        raise ValueError("tasks.md content is empty")

    phases: list[Phase] = []
    current_phase: Phase | None = None
    seen_phase_names: set[str] = set()
    seen_task_ids: set[str] = set()
    # Tasks before the first phase heading go into "Uncategorized"
    uncategorized: Phase | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()

        # Check for phase heading
        heading_match = _PHASE_HEADING.match(line)
        if heading_match:
            name = heading_match.group("name").strip()
            # Filter out non-phase headings (e.g., "Format: ...", "Notes", etc.)
            # Only treat as phase if it's not a known non-phase section
            _NON_PHASE_HEADINGS = {
                "format", "notes", "dependencies", "execution order",
                "phase dependencies", "user story dependencies",
                "within each user story", "parallel opportunities",
                "parallel example", "implementation strategy",
                "mvp first", "incremental delivery", "parallel team strategy",
            }
            if name.lower().split(":")[0].strip() in _NON_PHASE_HEADINGS:
                continue
            if name in seen_phase_names:
                raise ValueError(f"Duplicate phase name: '{name}'")
            seen_phase_names.add(name)
            current_phase = Phase(name=name)
            phases.append(current_phase)
            continue

        # Check for task line
        effective_phase_name = current_phase.name if current_phase else "Uncategorized"
        task = _parse_task_line(line, effective_phase_name)
        if task is None:
            continue

        if not task.title:
            raise ValueError(f"Task {task.id} has an empty title")

        if task.id in seen_task_ids:
            raise ValueError(f"Duplicate task ID: '{task.id}'")
        seen_task_ids.add(task.id)

        if current_phase is None:
            # First task before any heading — create Uncategorized phase
            if uncategorized is None:
                uncategorized = Phase(name="Uncategorized")
                phases.insert(0, uncategorized)
            uncategorized.tasks.append(task)
        else:
            current_phase.tasks.append(task)

    # Remove empty phases (phases with no tasks)
    phases = [p for p in phases if p.tasks]

    return phases
