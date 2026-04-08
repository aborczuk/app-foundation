"""Unit tests for ClickUp control-plane policy evaluation."""

from __future__ import annotations

from clickup_control_plane.config import ScopeAllowlist
from clickup_control_plane.policy import (
    evaluate_dispatch_policy,
    evaluate_qa_dispatch_gate,
    extract_routing_metadata,
)
from clickup_control_plane.schemas import ClickUpWebhookPayload, RoutingMetadata


def _payload(*, list_id: str | None = "list-123", space_id: str | None = None) -> ClickUpWebhookPayload:
    return ClickUpWebhookPayload.model_validate(
        {
            "event": "statusUpdated",
            "task_id": "task-123",
            "list_id": list_id,
            "space_id": space_id,
        }
    )


def test_evaluate_dispatch_policy_accepts_allowlisted_payload_with_complete_metadata() -> None:
    """Test the expected behavior."""
    payload = _payload()
    allowlist = ScopeAllowlist(space_ids=(), list_ids=("list-123",))
    payload_raw = {
        "workflow_type": "build-spec",
        "context_ref": "specs/015-control-plane-dispatch",
        "execution_policy": "strict",
    }

    result = evaluate_dispatch_policy(
        payload=payload,
        payload_raw=payload_raw,
        allowlist=allowlist,
    )

    assert result.decision == "dispatch"
    assert result.reason_code == "eligible_for_dispatch"
    assert result.missing_fields == ()
    assert result.routing_metadata is not None
    assert result.routing_metadata.workflow_type == "build_spec"
    assert result.routing_metadata.context_ref == "specs/015-control-plane-dispatch"
    assert result.routing_metadata.execution_policy == "strict"


def test_evaluate_dispatch_policy_rejects_out_of_scope_payload() -> None:
    """Test the expected behavior."""
    payload = _payload(list_id="list-999")
    allowlist = ScopeAllowlist(space_ids=(), list_ids=("list-123",))
    payload_raw = {
        "workflow_type": "build-spec",
        "context_ref": "specs/015-control-plane-dispatch",
        "execution_policy": "strict",
    }

    result = evaluate_dispatch_policy(
        payload=payload,
        payload_raw=payload_raw,
        allowlist=allowlist,
    )

    assert result.decision == "reject_scope"
    assert result.reason_code == "out_of_scope"
    assert result.missing_fields == ()
    assert result.routing_metadata is None


def test_evaluate_dispatch_policy_rejects_missing_metadata_and_reports_missing_fields() -> None:
    """Test the expected behavior."""
    payload = _payload()
    allowlist = ScopeAllowlist(space_ids=(), list_ids=("list-123",))
    payload_raw = {
        "workflow_type": "build-spec",
    }

    result = evaluate_dispatch_policy(
        payload=payload,
        payload_raw=payload_raw,
        allowlist=allowlist,
    )

    assert result.decision == "reject_missing_metadata"
    assert result.reason_code == "missing_metadata"
    assert result.missing_fields == ("context_ref", "execution_policy")
    assert result.routing_metadata is None


def test_extract_routing_metadata_supports_nested_routing_block_and_camel_case_keys() -> None:
    """Test the expected behavior."""
    payload_raw: dict[str, object] = {
        "routing": {
            "workflowType": "qa-loop",
            "contextRef": "specs/015-control-plane-dispatch",
            "executionPolicy": "strict",
        }
    }

    metadata, missing = extract_routing_metadata(payload_raw=payload_raw)

    assert missing == ()
    assert metadata == RoutingMetadata(
        workflow_type="qa_loop",
        context_ref="specs/015-control-plane-dispatch",
        execution_policy="strict",
    )


def test_extract_routing_metadata_supports_nested_metadata_block_and_snake_case_keys() -> None:
    """Test the expected behavior."""
    payload_raw: dict[str, object] = {
        "metadata": {
            "workflow_type": "build-spec",
            "context_ref": "specs/015-control-plane-dispatch",
            "execution_policy": "strict",
        }
    }

    metadata, missing = extract_routing_metadata(payload_raw=payload_raw)

    assert missing == ()
    assert metadata == RoutingMetadata(
        workflow_type="build_spec",
        context_ref="specs/015-control-plane-dispatch",
        execution_policy="strict",
    )


def test_evaluate_qa_dispatch_gate_rejects_when_criteria_missing() -> None:
    """Test the expected behavior."""
    result = evaluate_qa_dispatch_gate(payload_raw={})
    assert result.decision == "missing_criteria"
    assert result.reason_code == "missing_criteria"
    assert result.criteria_items == ()


def test_evaluate_qa_dispatch_gate_rejects_when_blocked_state_present() -> None:
    """Test the expected behavior."""
    result = evaluate_qa_dispatch_gate(
        payload_raw={
            "qa_state": "blocked_human_required",
            "acceptance_criteria": ["criterion"],
        }
    )
    assert result.decision == "qa_unblock_required"
    assert result.reason_code == "qa_unblock_required"
    assert result.criteria_items == ()


def test_evaluate_qa_dispatch_gate_accepts_when_criteria_present() -> None:
    """Test the expected behavior."""
    result = evaluate_qa_dispatch_gate(
        payload_raw={
            "acceptance_criteria": ["criterion one", "criterion two"],
        }
    )
    assert result.decision == "dispatch"
    assert result.reason_code == "eligible_for_dispatch"
    assert result.criteria_items == ("criterion one", "criterion two")
