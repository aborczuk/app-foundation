#!/usr/bin/env python3
"""Scaffold and validate task HUD artifacts for the plan-first tasking flow."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

TASK_LINE_RE = re.compile(
    r"^\s*-\s*\[(?P<checked>[xX ])\]\s+"
    r"(?P<task_id>T\d{3})"
    r"(?:\s+\[(?P<parallel>P)\])?"
    r"(?:\s+\[(?P<human>H)\])?"
    r"(?:\s+\[(?P<story>US\d+)\])?"
    r"\s+(?P<description>.+?)\s*$"
)
HEADING_RE = re.compile(r"^\s{0,3}(?P<hashes>#{2,3})\s+(?P<title>.+?)\s*$")
TASK_REF_RE = re.compile(r"`([^`]+:[^`]+)`")
CODE_SPAN_RE = re.compile(r"`([^`]+)`")
USER_STORY_RE = re.compile(r"^### User Story (?P<number>\d+) - (?P<title>.+?)$", re.MULTILINE)
BAN_MARKERS = (
    "[FILL:",
    "[EXAMPLE:",
    "[EXAMPLE INVALID:",
    "## Working Memory",
    "## Quality Guards",
    "Resolve during implement discovery",
    "Reuse existing behavior",
    "lld_recorded  <-",
)
REQUIRED_CODE_SECTIONS = (
    "## Objective",
    "## Relevant Domains",
    "## Candidate Design Slices",
    "## Current Repo Behavior",
    "## Target Behavior",
    "## Primary Edit Seam",
    "## Reuse Candidates",
    "## Required Edits",
    "## Touched Symbols",
    "## Tests To Add Or Update",
    "## Done Criteria",
    "## Constraints And Invariants",
    "## Implementation Checklist",
    "## Dependencies",
)


@dataclass(frozen=True)
class TaskRecord:
    """Parsed task metadata needed for HUD scaffolding and validation."""

    task_id: str
    description: str
    heading: str
    is_human: bool
    story: str | None


@dataclass(frozen=True)
class StoryRecord:
    """User-story metadata loaded from spec.md."""

    story_id: str
    title: str
    summary: str
    independent_test: str
    acceptance: tuple[str, ...]


@dataclass(frozen=True)
class SliceRecord:
    """Machine-readable design slice loaded from routing.json or plan parsing."""

    slice_id: str
    title: str
    estimate: str
    why: str
    seams: tuple[str, ...]
    directive: str


@dataclass(frozen=True)
class SliceMatch:
    """Candidate task-to-slice match exported in scaffold frontmatter."""

    slice_id: str
    title: str
    basis: str
    confidence: str


@dataclass(frozen=True)
class FeatureContext:
    """Combined feature artifacts that seed HUD scaffolding."""

    feature_id: str
    feature_dir: Path
    task_records: tuple[TaskRecord, ...]
    story_map: dict[str, StoryRecord]
    edge_cases: tuple[str, ...]
    domains: dict[str, str]
    slices: tuple[SliceRecord, ...]
    dependencies: dict[str, tuple[str, ...]]


def _build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for HUD scaffold and validation operations."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    prepare = subparsers.add_parser("prepare", help="Scaffold HUDs from tasks + routing context.")
    prepare.add_argument("--feature-dir", required=True)
    prepare.add_argument("--rewrite-existing", action="store_true")
    prepare.add_argument("--json", action="store_true")

    validate = subparsers.add_parser("validate", help="Validate completed HUDs for implement readiness.")
    validate.add_argument("--feature-dir", required=True)
    validate.add_argument("--json", action="store_true")

    return parser


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Preserve the historical `--feature-dir` prepare invocation as a compatibility path."""
    if argv and argv[0].startswith("-"):
        compat_parser = argparse.ArgumentParser(description=__doc__)
        compat_parser.add_argument("--feature-dir", required=True)
        compat_parser.add_argument("--rewrite-existing", action="store_true")
        compat_parser.add_argument("--json", action="store_true")
        parsed = compat_parser.parse_args(argv)
        parsed.command = "prepare"
        return parsed
    parser = _build_parser()
    parsed = parser.parse_args(argv)
    if not parsed.command:
        parser.error("a subcommand is required")
    return parsed


