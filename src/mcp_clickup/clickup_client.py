"""Async ClickUp REST client foundation with typed error mapping."""

from __future__ import annotations

import logging
from typing import Any

import httpx

_BASE_URL = "https://api.clickup.com/api/v2"
_TIMEOUT_SECONDS = 10.0

# Suppress noisy HTTP transport logs that can include request metadata.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class ClickUpError(Exception):
    """Base error for ClickUp client failures."""


class ClickUpAuthError(ClickUpError):
    """Raised when ClickUp returns 401."""


class ClickUpNotFoundError(ClickUpError):
    """Raised when ClickUp returns 404."""


class ClickUpRateLimitError(ClickUpError):
    """Raised when ClickUp returns 429."""


class ClickUpTimeoutError(ClickUpError):
    """Raised on HTTP timeout exceptions."""


class ClickUpApiError(ClickUpError):
    """Raised for other API-level request failures."""


class ClickUpClient:
    """Async ClickUp REST client with auth header injection."""

    def __init__(
        self,
        api_token: str,
        *,
        base_url: str = _BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize."""
        self._api_token = api_token
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> ClickUpClient:
        """Enter context."""
        kwargs: dict[str, Any] = {"timeout": _TIMEOUT_SECONDS}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        self._client = httpx.AsyncClient(**kwargs)
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit context."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        assert self._client is not None, "Use 'async with ClickUpClient(...)'"

        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = self._api_token

        try:
            response = await self._client.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise ClickUpTimeoutError("ClickUp request timed out") from exc
        except httpx.RequestError as exc:
            raise ClickUpApiError(f"ClickUp request failed: {type(exc).__name__}") from exc

        if response.status_code == 401:
            raise ClickUpAuthError("ClickUp authentication failed")
        if response.status_code == 404:
            raise ClickUpNotFoundError("ClickUp resource not found")
        if response.status_code == 429:
            raise ClickUpRateLimitError("ClickUp rate limit exceeded")
        if response.status_code >= 500:
            raise ClickUpApiError(f"ClickUp server error ({response.status_code})")
        if response.status_code >= 400:
            raise ClickUpApiError(f"ClickUp API returned status {response.status_code}")

        payload = response.json()
        if isinstance(payload, dict):
            return payload
        return {"data": payload}

    async def get_space(self, space_id: str) -> dict[str, Any]:
        """Fetch a ClickUp Space by id."""
        return await self._request_json("GET", f"/space/{space_id}")

    async def list_folders(self, space_id: str) -> list[dict[str, Any]]:
        """List folders under a ClickUp space."""
        payload = await self._request_json("GET", f"/space/{space_id}/folder")
        folders = payload.get("folders", [])
        if isinstance(folders, list):
            return [dict(item) for item in folders if isinstance(item, dict)]
        return []

    async def create_folder(self, space_id: str, name: str) -> dict[str, Any]:
        """Create a folder under a ClickUp space."""
        return await self._request_json("POST", f"/space/{space_id}/folder", json={"name": name})

    async def list_lists(self, folder_id: str) -> list[dict[str, Any]]:
        """List lists under a ClickUp folder."""
        payload = await self._request_json("GET", f"/folder/{folder_id}/list")
        lists = payload.get("lists", [])
        if isinstance(lists, list):
            return [dict(item) for item in lists if isinstance(item, dict)]
        return []

    async def get_list(self, list_id: str) -> dict[str, Any]:
        """Fetch list metadata by ID."""
        return await self._request_json("GET", f"/list/{list_id}")

    async def create_list(self, folder_id: str, name: str) -> dict[str, Any]:
        """Create a list under a ClickUp folder."""
        return await self._request_json("POST", f"/folder/{folder_id}/list", json={"name": name})

    async def list_tasks(self, list_id: str) -> list[dict[str, Any]]:
        """List parent tasks under a ClickUp list."""
        payload = await self._request_json("GET", f"/list/{list_id}/task")
        tasks = payload.get("tasks", [])
        if isinstance(tasks, list):
            return [dict(item) for item in tasks if isinstance(item, dict)]
        return []

    async def list_subtasks(self, task_id: str) -> list[dict[str, Any]]:
        """List subtasks for a given parent task by filtering list tasks."""
        tasks = await self._request_json("GET", f"/task/{task_id}")
        list_id = str(tasks.get("list", {}).get("id", ""))
        if not list_id:
            return []
        all_tasks = await self.list_tasks(list_id)
        return [task for task in all_tasks if str(task.get("parent", "")) == task_id]

    async def create_task(
        self,
        list_id: str,
        name: str,
        parent: str | None = None,
    ) -> dict[str, Any]:
        """Create a task or subtask in a list."""
        body: dict[str, Any] = {"name": name}
        if parent:
            body["parent"] = parent
        return await self._request_json("POST", f"/list/{list_id}/task", json=body)

    async def update_task(self, task_id: str, *, name: str) -> dict[str, Any]:
        """Update task/subtask mutable fields."""
        return await self._request_json("PUT", f"/task/{task_id}", json={"name": name})

    async def list_custom_fields(self, list_id: str) -> list[dict[str, Any]]:
        """List custom fields visible on a list."""
        payload = await self._request_json("GET", f"/list/{list_id}/field")
        fields = payload.get("fields", [])
        if isinstance(fields, list):
            return [dict(item) for item in fields if isinstance(item, dict)]
        return []

    async def set_custom_field(self, task_id: str, field_id: str, value: str) -> None:
        """Set a task custom field value."""
        await self._request_json(
            "POST",
            f"/task/{task_id}/field/{field_id}",
            json={"value": value},
        )
