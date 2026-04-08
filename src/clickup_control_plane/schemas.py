"""Pydantic schemas for ClickUp webhook normalization and dispatch decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

WebhookDecision = Literal[
    "dispatch",
    "input_resumed",
    "cancelled_by_operator",
    "qa_passed",
    "qa_failed_to_build",
    "qa_blocked_after_retries",
    "skip_duplicate",
    "stale_event",
    "reject_active_run",
    "reject_scope",
    "action_scope_violation",
    "reject_missing_metadata",
    "reject_signature",
    "schema_mismatch",
    "dispatch_failed",
    "missing_criteria",
    "qa_unblock_required",
]
WorkflowCompletionStatus = Literal[
    "completed",
    "failed",
    "waiting_input",
    "timed_out",
    "cancelled",
]
QaWorkflowResult = Literal["pass", "fail"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ClickUpHistoryItem(BaseModel):
    """Single ClickUp history entry used to infer status transitions."""

    model_config = ConfigDict(extra="ignore")

    field: str | None = None
    before: str | None = None
    after: str | None = None


class ClickUpWebhookPayload(BaseModel):
    """Inbound webhook payload contract accepted from ClickUp."""

    model_config = ConfigDict(extra="allow")

    event: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    history_items: list[ClickUpHistoryItem] = Field(default_factory=list)
    space_id: str | None = None
    list_id: str | None = None
    occurred_at_utc: datetime | None = None

    def to_normalized_event(
        self,
        *,
        event_id: str,
        received_at_utc: datetime | None = None,
    ) -> "ClickUpWebhookEvent":
        """Convert raw payload into normalized event shape used by service layers."""
        status_before, status_after = _derive_status_transition(self.history_items)
        occurred_at = self.occurred_at_utc or received_at_utc or utc_now()
        return ClickUpWebhookEvent(
            event_id=event_id,
            task_id=self.task_id,
            list_id=self.list_id,
            space_id=self.space_id,
            status_before=status_before,
            status_after=status_after or "unknown",
            occurred_at_utc=occurred_at,
            raw_payload=self.model_dump(mode="json"),
        )


class ClickUpWebhookEvent(BaseModel):
    """Normalized event entity used across policy/state/dispatch layers."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    list_id: str | None = None
    space_id: str | None = None
    status_before: str | None = None
    status_after: str = Field(min_length=1)
    occurred_at_utc: datetime = Field(default_factory=utc_now)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class RoutingMetadata(BaseModel):
    """Task metadata required to route to an n8n workflow."""

    model_config = ConfigDict(extra="ignore")

    workflow_type: str = Field(min_length=1)
    context_ref: str = Field(min_length=1)
    execution_policy: str = Field(min_length=1)


class DispatchDecision(BaseModel):
    """Terminal decision state for a single webhook event."""

    model_config = ConfigDict(extra="forbid")

    decision: WebhookDecision
    reason_code: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    operator_message: str = Field(min_length=1)
    n8n_workflow_id: str | None = None
    created_at_utc: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_dispatch_fields(self) -> "DispatchDecision":
        """Enforce workflow ID presence when a decision is dispatch."""
        if self.decision == "dispatch" and not self.n8n_workflow_id:
            raise ValueError("n8n_workflow_id is required when decision='dispatch'.")
        return self


class WebhookAcceptedResponse(BaseModel):
    """Success/accepted envelope returned by webhook endpoint."""

    accepted: Literal[True] = True
    event_id: str = Field(min_length=1)
    decision: WebhookDecision


class WebhookErrorDetail(BaseModel):
    """Sanitized error envelope payload."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    action: str = Field(min_length=1)


class WebhookErrorResponse(BaseModel):
    """Top-level webhook error response body."""

    error: WebhookErrorDetail


class WorkflowCompletionPayload(BaseModel):
    """Completion payload accepted from automation runners."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    workflow_type: str = Field(min_length=1)
    status: WorkflowCompletionStatus
    summary: str = Field(min_length=1)
    details: str | None = None
    context_ref: str | None = None
    execution_policy: str | None = None
    run_id: str | None = None
    artifact_links: list[str] = Field(default_factory=list)
    human_input_request: "HumanInputRequest | None" = None

    @model_validator(mode="after")
    def validate_waiting_input_contract(self) -> "WorkflowCompletionPayload":
        """Require a structured HITL request for waiting_input lifecycle updates."""
        if self.status == "waiting_input" and self.human_input_request is None:
            raise ValueError("human_input_request is required when status='waiting_input'.")
        return self


class WorkflowCompletionAcceptedResponse(BaseModel):
    """Success/accepted envelope returned by completion callback endpoint."""

    accepted: Literal[True] = True
    task_id: str = Field(min_length=1)
    status: WorkflowCompletionStatus


class HumanInputRequest(BaseModel):
    """Structured HITL request payload emitted when automation pauses for operator input."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    response_format: str = Field(default="text", min_length=1)
    timeout_at_utc: datetime | None = None


class QaFailureReport(BaseModel):
    """Structured QA failure report written to ClickUp on QA fail outcomes."""

    model_config = ConfigDict(extra="forbid")

    issue_description: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    observed_behavior: str = Field(min_length=1)
    reproduction_context: str = Field(min_length=1)
    artifact_links: list[str] = Field(default_factory=list)


class QaDispatchPayload(BaseModel):
    """Dispatch payload contract for QA-loop workflow trigger requests."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    criteria_items: list[str] = Field(min_length=1)
    prior_failure_context: list[QaFailureReport] = Field(default_factory=list)


class QaWorkflowResultPayload(BaseModel):
    """Response payload contract expected from QA-loop workflow execution."""

    model_config = ConfigDict(extra="forbid")

    result: QaWorkflowResult
    artifact_links: list[str] = Field(default_factory=list)
    failure_report: QaFailureReport | None = None

    @model_validator(mode="after")
    def validate_failure_report_requirement(self) -> "QaWorkflowResultPayload":
        """Require structured failure report details whenever result is fail."""
        if self.result == "fail" and self.failure_report is None:
            raise ValueError("failure_report is required when result='fail'.")
        if self.result == "pass" and self.failure_report is not None:
            raise ValueError("failure_report must be omitted when result='pass'.")
        return self


def _derive_status_transition(history_items: list[ClickUpHistoryItem]) -> tuple[str | None, str | None]:
    for item in history_items:
        if not item.field:
            continue
        field_name = item.field.strip().lower()
        if field_name in {"status", "task_status"}:
            return item.before, item.after
    return None, None


__all__ = [
    "ClickUpHistoryItem",
    "ClickUpWebhookPayload",
    "ClickUpWebhookEvent",
    "RoutingMetadata",
    "DispatchDecision",
    "WebhookAcceptedResponse",
    "WebhookErrorDetail",
    "WebhookErrorResponse",
    "WebhookDecision",
    "WorkflowCompletionAcceptedResponse",
    "WorkflowCompletionPayload",
    "WorkflowCompletionStatus",
    "QaDispatchPayload",
    "QaFailureReport",
    "QaWorkflowResult",
    "QaWorkflowResultPayload",
    "HumanInputRequest",
]
