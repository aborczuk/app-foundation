"""Deterministic unit coverage for the Tetris engine and service seams."""

from __future__ import annotations

from dataclasses import replace

from src.clickup_control_plane.tetris.models import (
    ActivePiece,
    GameState,
    PieceKind,
    ScoreState,
    SessionStatus,
    empty_board,
)
from src.clickup_control_plane.tetris.service import TetrisService


def _board_with_cells(cells: set[tuple[int, int]]) -> tuple[tuple[PieceKind | None, ...], ...]:
    """Build a board with the requested occupied cells."""
    rows: list[list[PieceKind | None]] = [
        [None for _ in range(10)]
        for _ in range(20)
    ]
    for x, y in cells:
        rows[y][x] = PieceKind.T
    return tuple(tuple(row) for row in rows)


def test_start_session_spawns_first_piece_deterministically() -> None:
    """Starting a session should spawn the first queued piece."""
    service = TetrisService(piece_sequence=(PieceKind.T, PieceKind.I))

    state = service.start_session()

    assert state.status is SessionStatus.ACTIVE
    assert state.active_piece is not None
    assert state.active_piece.kind is PieceKind.T
    assert state.board == empty_board()
    assert state.next_piece_queue == (PieceKind.I,)


def test_move_and_rotate_are_deterministic() -> None:
    """Movement and rotation should update the active piece when legal."""
    service = TetrisService(piece_sequence=(PieceKind.T, PieceKind.I))
    state = service.start_session()

    moved = service.move(state, -1, 0)
    rotated = service.rotate(moved)

    assert moved.active_piece is not None
    assert moved.active_piece.position == (2, 0)
    assert rotated.active_piece is not None
    assert rotated.active_piece.rotation == 1
    assert rotated.active_piece.position == (2, 0)


def test_illegal_move_and_rotation_leave_state_unchanged() -> None:
    """Blocked transitions should return the original state."""
    service = TetrisService(piece_sequence=(PieceKind.T, PieceKind.I))
    state = service.start_session()

    blocked_move = service.move(state, -10, 0)
    blocked_rotation_board = _board_with_cells({(4, 1)})
    blocked_rotation_state = replace(state, board=blocked_rotation_board)
    blocked_rotation = service.rotate(blocked_rotation_state)

    assert blocked_move is state
    assert blocked_rotation is blocked_rotation_state


def test_tick_locks_piece_and_spawns_next_piece() -> None:
    """Gravity should lock a blocked piece and advance the queue."""
    service = TetrisService(piece_sequence=(PieceKind.O, PieceKind.I))
    state = service.start_session()
    blocked_board = _board_with_cells({(4, 19)})
    blocked_state = replace(
        state,
        board=blocked_board,
        active_piece=ActivePiece(kind=PieceKind.O, position=(3, 17)),
    )

    next_state = service.tick(blocked_state)

    assert next_state.status is SessionStatus.ACTIVE
    assert next_state.active_piece is not None
    assert next_state.active_piece.kind is PieceKind.I
    assert next_state.board[17][4] is PieceKind.O
    assert next_state.board[17][5] is PieceKind.O
    assert next_state.board[18][4] is PieceKind.O
    assert next_state.board[18][5] is PieceKind.O
    assert next_state.board[19][4] is PieceKind.T
    assert next_state.next_piece_queue == ()


def test_lock_clears_rows_and_updates_score() -> None:
    """Locking a piece should clear completed rows and accumulate score."""
    service = TetrisService(piece_sequence=(PieceKind.O, PieceKind.I))
    state = service.start_session()
    board_rows: list[list[PieceKind | None]] = [
        [None for _ in range(10)]
        for _ in range(20)
    ]
    for y in (18, 19):
        for x in range(10):
            if x not in {4, 5}:
                board_rows[y][x] = PieceKind.S
    locked_state = replace(
        state,
        board=tuple(tuple(row) for row in board_rows),
        active_piece=ActivePiece(kind=PieceKind.O, position=(3, 18)),
        score=ScoreState(score=0, lines_cleared=0, level=1),
    )

    next_state = service.lock(locked_state)

    assert next_state.status is SessionStatus.ACTIVE
    assert next_state.active_piece is not None
    assert next_state.active_piece.kind is PieceKind.I
    assert next_state.score.lines_cleared == 2
    assert next_state.score.score == 100
    assert next_state.score.level == 1
    assert next_state.board == empty_board()


