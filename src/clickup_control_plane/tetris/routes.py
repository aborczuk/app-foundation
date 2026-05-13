"""Routing seam for the Tetris feature."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .models import ActivePiece, GameState, PieceKind, ScoreState
from .service import TetrisService

router = APIRouter(prefix="/tetris", tags=["tetris"])
ASSET_ROOT = Path(__file__).with_name("assets")
ASSET_MEDIA_TYPES = {
    "tetris.css": "text/css; charset=utf-8",
    "tetris.js": "text/javascript; charset=utf-8",
}


class MoveCommand(BaseModel):
    """Describe a deterministic movement request."""

    dx: int = Field(..., description="Horizontal delta in board cells.")
    dy: int = Field(..., description="Vertical delta in board cells.")


class RotateCommand(BaseModel):
    """Describe a deterministic rotation request."""

    clockwise: bool = Field(default=True, description="Rotate clockwise when true.")


@router.api_route("", methods=["GET", "HEAD"], include_in_schema=False, response_class=HTMLResponse)
async def tetris_root() -> HTMLResponse:
    """Render the thin browser shell for the server-backed Tetris session."""
    return HTMLResponse(
        "<!doctype html>"
        "<html lang='en' data-traceability='PL-03'>"
        "<head>"
        "<meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Tetris</title>"
        "<link rel='stylesheet' href='/tetris/assets/tetris.css'>"
        "<script defer src='/tetris/assets/tetris.js'></script>"
        "</head>"
        "<body>"
        "<main class='tetris-page' id='tetris-app' "
        "data-session-endpoint='/tetris/session' "
        "data-command-move='/tetris/session/move' "
        "data-command-rotate='/tetris/session/rotate' "
        "data-command-tick='/tetris/session/tick' "
        "data-command-restart='/tetris/session/restart'>"
        "<section class='tetris-panel tetris-panel--board' aria-labelledby='tetris-board-title'>"
        "<div class='tetris-panel__header'>"
        "<p class='tetris-kicker'>PL-03</p>"
        "<h1 id='tetris-board-title'>Tetris</h1>"
        "<p class='tetris-summary'>Server-backed play surface, board, and gravity loop.</p>"
        "</div>"
        "<div class='tetris-board-shell'>"
        "<div id='tetris-board' class='tetris-board' role='grid' aria-label='Tetris board' "
        "aria-live='polite'></div>"
        "</div>"
        "</section>"
        "<aside class='tetris-panel tetris-panel--hud'>"
        "<section class='tetris-hud-block' aria-labelledby='tetris-score-title'>"
        "<div class='tetris-panel__header'>"
        "<p class='tetris-kicker'>Snapshot</p>"
        "<h2 id='tetris-score-title'>Score</h2>"
        "</div>"
        "<dl class='tetris-stats'>"
        "<div><dt>Status</dt><dd id='tetris-status'>ready</dd></div>"
        "<div><dt>Score</dt><dd id='tetris-score'>0</dd></div>"
        "<div><dt>Lines</dt><dd id='tetris-lines'>0</dd></div>"
        "<div><dt>Level</dt><dd id='tetris-level'>1</dd></div>"
        "<div><dt>Ticks</dt><dd id='tetris-ticks'>0</dd></div>"
        "</dl>"
        "</section>"
        "<section class='tetris-hud-block' aria-labelledby='tetris-next-title'>"
        "<div class='tetris-panel__header'>"
        "<p class='tetris-kicker'>Queue</p>"
        "<h2 id='tetris-next-title'>Next pieces</h2>"
        "</div>"
        "<ol id='tetris-next-queue' class='tetris-queue'></ol>"
        "</section>"
        "<section class='tetris-hud-block' aria-labelledby='tetris-controls-title'>"
        "<div class='tetris-panel__header'>"
        "<p class='tetris-kicker'>Control</p>"
        "<h2 id='tetris-controls-title'>Controls</h2>"
        "</div>"
        "<div id='tetris-controls' class='tetris-controls'>"
        "<button type='button' data-command='move-left'>Left</button>"
        "<button type='button' data-command='rotate'>Rotate</button>"
        "<button type='button' data-command='move-right'>Right</button>"
        "<button type='button' data-command='soft-drop'>Drop</button>"
        "<button type='button' data-command='new-game'>New game</button>"
        "</div>"
        "<p class='tetris-hint'>Arrow keys map to the same route-backed commands.</p>"
        "</section>"
        "</aside>"
        "</main>"
        "</body>"
        "</html>"
    )


@router.api_route("/assets/{asset_name}", methods=["GET", "HEAD"], include_in_schema=False)
async def tetris_asset(asset_name: str) -> FileResponse:
    """Serve a versioned browser asset for the Tetris shell."""
    if asset_name not in ASSET_MEDIA_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown Tetris asset.")
    asset_path = ASSET_ROOT / asset_name
    return FileResponse(asset_path, media_type=ASSET_MEDIA_TYPES[asset_name])


@router.get("/session")
async def get_session(request: Request) -> JSONResponse:
    """Return the current authoritative Tetris session."""
    state = _get_session_state(request)
    return JSONResponse(content=_serialize_state(state))


@router.post("/session", status_code=status.HTTP_201_CREATED)
async def create_session(request: Request) -> JSONResponse:
    """Create and store a fresh authoritative Tetris session."""
    service = _get_tetris_service(request)
    state = service.start_session()
    _set_session_state(request, state)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=_serialize_state(state))


@router.post("/session/restart")
async def restart_session(request: Request) -> JSONResponse:
    """Restart the authoritative session after game over or manual reset."""
    service = _get_tetris_service(request)
    state = service.restart_session()
    _set_session_state(request, state)
    return JSONResponse(content=_serialize_state(state))


@router.post("/session/move")
async def move_session(request: Request, command: MoveCommand) -> JSONResponse:
    """Apply a deterministic move command to the current session."""
    service = _get_tetris_service(request)
    state = service.move(_get_session_state(request), command.dx, command.dy)
    _set_session_state(request, state)
    return JSONResponse(content=_serialize_state(state))


@router.post("/session/rotate")
async def rotate_session(request: Request, command: RotateCommand) -> JSONResponse:
    """Apply a deterministic rotation command to the current session."""
    service = _get_tetris_service(request)
    state = service.rotate(_get_session_state(request), clockwise=command.clockwise)
    _set_session_state(request, state)
    return JSONResponse(content=_serialize_state(state))


@router.post("/session/tick")
async def tick_session(request: Request) -> JSONResponse:
    """Advance gravity for the current session."""
    service = _get_tetris_service(request)
    state = service.tick(_get_session_state(request))
    _set_session_state(request, state)
    return JSONResponse(content=_serialize_state(state))


def _get_tetris_service(request: Request) -> TetrisService:
    """Return the request-scoped Tetris service, creating one if needed."""
    service = getattr(request.app.state, "tetris_service", None)
    if service is None:
        service = TetrisService()
        request.app.state.tetris_service = service
    return service


def _get_session_state(request: Request) -> GameState:
    """Return the current session state, creating a fresh one if needed."""
    state = getattr(request.app.state, "tetris_state", None)
    if state is None:
        state = _get_tetris_service(request).start_session()
        request.app.state.tetris_state = state
    return state


def _set_session_state(request: Request, state: GameState) -> None:
    """Persist the authoritative session state on the app."""
    request.app.state.tetris_state = state


def _serialize_state(state: GameState) -> dict[str, object]:
    """Serialize the authoritative session state for browser delivery."""
    return {
        "board": [[_serialize_cell(cell) for cell in row] for row in state.board],
        "status": state.status.value,
        "active_piece": _serialize_active_piece(state.active_piece),
        "next_piece_queue": [piece.value for piece in state.next_piece_queue],
        "score": _serialize_score(state.score),
        "tick_count": state.tick_count,
    }


def _serialize_cell(cell: PieceKind | None) -> str | None:
    """Serialize a single board cell to a JSON-friendly value."""
    return None if cell is None else cell.value


def _serialize_active_piece(piece: ActivePiece | None) -> dict[str, object] | None:
    """Serialize the active piece state for transport to the browser."""
    if piece is None:
        return None
    return {
        "kind": piece.kind.value,
        "rotation": piece.rotation,
        "position": {"x": piece.position[0], "y": piece.position[1]},
    }


def _serialize_score(score: ScoreState) -> dict[str, int]:
    """Serialize score state for transport to the browser."""
    return {
        "score": score.score,
        "lines_cleared": score.lines_cleared,
        "level": score.level,
    }
