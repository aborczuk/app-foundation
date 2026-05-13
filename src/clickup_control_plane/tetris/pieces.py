"""Canonical tetromino definitions for the Tetris feature."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .models import PieceKind, Point

PieceOrientation: TypeAlias = tuple[Point, ...]
PieceRotations: TypeAlias = tuple[
    PieceOrientation,
    PieceOrientation,
    PieceOrientation,
    PieceOrientation,
]


@dataclass(frozen=True, slots=True)
class PieceDefinition:
    """Describe one tetromino's orientation cycle and spawn placement."""

    kind: PieceKind
    orientations: PieceRotations
    spawn_position: Point
    spawn_rotation: int = 0


PIECE_DEFINITIONS: dict[PieceKind, PieceDefinition] = {
    PieceKind.I: PieceDefinition(
        kind=PieceKind.I,
        orientations=(
            ((0, 1), (1, 1), (2, 1), (3, 1)),
            ((2, 0), (2, 1), (2, 2), (2, 3)),
            ((0, 2), (1, 2), (2, 2), (3, 2)),
            ((1, 0), (1, 1), (1, 2), (1, 3)),
        ),
        spawn_position=(3, 0),
    ),
    PieceKind.O: PieceDefinition(
        kind=PieceKind.O,
        orientations=(
            ((1, 0), (2, 0), (1, 1), (2, 1)),
            ((1, 0), (2, 0), (1, 1), (2, 1)),
            ((1, 0), (2, 0), (1, 1), (2, 1)),
            ((1, 0), (2, 0), (1, 1), (2, 1)),
        ),
        spawn_position=(3, 0),
    ),
    PieceKind.T: PieceDefinition(
        kind=PieceKind.T,
        orientations=(
            ((1, 0), (0, 1), (1, 1), (2, 1)),
            ((1, 0), (1, 1), (2, 1), (1, 2)),
            ((0, 1), (1, 1), (2, 1), (1, 2)),
            ((1, 0), (0, 1), (1, 1), (1, 2)),
        ),
        spawn_position=(3, 0),
    ),
    PieceKind.S: PieceDefinition(
        kind=PieceKind.S,
        orientations=(
            ((1, 0), (2, 0), (0, 1), (1, 1)),
            ((1, 0), (1, 1), (2, 1), (2, 2)),
            ((1, 1), (2, 1), (0, 2), (1, 2)),
            ((0, 0), (0, 1), (1, 1), (1, 2)),
        ),
        spawn_position=(3, 0),
    ),
    PieceKind.Z: PieceDefinition(
        kind=PieceKind.Z,
        orientations=(
            ((0, 0), (1, 0), (1, 1), (2, 1)),
            ((2, 0), (1, 1), (2, 1), (1, 2)),
            ((0, 1), (1, 1), (1, 2), (2, 2)),
            ((1, 0), (0, 1), (1, 1), (0, 2)),
        ),
        spawn_position=(3, 0),
    ),
    PieceKind.J: PieceDefinition(
        kind=PieceKind.J,
        orientations=(
            ((0, 0), (0, 1), (1, 1), (2, 1)),
            ((1, 0), (2, 0), (1, 1), (1, 2)),
            ((0, 1), (1, 1), (2, 1), (2, 2)),
            ((1, 0), (1, 1), (0, 2), (1, 2)),
        ),
        spawn_position=(3, 0),
    ),
    PieceKind.L: PieceDefinition(
        kind=PieceKind.L,
        orientations=(
            ((2, 0), (0, 1), (1, 1), (2, 1)),
            ((1, 0), (1, 1), (1, 2), (2, 2)),
            ((0, 1), (1, 1), (2, 1), (0, 2)),
            ((0, 0), (1, 0), (1, 1), (1, 2)),
        ),
        spawn_position=(3, 0),
    ),
}


CANONICAL_PIECE_ORDER: tuple[PieceKind, ...] = (
    PieceKind.I,
    PieceKind.O,
    PieceKind.T,
    PieceKind.S,
    PieceKind.Z,
    PieceKind.J,
    PieceKind.L,
)
