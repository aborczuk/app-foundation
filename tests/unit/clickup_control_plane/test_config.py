"""Unit tests for control-plane runtime config helpers."""

from __future__ import annotations

import pytest

from src.clickup_control_plane.config import (
    LOCAL_TETRIS_RUNTIME_ENV,
    ConfigError,
    is_local_tetris_runtime,
)


def test_is_local_tetris_runtime_defaults_false() -> None:
    """Default runtime should remain the full control-plane app."""
    assert is_local_tetris_runtime({}) is False


def test_is_local_tetris_runtime_accepts_truthy_flag() -> None:
    """Truthy local-runtime values should enable the Tetris-only path."""
    assert is_local_tetris_runtime({LOCAL_TETRIS_RUNTIME_ENV: "true"}) is True


def test_is_local_tetris_runtime_rejects_blank_flag() -> None:
    """Blank local-runtime flags should fail fast as invalid config."""
    with pytest.raises(ConfigError):
        is_local_tetris_runtime({LOCAL_TETRIS_RUNTIME_ENV: "   "})
