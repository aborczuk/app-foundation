"""Contract tests for ClickUp control-plane webhook intake."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import httpx
from fastapi.testclient import TestClient

from clickup_control_plane.app import create_app
from clickup_control_plane.config import ControlPlaneRuntimeConfig, ScopeAllowlist
from clickup_control_plane.webhook_auth import build_expected_signature


def _runtime_config(tmp_path: Path) -> ControlPlaneRuntimeConfig:
    return ControlPlaneRuntimeConfig(
        clickup_api_token="clickup-token",
        clickup_webhook_secret="webhook-secret",
        n8n_dispatch_base_url="http://n8n.local",
        control_plane_db_path=tmp_path / "control-plane.db",
        allowlist=ScopeAllowlist(space_ids=(), list_ids=("list-123",)),
        request_timeout_seconds=0.5,
    )


def _canonical_body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _valid_payload() -> dict[str, Any]:
    return {
        "event": "taskStatusUpdated",
        "task_id": "task-123",
        "list_id": "list-123",
        "space_id": "space-456",
        "workflow_type": "build_spec",
        "context_ref": "specs/015-control-plane-dispatch/spec.md",
        "execution_policy": "strict",
        "history_items": [
            {
                "field": "status",
                "before": "ready",
                "after": "in progress",
            }
        ],
    }


def _valid_qa_payload() -> dict[str, Any]:
    payload = _valid_payload()
    payload["workflow_type"] = "qa_loop"
    payload["acceptance_criteria"] = ["criterion one", "criterion two"]
    return payload


def _install_runtime_mocks(
    monkeypatch,
    *,
    config: ControlPlaneRuntimeConfig,
    dispatch_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    original_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(dispatch_handler)

    def _async_client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        kwargs.pop("timeout", None)
        return original_async_client(*args, transport=transport, **kwargs)

    import clickup_control_plane.app as app_module
    import clickup_control_plane.clickup_client as clickup_client_module
    import clickup_control_plane.dispatcher as dispatcher_module

    monkeypatch.setattr(app_module, "get_runtime_config", lambda: config)
    monkeypatch.setattr(app_module.httpx, "AsyncClient", _async_client_factory)
    monkeypatch.setattr(clickup_client_module.httpx, "AsyncClient", _async_client_factory)
    monkeypatch.setattr(dispatcher_module.httpx, "AsyncClient", _async_client_factory)


def test_webhook_accepts_valid_in_scope_event_and_returns_dispatch_envelope(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Test the expected behavior."""
    payload = _valid_payload()
    body = _canonical_body(payload)
    signature = build_expected_signature("webhook-secret", body)
    config = _runtime_config(tmp_path)
    dispatch_requests: list[dict[str, Any]] = []
    clickup_comment_requests: list[dict[str, Any]] = []

    def dispatch_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/comment"):
            clickup_comment_requests.append(
                {
                    "path": path,
                    "json": json.loads(request.content.decode("utf-8")),
                }
            )
            return httpx.Response(200, json={"id": "comment-1"})

        dispatch_requests.append(
            {
                "path": path,
                "json": json.loads(request.content.decode("utf-8")),
            }
        )
        return httpx.Response(200, json={"run_id": "run-1"})

    _install_runtime_mocks(
        monkeypatch,
        config=config,
        dispatch_handler=dispatch_handler,
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/control-plane/clickup/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature,
            },
        )

    expected_event_id = f"evt_{hashlib.sha256(body).hexdigest()[:24]}"
    assert response.status_code == 202
    assert response.json() == {
        "accepted": True,
        "event_id": expected_event_id,
        "decision": "dispatch",
    }
    assert len(dispatch_requests) == 1
    request_payload = dispatch_requests[0]
    assert request_payload["path"] == "/control-plane/build-spec"
    assert request_payload["json"]["task_id"] == "task-123"
    assert request_payload["json"]["event_id"] == expected_event_id
    assert request_payload["json"]["workflow_type"] == "build_spec"
    assert request_payload["json"]["context_ref"] == "specs/015-control-plane-dispatch/spec.md"
    assert request_payload["json"]["execution_policy"] == "strict"
    assert request_payload["json"]["event"] == "taskStatusUpdated"
    assert isinstance(request_payload["json"]["occurred_at_utc"], str)
    assert request_payload["json"]["occurred_at_utc"]
    assert len(clickup_comment_requests) == 1
    assert clickup_comment_requests[0]["path"].endswith("/task/task-123/comment")


