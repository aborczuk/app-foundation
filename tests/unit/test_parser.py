"""Unit tests for the tasks.md parser (src/mcp_trello/parser.py).

Tests are written BEFORE implementation per Constitution XV (TDD).
All tests in this file must fail until parser.py is implemented.
"""

import pytest

from src.mcp_trello import Phase, Task
from src.mcp_trello.parser import parse_tasks_md

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_MD = """\
## Phase 1: Setup

- [ ] T001 Create directories
- [ ] T002 [P] Initialize project

## Phase 2: Core

- [ ] T003 [US1] Implement feature
"""

PARALLEL_PRIORITY_MD = """\
## Phase 1: Setup

- [ ] T001 [P] [US1] Task with parallel and user story with priority P1
"""

NO_PHASE_MD = """\
- [ ] T001 Task without phase header
"""

EMPTY_MD = ""

DUPLICATE_PHASE_MD = """\
## Phase 1: Setup

- [ ] T001 First task

## Phase 1: Setup

- [ ] T002 Second task in duplicate phase
"""

DUPLICATE_TASK_ID_MD = """\
## Phase 1: Setup

- [ ] T001 First task
- [ ] T001 Duplicate task ID
"""

EMPTY_TITLE_MD = """\
## Phase 1: Setup

- [ ] T001
"""

MULTI_STORY_MD = """\
## Phase 1: Setup

- [ ] T001 Create directories
- [ ] T002 [P] Init project

## Phase 2: Core

- [ ] T003 [US1] Implement sync engine create flow in sync_engine.py
- [ ] T004 [US2] [P] Add label support in trello_client.py

## Phase 3: Polish

- [ ] T005 Add docstrings
"""


# ---------------------------------------------------------------------------
# Multi-phase parsing
# ---------------------------------------------------------------------------

def test_parse_multi_phase_returns_correct_phase_count():
    """Test the expected behavior."""
    phases = parse_tasks_md(SIMPLE_MD)
    assert len(phases) == 2


def test_parse_multi_phase_names():
    """Test the expected behavior."""
    phases = parse_tasks_md(SIMPLE_MD)
    assert phases[0].name == "Phase 1: Setup"
    assert phases[1].name == "Phase 2: Core"


def test_parse_multi_phase_task_counts():
    """Test the expected behavior."""
    phases = parse_tasks_md(SIMPLE_MD)
    assert len(phases[0].tasks) == 2
    assert len(phases[1].tasks) == 1


def test_parse_returns_phase_objects():
    """Test the expected behavior."""
    phases = parse_tasks_md(SIMPLE_MD)
    assert all(isinstance(p, Phase) for p in phases)


def test_parse_returns_task_objects():
    """Test the expected behavior."""
    phases = parse_tasks_md(SIMPLE_MD)
    assert all(isinstance(t, Task) for p in phases for t in p.tasks)


# ---------------------------------------------------------------------------
# Task field extraction
# ---------------------------------------------------------------------------

def test_task_id_extracted():
    """Test the expected behavior."""
    phases = parse_tasks_md(SIMPLE_MD)
    assert phases[0].tasks[0].id == "T001"
    assert phases[0].tasks[1].id == "T002"


def test_task_title_extracted():
    """Test the expected behavior."""
    phases = parse_tasks_md(SIMPLE_MD)
    assert phases[0].tasks[0].title == "Create directories"


def test_task_phase_name_set():
    """Test the expected behavior."""
    phases = parse_tasks_md(SIMPLE_MD)
    for task in phases[0].tasks:
        assert task.phase_name == "Phase 1: Setup"


def test_task_parallel_marker_true():
    """Test the expected behavior."""
    phases = parse_tasks_md(SIMPLE_MD)
    assert phases[0].tasks[1].parallel is True


def test_task_parallel_marker_false_when_absent():
    """Test the expected behavior."""
    phases = parse_tasks_md(SIMPLE_MD)
    assert phases[0].tasks[0].parallel is False


def test_task_user_story_extracted():
    """Test the expected behavior."""
    phases = parse_tasks_md(SIMPLE_MD)
    assert phases[1].tasks[0].user_story == "US1"


def test_task_user_story_none_when_absent():
    """Test the expected behavior."""
    phases = parse_tasks_md(SIMPLE_MD)
    assert phases[0].tasks[0].user_story is None


def test_task_priority_extracted():
    """Test the expected behavior."""
    phases = parse_tasks_md(PARALLEL_PRIORITY_MD)
    # "Task with parallel and user story with priority P1" — P1 is in title, not a priority tag
    # priority is extracted from [P1] bracket tag, not from title text
    # This task has no [P1] bracket tag, so priority should be None
    assert phases[0].tasks[0].priority is None


def test_task_priority_extracted_from_bracket():
    """Test the expected behavior."""
    md = """\
## Phase 1: Setup

- [ ] T001 [P] [US1] [P2] Task with priority tag
"""
    phases = parse_tasks_md(md)
    assert phases[0].tasks[0].priority == "P2"


def test_task_parallel_and_user_story_coexist():
    """Test the expected behavior."""
    phases = parse_tasks_md(PARALLEL_PRIORITY_MD)
    t = phases[0].tasks[0]
    assert t.parallel is True
    assert t.user_story == "US1"


def test_task_title_excludes_bracket_markers():
    """Test the expected behavior."""
    md = """\
## Phase 1: Setup

- [ ] T001 [P] [US1] [P2] Actual title text here
"""
    phases = parse_tasks_md(md)
    assert phases[0].tasks[0].title == "Actual title text here"


def test_task_completed_checkbox_skipped():
    """Completed tasks [X] or [x] should not appear in the parsed output."""
    md = """\
## Phase 1: Setup

- [X] T001 Completed task
- [ ] T002 Pending task
"""
    phases = parse_tasks_md(md)
    ids = [t.id for t in phases[0].tasks]
    assert "T001" not in ids
    assert "T002" in ids


def test_multi_story_parsing():
    """Test the expected behavior."""
    phases = parse_tasks_md(MULTI_STORY_MD)
    assert len(phases) == 3
    assert phases[1].tasks[0].user_story == "US1"
    assert phases[1].tasks[1].user_story == "US2"
    assert phases[1].tasks[1].parallel is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_file_raises_error():
    """Test the expected behavior."""
    with pytest.raises(ValueError, match="empty"):
        parse_tasks_md(EMPTY_MD)


def test_missing_phase_header_assigns_uncategorized():
    """Test the expected behavior."""
    phases = parse_tasks_md(NO_PHASE_MD)
    assert len(phases) == 1
    assert phases[0].name == "Uncategorized"
    assert phases[0].tasks[0].id == "T001"


def test_duplicate_phase_names_raises_error():
    """Test the expected behavior."""
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        parse_tasks_md(DUPLICATE_PHASE_MD)


def test_duplicate_task_ids_raises_error():
    """Test the expected behavior."""
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        parse_tasks_md(DUPLICATE_TASK_ID_MD)


def test_whitespace_only_file_raises_error():
    """Test the expected behavior."""
    with pytest.raises(ValueError, match="empty"):
        parse_tasks_md("   \n\n   ")


def test_task_order_preserved():
    """Test the expected behavior."""
    phases = parse_tasks_md(SIMPLE_MD)
    ids = [t.id for t in phases[0].tasks]
    assert ids == ["T001", "T002"]