def _feature_id_from_dir(feature_dir: Path) -> str:
    """Extract a 3-digit feature id from the feature directory name."""
    match = re.match(r"^(?P<id>\d{3})[-_].+$", feature_dir.name)
    return match.group("id") if match else "000"


def _extract_summary_and_ref(description: str) -> tuple[str, str]:
    """Split a task description into summary text and file:symbol reference."""
    for separator in (" — ", " - "):
        if separator in description:
            summary, tail = description.rsplit(separator, 1)
            tail = tail.strip()
            if tail.startswith("`") and tail.endswith("`"):
                return summary.strip(), tail.strip("`")
    inline = TASK_REF_RE.search(description)
    if inline:
        ref = inline.group(1)
        summary = description.replace(inline.group(0), "").strip(" -")
        return summary, ref
    return description.strip(), "[resolve from tasks.md annotation]"


def _iter_tasks(tasks_file: Path) -> Iterable[TaskRecord]:
    """Yield parsed task records from tasks.md with nearest heading context."""
    current_heading = "Phase"
    for raw in tasks_file.read_text(encoding="utf-8").splitlines():
        heading_match = HEADING_RE.match(raw)
        if heading_match:
            current_heading = heading_match.group("title").strip()
            continue
        match = TASK_LINE_RE.match(raw)
        if not match:
            continue
        yield TaskRecord(
            task_id=match.group("task_id"),
            description=match.group("description").strip(),
            heading=current_heading,
            is_human=match.group("human") == "H",
            story=match.group("story"),
        )


def _extract_inline_value(text: str, label: str) -> str:
    """Extract an inline markdown value from a labeled line."""
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith(label):
            return stripped.removeprefix(label).strip()
    return ""


def _parse_stories(spec_text: str) -> tuple[dict[str, StoryRecord], tuple[str, ...]]:
    """Parse user stories and edge cases from spec.md."""
    matches = list(USER_STORY_RE.finditer(spec_text))
    stories: dict[str, StoryRecord] = {}
    for index, match in enumerate(matches):
        story_id = f"US{match.group('number')}"
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else spec_text.find("### Edge Cases", start)
        if end == -1:
            end = len(spec_text)
        body = spec_text[start:end]
        paragraphs = [line.strip() for line in body.splitlines() if line.strip()]
        stories[story_id] = StoryRecord(
            story_id=story_id,
            title=match.group("title").strip(),
            summary=paragraphs[0] if paragraphs else "",
            independent_test=_extract_inline_value(body, "**Independent Test**:"),
            acceptance=tuple(
                line.strip()
                for line in body.splitlines()
                if re.match(r"^\d+\.\s+\*\*Given\*\*", line.strip())
            ),
        )

    edge_cases: list[str] = []
    edge_index = spec_text.find("### Edge Cases")
    if edge_index != -1:
        for raw in spec_text[edge_index:].splitlines()[1:]:
            stripped = raw.strip()
            if stripped.startswith("## "):
                break
            if stripped.startswith("- "):
                edge_cases.append(stripped.removeprefix("- ").strip())
    return stories, tuple(edge_cases)


def _parse_dependency_map(tasks_text: str) -> dict[str, tuple[str, ...]]:
    """Parse task prerequisites from the dependency-order section."""
    mapping: dict[str, list[str]] = {}
    in_section = False
    for raw in tasks_text.splitlines():
        stripped = raw.strip()
        if stripped == "## Dependency Order":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section or not stripped.startswith("- ") or "->" not in stripped:
            continue
        sources_text, targets_text = stripped.removeprefix("- ").split("->", 1)
        sources = [part.strip() for part in sources_text.split(",") if part.strip()]
        targets = [part.strip() for part in targets_text.split(",") if part.strip()]
        for target in targets:
            mapping.setdefault(target, []).extend(sources)
    return {task_id: tuple(dict.fromkeys(values)) for task_id, values in mapping.items()}


def _routing_artifact_path(feature_dir: Path) -> Path:
    """Return the stable routing artifact path for one feature."""
    return feature_dir / "routing.json"


