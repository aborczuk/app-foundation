"""Routing seam for the Tetris feature."""

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .models import ActivePiece, GameState, PieceKind, ScoreState
from .service import TetrisService

router = APIRouter(prefix="/tetris", tags=["tetris"])


class MoveCommand(BaseModel):
    """Describe a deterministic movement request."""

    dx: int = Field(..., description="Horizontal delta in board cells.")
    dy: int = Field(..., description="Vertical delta in board cells.")


class RotateCommand(BaseModel):
    """Describe a deterministic rotation request."""

    clockwise: bool = Field(default=True, description="Rotate clockwise when true.")


@router.get("", include_in_schema=False, response_class=HTMLResponse)
async def tetris_root() -> HTMLResponse:
    """Render the initial Tetris surface shell."""
    return HTMLResponse(
        "<!doctype html>"
        "<html lang='en'>"
        "<head><meta charset='utf-8'><title>Tetris</title></head>"
        "<body>"
        "<main>"
        "<h1>Tetris</h1>"
        "<p>Session endpoint: <code>/tetris/session</code></p>"
        "<p>Commands: <code>/tetris/session/move</code>, "
        "<code>/tetris/session/rotate</code>, <code>/tetris/session/tick</code></p>"
        "</main>"
        "</body>"
        "</html>"
    )


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
