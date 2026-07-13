"""Composio-backed ClickUp transport scaffolds."""

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
    """Transport-shaped ClickUp adapter reserved for later Composio wiring."""

    def __init__(self, tool_runner: ComposioToolRunner, config: ComposioClickUpConfig) -> None:
        """Store the future tool-runner and connection configuration."""
        self._tool_runner = tool_runner
        self._config = config

    @property
    def connection_id(self) -> str:
        """Return the configured Composio connection identifier."""
        return self._config.connection_id

    def _not_implemented(self, operation: str) -> ComposioTransportError:
        """Build a uniform scaffold error for unimplemented transport operations."""
        return ComposioTransportError(
            f"Composio ClickUp adapter operation '{operation}' is scaffolded but not implemented yet"
        )

    async def get_space(self, space_id: str) -> dict[str, Any]:
        """Fetch a ClickUp Space by id."""
        raise self._not_implemented(f"get_space:{space_id}")

    async def list_folders(self, space_id: str) -> list[dict[str, Any]]:
        """List folders under a ClickUp space."""
        raise self._not_implemented(f"list_folders:{space_id}")

    async def create_folder(self, space_id: str, name: str) -> dict[str, Any]:
        """Create a folder under a ClickUp space."""
        raise self._not_implemented(f"create_folder:{space_id}:{name}")

    async def list_lists(self, folder_id: str) -> list[dict[str, Any]]:
        """List lists under a folder."""
        raise self._not_implemented(f"list_lists:{folder_id}")

    async def get_list(self, list_id: str) -> dict[str, Any]:
        """Fetch list metadata by id."""
        raise self._not_implemented(f"get_list:{list_id}")

    async def create_list(self, folder_id: str, name: str) -> dict[str, Any]:
        """Create a list under a folder."""
        raise self._not_implemented(f"create_list:{folder_id}:{name}")

    async def list_tasks(self, list_id: str) -> list[dict[str, Any]]:
        """List parent tasks under a list."""
        raise self._not_implemented(f"list_tasks:{list_id}")

    async def list_subtasks(self, task_id: str) -> list[dict[str, Any]]:
        """List child tasks under a parent task."""
        raise self._not_implemented(f"list_subtasks:{task_id}")

    async def create_task(
        self,
        list_id: str,
        name: str,
        parent: str | None = None,
    ) -> dict[str, Any]:
        """Create a task or subtask."""
        raise self._not_implemented(f"create_task:{list_id}:{name}:{parent or ''}")

    async def update_task(self, task_id: str, *, name: str) -> dict[str, Any]:
        """Update task mutable fields."""
        raise self._not_implemented(f"update_task:{task_id}:{name}")

    async def list_custom_fields(self, list_id: str) -> list[dict[str, Any]]:
        """List custom fields visible on a list."""
        raise self._not_implemented(f"list_custom_fields:{list_id}")

    async def set_custom_field(self, task_id: str, field_id: str, value: str) -> None:
        """Set a task custom field value."""
        raise self._not_implemented(f"set_custom_field:{task_id}:{field_id}:{value}")
