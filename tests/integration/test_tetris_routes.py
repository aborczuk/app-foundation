"""Integration coverage for the Tetris route and runtime seam."""

from __future__ import annotations

import httpx
import pytest

from src.clickup_control_plane.app import create_app
from src.clickup_control_plane.config import LOCAL_TETRIS_RUNTIME_ENV
from src.clickup_control_plane.tetris.models import (
    ActivePiece,
    GameState,
    PieceKind,
    ScoreState,
    SessionStatus,
)
from src.clickup_control_plane.tetris.service import TetrisService


@pytest.mark.asyncio
async def test_tetris_route_surface_supports_session_and_commands() -> None:
    """Open the Tetris page and drive the authoritative session via HTTP."""
    app = create_app()
    service = TetrisService(piece_sequence=(PieceKind.T, PieceKind.I))
    app.state.tetris_service = service
    app.state.tetris_state = service.start_session()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        page = await client.get("/tetris")
        css = await client.get("/tetris/assets/tetris.css")
        js = await client.get("/tetris/assets/tetris.js")
        created = await client.post("/tetris/session")
        moved = await client.post("/tetris/session/move", json={"dx": -1, "dy": 0})
        rotated = await client.post("/tetris/session/rotate", json={"clockwise": True})
        ticked = await client.post("/tetris/session/tick")
        current = await client.get("/tetris/session")

    assert page.status_code == 200
    assert "data-traceability='PL-03'" in page.text
    assert "/tetris/assets/tetris.css" in page.text
    assert "/tetris/assets/tetris.js" in page.text
    assert "id='tetris-board'" in page.text
    assert "id='tetris-controls'" in page.text
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")
    assert "tetris-board" in css.text
    assert js.status_code == 200
    assert js.headers["content-type"].startswith("text/javascript")
    assert "fetchSession" in js.text
    assert created.status_code == 201
    assert created.json()["status"] == "active"
    assert created.json()["active_piece"]["kind"] == "T"
    assert moved.status_code == 200
    assert moved.json()["active_piece"]["position"] == {"x": 2, "y": 0}
    assert rotated.status_code == 200
    assert rotated.json()["active_piece"]["rotation"] == 1
    assert ticked.status_code == 200
    assert ticked.json()["active_piece"]["position"] == {"x": 2, "y": 1}
    assert current.json()["status"] == "active"
    assert current.json()["next_piece_queue"] == ["I"]


@pytest.mark.asyncio
async def test_tetris_route_game_over_is_inert_until_restart() -> None:
    """Game-over sessions should ignore commands until the restart route resets them."""
    app = create_app()
    service = TetrisService(piece_sequence=(PieceKind.T, PieceKind.I))
    app.state.tetris_service = service
    game_over_state = GameState(
        board=tuple(
            tuple(PieceKind.S for _ in range(10))
            for _ in range(20)
        ),
        status=SessionStatus.GAME_OVER,
        active_piece=None,
        next_piece_queue=(),
    )
    app.state.tetris_state = game_over_state

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        moved = await client.post("/tetris/session/move", json={"dx": -1, "dy": 0})
        rotated = await client.post("/tetris/session/rotate", json={"clockwise": True})
        ticked = await client.post("/tetris/session/tick")
        restarted = await client.post("/tetris/session/restart")

    assert moved.status_code == 200
    assert moved.json()["status"] == "game_over"
    assert moved.json()["active_piece"] is None
    assert rotated.json() == moved.json()
    assert ticked.json() == moved.json()
    assert restarted.status_code == 200
    assert restarted.json()["status"] == "active"
    assert restarted.json()["score"] == {"score": 0, "lines_cleared": 0, "level": 1}
    assert restarted.json()["active_piece"]["kind"] == "T"


@pytest.mark.asyncio
async def test_tetris_route_tick_can_reach_game_over_before_restart() -> None:
    """A live tick should be able to lock, fail the next spawn, and mark game over."""
    app = create_app()
    service = TetrisService(piece_sequence=(PieceKind.T,))
    app.state.tetris_service = service
    board_rows: list[list[PieceKind | None]] = [
        [None for _ in range(10)]
        for _ in range(20)
    ]
    for x in (4, 5, 6):
        board_rows[1][x] = PieceKind.S
    terminal_state = GameState(
        board=tuple(tuple(row) for row in board_rows),
        status=SessionStatus.ACTIVE,
        active_piece=ActivePiece(kind=PieceKind.O, position=(3, 18)),
        next_piece_queue=(),
        score=ScoreState(),
    )
    app.state.tetris_state = terminal_state

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        ticked = await client.post("/tetris/session/tick")
        restarted = await client.post("/tetris/session/restart")

    assert ticked.status_code == 200
    assert ticked.json()["status"] == "game_over"
    assert ticked.json()["active_piece"] is None
    assert restarted.status_code == 200
    assert restarted.json()["status"] == "active"
    assert restarted.json()["active_piece"]["kind"] == "T"


@pytest.mark.asyncio
async def test_local_tetris_runtime_starts_without_control_plane_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Start the dedicated Tetris-only runtime without ClickUp/n8n bootstrap env."""
    for key in (
        "CLICKUP_API_TOKEN",
        "CLICKUP_WEBHOOK_SECRET",
        "N8N_DISPATCH_BASE_URL",
        "CONTROL_PLANE_ALLOWLIST",
        LOCAL_TETRIS_RUNTIME_ENV,
    ):
        monkeypatch.delenv(key, raising=False)

    app = create_app(local_tetris_only=True)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            page = await client.get("/tetris")
            health = await client.get("/control-plane/health")
            created = await client.post("/tetris/session")

    assert page.status_code == 200
    assert health.status_code == 200
    assert created.status_code == 201
    assert created.json()["status"] == "active"
    assert hasattr(app.state, "tetris_service")
    assert not hasattr(app.state, "dispatch_service")
