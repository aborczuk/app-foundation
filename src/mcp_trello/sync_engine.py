"""Sync engine for the MCP Trello Bridge.

Orchestrates the full sync flow:
1. Validate board access and fetch existing lists
2. Create missing lists (reuse existing by name match)
3. Fetch existing cards per list for deduplication
4. Fetch and resolve board labels (create missing ones with deterministic colors)
5. Create or update cards with <!-- speckit:TXXX --> marker and resolved labels
6. Collect CardSyncResults and build a SyncReport

Fails fast: aborts on the first transient error (5xx, timeout, 429).
Duplicate list names on the board are treated as an ambiguous state and abort.
"""

from __future__ import annotations

import logging

from src.mcp_trello import (
    CardSyncResult,
    Phase,
    SyncReport,
    Task,
    TrelloCard,
    TrelloList,
)
from src.mcp_trello.trello_client import (
    TrelloAPIError,
    TrelloAuthError,
    TrelloBoardNotFoundError,
    TrelloClient,
    TrelloRateLimitError,
)

logger = logging.getLogger(__name__)

_ABORT_ERRORS = (TrelloAPIError, TrelloAuthError, TrelloBoardNotFoundError, TrelloRateLimitError)

# Deterministic color map per spec (US2 label management):
# P1→red, P2→orange, P3→yellow, US*→blue, [P]→green
_LABEL_COLOR_MAP: dict[str, str] = {
    "P1": "red",
    "P2": "orange",
    "P3": "yellow",
    "[P]": "green",
}
_US_LABEL_COLOR = "blue"


def _label_color(name: str) -> str:
    """Return the deterministic Trello color for a label name."""
    if name in _LABEL_COLOR_MAP:
        return _LABEL_COLOR_MAP[name]
    if name.startswith("US") and name[2:].isdigit():
        return _US_LABEL_COLOR
    return "null"


def _speckit_desc(task_id: str) -> str:
    """Return the card description prefix with the speckit deduplication marker."""
    return f"<!-- speckit:{task_id} -->"


