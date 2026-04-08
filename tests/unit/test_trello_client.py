"""Unit tests for the Trello API client (src/mcp_trello/trello_client.py).

Tests are written BEFORE implementation per Constitution XV (TDD).
All tests in this file must fail until trello_client.py is implemented.

Uses httpx.MockTransport to intercept HTTP calls without network access.
"""

from unittest.mock import patch

import httpx
import pytest

from src.mcp_trello.trello_client import (
    TrelloAPIError,
    TrelloAuthError,
    TrelloBoardNotFoundError,
    TrelloClient,
    TrelloRateLimitError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_response(status_code: int, json_body) -> httpx.Response:
    """Execute the function."""
    import json
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(json_body).encode(),
        headers={"Content-Type": "application/json"},
    )


def mock_transport(responses: list[httpx.Response]) -> httpx.MockTransport:
    """Return a MockTransport that replays the given responses in order."""
    iter_responses = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return next(iter_responses)

    return httpx.MockTransport(handler)


BOARD_ID = "board123"
LIST_ID = "list456"
CARD_ID = "card789"
LABEL_ID = "label000"
API_KEY = "testkey"
TOKEN = "testtoken"


# ---------------------------------------------------------------------------
# Auth query param tests
# ---------------------------------------------------------------------------

async def test_auth_params_included_in_all_requests():
    """Every request must include key and token query params."""
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return make_response(200, [])

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    async with client:
        await client.get_lists(BOARD_ID)

    assert len(captured) == 1
    req = captured[0]
    assert req.url.params["key"] == API_KEY
    assert req.url.params["token"] == TOKEN


async def test_auth_params_present_on_create_card():
    """Test the expected behavior."""
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return make_response(200, {"id": CARD_ID, "name": "Test", "idList": LIST_ID, "desc": "", "idLabels": []})

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    async with client:
        await client.create_card(LIST_ID, "Test", "desc")

    req = captured[0]
    assert req.url.params["key"] == API_KEY
    assert req.url.params["token"] == TOKEN


# ---------------------------------------------------------------------------
# get_lists
# ---------------------------------------------------------------------------

async def test_get_lists_returns_trello_list_objects():
    """Test the expected behavior."""
    from src.mcp_trello import TrelloList

    def handler(req: httpx.Request) -> httpx.Response:
        return make_response(200, [
            {"id": "l1", "name": "Phase 1", "idBoard": BOARD_ID},
            {"id": "l2", "name": "Phase 2", "idBoard": BOARD_ID},
        ])

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    async with client:
        lists = await client.get_lists(BOARD_ID)

    assert len(lists) == 2
    assert all(isinstance(item, TrelloList) for item in lists)
    assert lists[0].trello_id == "l1"
    assert lists[0].name == "Phase 1"
    assert lists[0].board_id == BOARD_ID


async def test_get_lists_board_not_found_raises_error():
    """Test the expected behavior."""
    def handler(req: httpx.Request) -> httpx.Response:
        return make_response(404, {"message": "board not found"})

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    with pytest.raises(TrelloBoardNotFoundError):
        async with client:
            await client.get_lists(BOARD_ID)


async def test_get_lists_auth_failure_raises_error():
    """Test the expected behavior."""
    def handler(req: httpx.Request) -> httpx.Response:
        return make_response(401, {"message": "invalid token"})

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    with pytest.raises(TrelloAuthError):
        async with client:
            await client.get_lists(BOARD_ID)


# ---------------------------------------------------------------------------
# create_list
# ---------------------------------------------------------------------------

async def test_create_list_returns_trello_list():
    """Test the expected behavior."""
    from src.mcp_trello import TrelloList

    def handler(req: httpx.Request) -> httpx.Response:
        return make_response(200, {"id": "l99", "name": "New Phase", "idBoard": BOARD_ID})

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    async with client:
        result = await client.create_list("New Phase", BOARD_ID)

    assert isinstance(result, TrelloList)
    assert result.name == "New Phase"
    assert result.trello_id == "l99"


# ---------------------------------------------------------------------------
# get_cards
# ---------------------------------------------------------------------------

async def test_get_cards_returns_trello_card_objects():
    """Test the expected behavior."""
    from src.mcp_trello import TrelloCard

    def handler(req: httpx.Request) -> httpx.Response:
        return make_response(200, [
            {"id": CARD_ID, "name": "Task title", "idList": LIST_ID, "desc": "<!-- speckit:T001 -->", "idLabels": []},
        ])

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    async with client:
        cards = await client.get_cards(LIST_ID)

    assert len(cards) == 1
    assert isinstance(cards[0], TrelloCard)
    assert cards[0].trello_id == CARD_ID
    assert cards[0].task_id == "T001"


async def test_get_cards_card_without_marker_has_empty_task_id():
    """Cards with no speckit marker in desc should still be returned with empty task_id."""

    def handler(req: httpx.Request) -> httpx.Response:
        return make_response(200, [
            {"id": CARD_ID, "name": "Manual card", "idList": LIST_ID, "desc": "No marker here", "idLabels": []},
        ])

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    async with client:
        cards = await client.get_cards(LIST_ID)

    assert cards[0].task_id == ""


# ---------------------------------------------------------------------------
# create_card
# ---------------------------------------------------------------------------