def _parse_plan_slices(plan_file: Path) -> tuple[SliceRecord, ...]:
    """Fallback parser for design slices when routing.json is absent."""
    text = plan_file.read_text(encoding="utf-8")
    match = re.search(r"^## Design Slices\s*$([\s\S]*?)(?=^##\s|\Z)", text, re.MULTILINE)
    if not match:
        return ()
    blocks = re.split(r"^###\s+", match.group(1), flags=re.MULTILINE)
    parsed: list[SliceRecord] = []
    for block in blocks:
        stripped = block.strip()
        if not stripped:
            continue
        lines = stripped.splitlines()
        heading = lines[0].strip()
        body = "\n".join(lines[1:])
        header_match = re.match(r"(?:Slice\s+)?(?P<slice_id>PL-\d+)\s*-\s*(?P<title>.+)", heading)
        if not header_match:
            continue
        seams_raw = _extract_inline_value(body, "- File/Symbol Seams:")
        if not seams_raw:
            seams_raw = _extract_inline_value(body, "- Files / seams:")
        parsed.append(
            SliceRecord(
                slice_id=header_match.group("slice_id").strip(),
                title=header_match.group("title").strip(),
                estimate=_extract_inline_value(body, "- Estimate:") or _extract_inline_value(body, "- LOE:"),
                why=_extract_inline_value(body, "- Why this slice exists:") or _extract_inline_value(body, "- Goal:"),
                seams=tuple(match.group(1).strip() for match in CODE_SPAN_RE.finditer(seams_raw)),
                directive=_extract_inline_value(body, "- Implementation Directive:"),
            )
        )
    return tuple(parsed)


def _load_slices(feature_dir: Path) -> tuple[dict[str, str], tuple[SliceRecord, ...]]:
    """Load domain reasoning and machine-readable slices from routing.json when present."""
    routing_path = _routing_artifact_path(feature_dir)
    if routing_path.exists():
        payload = json.loads(routing_path.read_text(encoding="utf-8"))
        domains = dict(payload.get("domains", {}).get("reasoning", {}))
        slices = tuple(
            SliceRecord(
                slice_id=str(item.get("slice_id") or "").strip(),
                title=str(item.get("title") or "").strip(),
                estimate=str(item.get("estimate") or "").strip(),
                why=str(item.get("why") or "").strip(),
                seams=tuple(str(seam).strip() for seam in list(item.get("file_symbol_seams") or []) if str(seam).strip()),
                directive=str(item.get("implementation_directive") or "").strip(),
            )
            for item in list(payload.get("design_slices") or [])
            if isinstance(item, dict) and str(item.get("slice_id") or "").strip()
        )
        return domains, slices
    plan_file = feature_dir / "plan.md"
    if not plan_file.exists():
        return {}, ()
    plan_text = plan_file.read_text(encoding="utf-8")
    domains_match = re.search(r"```json\s*(?P<body>\{.*?\})\s*```", plan_text, re.DOTALL)
    domains: dict[str, str] = {}
    if domains_match:
        payload = json.loads(domains_match.group("body"))
        domains = dict(payload.get("domains", {}).get("reasoning", {}))
    return domains, _parse_plan_slices(plan_file)


def _load_feature_context(feature_dir: Path) -> FeatureContext:
    """Load feature artifacts that seed HUD scaffolding."""
    feature_id = _feature_id_from_dir(feature_dir)
    tasks_file = feature_dir / "tasks.md"
    spec_file = feature_dir / "spec.md"
    if not tasks_file.exists():
        raise RuntimeError(f"tasks_file_missing:{tasks_file}")
    task_records = tuple(_iter_tasks(tasks_file))
    story_map, edge_cases = _parse_stories(spec_file.read_text(encoding="utf-8") if spec_file.exists() else "")
    domains, slices = _load_slices(feature_dir)
    dependencies = _parse_dependency_map(tasks_file.read_text(encoding="utf-8"))
    return FeatureContext(
        feature_id=feature_id,
        feature_dir=feature_dir,
        task_records=task_records,
        story_map=story_map,
        edge_cases=edge_cases,
        domains=domains,
        slices=slices,
        dependencies=dependencies,
    )


