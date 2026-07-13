"""Composio-backed ClickUp transport implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


class ComposioTransportError(RuntimeError):
    """Base error for Composio transport failures."""


class ComposioConfigurationError(ComposioTransportError):
    """Raised when required Composio transport configuration is missing."""


class ComposioToolRunner(Protocol):
    """Minimal async tool-runner contract required by the adapter scaffold."""

    async def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        """Invoke a Composio-managed tool and return its decoded payload."""
        ...


@dataclass(frozen=True)
class ComposioClickUpConfig:
    """Stable configuration for future Composio ClickUp transport calls."""

    connection_id: str
    toolkit_slug: str = "clickup"


class ComposioClickUpAdapter:
    """Transport-shaped ClickUp adapter backed by Composio ClickUp tools."""

    def __init__(self, tool_runner: ComposioToolRunner, config: ComposioClickUpConfig) -> None:
        """Store the tool-runner and connection configuration."""
        if not config.connection_id.strip():
            raise ComposioConfigurationError("Composio ClickUp connection_id is required")
        self._tool_runner = tool_runner
        self._config = config

    @property
    def connection_id(self) -> str:
        """Return the configured Composio connection identifier."""
        return self._config.connection_id

    async def _call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        """Execute one Composio tool call and normalize transport-level failures."""
        try:
            response = await self._tool_runner.call_tool(tool_name, arguments)
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise ComposioTransportError(
                f"Composio ClickUp tool '{tool_name}' failed: {exc}"
            ) from exc
        if not isinstance(response, Mapping):
            raise ComposioTransportError(
                f"Composio ClickUp tool '{tool_name}' returned a non-mapping payload"
            )
        return response

    @staticmethod
    def _unwrap_data(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Extract the data object from either direct or wrapped Composio payloads."""
        response = payload.get("response")
        if isinstance(response, Mapping):
            payload = response

        data = payload.get("data")
        if isinstance(data, Mapping):
            return data
        if isinstance(payload, Mapping):
            return payload
        raise ComposioTransportError("Composio ClickUp payload did not contain a mapping data object")

    def _extract_object(self, payload: Mapping[str, Any], *, tool_name: str) -> dict[str, Any]:
        """Normalize one object payload for sync-engine consumption."""
        data = self._unwrap_data(payload)
        return dict(data)

    def _extract_list(
        self,
        payload: Mapping[str, Any],
        *,
        tool_name: str,
        key: str,
    ) -> list[dict[str, Any]]:
        """Normalize a list-valued payload field for sync-engine consumption."""
        data = self._unwrap_data(payload)
        items = data.get(key, [])
        if not isinstance(items, list):
            raise ComposioTransportError(
                f"Composio ClickUp tool '{tool_name}' returned a non-list '{key}' field"
            )
        return [dict(item) for item in items if isinstance(item, Mapping)]

    async def get_space(self, space_id: str) -> dict[str, Any]:
        """Fetch a ClickUp Space by id."""
        payload = await self._call_tool("CLICKUP_GET_SPACE", {"space_id": space_id})
        return self._extract_object(payload, tool_name="CLICKUP_GET_SPACE")

    async def list_folders(self, space_id: str) -> list[dict[str, Any]]:
        """List folders under a ClickUp space."""
        payload = await self._call_tool("CLICKUP_GET_FOLDERS", {"space_id": space_id})
        return self._extract_list(payload, tool_name="CLICKUP_GET_FOLDERS", key="folders")

    async def create_folder(self, space_id: str, name: str) -> dict[str, Any]:
        """Create a folder under a ClickUp space."""
        payload = await self._call_tool("CLICKUP_CREATE_FOLDER", {"space_id": space_id, "name": name})
        return self._extract_object(payload, tool_name="CLICKUP_CREATE_FOLDER")

    async def list_lists(self, folder_id: str) -> list[dict[str, Any]]:
        """List lists under a folder."""
        payload = await self._call_tool("CLICKUP_GET_LISTS", {"folder_id": folder_id})
        return self._extract_list(payload, tool_name="CLICKUP_GET_LISTS", key="lists")

    async def get_list(self, list_id: str) -> dict[str, Any]:
        """Fetch list metadata by id."""
        payload = await self._call_tool("CLICKUP_GET_LIST", {"list_id": list_id})
        return self._extract_object(payload, tool_name="CLICKUP_GET_LIST")

    async def create_list(self, folder_id: str, name: str) -> dict[str, Any]:
        """Create a list under a folder."""
        payload = await self._call_tool("CLICKUP_CREATE_LIST", {"folder_id": folder_id, "name": name})
        return self._extract_object(payload, tool_name="CLICKUP_CREATE_LIST")

    async def list_tasks(self, list_id: str) -> list[dict[str, Any]]:
        """List parent tasks under a list."""
        payload = await self._call_tool("CLICKUP_GET_TASKS", {"list_id": list_id})
        return self._extract_list(payload, tool_name="CLICKUP_GET_TASKS", key="tasks")

    async def list_subtasks(self, task_id: str) -> list[dict[str, Any]]:
        """List child tasks under a parent task."""
        task_payload = await self._call_tool("CLICKUP_GET_TASK", {"task_id": task_id})
        task_data = self._extract_object(task_payload, tool_name="CLICKUP_GET_TASK")
        list_id = str(task_data.get("list", {}).get("id", ""))
        if not list_id:
            return []
        tasks_payload = await self._call_tool(
            "CLICKUP_GET_TASKS",
            {"list_id": list_id, "subtasks": True},
        )
        tasks = self._extract_list(tasks_payload, tool_name="CLICKUP_GET_TASKS", key="tasks")
        return [task for task in tasks if str(task.get("parent", "")) == task_id]

    async def create_task(
        self,
        list_id: str,
        name: str,
        parent: str | None = None,
    ) -> dict[str, Any]:
        """Create a task or subtask."""
        arguments: dict[str, Any] = {"list_id": list_id, "name": name}
        if parent:
            arguments["parent"] = parent
        payload = await self._call_tool("CLICKUP_CREATE_TASK", arguments)
        return self._extract_object(payload, tool_name="CLICKUP_CREATE_TASK")

    async def update_task(self, task_id: str, *, name: str) -> dict[str, Any]:
        """Update task mutable fields."""
        payload = await self._call_tool("CLICKUP_UPDATE_TASK", {"task_id": task_id, "name": name})
        return self._extract_object(payload, tool_name="CLICKUP_UPDATE_TASK")

    async def list_custom_fields(self, list_id: str) -> list[dict[str, Any]]:
        """List custom fields visible on a list."""
        payload = await self._call_tool("CLICKUP_GET_ACCESSIBLE_CUSTOM_FIELDS", {"list_id": list_id})
        return self._extract_list(
            payload,
            tool_name="CLICKUP_GET_ACCESSIBLE_CUSTOM_FIELDS",
            key="fields",
        )

    async def set_custom_field(self, task_id: str, field_id: str, value: str) -> None:
        """Set a task custom field value."""
        await self._call_tool(
            "CLICKUP_SET_CUSTOM_FIELD_VALUE",
            {"task_id": task_id, "field_id": field_id, "value": value},
        )
