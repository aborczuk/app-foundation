"""Test module."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from clickup_control_plane.dispatcher import (
    DispatchCancelledError,
    DispatchRejectedError,
    DispatchRequest,
    DispatchTimeoutError,
    N8NDispatchClient,
    build_dispatch_request,
    resolve_workflow_path,
)


def _request() -> DispatchRequest:
    return DispatchRequest(
        task_id="task-1",
        event_id="evt-1",
        workflow_type="build_spec",
        context_ref="specs/015-control-plane-dispatch/spec.md",
        execution_policy="strict",
        event="taskStatusUpdated",
        occurred_at_utc="2026-04-03T00:00:00Z",
    )


def _qa_request() -> DispatchRequest:
    return DispatchRequest(
        task_id="task-qa-1",
        event_id="evt-qa-1",
        workflow_type="qa_loop",
        context_ref="specs/016-control-plane-qa-loop/spec.md",
        execution_policy="manual-test",
        event="taskStatusUpdated",
        occurred_at_utc="2026-04-03T00:00:00Z",
        attempt_number=2,
        criteria_items=("criterion a", "criterion b"),
        prior_failure_context=(
            {
                "issue_description": "example issue",
                "expected_behavior": "expected",
                "observed_behavior": "observed",
                "reproduction_context": "steps",
            },
        ),
    )


@pytest.mark.asyncio
async def test_dispatch_runs_inside_active_event_loop_without_nested_loop_errors() -> None:
    """Test the expected behavior."""
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"run_id": "run-1"})

    async with N8NDispatchClient(
        base_url="http://n8n.local/webhook",
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.dispatch(request=_request(), path="/control-plane/build-spec")

    assert result.run_id == "run-1"
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_dispatch_qa_path_includes_attempt_criteria_and_failure_context() -> None:
    """Test the expected behavior."""
    captured_payload: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"run_id": "run-qa-1"})

    async with N8NDispatchClient(
        base_url="http://n8n.local/webhook",
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.dispatch(request=_qa_request(), path="/control-plane/qa-loop")

    assert result.run_id == "run-qa-1"
    assert captured_payload["workflow_type"] == "qa_loop"
    assert captured_payload["attempt_number"] == 2
    assert captured_payload["criteria_items"] == ["criterion a", "criterion b"]
    assert isinstance(captured_payload["prior_failure_context"], list)
    assert len(captured_payload["prior_failure_context"]) == 1


@pytest.mark.asyncio
async def test_dispatch_resume_payload_includes_hitl_fields() -> None:
    """Test the expected behavior."""
    captured_payload: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"run_id": "run-resume-1"})

    request = build_dispatch_request(
        task_id="task-1",
        event_id="evt-1",
        workflow_type="build_spec",
        context_ref="specs/017/spec.md",
        execution_policy="manual-test",
        event="taskCommentPosted",
        resume_run_id="run-paused-1",
        human_input_response="Approved by operator",
        human_input_prompt="Approve deployment?",
    )

    async with N8NDispatchClient(
        base_url="http://n8n.local/webhook",
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.dispatch(request=request, path="/control-plane/build-spec")

    assert result.run_id == "run-resume-1"
    assert captured_payload["resume_run_id"] == "run-paused-1"
    assert captured_payload["human_input_response"] == "Approved by operator"
    assert captured_payload["human_input_prompt"] == "Approve deployment?"


@pytest.mark.asyncio
async def test_cancel_run_posts_cancel_signal_payload() -> None:
    """Test the expected behavior."""
    captured_payload: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(202, json={"accepted": True})

    async with N8NDispatchClient(
        base_url="http://n8n.local/webhook",
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    ) as client:
        await client.cancel_run(
            task_id="task-1",
            run_id="run-1",
            event_id="evt-2",
            reason="manual_status_change",
        )

    assert captured_payload["task_id"] == "task-1"
    assert captured_payload["run_id"] == "run-1"
    assert captured_payload["event_id"] == "evt-2"
    assert captured_payload["reason"] == "manual_status_change"
    assert isinstance(captured_payload["occurred_at_utc"], str)


@pytest.mark.asyncio
async def test_dispatch_timeout_cancels_inflight_request_task() -> None:
    """Test the expected behavior."""
    cancelled = asyncio.Event()

    async def slow_handler(request: httpx.Request) -> httpx.Response:
        try:
            await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return httpx.Response(200, json={"run_id": "late"})

    async with N8NDispatchClient(
        base_url="http://n8n.local/webhook",
        timeout_seconds=0.05,
        transport=httpx.MockTransport(slow_handler),
    ) as client:
        with pytest.raises(DispatchTimeoutError):
            await client.dispatch(request=_request(), path="/control-plane/build-spec")

    await asyncio.wait_for(cancelled.wait(), timeout=1.0)


@pytest.mark.asyncio
async def test_dispatch_cancel_signal_stops_request_and_raises_cancelled() -> None:
    """Test the expected behavior."""
    cancelled = asyncio.Event()
    cancel_event = asyncio.Event()

    async def slow_handler(request: httpx.Request) -> httpx.Response:
        try:
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return httpx.Response(200, json={"run_id": "late"})

    async with N8NDispatchClient(
        base_url="http://n8n.local/webhook",
        timeout_seconds=1.0,
        transport=httpx.MockTransport(slow_handler),
    ) as client:
        async def trigger_cancel() -> None:
            await asyncio.sleep(0.01)
            cancel_event.set()

        cancel_task = asyncio.create_task(trigger_cancel())
        with pytest.raises(DispatchCancelledError):
            await client.dispatch(
                request=_request(),
                path="/control-plane/build-spec",
                cancel_event=cancel_event,
            )
        await cancel_task

    await asyncio.wait_for(cancelled.wait(), timeout=1.0)


@pytest.mark.asyncio
async def test_dispatch_rejected_status_raises_rejected_error() -> None:
    """Test the expected behavior."""
    async def rejected_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"error": "bad gateway"})

    async with N8NDispatchClient(
        base_url="http://n8n.local/webhook",
        timeout_seconds=1.0,
        transport=httpx.MockTransport(rejected_handler),
    ) as client:
        with pytest.raises(DispatchRejectedError):
            await client.dispatch(request=_request(), path="/control-plane/build-spec")


def test_resolve_workflow_path_normalizes_workflow_type_keys() -> None:
    """Test the expected behavior."""
    assert resolve_workflow_path("BUILD-SPEC") == "/control-plane/build-spec"
    assert resolve_workflow_path("qa_loop") == "/control-plane/qa-loop"
    assert resolve_workflow_path("unknown") is None


def test_build_dispatch_request_normalizes_workflow_type_and_sets_timestamp() -> None:
    """Test the expected behavior."""
    request = build_dispatch_request(
        task_id="task-1",
        event_id="evt-1",
        workflow_type="BUILD-SPEC",
        context_ref="specs/015/spec.md",
        execution_policy="strict",
        event="taskStatusUpdated",
    )

    assert request.workflow_type == "build_spec"
    assert request.task_id == "task-1"
    assert request.context_ref == "specs/015/spec.md"
    assert request.execution_policy == "strict"
    assert isinstance(request.occurred_at_utc, str)
    assert request.occurred_at_utc


def test_build_dispatch_request_includes_optional_qa_fields() -> None:
    """Test the expected behavior."""
    request = build_dispatch_request(
        task_id="task-qa-1",
        event_id="evt-qa-1",
        workflow_type="qa_loop",
        context_ref="specs/016/spec.md",
        execution_policy="manual-test",
        event="taskStatusUpdated",
        attempt_number=3,
        criteria_items=("a", "b"),
        prior_failure_context=({"issue_description": "x"},),
    )

    assert request.workflow_type == "qa_loop"
    assert request.attempt_number == 3
    assert request.criteria_items == ("a", "b")
    assert request.prior_failure_context == ({"issue_description": "x"},)
