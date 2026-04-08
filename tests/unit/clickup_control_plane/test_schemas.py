"""Unit tests for Phase 2 QA-loop schema contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from clickup_control_plane.schemas import (
    QaFailureReport,
    QaWorkflowResultPayload,
    WorkflowCompletionPayload,
)


def test_qa_workflow_result_payload_requires_failure_report_for_fail() -> None:
    """Test the expected behavior."""
    with pytest.raises(ValidationError, match="failure_report is required"):
        QaWorkflowResultPayload.model_validate({"result": "fail"})


def test_qa_workflow_result_payload_rejects_failure_report_for_pass() -> None:
    """Test the expected behavior."""
    with pytest.raises(ValidationError, match="failure_report must be omitted"):
        QaWorkflowResultPayload.model_validate(
            {
                "result": "pass",
                "failure_report": {
                    "issue_description": "Issue",
                    "expected_behavior": "Expected",
                    "observed_behavior": "Observed",
                    "reproduction_context": "Steps",
                },
            }
        )


def test_qa_workflow_result_payload_accepts_pass_without_report() -> None:
    """Test the expected behavior."""
    payload = QaWorkflowResultPayload.model_validate(
        {
            "result": "pass",
            "artifact_links": ["https://example.test/report"],
        }
    )
    assert payload.result == "pass"
    assert payload.failure_report is None
    assert payload.artifact_links == ["https://example.test/report"]


def test_qa_failure_report_requires_all_narrative_fields() -> None:
    """Test the expected behavior."""
    report = QaFailureReport.model_validate(
        {
            "issue_description": "Issue",
            "expected_behavior": "Expected",
            "observed_behavior": "Observed",
            "reproduction_context": "Steps",
        }
    )
    assert report.issue_description == "Issue"


def test_workflow_completion_waiting_input_requires_human_input_request() -> None:
    """Test the expected behavior."""
    with pytest.raises(ValidationError, match="human_input_request is required"):
        WorkflowCompletionPayload.model_validate(
            {
                "task_id": "task-1",
                "workflow_type": "build_spec",
                "status": "waiting_input",
                "summary": "Need input.",
                "run_id": "run-1",
            }
        )


def test_workflow_completion_waiting_input_accepts_structured_request() -> None:
    """Test the expected behavior."""
    payload = WorkflowCompletionPayload.model_validate(
        {
            "task_id": "task-1",
            "workflow_type": "build_spec",
            "status": "waiting_input",
            "summary": "Need input.",
            "run_id": "run-1",
            "human_input_request": {
                "prompt": "Approve deployment?",
                "response_format": "yes_no",
                "timeout_at_utc": "2026-04-04T15:00:00Z",
            },
        }
    )
    assert payload.status == "waiting_input"
    assert payload.human_input_request is not None
    assert payload.human_input_request.prompt == "Approve deployment?"
