"""Regression tests for ClickUp client lifecycle and error mapping."""

from __future__ import annotations

import json

import httpx
import pytest

from src.mcp_clickup.clickup_client import (
    ClickUpAuthError,
    ClickUpClient,
    ClickUpNotFoundError,
    ClickUpRateLimitError,
    ClickUpTimeoutError,
)


def _json_response(status_code: int, payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


@pytest.mark.asyncio
async def test_clickup_client_maps_401_to_auth_error() -> None:
    """401 responses should raise ClickUpAuthError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(401, {"err": "unauthorized"})

    transport = httpx.MockTransport(handler)
    async with ClickUpClient(api_token="token", transport=transport) as client:
        with pytest.raises(ClickUpAuthError):
            await client.get_space("space-1")


@pytest.mark.asyncio
async def test_clickup_client_maps_404_to_not_found_error() -> None:
    """404 responses should raise ClickUpNotFoundError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(404, {"err": "not found"})

    transport = httpx.MockTransport(handler)
    async with ClickUpClient(api_token="token", transport=transport) as client:
        with pytest.raises(ClickUpNotFoundError):
            await client.get_space("space-1")


@pytest.mark.asyncio
async def test_clickup_client_maps_429_to_rate_limit_error() -> None:
    """429 responses should raise ClickUpRateLimitError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(429, {"err": "rate limited"})

    transport = httpx.MockTransport(handler)
    async with ClickUpClient(api_token="token", transport=transport) as client:
        with pytest.raises(ClickUpRateLimitError):
            await client.get_space("space-1")


@pytest.mark.asyncio
async def test_clickup_client_maps_timeout_to_timeout_error() -> None:
    """Timeout exceptions should raise ClickUpTimeoutError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    transport = httpx.MockTransport(handler)
    async with ClickUpClient(api_token="token", transport=transport) as client:
        with pytest.raises(ClickUpTimeoutError):
            await client.get_space("space-1")
