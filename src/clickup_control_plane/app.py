"""FastAPI entrypoint for ClickUp webhook intake and n8n dispatch."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import httpx
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .clickup_client import ClickUpError, ClickUpOutcomeClient, TaskOutcomePayload
from .config import ConfigError, ControlPlaneRuntimeConfig, load_runtime_config
from .dispatcher import N8NDispatchClient
from .qa_loop import resolve_qa_loop_config
from .reconcile import ReconciliationService
from .schemas import (
    ClickUpWebhookPayload,
    WebhookAcceptedResponse,
    WebhookDecision,
    WebhookErrorDetail,
    WebhookErrorResponse,
    WorkflowCompletionAcceptedResponse,
    WorkflowCompletionPayload,
)
from .service import DispatchOrchestrationService
from .state_store import StateStore
from .webhook_auth import SignatureVerificationError, assert_valid_clickup_signature

_CLICKUP_API_BASE = "https://api.clickup.com/api/v2"


@dataclass(frozen=True)
class _PayloadValidationFailure(Exception):
    """Structured payload validation failure for webhook envelope responses."""

    message: str
    action: str


@lru_cache(maxsize=1)
def get_runtime_config() -> ControlPlaneRuntimeConfig:
    """Load runtime settings once per process."""
    return load_runtime_config()


class _ClickUpTaskStatusProbe:
    """Startup reconciliation probe backed by ClickUp task status reads."""

    def __init__(
        self,
        *,
        api_token: str,
        timeout_seconds: float,
        base_url: str = _CLICKUP_API_BASE,
        transport: httpx.AsyncBaseTransport | httpx.MockTransport | None = None,
    ) -> None:
        self._api_token = api_token
        self._timeout_seconds = timeout_seconds
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> _ClickUpTaskStatusProbe:
        kwargs: dict[str, Any] = {"timeout": self._timeout_seconds}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        self._client = httpx.AsyncClient(**kwargs)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def is_task_run_active(self, *, task_id: str, run_id: str) -> bool:  # noqa: ARG002
        if self._client is None:
            raise RuntimeError("Probe client is not initialized.")

        response = await self._client.get(
            f"{self._base_url}/task/{task_id}",
            headers={"Authorization": self._api_token},
        )
        if response.status_code == 404:
            return False
        if response.status_code >= 400:
            raise RuntimeError(f"ClickUp probe status={response.status_code}")

        payload: Mapping[str, Any] = {}
        if response.content:
            try:
                parsed = response.json()
            except ValueError:
                parsed = {}
            if isinstance(parsed, Mapping):
                payload = parsed

        status_name = _extract_clickup_status(payload)
        if status_name is None:
            return True
        return _status_implies_active(status_name)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    config = get_runtime_config()
    state_store = StateStore(config.control_plane_db_path)
    await state_store.initialize()

    async with AsyncExitStack() as stack:
        dispatcher_client = await stack.enter_async_context(
            N8NDispatchClient(
                base_url=config.n8n_dispatch_base_url,
                timeout_seconds=config.request_timeout_seconds,
            )
        )
        clickup_client = await stack.enter_async_context(
            ClickUpOutcomeClient(
                api_token=config.clickup_api_token,
                timeout_seconds=config.request_timeout_seconds,
            )
        )
        probe = await stack.enter_async_context(
            _ClickUpTaskStatusProbe(
                api_token=config.clickup_api_token,
                timeout_seconds=config.request_timeout_seconds,
            )
        )
        reconciliation_service = ReconciliationService(
            state_store=state_store,
            run_state_probe=probe,
        )
        dispatch_service = DispatchOrchestrationService(
            state_store=state_store,
            dispatcher_client=dispatcher_client,
            clickup_outcome_client=clickup_client,
            qa_loop_config=resolve_qa_loop_config(config),
            allowlist=config.allowlist,
            workflow_controlled_statuses=_workflow_controlled_statuses(config),
            reconciliation_service=reconciliation_service,
        )
        reconciliation_result = await reconciliation_service.reconcile_stale_active_runs()

        app.state.runtime_config = config
        app.state.state_store = state_store
        app.state.dispatcher_client = dispatcher_client
        app.state.clickup_outcome_client = clickup_client
        app.state.dispatch_service = dispatch_service
        app.state.reconciliation_service = reconciliation_service
        app.state.reconciliation_result = reconciliation_result
        yield


def create_app() -> FastAPI:
    """Build and configure FastAPI application."""
    api = FastAPI(title="ClickUp Control Plane", version="0.1.0", lifespan=_lifespan)

    @api.get("/control-plane/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.post("/control-plane/clickup/webhook")
    async def clickup_webhook(request: Request) -> JSONResponse:
        try:
            config = get_runtime_config()
        except ConfigError as exc:
            return _error(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="Control-plane configuration is invalid.",
                action=f"Fix runtime env configuration and restart service. ({exc})",
            )

        if not _has_json_content_type(request.headers.get("content-type")):
            return _error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_payload",
                message="Request content type must be application/json.",
                action="Send JSON webhook payloads with Content-Type: application/json.",
            )

        body = await request.body()
        try:
            assert_valid_clickup_signature(
                body=body,
                headers=request.headers,
                webhook_secret=config.clickup_webhook_secret,
            )
        except SignatureVerificationError:
            return _error(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="invalid_signature",
                message="Webhook signature validation failed.",
                action="Verify ClickUp webhook secret and signature header forwarding.",
            )

        try:
            payload, payload_raw = _parse_payload(body)
        except _PayloadValidationFailure as exc:
            return _error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_payload",
                message=exc.message,
                action=exc.action,
            )

        event_id = _event_id_from_body(body)
        orchestration = get_dispatch_service(request)
        result = await orchestration.process_event(
            payload=payload,
            payload_raw=payload_raw,
            event_id=event_id,
        )

        if result.decision == "dispatch_failed":
            if result.reason_code == "qa_result_invalid":
                return _error(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    code="qa_result_invalid",
                    message="QA workflow response did not match required contract payload.",
                    action="Fix QA workflow response fields and retry webhook event.",
                )
            return _error(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="dispatch_failed",
                message="n8n dispatch request failed.",
                action="Review n8n workflow status and webhook endpoint mapping.",
            )

        return _accepted(event_id=event_id, decision=result.decision)

    @api.post("/control-plane/workflow/completion")
    async def workflow_completion(request: Request) -> JSONResponse:
        try:
            config = get_runtime_config()
        except ConfigError as exc:
            return _error(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="Control-plane configuration is invalid.",
                action=f"Fix runtime env configuration and restart service. ({exc})",
            )

        if not _has_json_content_type(request.headers.get("content-type")):
            return _error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_payload",
                message="Request content type must be application/json.",
                action="Send JSON completion payloads with Content-Type: application/json.",
            )
        if not _is_valid_completion_token(
            provided=request.headers.get("x-completion-token"),
            expected=config.completion_callback_token,
        ):
            return _error(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="invalid_completion_token",
                message="Completion callback token validation failed.",
                action=(
                    "Provide a valid X-Completion-Token header matching "
                    "CONTROL_PLANE_COMPLETION_TOKEN."
                ),
            )

        try:
            completion = _parse_completion_payload(await request.body())
        except _PayloadValidationFailure as exc:
            return _error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_payload",
                message=exc.message,
                action=exc.action,
            )

        try:
            await get_clickup_outcome_client(request).write_task_outcome(
                task_id=completion.task_id,
                outcome=_build_completion_outcome(completion),
            )
        except ClickUpError:
            return _error(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="completion_write_failed",
                message="Failed to write workflow completion outcome to ClickUp.",
                action="Verify ClickUp API connectivity/permissions and retry completion callback.",
            )

        state_store = get_state_store(request)
        if completion.status == "waiting_input":
            if completion.run_id is None:
                return _error(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="invalid_payload",
                    message="waiting_input callbacks require run_id.",
                    action="Provide run_id and human_input_request when status=waiting_input.",
                )
            request_details = completion.human_input_request
            assert request_details is not None  # guarded by schema validator
            try:
                await get_clickup_outcome_client(request).set_task_status(
                    task_id=completion.task_id,
                    status_name=config.hitl_waiting_status,
                )
            except ClickUpError:
                return _error(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    code="completion_write_failed",
                    message="Failed to update task status to waiting for input.",
                    action="Verify ClickUp status mapping and retry completion callback.",
                )

            timeout_at = (
                request_details.timeout_at_utc.astimezone(timezone.utc).isoformat()
                if request_details.timeout_at_utc is not None
                else (datetime.now(timezone.utc) + timedelta(seconds=config.hitl_timeout_seconds)).isoformat()
            )
            await state_store.upsert_paused_run(
                task_id=completion.task_id,
                run_id=completion.run_id,
                workflow_type=completion.workflow_type,
                context_ref=completion.context_ref or "unknown_context_ref",
                execution_policy=completion.execution_policy or "unknown_execution_policy",
                timeout_at_utc=timeout_at,
                prompt=request_details.prompt,
            )
        else:
            if completion.status == "timed_out":
                try:
                    await get_clickup_outcome_client(request).set_task_status(
                        task_id=completion.task_id,
                        status_name=config.hitl_blocked_status,
                    )
                except ClickUpError:
                    return _error(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        code="completion_write_failed",
                        message="Failed to set blocked status after HITL timeout.",
                        action="Verify ClickUp status mapping and retry completion callback.",
                    )

            if completion.run_id:
                await state_store.release_active_run(
                    task_id=completion.task_id,
                    run_id=completion.run_id,
                )
                await state_store.clear_paused_run(
                    task_id=completion.task_id,
                    run_id=completion.run_id,
                )
            else:
                active_run = await state_store.get_active_run(task_id=completion.task_id)
                if active_run is not None:
                    await state_store.release_active_run(
                        task_id=completion.task_id,
                        run_id=active_run.run_id,
                    )
                    await state_store.clear_paused_run(
                        task_id=completion.task_id,
                        run_id=active_run.run_id,
                    )

        payload = WorkflowCompletionAcceptedResponse(
            accepted=True,
            task_id=completion.task_id,
            status=completion.status,
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=payload.model_dump(mode="json"),
        )

    return api


def get_state_store(request: Request) -> StateStore:
    """Return the request-scoped state-store dependency."""
    return request.app.state.state_store


def get_dispatcher_client(request: Request) -> N8NDispatchClient:
    """Return the request-scoped n8n dispatcher client dependency."""
    return request.app.state.dispatcher_client


def get_clickup_outcome_client(request: Request) -> ClickUpOutcomeClient:
    """Return the request-scoped ClickUp outcome writer dependency."""
    return request.app.state.clickup_outcome_client


def get_dispatch_service(request: Request) -> DispatchOrchestrationService:
    """Return the request-scoped orchestration service dependency."""
    return request.app.state.dispatch_service


def _event_id_from_body(body: bytes) -> str:
    digest = hashlib.sha256(body).hexdigest()[:24]
    return f"evt_{digest}"


def _parse_payload(body: bytes) -> tuple[ClickUpWebhookPayload, Mapping[str, Any]]:
    try:
        payload_raw = json.loads(body)
    except json.JSONDecodeError as exc:
        raise _PayloadValidationFailure(
            message="Request body is not valid JSON.",
            action="Send a valid JSON payload.",
        ) from exc

    if not isinstance(payload_raw, Mapping):
        raise _PayloadValidationFailure(
            message="Webhook payload must be a JSON object.",
            action="Send a JSON object payload with event and task_id fields.",
        )

    try:
        payload = ClickUpWebhookPayload.model_validate(payload_raw)
    except ValidationError as exc:
        raise _PayloadValidationFailure(
            message="Webhook payload is missing required fields.",
            action="Ensure ClickUp event payload contains event and task_id.",
        ) from exc

    return payload, payload_raw


def _has_json_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return False
    value = content_type.strip().lower()
    return value.startswith("application/json")


def _is_valid_completion_token(*, provided: str | None, expected: str | None) -> bool:
    if expected is None:
        return True
    if provided is None:
        return False
    return secrets.compare_digest(provided.strip(), expected)


def _accepted(*, event_id: str, decision: WebhookDecision) -> JSONResponse:
    payload = WebhookAcceptedResponse(
        accepted=True,
        event_id=event_id,
        decision=decision,
    )
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=payload.model_dump(mode="json"))


def _error(*, status_code: int, code: str, message: str, action: str) -> JSONResponse:
    payload = WebhookErrorResponse(
        error=WebhookErrorDetail(code=code, message=message, action=action)
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def _parse_completion_payload(body: bytes) -> WorkflowCompletionPayload:
    try:
        payload_raw = json.loads(body)
    except json.JSONDecodeError as exc:
        raise _PayloadValidationFailure(
            message="Completion payload is not valid JSON.",
            action="Send a valid JSON payload.",
        ) from exc
    if not isinstance(payload_raw, Mapping):
        raise _PayloadValidationFailure(
            message="Completion payload must be a JSON object.",
            action=(
                "Send completion payload with required fields: "
                "task_id, workflow_type, status, summary."
            ),
        )
    try:
        return WorkflowCompletionPayload.model_validate(payload_raw)
    except ValidationError as exc:
        raise _PayloadValidationFailure(
            message="Completion payload is missing required fields.",
            action="Provide task_id, workflow_type, status, and summary in callback payload.",
        ) from exc


def _build_completion_outcome(completion: WorkflowCompletionPayload) -> TaskOutcomePayload:
    if completion.status == "completed":
        severity: str = "info"
    elif completion.status in {"failed", "timed_out"}:
        severity = "error"
    else:
        severity = "warning"
    run_clause = f" run_id={completion.run_id}" if completion.run_id else ""
    summary = (
        f"Workflow '{completion.workflow_type}' {completion.status} for task {completion.task_id}.{run_clause}"
    )
    details = completion.details or ""
    if completion.status == "waiting_input" and completion.human_input_request is not None:
        prompt = completion.human_input_request.prompt
        response_format = completion.human_input_request.response_format
        timeout_clause = ""
        if completion.human_input_request.timeout_at_utc is not None:
            timeout_clause = (
                f"\ntimeout_at_utc="
                f"{completion.human_input_request.timeout_at_utc.astimezone(timezone.utc).isoformat()}"
            )
        details = (
            f"HITL request issued.\nprompt={prompt}\nresponse_format={response_format}{timeout_clause}"
        )
    if completion.artifact_links:
        links = ", ".join(completion.artifact_links)
        details = f"{details}\nartifacts={links}".strip()
    if not details:
        details = completion.summary
    return TaskOutcomePayload(
        severity=severity,
        summary=summary,
        details=details,
        reason_code=f"workflow_{completion.status}",
        run_id=completion.run_id,
    )


def _workflow_controlled_statuses(config: ControlPlaneRuntimeConfig) -> tuple[str, ...]:
    return (
        config.qa_build_status,
        config.qa_trigger_status,
        config.qa_pass_status,
        config.hitl_waiting_status,
        config.hitl_blocked_status,
    )


def _extract_clickup_status(payload: Mapping[str, Any]) -> str | None:
    status_data = payload.get("status")
    if isinstance(status_data, str) and status_data.strip():
        return status_data.strip()
    if isinstance(status_data, Mapping):
        for key in ("status", "type", "name"):
            value = status_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _status_implies_active(status_name: str) -> bool:
    lowered = status_name.strip().lower()
    terminal_tokens = ("done", "complete", "closed", "cancelled", "canceled", "failed", "blocked")
    if any(token in lowered for token in terminal_tokens):
        return False
    return True


app = create_app()
