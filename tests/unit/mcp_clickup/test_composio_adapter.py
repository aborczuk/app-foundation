"""Unit tests for the Composio ClickUp adapter scaffold."""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

import pytest

from src.mcp_clickup.composio_adapter import (
    ComposioClickUpAdapter,
    ComposioClickUpConfig,
    ComposioToolRunner,
    ComposioTransportError,
)


class _DummyToolRunner(ComposioToolRunner):
    """Minimal tool runner used to construct scaffold adapters in tests."""

    async def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return a deterministic payload for scaffold construction tests."""
        return {"tool_name": tool_name, "arguments": dict(arguments)}


def test_connection_id_property_exposes_configured_value() -> None:
    """The scaffold adapter should surface the configured connection id."""
    adapter = ComposioClickUpAdapter(
        _DummyToolRunner(),
        ComposioClickUpConfig(connection_id="conn-123"),
    )

    assert adapter.connection_id == "conn-123"


def test_scaffold_methods_raise_uniform_not_implemented_error() -> None:
    """Unimplemented scaffold operations should fail with a consistent transport error."""
    adapter = ComposioClickUpAdapter(
        _DummyToolRunner(),
        ComposioClickUpConfig(connection_id="conn-123"),
    )

    with pytest.raises(ComposioTransportError, match="scaffolded but not implemented yet"):
        asyncio.run(adapter.get_space("space-1"))
