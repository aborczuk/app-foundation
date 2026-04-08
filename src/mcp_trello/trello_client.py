"""Trello REST API client for the MCP Trello Bridge.

Async httpx.AsyncClient wrapper with:
- Key+Token auth injected as query params on every request
- Typed error hierarchy (TrelloAuthError, TrelloBoardNotFoundError, etc.)
- Rate pacing: sliding 10-second window, pauses at 90 requests to avoid 429
- 10-second timeout per request
- httpx request logging suppressed to prevent credential leakage (III-a)
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import httpx

from src.mcp_trello import TrelloCard, TrelloList

# Suppress httpx transport logger to prevent credential leakage via auth query params
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

_TRELLO_BASE = "https://api.trello.com/1"
_TIMEOUT = 10.0
_RATE_LIMIT_WINDOW = 10.0   # seconds
_RATE_LIMIT_PAUSE_AT = 90   # pause before hitting 100/10s limit

_SPECKIT_MARKER_RE = re.compile(r"<!--\s*speckit:([A-Z0-9]+)\s*-->")


# ---------------------------------------------------------------------------
# Typed error hierarchy
# ---------------------------------------------------------------------------

class TrelloError(Exception):
    """Base class for all Trello client errors."""


class TrelloAuthError(TrelloError):
    """Raised on 401 Unauthorized responses."""


class TrelloBoardNotFoundError(TrelloError):
    """Raised on 404 responses when fetching board resources."""


class TrelloRateLimitError(TrelloError):
    """Raised on 429 Too Many Requests responses."""


class TrelloAPIError(TrelloError):
    """Raised on 5xx responses, timeouts, and other transient errors."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class TrelloClient:
    """Async Trello REST API client.

    Usage::

        async with TrelloClient(api_key=..., token=...) as client:
            lists = await client.get_lists(board_id)
    """

    def __init__(
        self,
        api_key: str,
        token: str,
        transport: httpx.AsyncBaseTransport | httpx.MockTransport | None = None,
    ) -> None:
        """Initialize the instance."""
        self._api_key = api_key
        self._token = token
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        # Rate pacing: sliding window of request timestamps
        self._request_times: list[float] = []

    async def __aenter__(self) -> TrelloClient:
        """Enter the async context."""
        kwargs: dict[str, Any] = {"timeout": _TIMEOUT}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        self._client = httpx.AsyncClient(**kwargs)
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit the async context."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auth_params(self) -> dict[str, str]:
        return {"key": self._api_key, "token": self._token}

    async def _pace(self) -> None:
        """Enforce rate pacing: pause when 90 requests have been made in the last 10s."""
        now = time.monotonic()
        # Remove timestamps outside the 10-second window
        self._request_times = [t for t in self._request_times if now - t < _RATE_LIMIT_WINDOW]
        if len(self._request_times) >= _RATE_LIMIT_PAUSE_AT:
            oldest = self._request_times[0]
            sleep_for = _RATE_LIMIT_WINDOW - (now - oldest) + 0.05
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            # Reset window after sleeping
            self._request_times = []
        self._request_times.append(time.monotonic())

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Execute an authenticated request and return the parsed JSON body."""
        assert self._client is not None, "Use 'async with TrelloClient(...)'"

        await self._pace()

        params = kwargs.pop("params", {})
        params.update(self._auth_params())

        try:
            response = await self._client.request(
                method,
                f"{_TRELLO_BASE}{path}",
                params=params,
                **kwargs,
            )
        except httpx.TimeoutException:
            raise TrelloAPIError("Trello API request timed out after 10 seconds")
        except httpx.RequestError as exc:
            raise TrelloAPIError(f"Trello API request failed: {type(exc).__name__}") from exc

        self._raise_for_status(response)
        return response.json()

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Raise typed errors based on HTTP status — never exposing raw response bodies."""
        if response.status_code == 200:
            return
        if response.status_code == 401:
            raise TrelloAuthError("Trello authentication failed: invalid API key or token")
        if response.status_code == 404:
            raise TrelloBoardNotFoundError("Trello resource not found (404)")
        if response.status_code == 429:
            raise TrelloRateLimitError("Trello rate limit exceeded (429)")
        if response.status_code >= 500:
            raise TrelloAPIError(f"Trello API server error ({response.status_code})")
        # Other 4xx — surface status code only, not body
        raise TrelloAPIError(f"Trello API returned unexpected status {response.status_code}")

    @staticmethod
    def _extract_task_id(desc: str) -> str:
        """Extract speckit task ID from card description marker."""
        m = _SPECKIT_MARKER_RE.search(desc or "")
        return m.group(1) if m else ""

    @staticmethod
    def _card_from_json(data: dict[str, Any]) -> TrelloCard:
        return TrelloCard(
            trello_id=data["id"],
            task_id=TrelloClient._extract_task_id(data.get("desc", "")),
            title=data["name"],
            list_id=data["idList"],
            label_ids=data.get("idLabels", []),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_lists(self, board_id: str) -> list[TrelloList]:
        """Return all lists on the given board."""
        data = await self._request("GET", f"/boards/{board_id}/lists")
        return [
            TrelloList(trello_id=item["id"], name=item["name"], board_id=board_id)
            for item in data
        ]

    async def create_list(self, name: str, board_id: str) -> TrelloList:
        """Create a new list on the board and return it."""
        data = await self._request(
            "POST", "/lists",
            params={"name": name, "idBoard": board_id},
        )
        return TrelloList(trello_id=data["id"], name=data["name"], board_id=board_id)

    async def get_cards(self, list_id: str) -> list[TrelloCard]:
        """Return all cards in the given list."""
        data = await self._request("GET", f"/lists/{list_id}/cards")
        return [self._card_from_json(item) for item in data]

    async def create_card(
        self,
        list_id: str,
        name: str,
        desc: str,
        id_labels: list[str] | None = None,
    ) -> TrelloCard:
        """Create a card in the given list."""
        body: dict[str, Any] = {"idList": list_id, "name": name, "desc": desc}
        if id_labels:
            body["idLabels"] = ",".join(id_labels)
        data = await self._request("POST", "/cards", params=body)
        return self._card_from_json(data)

    async def update_card(
        self,
        card_id: str,
        id_labels: list[str] | None = None,
        **fields: Any,
    ) -> TrelloCard:
        """Update an existing card. id_labels replaces the full label set atomically."""
        body: dict[str, Any] = dict(fields)
        if id_labels is not None:
            body["idLabels"] = ",".join(id_labels)
        data = await self._request("PUT", f"/cards/{card_id}", params=body)
        return self._card_from_json(data)

    async def get_labels(self, board_id: str) -> dict[str, str]:
        """Return a name→id map of all labels on the board."""
        data = await self._request("GET", f"/boards/{board_id}/labels")
        return {item["name"]: item["id"] for item in data}

    async def create_label(self, name: str, color: str, board_id: str) -> str:
        """Create a new label on the board and return its ID."""
        data = await self._request(
            "POST", "/labels",
            params={"name": name, "color": color, "idBoard": board_id},
        )
        return data["id"]