class SyncEngine:
    """Orchestrates sync of parsed phases/tasks to a Trello board.

    Usage::

        async with TrelloClient(api_key=..., token=...) as client:
            engine = SyncEngine(client)
            report = await engine.sync(phases, board_id)
    """

    def __init__(self, client: TrelloClient) -> None:
        """Initialize the instance."""
        self._client = client

    async def sync(self, phases: list[Phase], board_id: str) -> SyncReport:
        """Sync all phases and tasks to the board.

        Returns a SyncReport with counts of created/updated/unchanged cards
        and any error details. If aborted, SyncReport.aborted is True.
        """
        report = SyncReport()

        if not phases:
            return report

        # Step 1: Validate board access + fetch existing lists
        try:
            existing_lists = await self._client.get_lists(board_id)
        except _ABORT_ERRORS as exc:
            report.aborted = True
            report.abort_reason = str(exc)
            return report

        # Step 2: Check for duplicate list names (ambiguous state)
        name_counts: dict[str, int] = {}
        for tl in existing_lists:
            name_counts[tl.name] = name_counts.get(tl.name, 0) + 1

        duplicates = [name for name, count in name_counts.items() if count > 1]
        if duplicates:
            report.aborted = True
            report.abort_reason = (
                f"Duplicate Trello list name(s) on board: {', '.join(duplicates)}. "
                "Resolve manually before syncing."
            )
            return report

        # Build name → TrelloList lookup
        list_by_name: dict[str, TrelloList] = {tl.name: tl for tl in existing_lists}

        # Step 3: Resolve lists — reuse or create
        phase_lists: dict[str, TrelloList] = {}
        for phase in phases:
            if phase.name in list_by_name:
                phase_lists[phase.name] = list_by_name[phase.name]
            else:
                try:
                    new_list = await self._client.create_list(phase.name, board_id)
                    phase_lists[phase.name] = new_list
                except _ABORT_ERRORS as exc:
                    report.aborted = True
                    report.abort_reason = str(exc)
                    return report

        # Step 4: Fetch existing cards per list for deduplication
        existing_cards_by_list: dict[str, list[TrelloCard]] = {}
        for trello_list in phase_lists.values():
            try:
                cards = await self._client.get_cards(trello_list.trello_id)
                existing_cards_by_list[trello_list.trello_id] = cards
            except _ABORT_ERRORS as exc:
                report.aborted = True
                report.abort_reason = str(exc)
                return report

        # Build task_id → TrelloCard map for deduplication lookup
        card_by_task_id: dict[str, TrelloCard] = {}
        for cards in existing_cards_by_list.values():
            for card in cards:
                if card.task_id:
                    card_by_task_id[card.task_id] = card

        # Step 4b: Resolve board labels (US2)
        try:
            label_name_to_id = await self._resolve_labels(phases, board_id)
        except _ABORT_ERRORS as exc:
            report.aborted = True
            report.abort_reason = str(exc)
            return report

        # Step 5: Create or update cards
        for phase in phases:
            trello_list = phase_lists[phase.name]
            for task in phase.tasks:
                result = await self._sync_task(
                    task, trello_list, card_by_task_id, label_name_to_id
                )
                if result.status == "created":
                    report.created += 1
                elif result.status == "updated":
                    report.updated += 1
                elif result.status == "unchanged":
                    report.unchanged += 1
                elif result.status == "error":
                    report.errors.append(result)
                    report.aborted = True
                    report.abort_reason = result.error_message
                    return report

        return report

    async def _resolve_labels(
        self, phases: list[Phase], board_id: str
    ) -> dict[str, str]:
        """Fetch board labels and create any that are missing.

        Returns a name→id map for all labels needed by the tasks.
        """
        # Collect all label names needed
        needed: set[str] = set()
        for phase in phases:
            for task in phase.tasks:
                if task.priority:
                    needed.add(task.priority)
                if task.user_story:
                    needed.add(task.user_story)
                if task.parallel:
                    needed.add("[P]")

        if not needed:
            return {}

        # Fetch existing labels
        existing = await self._client.get_labels(board_id)  # name → id
        label_map: dict[str, str] = dict(existing)

        # Create missing labels
        for name in needed:
            if name not in label_map:
                color = _label_color(name)
                new_id = await self._client.create_label(name, color, board_id)
                label_map[name] = new_id

        return label_map

    def _task_label_ids(self, task: Task, label_map: dict[str, str]) -> list[str] | None:
        """Return the list of label IDs for a task, or None if no labels."""
        ids: list[str] = []
        if task.priority and task.priority in label_map:
            ids.append(label_map[task.priority])
        if task.user_story and task.user_story in label_map:
            ids.append(label_map[task.user_story])
        if task.parallel and "[P]" in label_map:
            ids.append(label_map["[P]"])
        return ids if ids else None

    async def _sync_task(
        self,
        task: Task,
        trello_list: TrelloList,
        card_by_task_id: dict[str, TrelloCard],
        label_map: dict[str, str],
    ) -> CardSyncResult:
        """Sync a single task: create if new, update if changed, skip if same."""
        existing = card_by_task_id.get(task.id)
        id_labels = self._task_label_ids(task, label_map)

        if existing is None:
            # Create new card
            desc = _speckit_desc(task.id)
            try:
                card = await self._client.create_card(
                    trello_list.trello_id,
                    task.title,
                    desc,
                    id_labels=id_labels,
                )
                return CardSyncResult(task_id=task.id, status="created", card_id=card.trello_id)
            except _ABORT_ERRORS as exc:
                return CardSyncResult(
                    task_id=task.id,
                    status="error",
                    error_message=str(exc),
                )
        else:
            # Check for changes — title or labels differ
            existing_label_ids = sorted(existing.label_ids)
            new_label_ids = sorted(id_labels or [])
            title_changed = existing.title != task.title
            labels_changed = existing_label_ids != new_label_ids

            if title_changed or labels_changed:
                update_kwargs: dict = {}
                if title_changed:
                    update_kwargs["name"] = task.title
                try:
                    await self._client.update_card(
                        existing.trello_id,
                        id_labels=id_labels,
                        **update_kwargs,
                    )
                    return CardSyncResult(task_id=task.id, status="updated", card_id=existing.trello_id)
                except _ABORT_ERRORS as exc:
                    return CardSyncResult(
                        task_id=task.id,
                        status="error",
                        error_message=str(exc),
                    )
            return CardSyncResult(task_id=task.id, status="unchanged", card_id=existing.trello_id)
