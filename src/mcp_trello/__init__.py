"""mcp_trello — shared data model dataclasses for the MCP Trello Bridge."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Task:
    """A single unit of work parsed from tasks.md."""

    id: str
    title: str
    phase_name: str
    user_story: str | None = None
    priority: str | None = None
    parallel: bool = False


@dataclass
class Phase:
    """A named group of tasks from tasks.md; maps to a Trello list."""

    name: str
    tasks: list[Task] = field(default_factory=list)


@dataclass
class TrelloCard:
    """A Trello card that is the sync target for a Task."""

    trello_id: str
    task_id: str
    title: str
    list_id: str
    label_ids: list[str] = field(default_factory=list)


@dataclass
class TrelloList:
    """A Trello list on the target board; maps to a Phase."""

    trello_id: str
    name: str
    board_id: str


@dataclass
class CardSyncResult:
    """The outcome of syncing a single Task."""

    task_id: str
    status: Literal["created", "updated", "unchanged", "error"]
    card_id: str | None = None
    error_message: str | None = None


@dataclass
class SyncReport:
    """Aggregate result returned after a sync operation completes or aborts."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: list[CardSyncResult] = field(default_factory=list)
    aborted: bool = False
    abort_reason: str | None = None
