"""Unit tests for local valuation DB fallback migrations."""

from __future__ import annotations

from pathlib import Path

from csp_trader.state.valuation_db import get_db_connection, run_migrations


async def test_valuation_db_migrations_create_valuation_tables_only(tmp_path: Path) -> None:
    """Test the expected behavior."""
    db_path = tmp_path / "valuation_state.db"
    async with get_db_connection(str(db_path)) as conn:
        await run_migrations(conn)
        async with conn.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
            tables = {row[0] for row in await cur.fetchall()}

    assert "valuation_versions" in tables
    assert "target_price_records" in tables
    assert "positions" not in tables
    assert "orders" not in tables


async def test_valuation_db_migrations_are_idempotent(tmp_path: Path) -> None:
    """Test the expected behavior."""
    db_path = tmp_path / "valuation_state.db"
    async with get_db_connection(str(db_path)) as conn:
        await run_migrations(conn)
        await run_migrations(conn)
        async with conn.execute("SELECT value FROM _schema_meta WHERE key='schema_version'") as cur:
            row = await cur.fetchone()

    assert row is not None
    assert int(row[0]) >= 1
