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


@pytest.mark.parametrize(
    ("operation", "expected_fragment"),
    [
        (lambda adapter: adapter.list_folders("space-1"), "list_folders:space-1"),
        (lambda adapter: adapter.create_folder("space-1", "Specs"), "create_folder:space-1:Specs"),
        (lambda adapter: adapter.list_lists("folder-1"), "list_lists:folder-1"),
        (lambda adapter: adapter.get_list("list-1"), "get_list:list-1"),
        (lambda adapter: adapter.create_list("folder-1", "Phase 1"), "create_list:folder-1:Phase 1"),
        (lambda adapter: adapter.list_tasks("list-1"), "list_tasks:list-1"),
        (lambda adapter: adapter.list_subtasks("task-1"), "list_subtasks:task-1"),
        (
            lambda adapter: adapter.create_task("list-1", "015:T001", parent="task-1"),
            "create_task:list-1:015:T001:task-1",
        ),
        (lambda adapter: adapter.update_task("task-1", name="Renamed task"), "update_task:task-1:Renamed task"),
        (lambda adapter: adapter.list_custom_fields("list-1"), "list_custom_fields:list-1"),
        (
            lambda adapter: adapter.set_custom_field("task-1", "field-1", "manual-test"),
            "set_custom_field:task-1:field-1:manual-test",
        ),
    ],
)
def test_scaffold_methods_report_operation_specific_errors(
    operation,
    expected_fragment: str,
) -> None:
    """Each scaffold transport method should identify its blocked operation clearly."""
    adapter = ComposioClickUpAdapter(
        _DummyToolRunner(),
        ComposioClickUpConfig(connection_id="conn-123"),
    )

    with pytest.raises(ComposioTransportError, match=expected_fragment):
        asyncio.run(operation(adapter))