def _related_paths(task: TaskRecord, primary_ref: str) -> tuple[str, ...]:
    """Return concrete file paths referenced by the task line."""
    paths: list[str] = []
    for item in CODE_SPAN_RE.findall(task.description):
        file_path = item.split(":", 1)[0]
        if "/" in file_path and file_path not in paths:
            paths.append(file_path)
    primary_path = primary_ref.split(":", 1)[0] if ":" in primary_ref else primary_ref
    if primary_path not in paths:
        paths.insert(0, primary_path)
    return tuple(paths)


def _related_test_tasks(task: TaskRecord, context: FeatureContext) -> tuple[TaskRecord, ...]:
    """Return same-story test tasks relevant to the current task."""
    if not task.story:
        return ()
    return tuple(
        record
        for record in context.task_records
        if record.story == task.story and "tests/" in record.description
    )


def _classify_task(task: TaskRecord, paths: tuple[str, ...]) -> str:
    """Return the deterministic/generative classification for one task."""
    if task.is_human:
        return "human_runbook"
    if paths and all(path.startswith("specs/") for path in paths):
        return "deterministic_only"
    if paths and all(path.startswith("tests/") for path in paths):
        return "needs_repo_search"
    return "needs_generative_fill"


def _domain_lines(task: TaskRecord, context: FeatureContext, paths: tuple[str, ...]) -> list[str]:
    """Return deterministic domain bullets for one task."""
    text = f"{task.description} {' '.join(paths)}".lower()
    selected: list[str] = []
    for domain in context.domains:
        domain_lower = domain.lower()
        if domain_lower == "testing" and ("tests/" in text or "coverage" in text or "verify" in text):
            selected.append(domain)
        elif domain_lower == "client/ui" and any(marker in text for marker in ("templates/", "static/", ".js", ".html", "browser", "ui")):
            selected.append(domain)
        elif domain_lower == "edge delivery" and any(marker in text for marker in ("router.py", "app.py", "route", "http", "fastapi")):
            selected.append(domain)
        elif domain_lower == "code patterns" and any(marker in text for marker in ("service.py", "models.py", "state", "restart", "score", "game-over")):
            selected.append(domain)
    if not selected:
        selected = list(context.domains)[:2]
    return [f"- `{domain}` - {context.domains.get(domain) or 'Relevant to the declared task seam.'}" for domain in selected]


def _slice_matches(task: TaskRecord, context: FeatureContext, paths: tuple[str, ...]) -> tuple[SliceMatch, ...]:
    """Return candidate task-to-slice matches with deterministic basis labels."""
    text = f"{task.description} {' '.join(paths)}".lower()
    matches: list[SliceMatch] = []
    for slice_record in context.slices:
        slice_text = f"{slice_record.title} {slice_record.directive} {' '.join(slice_record.seams)}".lower()
        if any(path in slice_text for path in paths if path):
            matches.append(
                SliceMatch(
                    slice_id=slice_record.slice_id,
                    title=slice_record.title,
                    basis="explicit seam overlap from task file ownership",
                    confidence="high",
                )
            )
            continue
        if "restart" in text and "restart" in f"{slice_record.title} {slice_record.directive}".lower():
            matches.append(
                SliceMatch(
                    slice_id=slice_record.slice_id,
                    title=slice_record.title,
                    basis="task summary overlaps slice directive language",
                    confidence="medium",
                )
            )
            continue
        if "tests/" in text and "verification" in slice_record.title.lower():
            matches.append(
                SliceMatch(
                    slice_id=slice_record.slice_id,
                    title=slice_record.title,
                    basis="test ownership overlaps verification slice",
                    confidence="high",
                )
            )
    return tuple(matches[:3])


def _render_target_behavior(task: TaskRecord, story: StoryRecord | None, matches: tuple[SliceMatch, ...]) -> list[str]:
    """Seed deterministic target-behavior bullets from story and slices."""
    summary, _ = _extract_summary_and_ref(task.description)
    lines: list[str] = []
    if story:
        lines.append(f"- Fulfill {story.story_id} ({story.title}): {story.summary}")
        if story.independent_test:
            lines.append(f"- Preserve the story proof: {story.independent_test}")
    for match in matches:
        lines.append(f"- Candidate slice `{match.slice_id}` ({match.confidence} confidence): {match.basis}")
    lines.append(f"- Task summary: {summary}.")
    return lines


