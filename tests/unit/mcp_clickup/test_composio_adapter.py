"""Unit tests for the Composio ClickUp transport adapter."""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

import pytest

from src.mcp_clickup.composio_adapter import (
    ComposioClickUpAdapter,
    ComposioClickUpConfig,
    ComposioConfigurationError,
    ComposioToolRunner,
    ComposioTransportError,
)


class _RecordingToolRunner(ComposioToolRunner):
    """Minimal async tool runner that records calls and returns scripted payloads."""

    def __init__(self, responses: Mapping[str, list[Mapping[str, Any]]]) -> None:
        """Store a queue of tool responses keyed by tool slug."""
        self._responses = {tool: list(items) for tool, items in responses.items()}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return the next scripted payload and record the invocation."""
        self.calls.append((tool_name, dict(arguments)))
        queue = self._responses.get(tool_name, [])
        if not queue:
            raise AssertionError(f"Unexpected tool call: {tool_name}")
        return queue.pop(0)


def _wrapped(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a Composio-style wrapped payload."""
    return {"response": {"successful": True, "data": dict(data)}}


def test_connection_id_property_exposes_configured_value() -> None:
    """The adapter should surface the configured connection id."""
    adapter = ComposioClickUpAdapter(
        _RecordingToolRunner({}),
        ComposioClickUpConfig(connection_id="conn-123"),
    )

    assert adapter.connection_id == "conn-123"


def test_blank_connection_id_fails_fast() -> None:
    """Adapter configuration should reject a blank Composio connection id."""
    with pytest.raises(ComposioConfigurationError, match="connection_id is required"):
        ComposioClickUpAdapter(_RecordingToolRunner({}), ComposioClickUpConfig(connection_id=" "))


def test_read_operations_normalize_composio_payloads() -> None:
    """Read operations should unwrap wrapped payloads into sync-engine-friendly shapes."""
    runner = _RecordingToolRunner(
        {
            "CLICKUP_GET_SPACE": [_wrapped({"id": "space-1", "team_id": "team-1"})],
            "CLICKUP_GET_FOLDERS": [_wrapped({"folders": [{"id": "folder-1", "name": "Specs"}]})],
            "CLICKUP_GET_LISTS": [_wrapped({"lists": [{"id": "list-1", "name": "Phase 1"}]})],
            "CLICKUP_GET_LIST": [_wrapped({"id": "list-1", "name": "Phase 1"})],
            "CLICKUP_GET_TASKS": [_wrapped({"tasks": [{"id": "task-1", "name": "US1", "parent": ""}]})],
            "CLICKUP_GET_ACCESSIBLE_CUSTOM_FIELDS": [
                _wrapped({"fields": [{"id": "field-1", "name": "workflow_type"}]})
            ],
        }
    )
    adapter = ComposioClickUpAdapter(runner, ComposioClickUpConfig(connection_id="conn-123"))

    assert asyncio.run(adapter.get_space("space-1")) == {"id": "space-1", "team_id": "team-1"}
    assert asyncio.run(adapter.list_folders("space-1")) == [{"id": "folder-1", "name": "Specs"}]
    assert asyncio.run(adapter.list_lists("folder-1")) == [{"id": "list-1", "name": "Phase 1"}]
    assert asyncio.run(adapter.get_list("list-1")) == {"id": "list-1", "name": "Phase 1"}
    assert asyncio.run(adapter.list_tasks("list-1")) == [{"id": "task-1", "name": "US1", "parent": ""}]
    assert asyncio.run(adapter.list_custom_fields("list-1")) == [
        {"id": "field-1", "name": "workflow_type"}
    ]

    assert runner.calls == [
        ("CLICKUP_GET_SPACE", {"space_id": "space-1"}),
        ("CLICKUP_GET_FOLDERS", {"space_id": "space-1"}),
        ("CLICKUP_GET_LISTS", {"folder_id": "folder-1"}),
        ("CLICKUP_GET_LIST", {"list_id": "list-1"}),
        ("CLICKUP_GET_TASKS", {"list_id": "list-1"}),
        ("CLICKUP_GET_ACCESSIBLE_CUSTOM_FIELDS", {"list_id": "list-1"}),
    ]