def test_lock_single_line_clear_collapses_board_and_replenishes_queue() -> None:
    """Single-line clears should collapse the board and continue with a replenished queue."""
    service = TetrisService(piece_sequence=(PieceKind.O,))
    state = service.start_session()
    board_rows: list[list[PieceKind | None]] = [
        [None for _ in range(10)]
        for _ in range(20)
    ]
    for x in range(10):
        if x not in {4, 5}:
            board_rows[19][x] = PieceKind.S
    locked_state = replace(
        state,
        board=tuple(tuple(row) for row in board_rows),
        active_piece=ActivePiece(kind=PieceKind.O, position=(3, 18)),
        score=ScoreState(score=0, lines_cleared=0, level=1),
    )

    next_state = service.lock(locked_state)

    assert next_state.status is SessionStatus.ACTIVE
    assert next_state.active_piece is not None
    assert next_state.active_piece.kind is PieceKind.O
    assert next_state.score.score == 40
    assert next_state.score.lines_cleared == 1
    assert next_state.score.level == 1
    assert next_state.board[19][4] is PieceKind.O
    assert next_state.board[19][5] is PieceKind.O
    assert next_state.next_piece_queue == ()


def test_spawn_next_piece_replenishes_empty_queue_deterministically() -> None:
    """Spawning from an empty ready-state queue should refill from the deterministic sequence."""
    service = TetrisService(piece_sequence=(PieceKind.Z, PieceKind.I))
    ready_state = replace(
        service.start_session(),
        active_piece=None,
        next_piece_queue=(),
        status=SessionStatus.READY,
    )

    spawned = service.spawn_next_piece(ready_state)

    assert spawned.status is SessionStatus.ACTIVE
    assert spawned.active_piece is not None
    assert spawned.active_piece.kind is PieceKind.Z
    assert spawned.next_piece_queue == (PieceKind.I,)


def test_illegal_spawn_marks_session_game_over() -> None:
    """Spawning into a filled board should end the session deterministically."""
    service = TetrisService(piece_sequence=(PieceKind.T,))
    blocked_state = GameState(
        board=_board_with_cells({(x, y) for x in range(10) for y in range(4)}),
        status=SessionStatus.READY,
        next_piece_queue=(PieceKind.T,),
    )

    game_over = service.spawn_next_piece(blocked_state)

    assert game_over.status is SessionStatus.GAME_OVER
    assert game_over.active_piece is None


def test_post_game_commands_are_inert_until_restart() -> None:
    """Ended sessions should ignore move/rotate/tick/lock until restart."""
    service = TetrisService(piece_sequence=(PieceKind.T, PieceKind.I))
    ended_state = GameState(
        board=_board_with_cells({(x, y) for x in range(10) for y in range(4)}),
        status=SessionStatus.GAME_OVER,
        active_piece=None,
        next_piece_queue=(),
        score=ScoreState(score=1200, lines_cleared=4, level=1),
    )

    assert service.move(ended_state, -1, 0) is ended_state
    assert service.rotate(ended_state) is ended_state
    assert service.tick(ended_state) is ended_state
    assert service.lock(ended_state) is ended_state

    restarted = service.restart_session()

    assert restarted.status is SessionStatus.ACTIVE
    assert restarted.score.score == 0
    assert restarted.score.lines_cleared == 0


def test_restart_session_returns_fresh_board_and_score() -> None:
    """Restarting should return a fresh session with a cleared board."""
    service = TetrisService(piece_sequence=(PieceKind.T, PieceKind.I))

    state = service.start_session()
    mutated = replace(
        state,
        board=_board_with_cells({(0, 19)}),
        score=ScoreState(score=240, lines_cleared=4, level=1),
    )
    restarted = service.restart_session()

    assert mutated.board != restarted.board
    assert restarted.board == empty_board()
    assert restarted.status is SessionStatus.ACTIVE
    assert restarted.active_piece is not None
    assert restarted.active_piece.kind is PieceKind.T
    assert restarted.score.score == 0
    assert restarted.score.lines_cleared == 0
