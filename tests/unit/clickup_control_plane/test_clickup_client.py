"""Test module."""

from __future__ import annotations

from clickup_control_plane.clickup_client import (
    build_decision_outcome,
    build_qa_blocked_escalation_outcome,
    build_qa_fail_to_build_outcome,
    build_qa_pass_outcome,
    render_operator_outcome,
)
from clickup_control_plane.schemas import QaFailureReport


def test_build_decision_outcome_reject_scope_contains_reason_code() -> None:
    """Test the expected behavior."""
    outcome = build_decision_outcome(
        decision="reject_scope",
        reason_code="out_of_scope",
        task_id="task-1",
    )

    rendered = render_operator_outcome(outcome)
    assert outcome.severity == "warning"
    assert "out of allowlisted scope" in outcome.summary
    assert "reason_code=out_of_scope" in rendered


def test_build_decision_outcome_dispatch_includes_run_id() -> None:
    """Test the expected behavior."""
    outcome = build_decision_outcome(
        decision="dispatch",
        reason_code="dispatch_started",
        task_id="task-1",
        workflow_type="build_spec",
        run_id="run-123",
    )

    rendered = render_operator_outcome(outcome)
    assert outcome.severity == "info"
    assert "Workflow dispatch accepted" in outcome.summary
    assert "run_id=run-123" in rendered


def test_build_decision_outcome_input_resumed_mentions_hitl_resume() -> None:
    """Test the expected behavior."""
    outcome = build_decision_outcome(
        decision="input_resumed",
        reason_code="hitl_resumed",
        task_id="task-1",
        workflow_type="build_spec",
        run_id="run-456",
    )
    assert outcome.severity == "info"
    assert "workflow resumed" in outcome.summary.lower()
    assert "reason_code=hitl_resumed" in render_operator_outcome(outcome)


def test_build_decision_outcome_cancelled_by_operator_mentions_manual_status_change() -> None:
    """Test the expected behavior."""
    outcome = build_decision_outcome(
        decision="cancelled_by_operator",
        reason_code="manual_status_change_cancelled",
        task_id="task-1",
        run_id="run-789",
    )
    assert outcome.severity == "warning"
    assert "cancelled by operator" in outcome.summary.lower()
    assert "reason_code=manual_status_change_cancelled" in render_operator_outcome(outcome)


def test_build_qa_pass_outcome_contains_reason_code_and_artifact_links() -> None:
    """Test the expected behavior."""
    outcome = build_qa_pass_outcome(
        task_id="task-1",
        attempt_number=2,
        artifact_links=("https://example.test/a",),
        run_id="run-qa-1",
    )
    rendered = render_operator_outcome(outcome)
    assert outcome.reason_code == "qa_passed"
    assert "QA passed" in outcome.summary
    assert "artifacts=https://example.test/a" in outcome.details
    assert "run_id=run-qa-1" in rendered


def test_build_qa_fail_to_build_outcome_renders_structured_fields() -> None:
    """Test the expected behavior."""
    report = QaFailureReport(
        issue_description="Issue",
        expected_behavior="Expected",
        observed_behavior="Observed",
        reproduction_context="Steps",
        artifact_links=["https://example.test/fail"],
    )
    outcome = build_qa_fail_to_build_outcome(
        task_id="task-1",
        attempt_number=3,
        failure_report=report,
    )
    assert outcome.reason_code == "qa_failed_to_build"
    assert "returned to build" in outcome.summary
    assert "issue_description=Issue" in outcome.details
    assert "artifacts=https://example.test/fail" in outcome.details


def test_build_qa_blocked_escalation_outcome_requires_manual_unblock() -> None:
    """Test the expected behavior."""
    outcome = build_qa_blocked_escalation_outcome(
        task_id="task-1",
        attempt_number=3,
    )
    assert outcome.reason_code == "qa_blocked_after_retries"
    assert "blocked" in outcome.summary.lower()
    assert "Manual unblock is required" in outcome.details
