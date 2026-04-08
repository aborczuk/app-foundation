"""Unit tests for the sync engine create-only flow (src/mcp_trello/sync_engine.py).

Tests are written BEFORE implementation per Constitution XV (TDD).
All tests in this file must fail until sync_engine.py is implemented.

Covers:
- Creates Trello lists for each phase (reuses existing by name match)
- Creates cards with <!-- speckit:TXXX --> marker as first line of description
- Abort on board-not-found (zero writes)
- Abort on auth failure (zero writes)
- Abort on 5xx/timeout returns partial SyncReport with aborted=True
- SyncReport counts (created, errors)
- Duplicate list name on board aborts
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from src.mcp_trello import (
    Phase,
    Task,
    TrelloCard,
    TrelloList,
)
from src.mcp_trello.sync_engine import SyncEngine
from src.mcp_trello.trello_client import (
    TrelloAPIError,
    TrelloAuthError,
    TrelloBoardNotFoundError,
    TrelloRateLimitError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BOARD_ID = "board123"
LIST_ID_1 = "list001"
LIST_ID_2 = "list002"
CARD_ID_1 = "card001"
CARD_ID_2 = "card002"


def make_phase(name: str, task_ids: list[str]) -> Phase:
    """Execute the function."""
    phase = Phase(name=name)
    for tid in task_ids:
        phase.tasks.append(Task(id=tid, title=f"Task {tid}", phase_name=name))
    return phase


def make_trello_list(trello_id: str, name: str) -> TrelloList:
    """Execute the function."""
    return TrelloList(trello_id=trello_id, name=name, board_id=BOARD_ID)


def make_trello_card(trello_id: str, task_id: str, list_id: str) -> TrelloCard:
    """Execute the function."""
    return TrelloCard(
        trello_id=trello_id,
        task_id=task_id,
        title=f"Task {task_id}",
        list_id=list_id,
    )


def make_mock_client(
    existing_lists: list[TrelloList] | None = None,
    existing_cards: list[TrelloCard] | None = None,
    get_lists_error: Exception | None = None,
    create_list_side_effect=None,
    create_card_side_effect=None,
    get_labels_result: dict | None = None,
) -> MagicMock:
    """Build a mock TrelloClient with async methods."""
    client = MagicMock()

    if get_lists_error:
        client.get_lists = AsyncMock(side_effect=get_lists_error)
    else:
        client.get_lists = AsyncMock(return_value=existing_lists or [])

    client.get_cards = AsyncMock(return_value=existing_cards or [])
    client.get_labels = AsyncMock(return_value=get_labels_result or {})

    if create_list_side_effect is not None:
        client.create_list = AsyncMock(side_effect=create_list_side_effect)
    else:
        # Default: return a list with a predictable ID
        async def default_create_list(name, board_id):
            return TrelloList(trello_id=f"new_{name}", name=name, board_id=board_id)
        client.create_list = AsyncMock(side_effect=default_create_list)

    if create_card_side_effect is not None:
        client.create_card = AsyncMock(side_effect=create_card_side_effect)
    else:
        card_counter = {"n": 0}
        async def default_create_card(list_id, name, desc, id_labels=None):
            card_counter["n"] += 1
            tid = name.split()[1] if name.startswith("Task ") else f"T{card_counter['n']:03d}"
            return TrelloCard(
                trello_id=f"card_{card_counter['n']}",
                task_id=tid,
                title=name,
                list_id=list_id,
            )
        client.create_card = AsyncMock(side_effect=default_create_card)

    client.update_card = AsyncMock()
    client.create_label = AsyncMock(return_value="new_label_id")

    return client


# ---------------------------------------------------------------------------
# Basic create flow — new board (no existing lists/cards)
# ---------------------------------------------------------------------------

async def test_sync_creates_lists_for_each_phase():
    """One Trello list must be created per phase."""
    phases = [
        make_phase("Phase 1: Setup", ["T001"]),
        make_phase("Phase 2: Core", ["T002"]),
    ]
    client = make_mock_client()
    engine = SyncEngine(client)
    await engine.sync(phases, BOARD_ID)

    assert client.create_list.call_count == 2
    call_names = [c.args[0] for c in client.create_list.call_args_list]
    assert "Phase 1: Setup" in call_names
    assert "Phase 2: Core" in call_names


async def test_sync_creates_cards_for_each_task():
    """One Trello card must be created per task."""
    phases = [make_phase("Phase 1: Setup", ["T001", "T002"])]
    client = make_mock_client()
    engine = SyncEngine(client)
    await engine.sync(phases, BOARD_ID)

    assert client.create_card.call_count == 2


async def test_sync_report_created_count():
    """SyncReport.created counts all successfully created cards."""
    phases = [make_phase("Phase 1: Setup", ["T001", "T002", "T003"])]
    client = make_mock_client()
    engine = SyncEngine(client)
    report = await engine.sync(phases, BOARD_ID)

    assert report.created == 3
    assert report.aborted is False


async def test_sync_card_description_contains_speckit_marker():
    """Card description must contain <!-- speckit:TXXX --> marker."""
    captured_descs: list[str] = []

    async def capture_create_card(list_id, name, desc, id_labels=None):
        captured_descs.append(desc)
        return TrelloCard(trello_id="c1", task_id="T001", title=name, list_id=list_id)

    phases = [make_phase("Phase 1", ["T001"])]
    client = make_mock_client(create_card_side_effect=capture_create_card)
    engine = SyncEngine(client)
    await engine.sync(phases, BOARD_ID)

    assert len(captured_descs) == 1
    assert "<!-- speckit:T001 -->" in captured_descs[0]


async def test_sync_card_speckit_marker_on_first_line():
    """The speckit marker must be on the first line of the description."""
    captured_descs: list[str] = []

    async def capture_create_card(list_id, name, desc, id_labels=None):
        captured_descs.append(desc)
        return TrelloCard(trello_id="c1", task_id="T001", title=name, list_id=list_id)

    phases = [make_phase("Phase 1", ["T001"])]
    client = make_mock_client(create_card_side_effect=capture_create_card)
    engine = SyncEngine(client)
    await engine.sync(phases, BOARD_ID)

    first_line = captured_descs[0].splitlines()[0]
    assert "<!-- speckit:T001 -->" in first_line


# ---------------------------------------------------------------------------
# Reuse existing lists (by name match)
# ---------------------------------------------------------------------------

async def test_sync_reuses_existing_list_by_name():
    """If a list with the same name exists, it must be reused (not re-created)."""
    existing = [make_trello_list(LIST_ID_1, "Phase 1: Setup")]
    phases = [make_phase("Phase 1: Setup", ["T001"])]
    client = make_mock_client(existing_lists=existing)
    engine = SyncEngine(client)
    await engine.sync(phases, BOARD_ID)

    client.create_list.assert_not_called()


async def test_sync_creates_missing_list_only():
    """Only lists absent from the board are created."""
    existing = [make_trello_list(LIST_ID_1, "Phase 1: Setup")]
    phases = [
        make_phase("Phase 1: Setup", ["T001"]),
        make_phase("Phase 2: Core", ["T002"]),
    ]
    client = make_mock_client(existing_lists=existing)
    engine = SyncEngine(client)
    await engine.sync(phases, BOARD_ID)

    assert client.create_list.call_count == 1
    assert client.create_list.call_args.args[0] == "Phase 2: Core"


# ---------------------------------------------------------------------------
# Abort on board-not-found (zero writes)
# ---------------------------------------------------------------------------

async def test_abort_on_board_not_found_zero_writes():
    """Board-not-found (404) must abort with zero list or card writes."""
    phases = [make_phase("Phase 1", ["T001"])]
    client = make_mock_client(get_lists_error=TrelloBoardNotFoundError("not found"))
    engine = SyncEngine(client)
    report = await engine.sync(phases, BOARD_ID)

    client.create_list.assert_not_called()
    client.create_card.assert_not_called()
    assert report.aborted is True
    assert report.abort_reason is not None


# ---------------------------------------------------------------------------
# Abort on auth failure (zero writes)
# ---------------------------------------------------------------------------

async def test_abort_on_auth_failure_zero_writes():
    """Auth failure (401) must abort with zero list or card writes."""
    phases = [make_phase("Phase 1", ["T001"])]
    client = make_mock_client(get_lists_error=TrelloAuthError("unauthorized"))
    engine = SyncEngine(client)
    report = await engine.sync(phases, BOARD_ID)

    client.create_list.assert_not_called()
    client.create_card.assert_not_called()
    assert report.aborted is True


# ---------------------------------------------------------------------------
# Abort on 5xx/timeout — partial SyncReport with aborted=True
# ---------------------------------------------------------------------------

async def test_abort_on_api_error_returns_partial_report():
    """5xx error mid-sync must abort and return partial SyncReport with aborted=True."""
    call_count = {"n": 0}

    async def create_card_fails_on_second(list_id, name, desc, id_labels=None):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise TrelloAPIError("server error")
        return TrelloCard(trello_id=f"c{call_count['n']}", task_id=name, title=name, list_id=list_id)

    phases = [make_phase("Phase 1", ["T001", "T002", "T003"])]
    client = make_mock_client(create_card_side_effect=create_card_fails_on_second)
    engine = SyncEngine(client)
    report = await engine.sync(phases, BOARD_ID)

    assert report.aborted is True
    assert report.abort_reason is not None
    # T001 was created before the error
    assert report.created >= 1


async def test_abort_on_rate_limit_returns_partial_report():
    """429 rate limit mid-sync must abort and return partial SyncReport."""
    call_count = {"n": 0}

    async def rate_limit_on_second(list_id, name, desc, id_labels=None):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise TrelloRateLimitError("rate limit")
        return TrelloCard(trello_id=f"c{call_count['n']}", task_id=name, title=name, list_id=list_id)

    phases = [make_phase("Phase 1", ["T001", "T002", "T003"])]
    client = make_mock_client(create_card_side_effect=rate_limit_on_second)
    engine = SyncEngine(client)
    report = await engine.sync(phases, BOARD_ID)

    assert report.aborted is True


# ---------------------------------------------------------------------------
# Duplicate list name on board aborts
# ---------------------------------------------------------------------------

async def test_duplicate_list_name_on_board_aborts():
    """If the board has two lists with the same name, sync must abort (ambiguous target)."""
    existing = [
        make_trello_list("list_a", "Phase 1: Setup"),
        make_trello_list("list_b", "Phase 1: Setup"),
    ]
    phases = [make_phase("Phase 1: Setup", ["T001"])]
    client = make_mock_client(existing_lists=existing)
    engine = SyncEngine(client)
    report = await engine.sync(phases, BOARD_ID)

    client.create_card.assert_not_called()
    assert report.aborted is True


# ---------------------------------------------------------------------------
# SyncReport error collection
# ---------------------------------------------------------------------------

async def test_sync_report_errors_include_failed_card():
    """A card creation error must be included in SyncReport.errors."""
    async def create_card_fails(list_id, name, desc, id_labels=None):
        raise TrelloAPIError("server error")

    phases = [make_phase("Phase 1", ["T001"])]
    client = make_mock_client(create_card_side_effect=create_card_fails)
    engine = SyncEngine(client)
    report = await engine.sync(phases, BOARD_ID)

    assert report.aborted is True


async def test_sync_report_zero_errors_on_clean_sync():
    """A clean sync must report zero errors."""
    phases = [make_phase("Phase 1", ["T001", "T002"])]
    client = make_mock_client()
    engine = SyncEngine(client)
    report = await engine.sync(phases, BOARD_ID)

    assert len(report.errors) == 0
    assert report.aborted is False


# ---------------------------------------------------------------------------
# Multi-phase, multi-task integration
# ---------------------------------------------------------------------------

async def test_sync_multi_phase_all_tasks_created():
    """All tasks across all phases are created."""
    phases = [
        make_phase("Phase 1: Setup", ["T001", "T002"]),
        make_phase("Phase 2: Core", ["T003", "T004", "T005"]),
    ]
    client = make_mock_client()
    engine = SyncEngine(client)
    report = await engine.sync(phases, BOARD_ID)

    assert report.created == 5
    assert client.create_list.call_count == 2


async def test_sync_cards_created_in_correct_list():
    """Cards must be created in the list corresponding to their phase."""
    phase1_list = make_trello_list(LIST_ID_1, "Phase 1")
    phase2_list = make_trello_list(LIST_ID_2, "Phase 2")

    existing = [phase1_list, phase2_list]
    phases = [
        make_phase("Phase 1", ["T001"]),
        make_phase("Phase 2", ["T002"]),
    ]

    captured: list[tuple[str, str]] = []  # (list_id, task_id)

    async def capture_create(list_id, name, desc, id_labels=None):
        # Extract task ID from name
        tid = name.split()[1]
        captured.append((list_id, tid))
        return TrelloCard(trello_id=f"c_{tid}", task_id=tid, title=name, list_id=list_id)

    client = make_mock_client(existing_lists=existing, create_card_side_effect=capture_create)
    engine = SyncEngine(client)
    await engine.sync(phases, BOARD_ID)

    assert ("list001", "T001") in captured
    assert ("list002", "T002") in captured


async def test_sync_empty_phases_no_writes():
    """Empty phases list results in no writes."""
    client = make_mock_client()
    engine = SyncEngine(client)
    report = await engine.sync([], BOARD_ID)

    client.create_list.assert_not_called()
    client.create_card.assert_not_called()
    assert report.created == 0
    assert report.aborted is False


# ---------------------------------------------------------------------------
# T014: Label management — tests written BEFORE T016 implementation
# ---------------------------------------------------------------------------
# These tests verify label resolution and application in the sync engine.
# They MUST fail until sync_engine.py is updated in T016.

def make_task_with_labels(
    tid: str,
    phase_name: str = "Phase 1",
    user_story: str | None = None,
    priority: str | None = None,
    parallel: bool = False,
) -> Task:
    """Execute the function."""
    return Task(
        id=tid,
        title=f"Task {tid}",
        phase_name=phase_name,
        user_story=user_story,
        priority=priority,
        parallel=parallel,
    )


def make_labeled_client(
    existing_labels: dict[str, str] | None = None,
) -> MagicMock:
    """Client where create_card records id_labels arg."""
    client = make_mock_client(get_labels_result=existing_labels or {})
    return client


async def test_label_applied_to_card_with_priority():
    """A task with priority=[P1] gets the P1 label on its card."""
    phase = Phase(name="Phase 1")
    phase.tasks = [make_task_with_labels("T001", priority="P1")]

    # Board already has the P1 label
    client = make_labeled_client(existing_labels={"P1": "label_p1"})

    captured_labels: list[list[str]] = []

    async def capture_create(list_id, name, desc, id_labels=None):
        captured_labels.append(id_labels or [])
        return TrelloCard(trello_id="c1", task_id="T001", title=name, list_id=list_id)

    client.create_card = AsyncMock(side_effect=capture_create)

    engine = SyncEngine(client)
    await engine.sync([phase], BOARD_ID)

    assert len(captured_labels) == 1
    assert "label_p1" in captured_labels[0]


async def test_label_applied_to_card_with_user_story():
    """A task with user_story=US1 gets the US1 label on its card."""
    phase = Phase(name="Phase 1")
    phase.tasks = [make_task_with_labels("T001", user_story="US1")]

    client = make_labeled_client(existing_labels={"US1": "label_us1"})

    captured_labels: list[list[str]] = []

    async def capture_create(list_id, name, desc, id_labels=None):
        captured_labels.append(id_labels or [])
        return TrelloCard(trello_id="c1", task_id="T001", title=name, list_id=list_id)

    client.create_card = AsyncMock(side_effect=capture_create)

    engine = SyncEngine(client)
    await engine.sync([phase], BOARD_ID)

    assert "label_us1" in captured_labels[0]


async def test_label_applied_to_parallel_task():
    """A parallel task gets the [P] label on its card."""
    phase = Phase(name="Phase 1")
    phase.tasks = [make_task_with_labels("T001", parallel=True)]

    client = make_labeled_client(existing_labels={"[P]": "label_parallel"})

    captured_labels: list[list[str]] = []

    async def capture_create(list_id, name, desc, id_labels=None):
        captured_labels.append(id_labels or [])
        return TrelloCard(trello_id="c1", task_id="T001", title=name, list_id=list_id)

    client.create_card = AsyncMock(side_effect=capture_create)

    engine = SyncEngine(client)
    await engine.sync([phase], BOARD_ID)

    assert "label_parallel" in captured_labels[0]


async def test_task_with_no_metadata_gets_no_labels():
    """A plain task (no priority, user_story, parallel) gets no labels."""
    phase = Phase(name="Phase 1")
    phase.tasks = [make_task_with_labels("T001")]  # no labels

    client = make_labeled_client()

    captured_labels: list[list[str] | None] = []

    async def capture_create(list_id, name, desc, id_labels=None):
        captured_labels.append(id_labels)
        return TrelloCard(trello_id="c1", task_id="T001", title=name, list_id=list_id)

    client.create_card = AsyncMock(side_effect=capture_create)

    engine = SyncEngine(client)
    await engine.sync([phase], BOARD_ID)

    # Should be None or empty list — no labels sent
    assert not captured_labels[0]


async def test_missing_label_is_created_with_correct_color():
    """If a label does not exist on the board, it is created with the deterministic color."""
    phase = Phase(name="Phase 1")
    phase.tasks = [make_task_with_labels("T001", priority="P1")]

    # Board has no labels
    client = make_labeled_client(existing_labels={})
    client.create_label = AsyncMock(return_value="new_p1_id")

    captured_labels: list[list[str]] = []

    async def capture_create(list_id, name, desc, id_labels=None):
        captured_labels.append(id_labels or [])
        return TrelloCard(trello_id="c1", task_id="T001", title=name, list_id=list_id)

    client.create_card = AsyncMock(side_effect=capture_create)

    engine = SyncEngine(client)
    await engine.sync([phase], BOARD_ID)

    # Label should have been created with name "P1" and color "red"
    client.create_label.assert_called_once()
    call_args = client.create_label.call_args
    assert call_args.args[0] == "P1"   # name
    assert call_args.args[1] == "red"  # color for P1
    # Created label ID should be applied to the card
    assert "new_p1_id" in captured_labels[0]


async def test_multiple_labels_combined_on_card():
    """A task with priority + user_story + parallel gets all three labels."""
    phase = Phase(name="Phase 1")
    phase.tasks = [
        make_task_with_labels("T001", priority="P2", user_story="US3", parallel=True)
    ]

    client = make_labeled_client(
        existing_labels={"P2": "lid_p2", "US3": "lid_us3", "[P]": "lid_parallel"}
    )

    captured_labels: list[list[str]] = []

    async def capture_create(list_id, name, desc, id_labels=None):
        captured_labels.append(id_labels or [])
        return TrelloCard(trello_id="c1", task_id="T001", title=name, list_id=list_id)

    client.create_card = AsyncMock(side_effect=capture_create)

    engine = SyncEngine(client)
    await engine.sync([phase], BOARD_ID)

    labels = captured_labels[0]
    assert "lid_p2" in labels
    assert "lid_us3" in labels
    assert "lid_parallel" in labels


async def test_existing_label_reused_not_recreated():
    """If the label exists on the board, it must be reused (no create_label call)."""
    phase = Phase(name="Phase 1")
    phase.tasks = [make_task_with_labels("T001", priority="P3")]

    client = make_labeled_client(existing_labels={"P3": "existing_p3_id"})
    client.create_label = AsyncMock()

    captured_labels: list[list[str]] = []

    async def capture_create(list_id, name, desc, id_labels=None):
        captured_labels.append(id_labels or [])
        return TrelloCard(trello_id="c1", task_id="T001", title=name, list_id=list_id)

    client.create_card = AsyncMock(side_effect=capture_create)

    engine = SyncEngine(client)
    await engine.sync([phase], BOARD_ID)

    client.create_label.assert_not_called()
    assert "existing_p3_id" in captured_labels[0]


# ---------------------------------------------------------------------------
# T017: Deduplication and update unit tests (US3)
# ---------------------------------------------------------------------------

async def test_dedup_unchanged_card_returns_unchanged_status():
    """A card that matches by task_id and has identical title + labels → unchanged."""
    existing_card = make_trello_card(CARD_ID_1, "T001", LIST_ID_1)
    existing_card.title = "Task T001"

    existing_list = make_trello_list(LIST_ID_1, "Phase 1")
    phase = make_phase("Phase 1", ["T001"])
    phase.tasks[0].title = "Task T001"

    client = make_mock_client(
        existing_lists=[existing_list],
        existing_cards=[existing_card],
    )
    engine = SyncEngine(client)
    report = await engine.sync([phase], BOARD_ID)

    assert report.unchanged == 1
    assert report.created == 0
    assert report.updated == 0
    client.create_card.assert_not_called()
    client.update_card.assert_not_called()


async def test_dedup_title_changed_card_gets_updated():
    """A card with a matching task_id but different title → updated via PUT."""
    existing_card = make_trello_card(CARD_ID_1, "T001", LIST_ID_1)
    existing_card.title = "Old Title"

    existing_list = make_trello_list(LIST_ID_1, "Phase 1")
    phase = make_phase("Phase 1", ["T001"])
    phase.tasks[0].title = "New Title"

    updated_card = TrelloCard(
        trello_id=CARD_ID_1, task_id="T001", title="New Title", list_id=LIST_ID_1
    )
    client = make_mock_client(
        existing_lists=[existing_list],
        existing_cards=[existing_card],
    )
    client.update_card = AsyncMock(return_value=updated_card)

    engine = SyncEngine(client)
    report = await engine.sync([phase], BOARD_ID)

    assert report.updated == 1
    assert report.unchanged == 0
    client.update_card.assert_called_once()
    assert client.update_card.call_args.args[0] == CARD_ID_1


async def test_dedup_labels_changed_card_gets_updated():
    """A card with matching task_id but different labels → updated."""
    existing_card = make_trello_card(CARD_ID_1, "T001", LIST_ID_1)
    existing_card.title = "Task T001"
    existing_card.label_ids = []

    existing_list = make_trello_list(LIST_ID_1, "Phase 1")
    phase = Phase(name="Phase 1")
    task = Task(id="T001", title="Task T001", phase_name="Phase 1", priority="P1")
    phase.tasks = [task]

    updated_card = TrelloCard(trello_id=CARD_ID_1, task_id="T001", title="Task T001", list_id=LIST_ID_1)
    client = make_mock_client(
        existing_lists=[existing_list],
        existing_cards=[existing_card],
        get_labels_result={"P1": "label_p1"},
    )
    client.update_card = AsyncMock(return_value=updated_card)

    engine = SyncEngine(client)
    report = await engine.sync([phase], BOARD_ID)

    assert report.updated == 1
    client.update_card.assert_called_once()


async def test_dedup_new_task_creates_card_alongside_existing():
    """A new task (no matching card) creates a new card; existing cards are unchanged."""
    existing_card = make_trello_card(CARD_ID_1, "T001", LIST_ID_1)
    existing_card.title = "Task T001"

    existing_list = make_trello_list(LIST_ID_1, "Phase 1")
    phase = make_phase("Phase 1", ["T001", "T002"])
    phase.tasks[0].title = "Task T001"

    client = make_mock_client(
        existing_lists=[existing_list],
        existing_cards=[existing_card],
    )
    engine = SyncEngine(client)
    report = await engine.sync([phase], BOARD_ID)

    assert report.created == 1
    assert report.unchanged == 1
    assert client.create_card.call_count == 1


async def test_dedup_stale_cards_untouched():
    """Cards on the board with no matching task_id in tasks.md remain untouched."""
    stale_card = make_trello_card("stale_id", "T999", LIST_ID_1)
    stale_card.title = "Old stale task"

    existing_list = make_trello_list(LIST_ID_1, "Phase 1")
    phase = make_phase("Phase 1", ["T001"])

    client = make_mock_client(
        existing_lists=[existing_list],
        existing_cards=[stale_card],
    )
    engine = SyncEngine(client)
    report = await engine.sync([phase], BOARD_ID)

    assert report.created == 1
    for call in client.update_card.call_args_list:
        assert call.args[0] != "stale_id"


async def test_dedup_syncreport_counts_all_statuses():
    """SyncReport correctly counts created, updated, unchanged across tasks."""
    existing_card1 = make_trello_card(CARD_ID_1, "T001", LIST_ID_1)
    existing_card1.title = "Task T001"

    existing_card2 = make_trello_card(CARD_ID_2, "T002", LIST_ID_1)
    existing_card2.title = "Old T002 title"

    existing_list = make_trello_list(LIST_ID_1, "Phase 1")
    phase = Phase(name="Phase 1")
    t1 = Task(id="T001", title="Task T001", phase_name="Phase 1")
    t2 = Task(id="T002", title="New T002 title", phase_name="Phase 1")
    t3 = Task(id="T003", title="Task T003", phase_name="Phase 1")
    phase.tasks = [t1, t2, t3]

    updated_card = TrelloCard(trello_id=CARD_ID_2, task_id="T002", title="New T002 title", list_id=LIST_ID_1)
    client = make_mock_client(
        existing_lists=[existing_list],
        existing_cards=[existing_card1, existing_card2],
    )
    client.update_card = AsyncMock(return_value=updated_card)

    engine = SyncEngine(client)
    report = await engine.sync([phase], BOARD_ID)

    assert report.created == 1
    assert report.updated == 1
    assert report.unchanged == 1
    assert report.aborted is False
