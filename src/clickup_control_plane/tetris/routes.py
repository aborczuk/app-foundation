"""Routing seam for the Tetris feature."""

from fastapi import APIRouter

router = APIRouter(prefix="/tetris", tags=["tetris"])


@router.get("", include_in_schema=False)
async def tetris_root() -> dict[str, str]:
    """Provide a placeholder root route for the future Tetris browser shell."""
    return {"status": "tetris-ready"}