def _render_test_blocks(task: TaskRecord, story: StoryRecord | None, related_tests: tuple[TaskRecord, ...]) -> list[str]:
    """Render deterministic test scaffolds or concrete doc-review checks."""
    if not related_tests and not task.story:
        return [
            "### Test 1",
            "",
            f"**File**: `{_extract_summary_and_ref(task.description)[1].split(':', 1)[0]}`  ",
            "**Name**: `tasking_review`",
            "",
            "Given:",
            "- the task artifact is updated",
            "",
            "When:",
            "- reviewing the task output for clarity and traceability",
            "",
            "Then assert:",
            "- the task artifact references the plan/spec seam it claims to implement",
            "- no placeholder or generic filler remains in the generated task detail",
        ]
    lines: list[str] = []
    for index, test_task in enumerate(related_tests, start=1):
        _, test_ref = _extract_summary_and_ref(test_task.description)
        test_file, _, test_name = test_ref.partition(":")
        lines.extend(
            [
                f"### Test {index}",
                "",
                f"**File**: `{test_file}`  ",
                f"**Name**: `{test_name or test_task.task_id}`",
                "",
                "Given:",
                f"- {story.acceptance[0] if story and story.acceptance else 'story preconditions are satisfied'}",
                f"- {story.acceptance[-1] if story and len(story.acceptance) > 1 else 'task preconditions are satisfied'}",
                "",
                "When:",
                f"- exercise the implementation seam for `{task.task_id}`",
                "",
                "Then assert:",
                f"- `{test_task.task_id}` passes for this task",
                f"- `{task.task_id}` behavior is covered at `{test_ref}`",
                "",
            ]
        )
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _render_code_scaffold(task: TaskRecord, context: FeatureContext) -> str:
    """Render a code-task HUD scaffold with deterministic seeds and explicit fill markers."""
    summary, primary_ref = _extract_summary_and_ref(task.description)
    paths = _related_paths(task, primary_ref)
    story = context.story_map.get(task.story or "")
    related_tests = _related_test_tasks(task, context)
    classification = _classify_task(task, paths)
    slice_matches = _slice_matches(task, context, paths)
    needs_generative_fill = classification != "deterministic_only"
    lines = [
        "---",
        f'feature_id: "{context.feature_id}"',
        f'task_id: "{task.task_id}"',
        f'classification: "{classification}"',
        f"needs_repo_search: {str(classification in {'needs_repo_search', 'needs_generative_fill'}).lower()}",
        f"needs_generative_fill: {str(needs_generative_fill).lower()}",
        f"candidate_design_slices: {json.dumps([match.slice_id for match in slice_matches])}",
        "---",
        "",
        f"# HUD: {task.task_id} - {summary}",
        "",
        "## Objective",
        "",
        f"Deliver `{task.task_id}` so the declared seam satisfies: {summary}.",
        "",
        "## Relevant Domains",
        "",
        *_domain_lines(task, context, paths),
        "",
        "## Candidate Design Slices",
        "",
    ]
    if slice_matches:
        lines.extend(
            [
                f"- `{match.slice_id}` - {match.basis}; {match.confidence} confidence."
                for match in slice_matches
            ]
        )
    elif classification == "deterministic_only":
        lines.append("- `None` - no additional design-slice narrowing is required beyond the declared documentation seam.")
    else:
        lines.append("- `[FILL: slice id]` - [FILL: explain the slice linkage after repo review.]")
    lines.extend(
        [
            "",
            "## Current Repo Behavior",
            "",
        ]
    )
    if classification == "deterministic_only":
        lines.append(
            f"Verified `{paths[0]}` is the file-scoped seam for this task. No runtime symbol discovery is required before updating the documentation artifact."
        )
    else:
        lines.append("[FILL: describe current repo behavior from bounded repo reads, or write exact `BLOCKED: current behavior not validated from repo reads.`]")
    lines.extend(
        [
            "",
            "## Target Behavior",
            "",
            *_render_target_behavior(task, story, slice_matches),
            "",
            "## Primary Edit Seam",
            "",
            f"**File:Symbol**: `{primary_ref}`",
            "",
            "## Reuse Candidates",
            "",
        ]
    )
    if classification == "deterministic_only":
        lines.append(f"- `{primary_ref}` - keep the change inside the declared documentation seam.")
    else:
        lines.append("- [FILL: concrete reuse candidate from repo reads, or `None validated from repo reads.`]")
    lines.extend(
        [
            "",
            "## Required Edits",
            "",
        ]
    )
    if classification == "deterministic_only":
        lines.append(f"- Update `{primary_ref}` so the task output is traceable to the plan and acceptance sources without widening the seam.")
    else:
        for path in paths:
            lines.append(f"- [FILL: concrete change required in `{path}`.]")
    lines.extend(
        [
            "",
            "## Touched Symbols",
            "",
            "### Modify",
            "",
        ]
    )
    for path in paths:
        if classification == "deterministic_only":
            lines.append(f"- `{path}` - documentation-only seam update for this task.")
        else:
            lines.append(f"- `{path}` - [FILL: specific intended change.]")
    lines.extend(
        [
            "",
            "### Create",
            "",
            "- None.",
            "",
            "### Preserve",
            "",
            "- Preserve the declared file ownership and do not widen this task into unrelated seams.",
            "- Preserve traceability back to the plan/spec contract for this task.",
            "",
            "## Tests To Add Or Update",
            "",
            *_render_test_blocks(task, story, related_tests),
            "",
            "## Done Criteria",
            "",
        ]
    )
    if classification == "deterministic_only":
        lines.extend(
            [
                "- The updated artifact points back to the relevant plan/spec seam.",
                "- No placeholder or example text remains in the task detail.",
            ]
        )
    else:
        lines.extend(
            [
                "- [FILL: targeted command or test that must pass.]",
                "- [FILL: deterministic artifact, behavior, or side-effect condition that must hold.]",
            ]
        )
    lines.extend(
        [
            "",
            "## Constraints And Invariants",
            "",
        ]
    )
    if story and story.acceptance:
        lines.extend(f"- {item}" for item in story.acceptance[:2])
    elif context.edge_cases:
        lines.extend(f"- {item}" for item in context.edge_cases[:2])
    else:
        lines.append("- Preserve the task contract stated in `tasks.md`.")
    lines.extend(
        [
            "",
            "## Implementation Checklist",
            "",
        ]
    )
    if classification == "deterministic_only":
        lines.append(f"- [ ] Update `{primary_ref}` with the required traceability detail.")
    else:
        lines.extend(
            [
                "- [ ] [FILL: repo-grounded current behavior captured.]",
                "- [ ] [FILL: concrete reuse path or explicit none validated.]",
                "- [ ] [FILL: seam-specific implementation steps listed.]",
            ]
        )
    dependencies = context.dependencies.get(task.task_id, ())
    if dependencies:
        lines.append(f"- [ ] Confirm prerequisite task outputs are present before editing: {', '.join(dependencies)}.")
    lines.extend(
        [
            "",
            "## Dependencies",
            "",
            f"- {', '.join(dependencies) if dependencies else 'None.'}",
            "",
            "## Process Checklist",
            "",
            "- [ ] current_behavior_verified",
            "- [ ] implementation_directive_complete",
            "- [ ] touched_symbols_verified",
            "- [ ] tests_specified",
            "- [ ] constraints_verified",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _render_human_hud(task: TaskRecord, context: FeatureContext) -> str:
    """Render a deterministic runbook HUD for human-required tasks."""
    summary, ref = _extract_summary_and_ref(task.description)
    return f"""---
feature_id: "{context.feature_id}"
task_id: "{task.task_id}"
classification: "human_runbook"
needs_repo_search: false
needs_generative_fill: false
candidate_design_slices: []
---

# HUD: {task.task_id} [H] - {summary}

## Runbook

**System**: `{ref.split(':', 1)[0]}`
**Steps**:
1. Execute the human-owned procedure for: {summary}
2. Record deterministic evidence in the task notes or referenced artifact.

## Process Checklist

- [ ] human_action_started
- [ ] human_action_verified
- [ ] task_closed
"""


def _is_template_or_stub(content: str) -> bool:
    """Return true when a HUD appears to be scaffold/template content."""
    return any(marker in content for marker in BAN_MARKERS)


def _prepare(feature_dir: Path, *, rewrite_existing: bool) -> dict[str, Any]:
    """Scaffold HUDs from deterministic task/spec/plan context."""
    context = _load_feature_context(feature_dir)
    hud_dir = feature_dir / "huds"
    hud_dir.mkdir(parents=True, exist_ok=True)
    updated: list[str] = []
    classifications: dict[str, str] = {}
    for task in context.task_records:
        summary, primary_ref = _extract_summary_and_ref(task.description)
        paths = _related_paths(task, primary_ref)
        classification = _classify_task(task, paths)
        classifications[task.task_id] = classification
        hud_path = hud_dir / f"{task.task_id}.md"
        if hud_path.exists() and not rewrite_existing:
            existing = hud_path.read_text(encoding="utf-8")
            if not _is_template_or_stub(existing):
                continue
        content = _render_human_hud(task, context) if task.is_human else _render_code_scaffold(task, context)
        hud_path.write_text(content, encoding="utf-8")
        updated.append(task.task_id)
    return {
        "ok": True,
        "feature_dir": str(feature_dir),
        "updated_count": len(updated),
        "updated_tasks": updated,
        "classifications": classifications,
    }


def _validate(feature_dir: Path) -> tuple[int, dict[str, Any]]:
    """Validate completed HUDs for implement readiness."""
    context = _load_feature_context(feature_dir)
    hud_dir = feature_dir / "huds"
    errors: list[dict[str, Any]] = []
    for task in context.task_records:
        if task.is_human:
            continue
        hud_path = hud_dir / f"{task.task_id}.md"
        if not hud_path.exists():
            errors.append({"task_id": task.task_id, "code": "missing_hud", "message": f"HUD not found: {hud_path}"})
            continue
        content = hud_path.read_text(encoding="utf-8")
        for marker in BAN_MARKERS[:3]:
            if marker in content:
                errors.append({"task_id": task.task_id, "code": "placeholder_remaining", "message": f"HUD still contains placeholder marker {marker!r}."})
                break
        for marker in BAN_MARKERS[3:]:
            if marker in content:
                errors.append({"task_id": task.task_id, "code": "legacy_stub_marker", "message": f"HUD still contains legacy stub marker {marker!r}."})
                break
        for heading in REQUIRED_CODE_SECTIONS:
            if heading not in content:
                errors.append({"task_id": task.task_id, "code": "missing_section", "message": f"HUD missing required section {heading}."})
        if "[FILL:" in content:
            errors.append({"task_id": task.task_id, "code": "unresolved_fill_marker", "message": "HUD still contains [FILL:] scaffolding."})
        if re.search(r"(?im)^\s*-\s*(?:Harden|Normalize|Wire implementation|Add tests|Update docs)\b", content):
            errors.append({"task_id": task.task_id, "code": "generic_only_language", "message": "HUD still contains generic-only implementation language."})
    payload = {
        "ok": not errors,
        "feature_dir": str(feature_dir),
        "error_count": len(errors),
        "errors": errors,
    }
    return (0 if not errors else 2, payload)


def main(argv: list[str] | None = None) -> int:
    """Dispatch the HUD scaffold/validate helper with compatibility for legacy prepare usage."""
    args = _parse_args(argv or sys.argv[1:])
    feature_dir = Path(args.feature_dir).resolve()
    if args.command == "prepare":
        payload = _prepare(feature_dir, rewrite_existing=bool(args.rewrite_existing))
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"updated={payload['updated_count']}")
            for task_id in payload["updated_tasks"]:
                print(task_id)
        return 0
    exit_code, payload = _validate(feature_dir)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"ok={payload['ok']} error_count={payload['error_count']}")
        for error in payload["errors"]:
            print(f"{error['task_id']}: {error['code']} - {error['message']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