def test_list_subtasks_filters_tasks_by_parent_from_live_list() -> None:
    """Subtask lookup should fetch the parent task's list and filter only its children."""
    runner = _RecordingToolRunner(
        {
            "CLICKUP_GET_TASK": [{"data": {"id": "task-1", "list": {"id": "list-1"}}}],
            "CLICKUP_GET_TASKS": [
                _wrapped(
                    {
                        "tasks": [
                            {"id": "subtask-1", "name": "T001", "parent": "task-1"},
                            {"id": "task-2", "name": "US2", "parent": ""},
                            {"id": "subtask-2", "name": "T002", "parent": "task-9"},
                        ]
                    }
                )
            ],
        }
    )
    adapter = ComposioClickUpAdapter(runner, ComposioClickUpConfig(connection_id="conn-123"))

    assert asyncio.run(adapter.list_subtasks("task-1")) == [
        {"id": "subtask-1", "name": "T001", "parent": "task-1"}
    ]
    assert runner.calls == [
        ("CLICKUP_GET_TASK", {"task_id": "task-1"}),
        ("CLICKUP_GET_TASKS", {"list_id": "list-1", "subtasks": True}),
    ]


def test_write_operations_call_expected_tool_slugs_and_arguments() -> None:
    """Create, update, and custom-field writes should map to the expected Composio tools."""
    runner = _RecordingToolRunner(
        {
            "CLICKUP_CREATE_FOLDER": [{"data": {"id": "folder-1", "name": "Specs"}}],
            "CLICKUP_CREATE_LIST": [{"data": {"id": "list-1", "name": "Phase 1"}}],
            "CLICKUP_CREATE_TASK": [{"data": {"id": "task-1", "name": "015:T001"}}],
            "CLICKUP_UPDATE_TASK": [{"data": {"id": "task-1", "name": "Renamed task"}}],
            "CLICKUP_SET_CUSTOM_FIELD_VALUE": [{"data": {"ok": True}}],
        }
    )
    adapter = ComposioClickUpAdapter(runner, ComposioClickUpConfig(connection_id="conn-123"))

    assert asyncio.run(adapter.create_folder("space-1", "Specs")) == {"id": "folder-1", "name": "Specs"}
    assert asyncio.run(adapter.create_list("folder-1", "Phase 1")) == {"id": "list-1", "name": "Phase 1"}
    assert asyncio.run(adapter.create_task("list-1", "015:T001", parent="task-parent")) == {
        "id": "task-1",
        "name": "015:T001",
    }
    assert asyncio.run(
        adapter.update_task("task-1", name="Renamed task", description="because blocked", status="blocked")
    ) == {
        "id": "task-1",
        "name": "Renamed task",
    }
    assert asyncio.run(adapter.set_custom_field("task-1", "field-1", "manual-test")) is None

    assert runner.calls == [
        ("CLICKUP_CREATE_FOLDER", {"space_id": "space-1", "name": "Specs"}),
        ("CLICKUP_CREATE_LIST", {"folder_id": "folder-1", "name": "Phase 1"}),
        ("CLICKUP_CREATE_TASK", {"list_id": "list-1", "name": "015:T001", "parent": "task-parent"}),
        (
            "CLICKUP_UPDATE_TASK",
            {
                "task_id": "task-1",
                "name": "Renamed task",
                "description": "because blocked",
                "status": "blocked",
            },
        ),
        ("CLICKUP_SET_CUSTOM_FIELD_VALUE", {"task_id": "task-1", "field_id": "field-1", "value": "manual-test"}),
    ]


def test_invalid_list_payload_raises_transport_error() -> None:
    """Malformed list payloads should fail with a transport-level error."""
    runner = _RecordingToolRunner({"CLICKUP_GET_TASKS": [{"data": {"tasks": "not-a-list"}}]})
    adapter = ComposioClickUpAdapter(runner, ComposioClickUpConfig(connection_id="conn-123"))

    with pytest.raises(ComposioTransportError, match="non-list 'tasks' field"):
        asyncio.run(adapter.list_tasks("list-1"))
