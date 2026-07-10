"""Tests for the acceptance scaffold task-story fallback."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    """Load the repository-local acceptance scaffold helper."""
    script_path = Path(".specify/scripts/acceptance-test-scaffold.py")
    spec = importlib.util.spec_from_file_location("acceptance_test_scaffold", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_story_sections_uses_task_story_labels_when_headings_are_phased() -> None:
    """Phase-oriented task files still produce one acceptance scaffold per US label."""
    module = _load_module()
    tasks = "\n".join(
        [
            "## Phase 1: Setup",
            "- [ ] T001 [US4] Add preflight in scripts/preflight.py.",
            "## Phase 2: Routing",
            "- [ ] T002a [US1] Add route in scripts/routes.py.",
            "- [ ] T002b [US1] Validate route in tests/test_routes.py.",
        ]
    )

    stories = module.extract_story_sections(tasks)

    assert [story["num"] for story in stories] == ["1", "4"]
    assert stories[0]["independent_test"].startswith("Add route")