async def test_create_card_returns_trello_card():
    """Test the expected behavior."""
    from src.mcp_trello import TrelloCard

    def handler(req: httpx.Request) -> httpx.Response:
        return make_response(200, {"id": CARD_ID, "name": "My Task", "idList": LIST_ID, "desc": "<!-- speckit:T001 -->", "idLabels": []})

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    async with client:
        card = await client.create_card(LIST_ID, "My Task", "<!-- speckit:T001 -->")

    assert isinstance(card, TrelloCard)
    assert card.trello_id == CARD_ID


async def test_create_card_with_id_labels():
    """Test the expected behavior."""
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return make_response(200, {"id": CARD_ID, "name": "Task", "idList": LIST_ID, "desc": "", "idLabels": [LABEL_ID]})

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    async with client:
        card = await client.create_card(LIST_ID, "Task", "", id_labels=[LABEL_ID])

    assert card.label_ids == [LABEL_ID]


# ---------------------------------------------------------------------------
# update_card
# ---------------------------------------------------------------------------

async def test_update_card_sends_put_request():
    """Test the expected behavior."""
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return make_response(200, {"id": CARD_ID, "name": "Updated", "idList": LIST_ID, "desc": "", "idLabels": []})

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    async with client:
        await client.update_card(CARD_ID, name="Updated")

    assert captured[0].method == "PUT"


async def test_update_card_with_id_labels_atomic():
    """update_card with idLabels should send complete label list (atomic replace)."""
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return make_response(200, {"id": CARD_ID, "name": "Task", "idList": LIST_ID, "desc": "", "idLabels": ["l1", "l2"]})

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    async with client:
        card = await client.update_card(CARD_ID, id_labels=["l1", "l2"])

    assert card.label_ids == ["l1", "l2"]


# ---------------------------------------------------------------------------
# get_labels
# ---------------------------------------------------------------------------

async def test_get_labels_returns_dict():
    """Test the expected behavior."""
    def handler(req: httpx.Request) -> httpx.Response:
        return make_response(200, [
            {"id": "lab1", "name": "P1", "color": "red"},
            {"id": "lab2", "name": "US1", "color": "blue"},
        ])

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    async with client:
        labels = await client.get_labels(BOARD_ID)

    assert labels["P1"] == "lab1"
    assert labels["US1"] == "lab2"


# ---------------------------------------------------------------------------
# create_label
# ---------------------------------------------------------------------------

async def test_create_label_returns_id():
    """Test the expected behavior."""
    def handler(req: httpx.Request) -> httpx.Response:
        return make_response(200, {"id": "newlabel", "name": "P2", "color": "orange"})

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    async with client:
        label_id = await client.create_label("P2", "orange", BOARD_ID)

    assert label_id == "newlabel"


# ---------------------------------------------------------------------------
# 10s timeout abort
# ---------------------------------------------------------------------------

async def test_timeout_raises_api_error():
    """Test the expected behavior."""
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=req)

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    with pytest.raises(TrelloAPIError):
        async with client:
            await client.get_lists(BOARD_ID)


# ---------------------------------------------------------------------------
# 5xx abort
# ---------------------------------------------------------------------------

async def test_5xx_response_raises_api_error():
    """Test the expected behavior."""
    def handler(req: httpx.Request) -> httpx.Response:
        return make_response(500, {"message": "internal server error"})

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    with pytest.raises(TrelloAPIError):
        async with client:
            await client.get_lists(BOARD_ID)


# ---------------------------------------------------------------------------
# 429 detection
# ---------------------------------------------------------------------------

async def test_429_raises_rate_limit_error():
    """Test the expected behavior."""
    def handler(req: httpx.Request) -> httpx.Response:
        return make_response(429, {"message": "rate limit exceeded"})

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    with pytest.raises(TrelloRateLimitError):
        async with client:
            await client.get_lists(BOARD_ID)


# ---------------------------------------------------------------------------
# Error wrapping — no raw Trello payloads exposed
# ---------------------------------------------------------------------------

async def test_api_error_does_not_expose_raw_payload():
    """Error messages must not contain raw Trello JSON bodies."""
    def handler(req: httpx.Request) -> httpx.Response:
        return make_response(500, {"message": "internal server error", "secret_field": "secret_value"})

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)
    with pytest.raises(TrelloAPIError) as exc_info:
        async with client:
            await client.get_lists(BOARD_ID)

    # Raw JSON body must not appear in the exception message
    assert "secret_field" not in str(exc_info.value)
    assert "secret_value" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# Rate pacing — sliding 10s window pauses at 90 requests
# ---------------------------------------------------------------------------

async def test_rate_pacing_pauses_at_90_requests():
    """Client should pause (asyncio.sleep) when 90 requests are made within 10s."""
    call_count = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return make_response(200, [])

    transport = httpx.MockTransport(handler)
    client = TrelloClient(api_key=API_KEY, token=TOKEN, transport=transport)

    sleep_calls: list[float] = []

    async def mock_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    with patch("src.mcp_trello.trello_client.asyncio.sleep", new=mock_sleep):
        async with client:
            for _ in range(91):
                await client.get_lists(BOARD_ID)

    # At least one sleep should have been triggered
    assert len(sleep_calls) >= 1
    # Sleep duration must be positive
    assert all(d > 0 for d in sleep_calls)
