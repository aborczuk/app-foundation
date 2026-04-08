"""Dispatch orchestration service for policy -> state -> n8n decision flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from pydantic import ValidationError

from .clickup_client import ClickUpError, ClickUpOutcomeClient, ClickUpSchemaMismatchError
from .dispatcher import (
    DispatchCancelledError,
    DispatchRejectedError,
    DispatchRequestError,
    DispatchTimeoutError,
    N8NDispatchClient,
    build_dispatch_request,
    resolve_workflow_path,
)
from .policy import evaluate_dispatch_policy, evaluate_qa_dispatch_gate
from .qa_loop import QaLoopConfig, evaluate_qa_attempt
from .reconcile import ReconciliationCheckpointError, ReconciliationService
from .schemas import ClickUpWebhookPayload, QaWorkflowResultPayload, WebhookDecision
from .state_store import ActiveTaskRun, PausedTaskRun, StateStore


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payload_event_timestamp_iso(payload: ClickUpWebhookPayload) -> str:
    occurred = payload.occurred_at_utc or datetime.now(timezone.utc)
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=timezone.utc)
    return occurred.astimezone(timezone.utc).isoformat()


def _extract_attempt_number(payload_raw: Mapping[str, object]) -> int:
    for key in ("attempt_number", "attemptNumber"):
        raw = payload_raw.get(key)
        if isinstance(raw, int) and raw >= 1:
            return raw
    for parent in ("routing", "metadata"):
        nested = payload_raw.get(parent)
        if not isinstance(nested, Mapping):
            continue
        for key in ("attempt_number", "attemptNumber"):
            raw = nested.get(key)
            if isinstance(raw, int) and raw >= 1:
                return raw
    return 1


def _extract_prior_failure_context(payload_raw: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    for key in ("prior_failure_context", "priorFailureContext"):
        context = _coerce_failure_context(payload_raw.get(key))
        if context:
            return context
    for parent in ("routing", "metadata"):
        nested = payload_raw.get(parent)
        if not isinstance(nested, Mapping):
            continue
        for key in ("prior_failure_context", "priorFailureContext"):
            context = _coerce_failure_context(nested.get(key))
            if context:
                return context
    return ()


def _coerce_failure_context(raw: object) -> tuple[dict[str, object], ...]:
    if not isinstance(raw, list):
        return ()
    normalized: list[dict[str, object]] = []
    for item in raw:
        if isinstance(item, Mapping):
            normalized.append({str(key): value for key, value in item.items()})
    return tuple(normalized)


def _extract_current_failure_streak(payload_raw: Mapping[str, object]) -> int:
    for key in ("qa_consecutive_failures", "qaConsecutiveFailures"):
        raw = payload_raw.get(key)
        if isinstance(raw, int) and raw >= 0:
            return raw
    for parent in ("routing", "metadata"):
        nested = payload_raw.get(parent)
        if not isinstance(nested, Mapping):
            continue
        for key in ("qa_consecutive_failures", "qaConsecutiveFailures"):
            raw = nested.get(key)
            if isinstance(raw, int) and raw >= 0:
                return raw
    return 0


def _has_manual_unblock_signal(payload_raw: Mapping[str, object]) -> bool:
    for key in ("manual_unblock", "manualUnblock"):
        raw = payload_raw.get(key)
        if isinstance(raw, bool) and raw:
            return True
    for parent in ("routing", "metadata"):
        nested = payload_raw.get(parent)
        if not isinstance(nested, Mapping):
            continue
        for key in ("manual_unblock", "manualUnblock"):
            raw = nested.get(key)
            if isinstance(raw, bool) and raw:
                return True
    return False


@dataclass(frozen=True)
class OrchestrationResult:
    """Terminal dispatch decision for a webhook event."""

    decision: WebhookDecision
    reason_code: str
    task_id: str
    event_id: str
    workflow_type: str | None = None
    run_id: str | None = None


class DispatchOrchestrationService:
    """Coordinate policy checks, state-locking, and n8n dispatch calls."""

    def __init__(
        self,
        *,
        state_store: StateStore,
        dispatcher_client: N8NDispatchClient,
        clickup_outcome_client: ClickUpOutcomeClient,
        qa_loop_config: QaLoopConfig,
        allowlist,
        workflow_controlled_statuses: tuple[str, ...],
        reconciliation_service: ReconciliationService | None = None,
    ) -> None:
        """Initialize orchestration dependencies for policy, state, dispatch, and outcomes."""
        self._state_store = state_store
        self._dispatcher_client = dispatcher_client
        self._clickup_outcome_client = clickup_outcome_client
        self._qa_loop_config = qa_loop_config
        self._allowlist = allowlist
        self._workflow_controlled_statuses = tuple(
            _normalize_status_name(value) for value in workflow_controlled_statuses if value.strip()
        )
        self._reconciliation_service = reconciliation_service

    async def process_event(
        self,
        *,
        payload: ClickUpWebhookPayload,
        payload_raw: Mapping[str, object],
        event_id: str,
    ) -> OrchestrationResult:
        """Return terminal webhook decision for one event."""
        occurred_at = _payload_event_timestamp_iso(payload)
        active_run = await self._state_store.get_active_run(task_id=payload.task_id)
        paused_run = await self._state_store.get_paused_run(task_id=payload.task_id)
        operator_response = _extract_human_input_response(payload_raw)
        if (
            active_run is not None
            and paused_run is not None
            and active_run.run_id == paused_run.run_id
            and operator_response is not None
        ):
            return await self._resume_paused_run(
                payload=payload,
                event_id=event_id,
                occurred_at_utc=occurred_at,
                paused_run=paused_run,
                operator_response=operator_response,
            )
        if active_run is not None and _is_manual_cancel_signal(
            payload=payload,
            controlled_statuses=self._workflow_controlled_statuses,
        ):
            return await self._cancel_active_run_from_manual_status_change(
                payload=payload,
                event_id=event_id,
                occurred_at_utc=occurred_at,
                active_run=active_run,
                paused_run=paused_run,
            )

        policy = evaluate_dispatch_policy(
            payload=payload,
            payload_raw=payload_raw,
            allowlist=self._allowlist,
        )
        if policy.decision == "action_scope_violation":
            result = OrchestrationResult(
                decision="action_scope_violation",
                reason_code=policy.reason_code,
                task_id=payload.task_id,
                event_id=event_id,
            )
            if await self._write_outcome(result=result):
                return self._schema_mismatch_result(
                    task_id=payload.task_id,
                    event_id=event_id,
                    run_id=None,
                )
            return result

        if policy.decision != "dispatch":
            result = OrchestrationResult(
                decision=policy.decision,
                reason_code=policy.reason_code,
                task_id=payload.task_id,
                event_id=event_id,
            )
            if await self._write_outcome(
                result=result,
                missing_fields=policy.missing_fields,
            ):
                return self._schema_mismatch_result(
                    task_id=payload.task_id,
                    event_id=event_id,
                    run_id=None,
                )
            return result

        routing = policy.routing_metadata
        if routing is None:
            result = OrchestrationResult(
                decision="reject_missing_metadata",
                reason_code="missing_metadata",
                task_id=payload.task_id,
                event_id=event_id,
            )
            if await self._write_outcome(result=result):
                return self._schema_mismatch_result(
                    task_id=payload.task_id,
                    event_id=event_id,
                    run_id=None,
                )
            return result

        if self._reconciliation_service is not None:
            try:
                await self._reconciliation_service.enforce_pre_dispatch_checkpoint()
            except ReconciliationCheckpointError:
                result = OrchestrationResult(
                    decision="dispatch_failed",
                    reason_code="reconciliation_checkpoint_failed",
                    task_id=payload.task_id,
                    event_id=event_id,
                    workflow_type=routing.workflow_type,
                )
                if await self._write_outcome(result=result):
                    return self._schema_mismatch_result(
                        task_id=payload.task_id,
                        event_id=event_id,
                        run_id=None,
                    )
                return result

        lock = await self._state_store.record_event_and_acquire_lock(
            task_id=payload.task_id,
            event_id=event_id,
            run_id=f"run_pending_{event_id}",
            processed_at_utc=occurred_at,
        )
        if lock.decision == "skip_duplicate":
            return OrchestrationResult(
                decision="skip_duplicate",
                reason_code=lock.reason_code,
                task_id=payload.task_id,
                event_id=event_id,
            )
        if lock.decision == "stale_event":
            result = OrchestrationResult(
                decision="stale_event",
                reason_code=lock.reason_code,
                task_id=payload.task_id,
                event_id=event_id,
            )
            if await self._write_outcome(result=result):
                await self._state_store.update_processed_event_decision(
                    event_id=event_id,
                    decision="schema_mismatch",
                )
                return self._schema_mismatch_result(
                    task_id=payload.task_id,
                    event_id=event_id,
                    run_id=None,
                )
            return result
        if lock.decision == "reject_active_run":
            result = OrchestrationResult(
                decision="reject_active_run",
                reason_code=lock.reason_code,
                task_id=payload.task_id,
                event_id=event_id,
            )
            if await self._write_outcome(result=result):
                await self._state_store.update_processed_event_decision(
                    event_id=event_id,
                    decision="schema_mismatch",
                )
                return self._schema_mismatch_result(
                    task_id=payload.task_id,
                    event_id=event_id,
                    run_id=None,
                )
            return result

        route = resolve_workflow_path(routing.workflow_type)
        if route is None:
            await self._state_store.update_processed_event_decision(
                event_id=event_id,
                decision="reject_missing_metadata",
            )
            result = OrchestrationResult(
                decision="reject_missing_metadata",
                reason_code="missing_workflow_route",
                task_id=payload.task_id,
                event_id=event_id,
            )
            if await self._write_outcome(result=result):
                await self._state_store.update_processed_event_decision(
                    event_id=event_id,
                    decision="schema_mismatch",
                )
                return self._schema_mismatch_result(
                    task_id=payload.task_id,
                    event_id=event_id,
                    run_id=None,
                )
            return result

        qa_attempt_number: int | None = None
        qa_criteria_items: tuple[str, ...] = ()
        qa_prior_failure_context: tuple[dict[str, object], ...] = ()
        if routing.workflow_type == "qa_loop":
            qa_gate = evaluate_qa_dispatch_gate(payload_raw=payload_raw)
            if qa_gate.decision != "dispatch":
                qa_result = OrchestrationResult(
                    decision=qa_gate.decision,
                    reason_code=qa_gate.reason_code,
                    task_id=payload.task_id,
                    event_id=event_id,
                    workflow_type=routing.workflow_type,
                )
                if await self._write_outcome(result=qa_result):
                    await self._state_store.update_processed_event_decision(
                        event_id=event_id,
                        decision="schema_mismatch",
                    )
                    return self._schema_mismatch_result(
                        task_id=payload.task_id,
                        event_id=event_id,
                        run_id=None,
                    )
                await self._state_store.persist_terminal_decision(
                    task_id=payload.task_id,
                    event_id=event_id,
                    decision=qa_gate.decision,
                    active_run_id=f"run_pending_{event_id}",
                    release_lock=True,
                )
                return qa_result
            qa_attempt_number = _extract_attempt_number(payload_raw)
            qa_criteria_items = qa_gate.criteria_items
            qa_prior_failure_context = _extract_prior_failure_context(payload_raw)

        request = build_dispatch_request(
            task_id=payload.task_id,
            event_id=event_id,
            workflow_type=routing.workflow_type,
            context_ref=routing.context_ref,
            execution_policy=routing.execution_policy,
            event=payload.event,
            attempt_number=qa_attempt_number,
            criteria_items=qa_criteria_items,
            prior_failure_context=qa_prior_failure_context,
        )
        try:
            result = await self._dispatcher_client.dispatch(
                request=request,
                path=route,
            )
        except (DispatchTimeoutError, DispatchRequestError, DispatchRejectedError):
            await self._state_store.persist_terminal_decision(
                task_id=payload.task_id,
                event_id=event_id,
                decision="dispatch_failed",
                active_run_id=f"run_pending_{event_id}",
                release_lock=True,
            )
            result = OrchestrationResult(
                decision="dispatch_failed",
                reason_code="dispatch_failed",
                task_id=payload.task_id,
                event_id=event_id,
                workflow_type=routing.workflow_type,
            )
            if await self._write_outcome(result=result):
                await self._state_store.persist_terminal_decision(
                    task_id=payload.task_id,
                    event_id=event_id,
                    decision="schema_mismatch",
                    release_lock=False,
                )
                return self._schema_mismatch_result(
                    task_id=payload.task_id,
                    event_id=event_id,
                    run_id=None,
                )
            return result

        active_run_id = f"run_pending_{event_id}"
        if result.run_id and result.run_id.strip():
            active_run_id = result.run_id.strip()
            await self._state_store.set_active_run_id(
                task_id=payload.task_id,
                current_run_id=f"run_pending_{event_id}",
                new_run_id=active_run_id,
            )

        if routing.workflow_type == "qa_loop":
            return await self._handle_qa_workflow_result(
                payload=payload,
                payload_raw=payload_raw,
                event_id=event_id,
                active_run_id=active_run_id,
                run_id=result.run_id,
                response_body=result.response_body,
            )

        dispatch_result = OrchestrationResult(
            decision="dispatch",
            reason_code="dispatch_started",
            task_id=payload.task_id,
            event_id=event_id,
            workflow_type=routing.workflow_type,
            run_id=result.run_id,
        )
        if await self._write_outcome(result=dispatch_result):
            await self._state_store.persist_terminal_decision(
                task_id=payload.task_id,
                event_id=event_id,
                decision="schema_mismatch",
                active_run_id=active_run_id,
                release_lock=True,
            )
            return self._schema_mismatch_result(
                task_id=payload.task_id,
                event_id=event_id,
                run_id=result.run_id,
            )
        return dispatch_result

    async def _write_outcome(
        self,
        *,
        result: OrchestrationResult,
        missing_fields: tuple[str, ...] = (),
    ) -> bool:
        if result.decision == "skip_duplicate":
            return False
        try:
            await self._clickup_outcome_client.write_decision_outcome(
                task_id=result.task_id,
                decision=result.decision,
                reason_code=result.reason_code,
                workflow_type=result.workflow_type,
                run_id=result.run_id,
                missing_fields=missing_fields,
            )
            return False
        except ClickUpSchemaMismatchError:
            return True
        except ClickUpError:
            return False

    async def _handle_qa_workflow_result(
        self,
        *,
        payload: ClickUpWebhookPayload,
        payload_raw: Mapping[str, object],
        event_id: str,
        active_run_id: str,
        run_id: str | None,
        response_body: dict[str, object],
    ) -> OrchestrationResult:
        try:
            qa_result = QaWorkflowResultPayload.model_validate(response_body)
        except ValidationError:
            await self._state_store.persist_terminal_decision(
                task_id=payload.task_id,
                event_id=event_id,
                decision="dispatch_failed",
                active_run_id=active_run_id,
                release_lock=True,
            )
            result = OrchestrationResult(
                decision="dispatch_failed",
                reason_code="qa_result_invalid",
                task_id=payload.task_id,
                event_id=event_id,
                workflow_type="qa_loop",
                run_id=run_id,
            )
            await self._write_outcome(result=result)
            return result

        current_failures = _extract_current_failure_streak(payload_raw)
        if _has_manual_unblock_signal(payload_raw):
            current_failures = 0

        transition = evaluate_qa_attempt(
            result=qa_result.result,
            current_consecutive_failures=current_failures,
            config=self._qa_loop_config,
        )
        if qa_result.result == "pass":
            try:
                await self._clickup_outcome_client.set_task_status(
                    task_id=payload.task_id,
                    status_name=self._qa_loop_config.pass_status,
                )
                await self._clickup_outcome_client.write_qa_pass_outcome(
                    task_id=payload.task_id,
                    attempt_number=_extract_attempt_number(payload_raw),
                    artifact_links=tuple(qa_result.artifact_links),
                    run_id=run_id,
                )
            except ClickUpSchemaMismatchError:
                await self._state_store.persist_terminal_decision(
                    task_id=payload.task_id,
                    event_id=event_id,
                    decision="schema_mismatch",
                    active_run_id=active_run_id,
                    release_lock=True,
                )
                return self._schema_mismatch_result(
                    task_id=payload.task_id,
                    event_id=event_id,
                    run_id=run_id,
                )
            except ClickUpError:
                pass
            await self._state_store.persist_terminal_decision(
                task_id=payload.task_id,
                event_id=event_id,
                decision="qa_passed",
                active_run_id=active_run_id,
                release_lock=True,
            )
            return OrchestrationResult(
                decision="qa_passed",
                reason_code=transition.reason_code,
                task_id=payload.task_id,
                event_id=event_id,
                workflow_type="qa_loop",
                run_id=run_id,
            )

        failure_report = qa_result.failure_report
        if failure_report is None:
            await self._state_store.persist_terminal_decision(
                task_id=payload.task_id,
                event_id=event_id,
                decision="dispatch_failed",
                active_run_id=active_run_id,
                release_lock=True,
            )
            return OrchestrationResult(
                decision="dispatch_failed",
                reason_code="qa_result_invalid",
                task_id=payload.task_id,
                event_id=event_id,
                workflow_type="qa_loop",
                run_id=run_id,
            )

        if transition.blocked_human_required:
            next_status = "Blocked"
            decision: WebhookDecision = "qa_blocked_after_retries"
            outcome_writer = self._clickup_outcome_client.write_qa_blocked_escalation_outcome
        else:
            next_status = self._qa_loop_config.build_status
            decision = "qa_failed_to_build"
            outcome_writer = self._clickup_outcome_client.write_qa_fail_to_build_outcome

        try:
            await self._clickup_outcome_client.set_task_status(
                task_id=payload.task_id,
                status_name=next_status,
            )
            await outcome_writer(
                task_id=payload.task_id,
                attempt_number=_extract_attempt_number(payload_raw),
                failure_report=failure_report,
                run_id=run_id,
            )
        except ClickUpSchemaMismatchError:
            await self._state_store.persist_terminal_decision(
                task_id=payload.task_id,
                event_id=event_id,
                decision="schema_mismatch",
                active_run_id=active_run_id,
                release_lock=True,
            )
            return self._schema_mismatch_result(
                task_id=payload.task_id,
                event_id=event_id,
                run_id=run_id,
            )
        except ClickUpError:
            pass

        await self._state_store.persist_terminal_decision(
            task_id=payload.task_id,
            event_id=event_id,
            decision=decision,
            active_run_id=active_run_id,
            release_lock=True,
        )
        return OrchestrationResult(
            decision=decision,
            reason_code=transition.reason_code,
            task_id=payload.task_id,
            event_id=event_id,
            workflow_type="qa_loop",
            run_id=run_id,
        )

    async def _resume_paused_run(
        self,
        *,
        payload: ClickUpWebhookPayload,
        event_id: str,
        occurred_at_utc: str,
        paused_run: PausedTaskRun,
        operator_response: str,
    ) -> OrchestrationResult:
        inserted = await self._state_store.record_processed_event(
            task_id=payload.task_id,
            event_id=event_id,
            decision="pending",
            processed_at_utc=occurred_at_utc,
        )
        if not inserted:
            return OrchestrationResult(
                decision="skip_duplicate",
                reason_code="duplicate_event",
                task_id=payload.task_id,
                event_id=event_id,
            )

        route = resolve_workflow_path(paused_run.workflow_type)
        if route is None:
            await self._state_store.update_processed_event_decision(
                event_id=event_id,
                decision="reject_missing_metadata",
            )
            result = OrchestrationResult(
                decision="reject_missing_metadata",
                reason_code="missing_workflow_route",
                task_id=payload.task_id,
                event_id=event_id,
            )
            if await self._write_outcome(result=result):
                await self._state_store.update_processed_event_decision(
                    event_id=event_id,
                    decision="schema_mismatch",
                )
                return self._schema_mismatch_result(
                    task_id=payload.task_id,
                    event_id=event_id,
                    run_id=paused_run.run_id,
                )
            return result

        request = build_dispatch_request(
            task_id=payload.task_id,
            event_id=event_id,
            workflow_type=paused_run.workflow_type,
            context_ref=paused_run.context_ref,
            execution_policy=paused_run.execution_policy,
            event=payload.event,
            occurred_at_utc=occurred_at_utc,
            resume_run_id=paused_run.run_id,
            human_input_response=operator_response,
            human_input_prompt=paused_run.prompt,
        )
        try:
            dispatch_result = await self._dispatcher_client.dispatch(
                request=request,
                path=route,
            )
        except (DispatchCancelledError, DispatchTimeoutError, DispatchRequestError, DispatchRejectedError):
            await self._state_store.update_processed_event_decision(
                event_id=event_id,
                decision="dispatch_failed",
            )
            failed = OrchestrationResult(
                decision="dispatch_failed",
                reason_code="resume_dispatch_failed",
                task_id=payload.task_id,
                event_id=event_id,
                workflow_type=paused_run.workflow_type,
                run_id=paused_run.run_id,
            )
            if await self._write_outcome(result=failed):
                await self._state_store.update_processed_event_decision(
                    event_id=event_id,
                    decision="schema_mismatch",
                )
                return self._schema_mismatch_result(
                    task_id=payload.task_id,
                    event_id=event_id,
                    run_id=paused_run.run_id,
                )
            return failed

        resumed_run_id = dispatch_result.run_id or paused_run.run_id
        if resumed_run_id != paused_run.run_id:
            await self._state_store.set_active_run_id(
                task_id=payload.task_id,
                current_run_id=paused_run.run_id,
                new_run_id=resumed_run_id,
            )
        await self._state_store.clear_paused_run(
            task_id=payload.task_id,
            run_id=paused_run.run_id,
        )
        await self._state_store.update_processed_event_decision(
            event_id=event_id,
            decision="input_resumed",
        )
        resumed = OrchestrationResult(
            decision="input_resumed",
            reason_code="hitl_resumed",
            task_id=payload.task_id,
            event_id=event_id,
            workflow_type=paused_run.workflow_type,
            run_id=resumed_run_id,
        )
        if await self._write_outcome(result=resumed):
            await self._state_store.update_processed_event_decision(
                event_id=event_id,
                decision="schema_mismatch",
            )
            return self._schema_mismatch_result(
                task_id=payload.task_id,
                event_id=event_id,
                run_id=resumed_run_id,
            )
        return resumed

    async def _cancel_active_run_from_manual_status_change(
        self,
        *,
        payload: ClickUpWebhookPayload,
        event_id: str,
        occurred_at_utc: str,
        active_run: ActiveTaskRun,
        paused_run: PausedTaskRun | None,
    ) -> OrchestrationResult:
        inserted = await self._state_store.record_processed_event(
            task_id=payload.task_id,
            event_id=event_id,
            decision="pending",
            processed_at_utc=occurred_at_utc,
        )
        if not inserted:
            return OrchestrationResult(
                decision="skip_duplicate",
                reason_code="duplicate_event",
                task_id=payload.task_id,
                event_id=event_id,
            )

        reason_code = "manual_status_change_cancelled"
        try:
            await self._dispatcher_client.cancel_run(
                task_id=payload.task_id,
                run_id=active_run.run_id,
                event_id=event_id,
                reason="manual_status_change",
            )
        except (DispatchTimeoutError, DispatchRequestError, DispatchRejectedError):
            reason_code = "manual_status_change_cancel_signal_failed"

        await self._state_store.release_active_run(
            task_id=payload.task_id,
            run_id=active_run.run_id,
        )
        if paused_run is not None:
            await self._state_store.clear_paused_run(
                task_id=payload.task_id,
                run_id=paused_run.run_id,
            )
        await self._state_store.update_processed_event_decision(
            event_id=event_id,
            decision="cancelled_by_operator",
        )

        cancelled = OrchestrationResult(
            decision="cancelled_by_operator",
            reason_code=reason_code,
            task_id=payload.task_id,
            event_id=event_id,
            workflow_type=paused_run.workflow_type if paused_run is not None else None,
            run_id=active_run.run_id,
        )
        if await self._write_outcome(result=cancelled):
            await self._state_store.update_processed_event_decision(
                event_id=event_id,
                decision="schema_mismatch",
            )
            return self._schema_mismatch_result(
                task_id=payload.task_id,
                event_id=event_id,
                run_id=active_run.run_id,
            )
        return cancelled

    @staticmethod
    def _schema_mismatch_result(
        *,
        task_id: str,
        event_id: str,
        run_id: str | None,
    ) -> OrchestrationResult:
        return OrchestrationResult(
            decision="schema_mismatch",
            reason_code="schema_mismatch",
            task_id=task_id,
            event_id=event_id,
            run_id=run_id,
        )


def _normalize_status_name(raw: str) -> str:
    return raw.strip().lower().replace("-", " ")


def _status_transition(payload: ClickUpWebhookPayload) -> tuple[str | None, str | None]:
    for item in payload.history_items:
        if not item.field:
            continue
        field_name = item.field.strip().lower()
        if field_name not in {"status", "task_status"}:
            continue
        before = _normalize_status_name(item.before) if item.before else None
        after = _normalize_status_name(item.after) if item.after else None
        return before, after
    return None, None


def _is_manual_cancel_signal(
    *,
    payload: ClickUpWebhookPayload,
    controlled_statuses: tuple[str, ...],
) -> bool:
    before, after = _status_transition(payload)
    if not before or not after or before == after:
        return False
    controlled = set(controlled_statuses)
    return before in controlled and after not in controlled


def _extract_human_input_response(payload_raw: Mapping[str, object]) -> str | None:
    for key in ("human_input_response", "humanInputResponse"):
        raw = payload_raw.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    for parent in ("routing", "metadata"):
        nested = payload_raw.get(parent)
        if not isinstance(nested, Mapping):
            continue
        for key in ("human_input_response", "humanInputResponse"):
            raw = nested.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()

    comment_candidates = ("comment_text", "comment", "text")
    for key in comment_candidates:
        raw_comment = payload_raw.get(key)
        if not isinstance(raw_comment, str):
            continue
        comment = raw_comment.strip()
        if not comment:
            continue
        prefix = "hitl_response:"
        if comment.lower().startswith(prefix):
            response = comment[len(prefix):].strip()
            if response:
                return response
    return None


__all__ = [
    "DispatchOrchestrationService",
    "OrchestrationResult",
]
