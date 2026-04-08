"""Performance smoke test for the sync engine.

SC-001: Full sync of 200 tasks must complete in ≤30 seconds.

Uses a mock Trello client to avoid network calls.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

from src.mcp_trello import Phase, Task, TrelloCard, TrelloList
from src.mcp_trello.sync_engine import SyncEngine


def make_large_task_set(n_tasks: int = 200, n_phases: int = 5) -> list[Phase]:
    """Generate n_tasks tasks spread across n_phases phases."""
    phases = [Phase(name=f"Phase {i + 1}: Section") for i in range(n_phases)]
    for idx in range(n_tasks):
        phase = phases[idx % n_phases]
        task = Task(
            id=f"T{idx + 1:03d}",
            title=f"Task {idx + 1} description",
            phase_name=phase.name,
        )
        phase.tasks.append(task)
    return phases


async def test_sync_200_tasks_under_30_seconds():
    """Sync 200 tasks against a mock client must complete in ≤30 seconds (SC-001)."""
    phases = make_large_task_set(n_tasks=200, n_phases=5)

    client = MagicMock()
    client.get_lists = AsyncMock(return_value=[])
    client.get_labels = AsyncMock(return_value={})
    client.get_cards = AsyncMock(return_value=[])

    async def fast_create_list(name, board_id):
        return TrelloList(trello_id=f"list_{name}", name=name, board_id=board_id)

    async def fast_create_card(list_id, name, desc, id_labels=None):
        return TrelloCard(trello_id=f"card_{name}", task_id=name, title=name, list_id=list_id)

    client.create_list = AsyncMock(side_effect=fast_create_list)
    client.create_card = AsyncMock(side_effect=fast_create_card)

    engine = SyncEngine(client)

    start = time.monotonic()
    report = await engine.sync(phases, "board123")
    elapsed = time.monotonic() - start

    assert report.created == 200, f"Expected 200 created, got {report.created}"
    assert report.aborted is False
    assert elapsed < 30.0, f"Sync took {elapsed:.2f}s, must be < 30s (SC-001)"
