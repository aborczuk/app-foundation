"""Session orchestration for the Tetris feature."""

from __future__ import annotations

from dataclasses import replace

from . import engine
from .models import GameState, PieceKind, SessionStatus
from .pieces import CANONICAL_PIECE_ORDER

DEFAULT_PIECE_SEQUENCE: tuple[PieceKind, ...] = CANONICAL_PIECE_ORDER * 16


class TetrisService:
    """Coordinate deterministic session lifecycle and engine transitions."""

    def __init__(self, *, piece_sequence: tuple[PieceKind, ...] = DEFAULT_PIECE_SEQUENCE) -> None:
        """Store the deterministic piece sequence used for sessions."""
        self._piece_sequence = piece_sequence

    def start_session(self) -> GameState:
        """Create a fresh active session."""
        return engine.restart_state(self._piece_sequence)

    def restart_session(self) -> GameState:
        """Reset the session to a fresh active state."""
        return self.start_session()

    def spawn_next_piece(self, state: GameState) -> GameState:
        """Spawn the next piece, replenishing the queue if needed."""
        next_state = state
        if not next_state.next_piece_queue:
            next_state = replace(next_state, next_piece_queue=self._piece_sequence)
        return engine.spawn_next_piece(next_state)

    def move(self, state: GameState, dx: int, dy: int) -> GameState:
        """Move the active piece through the pure engine seam."""
        return engine.move_active_piece(state, dx, dy)

    def rotate(self, state: GameState, clockwise: bool = True) -> GameState:
        """Rotate the active piece through the pure engine seam."""
        return engine.rotate_active_piece(state, clockwise=clockwise)

    def tick(self, state: GameState) -> GameState:
        """Advance gravity through the pure engine seam."""
        return engine.tick(state)

    def lock(self, state: GameState) -> GameState:
        """Lock the active piece and replenish the deterministic queue when needed."""
        locked_state = engine.lock_active_piece(state)
        if (
            locked_state.status is SessionStatus.GAME_OVER
            and locked_state.active_piece is None
            and not locked_state.next_piece_queue
        ):
            replenished_state = replace(
                locked_state,
                status=SessionStatus.READY,
                next_piece_queue=self._piece_sequence,
            )
            return engine.spawn_next_piece(replenished_state)
        return locked_state
