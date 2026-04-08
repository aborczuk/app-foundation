"""n8n dispatch client with explicit async timeout/cancel lifecycle handling."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

WORKFLOW_ROUTE_MAP: dict[str, str] = {
    "build_spec": "/control-plane/build-spec",
    "qa_loop": "/control-plane/qa-loop",
}
WORKFLOW_CANCEL_ROUTE = "/control-plane/cancel-run"


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


class DispatchError(Exception):
    """Base class for dispatch failures."""


class DispatchTimeoutError(DispatchError):
    """Raised when dispatch exceeds the configured timeout."""


class DispatchCancelledError(DispatchError):
    """Raised when dispatch is cancelled by caller cancellation signal."""


class DispatchRequestError(DispatchError):
    """Raised when dispatch transport fails."""


class DispatchRejectedError(DispatchError):
    """Raised when n8n rejects the dispatch request (non-2xx)."""


@dataclass(frozen=True)
class DispatchRequest:
    """Dispatch input payload for n8n workflow triggers."""

    task_id: str
    event_id: str
    workflow_type: str
    context_ref: str
    execution_policy: str
    event: str
    occurred_at_utc: str
    attempt_number: int | None = None
    criteria_items: tuple[str, ...] = ()
    prior_failure_context: tuple[dict[str, Any], ...] = ()
    resume_run_id: str | None = None
    human_input_response: str | None = None
    human_input_prompt: str | None = None


@dataclass(frozen=True)
class DispatchResult:
    """Successful dispatch response details."""

    status_code: int
    run_id: str | None
    response_body: dict[str, Any]


class N8NDispatchClient:
    """Async n8n trigger client with explicit timeout and cancellation control."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | httpx.MockTransport | None = None,
    ) -> None:
        """Initialize dispatch transport configuration."""
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> N8NDispatchClient:
        """Open the underlying async HTTP client used for dispatch requests."""
        kwargs: dict[str, Any] = {"timeout": self._timeout_seconds}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        self._client = httpx.AsyncClient(**kwargs)
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Close the async HTTP client and release transport resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def dispatch(
        self,
        *,
        request: DispatchRequest,
        path: str,
        cancel_event: asyncio.Event | None = None,
    ) -> DispatchResult:
        """Dispatch to n8n with explicit task lifecycle handling."""
        if self._client is None:
            raise DispatchRequestError("Use 'async with N8NDispatchClient(...)' before dispatch.")
        client = self._client

        payload: dict[str, Any] = {
            "task_id": request.task_id,
            "event_id": request.event_id,
            "workflow_type": request.workflow_type,
            "context_ref": request.context_ref,
            "execution_policy": request.execution_policy,
            "event": request.event,
            "occurred_at_utc": request.occurred_at_utc,
        }
        if request.attempt_number is not None:
            payload["attempt_number"] = request.attempt_number
        if request.criteria_items:
            payload["criteria_items"] = list(request.criteria_items)
        if request.prior_failure_context:
            payload["prior_failure_context"] = list(request.prior_failure_context)
        if request.resume_run_id:
            payload["resume_run_id"] = request.resume_run_id
        if request.human_input_response:
            payload["human_input_response"] = request.human_input_response
        if request.human_input_prompt:
            payload["human_input_prompt"] = request.human_input_prompt
        url = f"{self._base_url}/{path.lstrip('/')}"

        async def send() -> httpx.Response:
            try:
                return await client.post(url, json=payload)
            except httpx.TimeoutException as exc:
                raise DispatchTimeoutError("n8n dispatch timed out.") from exc
            except httpx.RequestError as exc:
                raise DispatchRequestError(
                    f"n8n dispatch request failed: {type(exc).__name__}"
                ) from exc

        response = await _run_with_timeout_and_cancel(
            send(),
            timeout_seconds=self._timeout_seconds,
            cancel_event=cancel_event,
        )

        if response.status_code >= 300:
            raise DispatchRejectedError(
                f"n8n rejected dispatch with status {response.status_code}."
            )

        body = _safe_json(response)
        run_id = _extract_run_id(body)
        return DispatchResult(
            status_code=response.status_code,
            run_id=run_id,
            response_body=body,
        )

    async def cancel_run(
        self,
        *,
        task_id: str,
        run_id: str,
        event_id: str,
        reason: str,
        path: str = WORKFLOW_CANCEL_ROUTE,
    ) -> None:
        """Send best-effort cancellation signal to workflow runtime."""
        if self._client is None:
            raise DispatchRequestError("Use 'async with N8NDispatchClient(...)' before dispatch.")
        client = self._client
        url = f"{self._base_url}/{path.lstrip('/')}"
        payload = {
            "task_id": task_id,
            "run_id": run_id,
            "event_id": event_id,
            "reason": reason,
            "occurred_at_utc": utc_now_iso(),
        }
        try:
            response = await client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise DispatchTimeoutError("n8n cancel request timed out.") from exc
        except httpx.RequestError as exc:
            raise DispatchRequestError(
                f"n8n cancel request failed: {type(exc).__name__}"
            ) from exc
        if response.status_code >= 300:
            raise DispatchRejectedError(
                f"n8n rejected cancel request with status {response.status_code}."
            )


