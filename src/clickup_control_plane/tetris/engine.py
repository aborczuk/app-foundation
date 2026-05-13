"""Deterministic Tetris state transitions."""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from .models import (
    ActivePiece,
    Board,
    BoardCell,
    BoardRow,
    GameState,
    PieceKind,
    ScoreState,
    SessionStatus,
    empty_board,
)
from .pieces import PIECE_DEFINITIONS, PieceDefinition

_LINE_CLEAR_SCORES: Final[dict[int, int]] = {
    1: 40,
    2: 100,
    3: 300,
    4: 1200,
}


def _definition(kind: PieceKind) -> PieceDefinition:
    """Return the canonical definition for a tetromino kind."""
    return PIECE_DEFINITIONS[kind]


def _piece_cells(piece: ActivePiece) -> tuple[tuple[int, int], ...]:
    """Return absolute board coordinates occupied by a piece."""
    definition = _definition(piece.kind)
    rotation = piece.rotation % len(definition.orientations)
    cells = definition.orientations[rotation]
    origin_x, origin_y = piece.position
    return tuple((origin_x + dx, origin_y + dy) for dx, dy in cells)


def _can_place(board: Board, piece: ActivePiece) -> bool:
    """Return whether a piece fits within the current board."""
    for x, y in _piece_cells(piece):
        if x < 0 or y < 0:
            return False
        if x >= len(board[0]) or y >= len(board):
            return False
        if board[y][x] is not None:
            return False
    return True


def _apply_piece(board: Board, piece: ActivePiece) -> Board:
    """Overlay a locked piece onto a board."""
    cells = set(_piece_cells(piece))
    next_rows: list[BoardRow] = []
    for y, row in enumerate(board):
        next_row: list[BoardCell] = list(row)
        for x in range(len(next_row)):
            if (x, y) in cells:
                next_row[x] = piece.kind
        next_rows.append(tuple(next_row))
    return tuple(next_rows)


def _clear_full_rows(board: Board) -> tuple[Board, tuple[int, ...]]:
    """Remove completed rows and return their original indexes."""
    remaining_rows: list[BoardRow] = []
    cleared_rows: list[int] = []
    for index, row in enumerate(board):
        if all(cell is not None for cell in row):
            cleared_rows.append(index)
            continue
        remaining_rows.append(row)

    empty_rows = [
        tuple(None for _ in range(len(board[0])))
        for _ in range(len(cleared_rows))
    ]
    return tuple(empty_rows + remaining_rows), tuple(cleared_rows)


def _score_for_clear(lines_cleared: int, level: int) -> int:
    """Compute a deterministic line-clear score delta."""
    return _LINE_CLEAR_SCORES.get(lines_cleared, 0) * level


def _spawn_piece(state: GameState, kind: PieceKind) -> GameState:
    """Spawn a specific piece kind at its canonical origin."""
    definition = _definition(kind)
    active_piece = ActivePiece(
        kind=kind,
        rotation=definition.spawn_rotation,
        position=definition.spawn_position,
    )
    if not _can_place(state.board, active_piece):
        return replace(
            state,
            active_piece=None,
            status=SessionStatus.GAME_OVER,
        )
    return replace(state, active_piece=active_piece, status=SessionStatus.ACTIVE)


def spawn_next_piece(state: GameState) -> GameState:
    """Spawn the next queued piece into an active session."""
    if state.status is SessionStatus.GAME_OVER or state.active_piece is not None:
        return state
    if not state.next_piece_queue:
        return replace(state, status=SessionStatus.GAME_OVER)
    next_kind = state.next_piece_queue[0]
    next_queue = state.next_piece_queue[1:]
    return _spawn_piece(replace(state, next_piece_queue=next_queue), next_kind)


def move_active_piece(state: GameState, dx: int, dy: int) -> GameState:
    """Translate the active piece when the destination is legal."""
    if state.status is not SessionStatus.ACTIVE or state.active_piece is None:
        return state
    moved_piece = replace(
        state.active_piece,
        position=(
            state.active_piece.position[0] + dx,
            state.active_piece.position[1] + dy,
        ),
    )
    if not _can_place(state.board, moved_piece):
        return state
    return replace(state, active_piece=moved_piece)


def rotate_active_piece(state: GameState, clockwise: bool = True) -> GameState:
    """Rotate the active piece when the destination is legal."""
    if state.status is not SessionStatus.ACTIVE or state.active_piece is None:
        return state
    step = 1 if clockwise else -1
    rotated_piece = replace(
        state.active_piece,
        rotation=state.active_piece.rotation + step,
    )
    if not _can_place(state.board, rotated_piece):
        return state
    return replace(state, active_piece=rotated_piece)


def lock_active_piece(state: GameState) -> GameState:
    """Lock the active piece, apply line clears, and advance the queue."""
    if state.active_piece is None or state.status is not SessionStatus.ACTIVE:
        return state

    locked_board = _apply_piece(state.board, state.active_piece)
    cleared_board, cleared_rows = _clear_full_rows(locked_board)
    cleared_count = len(cleared_rows)
    score_delta = _score_for_clear(cleared_count, state.score.level)
    total_lines = state.score.lines_cleared + cleared_count
    next_level = total_lines // 10 + 1
    updated_state = replace(
        state,
        board=cleared_board,
        active_piece=None,
        score=ScoreState(
            score=state.score.score + score_delta,
            lines_cleared=total_lines,
            level=next_level,
        ),
    )
    return spawn_next_piece(updated_state)


def tick(state: GameState) -> GameState:
    """Advance gravity by one step or lock the active piece."""
    if state.status is not SessionStatus.ACTIVE or state.active_piece is None:
        return state
    dropped = move_active_piece(state, 0, 1)
    if dropped is state:
        return lock_active_piece(state)
    return dropped


def restart_state(queue: tuple[PieceKind, ...]) -> GameState:
    """Build a fresh session state and spawn the first queued piece."""
    return spawn_next_piece(empty_session_state(queue))


def empty_session_state(queue: tuple[PieceKind, ...]) -> GameState:
    """Create a clean ready-state session with a deterministic queue."""
    return GameState(board=empty_board(), next_piece_queue=queue)
