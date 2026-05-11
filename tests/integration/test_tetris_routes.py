"""Integration coverage for the Tetris route and runtime seam."""

from __future__ import annotations

import httpx
import pytest

from src.clickup_control_plane.app import create_app
from src.clickup_control_plane.tetris.models import PieceKind
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