def normalize_workflow_type(raw_workflow_type: str) -> str:
    """Normalize workflow discriminator into canonical snake_case key."""
    return raw_workflow_type.strip().lower().replace("-", "_")


def resolve_workflow_path(workflow_type: str) -> str | None:
    """Resolve workflow type to configured n8n route path."""
    normalized = normalize_workflow_type(workflow_type)
    return WORKFLOW_ROUTE_MAP.get(normalized)


def build_dispatch_request(
    *,
    task_id: str,
    event_id: str,
    workflow_type: str,
    context_ref: str,
    execution_policy: str,
    event: str,
    occurred_at_utc: str | None = None,
    attempt_number: int | None = None,
    criteria_items: tuple[str, ...] = (),
    prior_failure_context: tuple[dict[str, Any], ...] = (),
    resume_run_id: str | None = None,
    human_input_response: str | None = None,
    human_input_prompt: str | None = None,
) -> DispatchRequest:
    """Build normalized n8n dispatch request payload."""
    return DispatchRequest(
        task_id=task_id,
        event_id=event_id,
        workflow_type=normalize_workflow_type(workflow_type),
        context_ref=context_ref,
        execution_policy=execution_policy,
        event=event,
        occurred_at_utc=occurred_at_utc or utc_now_iso(),
        attempt_number=attempt_number,
        criteria_items=criteria_items,
        prior_failure_context=prior_failure_context,
        resume_run_id=resume_run_id,
        human_input_response=human_input_response,
        human_input_prompt=human_input_prompt,
    )


async def _run_with_timeout_and_cancel(
    awaitable: Any,
    *,
    timeout_seconds: float,
    cancel_event: asyncio.Event | None,
) -> Any:
    """Await coroutine with explicit timeout and cooperative cancellation cleanup."""
    task = asyncio.create_task(awaitable)
    cancel_waiter: asyncio.Task[bool] | None = None

    if cancel_event is not None:
        cancel_waiter = asyncio.create_task(cancel_event.wait())
        done, pending = await asyncio.wait(
            {task, cancel_waiter},
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_waiter in done and cancel_event.is_set():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise DispatchCancelledError("Dispatch cancelled by caller signal.")
        if task not in done:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise DispatchTimeoutError("Dispatch timed out before completion.")
        for pending_task in pending:
            pending_task.cancel()
            await asyncio.gather(pending_task, return_exceptions=True)
        return await task

    try:
        return await asyncio.wait_for(task, timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise DispatchTimeoutError("Dispatch timed out before completion.") from exc


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    if not response.content:
        return {}
    try:
        parsed = response.json()
    except ValueError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _extract_run_id(body: dict[str, Any]) -> str | None:
    for key in ("run_id", "runId", "execution_id", "executionId", "id"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


__all__ = [
    "DispatchCancelledError",
    "DispatchError",
    "DispatchRejectedError",
    "DispatchRequest",
    "DispatchRequestError",
    "DispatchResult",
    "DispatchTimeoutError",
    "N8NDispatchClient",
    "WORKFLOW_CANCEL_ROUTE",
    "WORKFLOW_ROUTE_MAP",
    "build_dispatch_request",
    "normalize_workflow_type",
    "resolve_workflow_path",
    "utc_now_iso",
]
