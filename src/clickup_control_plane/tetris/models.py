"""Typed gameplay state for the Tetris feature."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final, TypeAlias

BOARD_WIDTH: Final[int] = 10
BOARD_HEIGHT: Final[int] = 20

Point: TypeAlias = tuple[int, int]


class PieceKind(str, Enum):
    """Canonical tetromino identifiers used by the engine."""

    I = "I"  # noqa: E741
    O = "O"  # noqa: E741
    T = "T"
    S = "S"
    Z = "Z"
    J = "J"
    L = "L"


class SessionStatus(str, Enum):
    """Lifecycle states for a Tetris session."""

    READY = "ready"
    ACTIVE = "active"
    PAUSED = "paused"
    GAME_OVER = "game_over"


BoardCell: TypeAlias = PieceKind | None
BoardRow: TypeAlias = tuple[BoardCell, ...]
Board: TypeAlias = tuple[BoardRow, ...]


@dataclass(frozen=True, slots=True)
class ScoreState:
    """Track score progression for a single session."""

    score: int = 0
    lines_cleared: int = 0
    level: int = 1


@dataclass(frozen=True, slots=True)
class ActivePiece:
    """Describe the active tetromino and its placement on the board."""

    kind: PieceKind
    rotation: int = 0
    position: Point = (0, 0)


@dataclass(frozen=True, slots=True)
class GameState:
    """Capture the authoritative session state for deterministic play."""

    board: Board
    status: SessionStatus = SessionStatus.READY
    active_piece: ActivePiece | None = None
    next_piece_queue: tuple[PieceKind, ...] = ()
    score: ScoreState = field(default_factory=ScoreState)
    tick_count: int = 0


def empty_board() -> Board:
    """Return a cleared board in the canonical playfield geometry."""
    return tuple(
        tuple(None for _ in range(BOARD_WIDTH))
        for _ in range(BOARD_HEIGHT)
    )


def new_game_state(*, next_piece_queue: tuple[PieceKind, ...] = ()) -> GameState:
    """Build a fresh ready-to-play state with an empty board."""
    return GameState(
        board=empty_board(),
        next_piece_queue=next_piece_queue,
    )
