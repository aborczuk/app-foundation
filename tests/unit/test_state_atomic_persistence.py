"""Unit tests for atomic position/order persistence helpers."""

from __future__ import annotations

import sqlite3

import aiosqlite
import pytest

from csp_trader.state.db import run_migrations
from csp_trader.state.positions import (
    create_position,
    persist_btc_cancel_and_reopen_position,
    persist_btc_fill_and_close_position,
    persist_sto_fill,
)


async def _new_conn() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await run_migrations(conn)
    return conn


@pytest.mark.asyncio
async def test_persist_sto_fill_writes_position_and_order_atomically() -> None:
    """Test the expected behavior."""
    conn = await _new_conn()
    try:
        position, order = await persist_sto_fill(
            conn,
            ticker="NVDA",
            strike=182.5,
            expiry="2026-03-20",
            qty=1,
            fill_price=2.13,
            ibkr_conid=754444813,
            ibkr_order_id=4262,
        )

        assert order["position_id"] == position["id"]
        assert position["open_order_id"] == order["id"]

        async with conn.execute("SELECT COUNT(*) FROM positions") as cur:
            positions_count = (await cur.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM orders") as cur:
            orders_count = (await cur.fetchone())[0]

        assert positions_count == 1
        assert orders_count == 1
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_persist_sto_fill_rolls_back_position_when_order_insert_fails() -> None:
    """Test the expected behavior."""
    conn = await _new_conn()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            await persist_sto_fill(
                conn,
                ticker="NVDA",
                strike=182.5,
                expiry="2026-03-20",
                qty=1,
                fill_price=2.13,
                ibkr_conid=754444813,
                ibkr_order_id=4262,
                qty_requested=0,  # violates CHECK(qty_requested > 0)
            )

        async with conn.execute("SELECT COUNT(*) FROM positions") as cur:
            positions_count = (await cur.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM orders") as cur:
            orders_count = (await cur.fetchone())[0]

        assert positions_count == 0
        assert orders_count == 0
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_persist_btc_fill_closes_position_atomically() -> None:
    """Test the expected behavior."""
    conn = await _new_conn()
    try:
        position = await create_position(
            conn,
            {
                "ibkr_conid": 754444813,
                "ticker": "NVDA",
                "strike": 182.5,
                "expiry": "2026-03-20",
                "qty": 1,
                "fill_price": 2.13,
                "premium_collected": 213.0,
                "lifecycle_state": "closing",
            },
        )

        order = await persist_btc_fill_and_close_position(
            conn,
            position_id=position["id"],
            ibkr_order_id=4805,
            qty_requested=1,
            qty_filled=1,
            fill_price=0.45,
        )

        assert order["position_id"] == position["id"]

        async with conn.execute(
            "SELECT lifecycle_state, close_order_id, closed_at FROM positions WHERE id = ?",
            (position["id"],),
        ) as cur:
            row = await cur.fetchone()

        assert row is not None
        assert row["lifecycle_state"] == "closed"
        assert row["close_order_id"] == order["id"]
        assert row["closed_at"] is not None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_persist_btc_fill_rolls_back_state_when_order_insert_fails() -> None:
    """Test the expected behavior."""
    conn = await _new_conn()
    try:
        position = await create_position(
            conn,
            {
                "ibkr_conid": 754444813,
                "ticker": "NVDA",
                "strike": 182.5,
                "expiry": "2026-03-20",
                "qty": 1,
                "fill_price": 2.13,
                "premium_collected": 213.0,
                "lifecycle_state": "closing",
            },
        )

        with pytest.raises(sqlite3.IntegrityError):
            await persist_btc_fill_and_close_position(
                conn,
                position_id=position["id"],
                ibkr_order_id=4805,
                qty_requested=0,  # violates CHECK(qty_requested > 0)
                fill_price=0.45,
            )

        async with conn.execute(
            "SELECT lifecycle_state, close_order_id, closed_at FROM positions WHERE id = ?",
            (position["id"],),
        ) as cur:
            row = await cur.fetchone()
        async with conn.execute("SELECT COUNT(*) FROM orders WHERE position_id = ?", (position["id"],)) as cur:
            orders_count = (await cur.fetchone())[0]

        assert row is not None
        assert row["lifecycle_state"] == "closing"
        assert row["close_order_id"] is None
        assert row["closed_at"] is None
        assert orders_count == 0
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_persist_btc_cancel_reopens_position_atomically() -> None:
    """Test the expected behavior."""
    conn = await _new_conn()
    try:
        position = await create_position(
            conn,
            {
                "ibkr_conid": 754444813,
                "ticker": "NVDA",
                "strike": 182.5,
                "expiry": "2026-03-20",
                "qty": 1,
                "fill_price": 2.13,
                "premium_collected": 213.0,
                "lifecycle_state": "closing",
            },
        )

        order = await persist_btc_cancel_and_reopen_position(
            conn,
            position_id=position["id"],
            cancel_reason="timeout_no_fill",
            qty_requested=1,
            ibkr_order_id=777,
            limit_price_initial=0.45,
        )

        async with conn.execute(
            "SELECT lifecycle_state, close_order_id, closed_at FROM positions WHERE id = ?",
            (position["id"],),
        ) as cur:
            row = await cur.fetchone()

        assert row is not None
        assert row["lifecycle_state"] == "open"
        assert row["close_order_id"] == order["id"]
        assert row["closed_at"] is None

        async with conn.execute(
            "SELECT status, cancel_reason FROM orders WHERE id = ?",
            (order["id"],),
        ) as cur:
            order_row = await cur.fetchone()

        assert order_row is not None
        assert order_row["status"] == "cancelled"
        assert order_row["cancel_reason"] == "timeout_no_fill"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_persist_btc_cancel_rolls_back_when_order_insert_fails() -> None:
    """Test the expected behavior."""
    conn = await _new_conn()
    try:
        position = await create_position(
            conn,
            {
                "ibkr_conid": 754444813,
                "ticker": "NVDA",
                "strike": 182.5,
                "expiry": "2026-03-20",
                "qty": 1,
                "fill_price": 2.13,
                "premium_collected": 213.0,
                "lifecycle_state": "closing",
            },
        )

        with pytest.raises(sqlite3.IntegrityError):
            await persist_btc_cancel_and_reopen_position(
                conn,
                position_id=position["id"],
                cancel_reason="timeout_no_fill",
                qty_requested=0,  # violates CHECK(qty_requested > 0)
                ibkr_order_id=777,
                limit_price_initial=0.45,
            )

        async with conn.execute(
            "SELECT lifecycle_state, close_order_id FROM positions WHERE id = ?",
            (position["id"],),
        ) as cur:
            row = await cur.fetchone()
        async with conn.execute("SELECT COUNT(*) FROM orders WHERE position_id = ?", (position["id"],)) as cur:
            orders_count = (await cur.fetchone())[0]

        assert row is not None
        assert row["lifecycle_state"] == "closing"
        assert row["close_order_id"] is None
        assert orders_count == 0
    finally:
        await conn.close()