def test_webhook_rejects_invalid_signature_with_error_envelope(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Test the expected behavior."""
    payload = _valid_payload()
    body = _canonical_body(payload)
    config = _runtime_config(tmp_path)

    def dispatch_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"run_id": "unused"})

    _install_runtime_mocks(
        monkeypatch,
        config=config,
        dispatch_handler=dispatch_handler,
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/control-plane/clickup/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": "invalid-signature",
            },
        )

    payload = response.json()
    assert response.status_code == 401
    assert set(payload.keys()) == {"error"}
    assert set(payload["error"].keys()) == {"code", "message", "action"}
    assert payload["error"]["code"] == "invalid_signature"
    assert payload["error"]["message"]
    assert payload["error"]["action"]


def test_completion_callback_accepts_valid_payload_and_writes_outcome(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Test the expected behavior."""
    config = replace(_runtime_config(tmp_path), completion_callback_token="completion-secret")
    clickup_comment_requests: list[dict[str, Any]] = []

    def dispatch_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/comment"):
            clickup_comment_requests.append(
                {
                    "path": request.url.path,
                    "json": json.loads(request.content.decode("utf-8")),
                }
            )
            return httpx.Response(200, json={"id": "comment-2"})
        return httpx.Response(200, json={"run_id": "run-unused"})

    _install_runtime_mocks(
        monkeypatch,
        config=config,
        dispatch_handler=dispatch_handler,
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/control-plane/workflow/completion",
            json={
                "task_id": "task-123",
                "workflow_type": "build_spec",
                "status": "completed",
                "summary": "Codex run finished.",
                "details": "Updated 2 files and added tests.",
                "run_id": "run-123",
                "artifact_links": ["https://example.local/artifact/1"],
            },
            headers={
                "Content-Type": "application/json",
                "X-Completion-Token": "completion-secret",
            },
        )

    assert response.status_code == 202
    assert response.json() == {
        "accepted": True,
        "task_id": "task-123",
        "status": "completed",
    }
    assert len(clickup_comment_requests) == 1
    assert clickup_comment_requests[0]["path"].endswith("/task/task-123/comment")
    comment_text = clickup_comment_requests[0]["json"]["comment_text"]
    assert "workflow 'build_spec' completed" in comment_text.lower()
    assert "artifacts=https://example.local/artifact/1" in comment_text


def test_completion_callback_rejects_invalid_token(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Test the expected behavior."""
    config = replace(_runtime_config(tmp_path), completion_callback_token="expected-token")

    def dispatch_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/comment"):
            return httpx.Response(200, json={"id": "comment-unexpected"})
        return httpx.Response(200, json={"run_id": "run-unused"})

    _install_runtime_mocks(
        monkeypatch,
        config=config,
        dispatch_handler=dispatch_handler,
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/control-plane/workflow/completion",
            json={
                "task_id": "task-123",
                "workflow_type": "build_spec",
                "status": "failed",
                "summary": "Codex run failed.",
            },
            headers={
                "Content-Type": "application/json",
                "X-Completion-Token": "wrong-token",
            },
        )

    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "invalid_completion_token"


def test_completion_callback_accepts_waiting_input_payload_and_returns_envelope(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Test the expected behavior."""
    config = replace(_runtime_config(tmp_path), completion_callback_token="completion-secret")

    def dispatch_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/comment"):
            return httpx.Response(200, json={"id": "comment-waiting"})
        if request.method.upper() == "PUT" and "/task/" in request.url.path:
            return httpx.Response(200, json={"id": "status-waiting"})
        return httpx.Response(200, json={"run_id": "run-unused"})

    _install_runtime_mocks(
        monkeypatch,
        config=config,
        dispatch_handler=dispatch_handler,
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/control-plane/workflow/completion",
            json={
                "task_id": "task-123",
                "workflow_type": "build_spec",
                "status": "waiting_input",
                "summary": "Need human approval.",
                "run_id": "run-123",
                "context_ref": "specs/017-control-plane-hitl-audit/spec.md",
                "execution_policy": "manual-test",
                "human_input_request": {
                    "prompt": "Approve deployment?",
                    "response_format": "yes_no",
                },
            },
            headers={
                "Content-Type": "application/json",
                "X-Completion-Token": "completion-secret",
            },
        )

    assert response.status_code == 202
    assert response.json() == {
        "accepted": True,
        "task_id": "task-123",
        "status": "waiting_input",
    }


def test_completion_callback_rejects_waiting_input_without_structured_request(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Test the expected behavior."""
    config = replace(_runtime_config(tmp_path), completion_callback_token="completion-secret")

    def dispatch_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"run_id": "run-unused"})

    _install_runtime_mocks(
        monkeypatch,
        config=config,
        dispatch_handler=dispatch_handler,
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/control-plane/workflow/completion",
            json={
                "task_id": "task-123",
                "workflow_type": "build_spec",
                "status": "waiting_input",
                "summary": "Need human approval.",
                "run_id": "run-123",
            },
            headers={
                "Content-Type": "application/json",
                "X-Completion-Token": "completion-secret",
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_payload"


def test_qa_webhook_pass_returns_qa_passed_envelope(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Test the expected behavior."""
    payload = _valid_qa_payload()
    body = _canonical_body(payload)
    signature = build_expected_signature("webhook-secret", body)
    config = _runtime_config(tmp_path)
    dispatch_requests: list[dict[str, Any]] = []

    def dispatch_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/comment"):
            return httpx.Response(200, json={"id": "comment-qa-pass"})
        if request.method.upper() == "PUT" and "/task/" in request.url.path:
            return httpx.Response(200, json={"id": "task-update-qa-pass"})
        dispatch_requests.append(
            {
                "path": request.url.path,
                "json": json.loads(request.content.decode("utf-8")),
            }
        )
        return httpx.Response(
            200,
            json={"result": "pass", "artifact_links": ["https://example.local/qa/pass"]},
        )

    _install_runtime_mocks(
        monkeypatch,
        config=config,
        dispatch_handler=dispatch_handler,
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/control-plane/clickup/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature,
            },
        )

    assert response.status_code == 202
    assert response.json()["decision"] == "qa_passed"
    assert len(dispatch_requests) == 1
    assert dispatch_requests[0]["path"] == "/control-plane/qa-loop"
    assert dispatch_requests[0]["json"]["attempt_number"] == 1
    assert dispatch_requests[0]["json"]["criteria_items"] == ["criterion one", "criterion two"]


def test_qa_webhook_fail_below_threshold_returns_rework_envelope(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Test the expected behavior."""
    payload = _valid_qa_payload()
    payload["qa_consecutive_failures"] = 1
    body = _canonical_body(payload)
    signature = build_expected_signature("webhook-secret", body)
    config = _runtime_config(tmp_path)

    def dispatch_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/comment"):
            return httpx.Response(200, json={"id": "comment-qa-fail"})
        if request.method.upper() == "PUT" and "/task/" in request.url.path:
            return httpx.Response(200, json={"id": "task-update-qa-fail"})
        return httpx.Response(
            200,
            json={
                "result": "fail",
                "failure_report": {
                    "issue_description": "Issue",
                    "expected_behavior": "Expected",
                    "observed_behavior": "Observed",
                    "reproduction_context": "Steps",
                },
            },
        )

    _install_runtime_mocks(
        monkeypatch,
        config=config,
        dispatch_handler=dispatch_handler,
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/control-plane/clickup/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature,
            },
        )

    assert response.status_code == 202
    assert response.json()["decision"] == "qa_failed_to_build"


def test_qa_webhook_third_fail_returns_blocked_envelope(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Test the expected behavior."""
    payload = _valid_qa_payload()
    payload["qa_consecutive_failures"] = 2
    body = _canonical_body(payload)
    signature = build_expected_signature("webhook-secret", body)
    config = _runtime_config(tmp_path)

    def dispatch_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/comment"):
            return httpx.Response(200, json={"id": "comment-qa-block"})
        if request.method.upper() == "PUT" and "/task/" in request.url.path:
            return httpx.Response(200, json={"id": "task-update-qa-block"})
        return httpx.Response(
            200,
            json={
                "result": "fail",
                "failure_report": {
                    "issue_description": "Issue",
                    "expected_behavior": "Expected",
                    "observed_behavior": "Observed",
                    "reproduction_context": "Steps",
                },
            },
        )

    _install_runtime_mocks(
        monkeypatch,
        config=config,
        dispatch_handler=dispatch_handler,
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/control-plane/clickup/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature,
            },
        )

    assert response.status_code == 202
    assert response.json()["decision"] == "qa_blocked_after_retries"
