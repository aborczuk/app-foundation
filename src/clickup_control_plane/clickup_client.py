"""ClickUp outcome writer with operator-safe redaction and typed error mapping."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from .schemas import QaFailureReport, WebhookDecision

OutcomeSeverity = Literal["info", "warning", "error"]

_DEFAULT_BASE_URL = "https://api.clickup.com/api/v2"
_DEFAULT_TIMEOUT_SECONDS = 10.0
_MAX_TEXT_LEN = 700

_TOKEN_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)(token=)[^\s&]+"),
    re.compile(r"(?i)(authorization:\s*)[^\s]+"),
)

logger = logging.getLogger(__name__)


class ClickUpError(Exception):
    """Base class for ClickUp client failures."""


class ClickUpAuthError(ClickUpError):
    """Raised for authentication failures."""


class ClickUpNotFoundError(ClickUpError):
    """Raised when referenced ClickUp resources are missing."""


class ClickUpRateLimitError(ClickUpError):
    """Raised when ClickUp API rate limits the request."""


class ClickUpSchemaMismatchError(ClickUpError):
    """Raised when outcome writes target unknown/invalid schema fields."""


class ClickUpAPIError(ClickUpError):
    """Raised for transient/unexpected API failures."""


@dataclass(frozen=True)
class TaskOutcomePayload:
    """Operator-visible outcome content written back to a ClickUp task."""

    severity: OutcomeSeverity
    summary: str
    details: str
    reason_code: str
    run_id: str | None = None


class ClickUpOutcomeClient:
    """Async client for posting redacted outcome records to ClickUp tasks."""

    def __init__(
        self,
        *,
        api_token: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | httpx.MockTransport | None = None,
    ) -> None:
        """Initialize client config and validate immutable authentication settings."""
        token = api_token.strip()
        if not token:
            raise ClickUpAuthError("ClickUp API token cannot be blank.")
        self._api_token = token
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> ClickUpOutcomeClient:
        """Open the underlying async HTTP client for API calls."""
        kwargs: dict[str, Any] = {"timeout": self._timeout_seconds}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        self._client = httpx.AsyncClient(**kwargs)
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Close the underlying async HTTP client and clear local handle."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def write_task_outcome(
        self,
        *,
        task_id: str,
        outcome: TaskOutcomePayload,
    ) -> None:
        """Write a structured outcome comment to a ClickUp task."""
        task = task_id.strip()
        if not task:
            raise ClickUpAPIError("task_id cannot be blank.")
        body = {"comment_text": render_operator_outcome(outcome)}
        await self._request("POST", f"/task/{task}/comment", json=body)

    async def set_task_status(self, *, task_id: str, status_name: str) -> None:
        """Set task status by status name via ClickUp task update API."""
        task = task_id.strip()
        if not task:
            raise ClickUpAPIError("task_id cannot be blank.")
        status_value = status_name.strip()
        if not status_value:
            raise ClickUpAPIError("status_name cannot be blank.")
        await self._request("PUT", f"/task/{task}", json={"status": status_value})

    async def write_decision_outcome(
        self,
        *,
        task_id: str,
        decision: WebhookDecision,
        reason_code: str,
        workflow_type: str | None = None,
        run_id: str | None = None,
        missing_fields: tuple[str, ...] = (),
    ) -> None:
        """Render and persist a decision-specific operator outcome comment."""
        outcome = build_decision_outcome(
            decision=decision,
            reason_code=reason_code,
            task_id=task_id,
            workflow_type=workflow_type,
            run_id=run_id,
            missing_fields=missing_fields,
        )
        await self.write_task_outcome(task_id=task_id, outcome=outcome)

    async def write_qa_pass_outcome(
        self,
        *,
        task_id: str,
        attempt_number: int,
        artifact_links: tuple[str, ...] = (),
        run_id: str | None = None,
    ) -> None:
        """Write QA pass outcome message to ClickUp."""
        outcome = build_qa_pass_outcome(
            task_id=task_id,
            attempt_number=attempt_number,
            artifact_links=artifact_links,
            run_id=run_id,
        )
        await self.write_task_outcome(task_id=task_id, outcome=outcome)

    async def write_qa_fail_to_build_outcome(
        self,
        *,
        task_id: str,
        attempt_number: int,
        failure_report: QaFailureReport,
        run_id: str | None = None,
    ) -> None:
        """Write QA fail outcome (with rework route) to ClickUp."""
        outcome = build_qa_fail_to_build_outcome(
            task_id=task_id,
            attempt_number=attempt_number,
            failure_report=failure_report,
            run_id=run_id,
        )
        await self.write_task_outcome(task_id=task_id, outcome=outcome)

    async def write_qa_blocked_escalation_outcome(
        self,
        *,
        task_id: str,
        attempt_number: int,
        failure_report: QaFailureReport | None = None,
        run_id: str | None = None,
    ) -> None:
        """Write QA blocked-escalation outcome requiring human unblock."""
        outcome = build_qa_blocked_escalation_outcome(
            task_id=task_id,
            attempt_number=attempt_number,
            failure_report=failure_report,
            run_id=run_id,
        )
        await self.write_task_outcome(task_id=task_id, outcome=outcome)

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if self._client is None:
            raise ClickUpAPIError("Use 'async with ClickUpOutcomeClient(...)' before requests.")

        try:
            response = await self._client.request(
                method,
                f"{self._base_url}{path}",
                headers={
                    "Authorization": self._api_token,
                    "Content-Type": "application/json",
                },
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise ClickUpAPIError("ClickUp API request timed out.") from exc
        except httpx.RequestError as exc:
            raise ClickUpAPIError(f"ClickUp API request failed: {type(exc).__name__}") from exc

        self._raise_for_status(response)
        if not response.content:
            return {}
        try:
            parsed = response.json()
        except ValueError:
            return {}
        if isinstance(parsed, dict):
            return parsed
        return {}

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status_code = response.status_code
        if status_code < 300:
            return

        body_text = response.text or ""
        body_lower = body_text.lower()

        if status_code == 401:
            raise ClickUpAuthError("ClickUp authentication failed.")
        if status_code == 404:
            raise ClickUpNotFoundError("ClickUp task/resource not found.")
        if status_code == 429:
            raise ClickUpRateLimitError("ClickUp API rate limit exceeded.")
        if status_code == 400 and ("field" in body_lower or "status" in body_lower or "schema" in body_lower):
            raise ClickUpSchemaMismatchError("ClickUp schema mismatch detected while writing outcome.")
        if status_code >= 500:
            raise ClickUpAPIError(f"ClickUp server error ({status_code}).")

        raise ClickUpAPIError(f"ClickUp API returned unexpected status {status_code}.")


def render_operator_outcome(outcome: TaskOutcomePayload) -> str:
    """Render operator-visible outcome text with mandatory redaction."""
    summary = _sanitize_text(outcome.summary)
    details = _sanitize_text(outcome.details)
    reason_code = _sanitize_text(outcome.reason_code)

    lines = [
        f"[{outcome.severity.upper()}] {summary}",
        details,
        f"reason_code={reason_code}",
    ]
    if outcome.run_id:
        lines.append(f"run_id={_sanitize_text(outcome.run_id)}")

    rendered = "\n".join(line for line in lines if line)
    logger.debug("Rendered ClickUp outcome message with severity=%s", outcome.severity)
    return rendered


def build_decision_outcome(
    *,
    decision: WebhookDecision,
    reason_code: str,
    task_id: str,
    workflow_type: str | None = None,
    run_id: str | None = None,
    missing_fields: tuple[str, ...] = (),
) -> TaskOutcomePayload:
    """Build standardized operator-safe outcome templates for terminal decisions."""
    clean_reason = _sanitize_text(reason_code)
    clean_task = _sanitize_text(task_id)
    clean_workflow = _sanitize_text(workflow_type) if workflow_type else "unknown"

    if decision == "dispatch":
        return TaskOutcomePayload(
            severity="info",
            summary=f"Workflow dispatch accepted for task {clean_task}.",
            details=(
                f"Triggered workflow '{clean_workflow}'. lifecycle=queued->running. "
                "Monitor task activity in ClickUp for downstream run updates."
            ),
            reason_code=clean_reason,
            run_id=run_id,
        )

    if decision == "input_resumed":
        return TaskOutcomePayload(
            severity="info",
            summary=f"HITL response accepted for task {clean_task}; workflow resumed.",
            details=(
                f"Resumed workflow '{clean_workflow}' from waiting-for-input state "
                "using operator-provided response."
            ),
            reason_code=clean_reason,
            run_id=run_id,
        )

    if decision == "cancelled_by_operator":
        return TaskOutcomePayload(
            severity="warning",
            summary=f"Active workflow cancelled by operator action on task {clean_task}.",
            details=(
                "Manual status transition moved the task out of workflow-controlled states. "
                "Cancellation signal was sent and active run lock was released."
            ),
            reason_code=clean_reason,
            run_id=run_id,
        )

    if decision == "reject_scope":
        return TaskOutcomePayload(
            severity="warning",
            summary=f"Dispatch skipped for task {clean_task}: out of allowlisted scope.",
            details=(
                "Move this task into an allowlisted list/space or update allowlist configuration "
                "before retrying."
            ),
            reason_code=clean_reason,
        )

    if decision == "reject_missing_metadata":
        missing_clause = ""
        if missing_fields:
            fields = ", ".join(_sanitize_text(field) for field in missing_fields)
            missing_clause = f" Missing fields: {fields}."
        return TaskOutcomePayload(
            severity="warning",
            summary=f"Dispatch blocked for task {clean_task}: routing metadata is incomplete.",
            details=(
                "Populate workflow_type, context_ref, and execution_policy on the task before retrying."
                f"{missing_clause}"
            ),
            reason_code=clean_reason,
        )

    if decision == "reject_active_run":
        return TaskOutcomePayload(
            severity="warning",
            summary=f"Dispatch skipped for task {clean_task}: another workflow run is active.",
            details=(
                "Wait for the active run to complete or clear stale run state before triggering again."
            ),
            reason_code=clean_reason,
        )

    if decision == "dispatch_failed":
        return TaskOutcomePayload(
            severity="error",
            summary=f"Dispatch failed for task {clean_task}.",
            details=(
                "n8n did not accept the trigger request. Verify n8n availability and workflow route "
                "configuration, then retry."
            ),
            reason_code=clean_reason,
        )

    if decision == "schema_mismatch":
        return TaskOutcomePayload(
            severity="error",
            summary=f"Task {clean_task} is blocked due to schema mismatch.",
            details=(
                "A target ClickUp schema field/status is missing or invalid. Update workspace schema "
                "or workflow mapping before retrying."
            ),
            reason_code=clean_reason,
            run_id=run_id,
        )

    if decision == "stale_event":
        return TaskOutcomePayload(
            severity="warning",
            summary=f"Stale event ignored for task {clean_task}.",
            details="This webhook event predates the latest processed transition and was not dispatched.",
            reason_code=clean_reason,
        )

    if decision == "action_scope_violation":
        return TaskOutcomePayload(
            severity="warning",
            summary=f"Dispatch rejected for task {clean_task}: action scope violation.",
            details=(
                "Requested behavior exceeds configured action scope for this task type. Adjust metadata "
                "or policy before retrying."
            ),
            reason_code=clean_reason,
        )

    if decision == "missing_criteria":
        return TaskOutcomePayload(
            severity="warning",
            summary=f"QA dispatch blocked for task {clean_task}: acceptance criteria missing.",
            details=(
                "Add explicit acceptance criteria on the task before retrying QA automation."
            ),
            reason_code=clean_reason,
        )

    if decision == "qa_unblock_required":
        return TaskOutcomePayload(
            severity="warning",
            summary=f"QA dispatch blocked for task {clean_task}: manual unblock required.",
            details=(
                "Task is in blocked_human_required state. Perform explicit human unblock "
                "before retrying QA automation."
            ),
            reason_code=clean_reason,
        )

    if decision == "reject_signature":
        return TaskOutcomePayload(
            severity="error",
            summary=f"Webhook signature rejected for task {clean_task}.",
            details="Verify ClickUp webhook secret and signature forwarding configuration.",
            reason_code=clean_reason,
        )

    if decision == "skip_duplicate":
        return TaskOutcomePayload(
            severity="info",
            summary=f"Duplicate webhook ignored for task {clean_task}.",
            details="This event was already processed; no additional dispatch was executed.",
            reason_code=clean_reason,
        )

    return TaskOutcomePayload(
        severity="warning",
        summary=f"Dispatch decision recorded for task {clean_task}.",
        details="Review control-plane routing policy and retry after correcting task metadata.",
        reason_code=clean_reason or "unknown_decision",
    )


def build_qa_pass_outcome(
    *,
    task_id: str,
    attempt_number: int,
    artifact_links: tuple[str, ...] = (),
    run_id: str | None = None,
) -> TaskOutcomePayload:
    """Build QA pass terminal outcome for operator visibility."""
    clean_task = _sanitize_text(task_id)
    links_clause = ""
    if artifact_links:
        links_clause = f"\nartifacts={', '.join(_sanitize_text(link) for link in artifact_links)}"
    return TaskOutcomePayload(
        severity="info",
        summary=f"QA passed for task {clean_task} on attempt {attempt_number}.",
        details=f"Task advanced to QA pass status.{links_clause}".strip(),
        reason_code="qa_passed",
        run_id=run_id,
    )


def build_qa_fail_to_build_outcome(
    *,
    task_id: str,
    attempt_number: int,
    failure_report: QaFailureReport,
    run_id: str | None = None,
) -> TaskOutcomePayload:
    """Build QA fail-to-build outcome with structured failure report details."""
    clean_task = _sanitize_text(task_id)
    details = (
        f"Attempt {attempt_number} failed QA and was routed back to build.\n"
        f"issue_description={_sanitize_text(failure_report.issue_description)}\n"
        f"expected_behavior={_sanitize_text(failure_report.expected_behavior)}\n"
        f"observed_behavior={_sanitize_text(failure_report.observed_behavior)}\n"
        f"reproduction_context={_sanitize_text(failure_report.reproduction_context)}"
    )
    if failure_report.artifact_links:
        links = ", ".join(_sanitize_text(link) for link in failure_report.artifact_links)
        details = f"{details}\nartifacts={links}"
    return TaskOutcomePayload(
        severity="warning",
        summary=f"QA failed for task {clean_task}; returned to build.",
        details=details,
        reason_code="qa_failed_to_build",
        run_id=run_id,
    )


def build_qa_blocked_escalation_outcome(
    *,
    task_id: str,
    attempt_number: int,
    failure_report: QaFailureReport | None = None,
    run_id: str | None = None,
) -> TaskOutcomePayload:
    """Build blocked-escalation outcome after max consecutive QA failures."""
    clean_task = _sanitize_text(task_id)
    details = (
        f"Task reached failure threshold on attempt {attempt_number} and is blocked for "
        "human intervention. Manual unblock is required before automation can resume."
    )
    if failure_report is not None:
        details = (
            f"{details}\nissue_description={_sanitize_text(failure_report.issue_description)}\n"
            f"expected_behavior={_sanitize_text(failure_report.expected_behavior)}\n"
            f"observed_behavior={_sanitize_text(failure_report.observed_behavior)}\n"
            f"reproduction_context={_sanitize_text(failure_report.reproduction_context)}"
        )
    return TaskOutcomePayload(
        severity="error",
        summary=f"QA blocked after retries for task {clean_task}.",
        details=details,
        reason_code="qa_blocked_after_retries",
        run_id=run_id,
    )


def _sanitize_text(raw: str) -> str:
    value = " ".join(raw.strip().split())
    for pattern in _TOKEN_PATTERNS:
        value = pattern.sub(r"\1[REDACTED]", value)
    if len(value) > _MAX_TEXT_LEN:
        return value[: _MAX_TEXT_LEN - 3] + "..."
    return value


__all__ = [
    "ClickUpAPIError",
    "ClickUpAuthError",
    "ClickUpError",
    "ClickUpNotFoundError",
    "ClickUpOutcomeClient",
    "ClickUpRateLimitError",
    "ClickUpSchemaMismatchError",
    "OutcomeSeverity",
    "TaskOutcomePayload",
    "build_decision_outcome",
    "build_qa_blocked_escalation_outcome",
    "build_qa_fail_to_build_outcome",
    "build_qa_pass_outcome",
    "render_operator_outcome",
]
