"""Allowlist and routing-metadata policy evaluation for webhook dispatch."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from .config import ScopeAllowlist
from .schemas import ClickUpWebhookPayload, RoutingMetadata

PolicyDecision = Literal[
    "dispatch",
    "reject_scope",
    "reject_missing_metadata",
    "action_scope_violation",
]
QaGateDecision = Literal[
    "dispatch",
    "missing_criteria",
    "qa_unblock_required",
]


@dataclass(frozen=True)
class PolicyEvaluation:
    """Result of evaluating scope and metadata requirements for dispatch."""

    decision: PolicyDecision
    reason_code: str
    missing_fields: tuple[str, ...] = ()
    routing_metadata: RoutingMetadata | None = None


@dataclass(frozen=True)
class QaGateEvaluation:
    """Result of QA-specific gating (criteria + blocked-state checks)."""

    decision: QaGateDecision
    reason_code: str
    criteria_items: tuple[str, ...] = ()


def evaluate_dispatch_policy(
    *,
    payload: ClickUpWebhookPayload,
    payload_raw: Mapping[str, Any],
    allowlist: ScopeAllowlist,
) -> PolicyEvaluation:
    """Evaluate allowlist scope and required routing metadata."""
    if not is_in_allowlist(payload=payload, allowlist=allowlist):
        return PolicyEvaluation(
            decision="reject_scope",
            reason_code="out_of_scope",
        )

    metadata, missing = extract_routing_metadata(payload_raw=payload_raw)
    if missing:
        return PolicyEvaluation(
            decision="reject_missing_metadata",
            reason_code="missing_metadata",
            missing_fields=missing,
        )

    action_scope = _extract_first_string(
        payload_raw,
        keys=("action_scope", "actionScope"),
        nested_parents=("routing", "metadata"),
    )
    if metadata is not None and not _is_within_action_scope(
        workflow_type=metadata.workflow_type,
        action_scope=action_scope,
    ):
        return PolicyEvaluation(
            decision="action_scope_violation",
            reason_code="action_scope_violation",
            routing_metadata=metadata,
        )

    return PolicyEvaluation(
        decision="dispatch",
        reason_code="eligible_for_dispatch",
        routing_metadata=metadata,
    )


def is_in_allowlist(*, payload: ClickUpWebhookPayload, allowlist: ScopeAllowlist) -> bool:
    """Return whether the task event is in an allowlisted space/list scope."""
    if payload.list_id and payload.list_id in allowlist.list_ids:
        return True
    if payload.space_id and payload.space_id in allowlist.space_ids:
        return True
    return False


def extract_routing_metadata(
    *,
    payload_raw: Mapping[str, Any],
) -> tuple[RoutingMetadata | None, tuple[str, ...]]:
    """Extract required routing metadata and return any missing fields."""
    workflow_type = _extract_first_string(
        payload_raw,
        keys=("workflow_type", "workflowType"),
        nested_parents=("routing", "metadata"),
    )
    context_ref = _extract_first_string(
        payload_raw,
        keys=("context_ref", "contextRef"),
        nested_parents=("routing", "metadata"),
    )
    execution_policy = _extract_first_string(
        payload_raw,
        keys=("execution_policy", "executionPolicy"),
        nested_parents=("routing", "metadata"),
    )

    missing: list[str] = []
    if not workflow_type:
        missing.append("workflow_type")
    if not context_ref:
        missing.append("context_ref")
    if not execution_policy:
        missing.append("execution_policy")
    if missing:
        return None, tuple(missing)

    # Defensive narrowing for static type checkers after required-field validation.
    assert workflow_type is not None
    assert context_ref is not None
    assert execution_policy is not None
    metadata = RoutingMetadata(
        workflow_type=workflow_type.strip().lower().replace("-", "_"),
        context_ref=context_ref.strip(),
        execution_policy=execution_policy.strip(),
    )
    return metadata, ()


def _extract_first_string(
    payload_raw: Mapping[str, Any],
    *,
    keys: tuple[str, ...],
    nested_parents: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = payload_raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for parent in nested_parents:
        nested = payload_raw.get(parent)
        if not isinstance(nested, Mapping):
            continue
        for key in keys:
            value = nested.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return None


def _is_within_action_scope(*, workflow_type: str, action_scope: str | None) -> bool:
    if action_scope is None:
        return True

    scope = action_scope.strip().lower().replace("-", "_")
    workflow = workflow_type.strip().lower().replace("-", "_")
    allowed_workflows_by_scope: dict[str, set[str]] = {
        "all": {"build_spec", "qa_loop"},
        "build_only": {"build_spec"},
        "qa_only": {"qa_loop"},
        "read_only": set(),
    }
    allowed = allowed_workflows_by_scope.get(scope)
    if allowed is None:
        return True
    return workflow in allowed


def evaluate_qa_dispatch_gate(*, payload_raw: Mapping[str, Any]) -> QaGateEvaluation:
    """Evaluate QA-loop criteria and blocked-state gates before QA dispatch."""
    if _extract_blocked_indicator(payload_raw):
        return QaGateEvaluation(
            decision="qa_unblock_required",
            reason_code="qa_unblock_required",
            criteria_items=(),
        )

    criteria_items = _extract_criteria_items(payload_raw)
    if not criteria_items:
        return QaGateEvaluation(
            decision="missing_criteria",
            reason_code="missing_criteria",
            criteria_items=(),
        )

    return QaGateEvaluation(
        decision="dispatch",
        reason_code="eligible_for_dispatch",
        criteria_items=criteria_items,
    )


def _extract_blocked_indicator(payload_raw: Mapping[str, Any]) -> bool:
    explicit_blocked = _extract_first_string(
        payload_raw,
        keys=("qa_state", "qaState"),
        nested_parents=("routing", "metadata"),
    )
    if explicit_blocked and explicit_blocked.strip().lower().replace("-", "_") == "blocked_human_required":
        return True

    for key in ("qa_blocked", "qaBlocked", "blocked_human_required"):
        value = payload_raw.get(key)
        if isinstance(value, bool) and value:
            return True
    return False


def _extract_criteria_items(payload_raw: Mapping[str, Any]) -> tuple[str, ...]:
    for key in ("acceptance_criteria", "acceptanceCriteria"):
        raw_value = payload_raw.get(key)
        items = _coerce_criteria_items(raw_value)
        if items:
            return items

    for parent in ("routing", "metadata"):
        nested = payload_raw.get(parent)
        if not isinstance(nested, Mapping):
            continue
        for key in ("acceptance_criteria", "acceptanceCriteria"):
            items = _coerce_criteria_items(nested.get(key))
            if items:
                return items

    return ()


def _coerce_criteria_items(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        return tuple(lines)
    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                normalized.append(item.strip())
        return tuple(normalized)
    return ()


__all__ = [
    "PolicyDecision",
    "PolicyEvaluation",
    "QaGateDecision",
    "QaGateEvaluation",
    "evaluate_qa_dispatch_gate",
    "evaluate_dispatch_policy",
    "extract_routing_metadata",
    "is_in_allowlist",
]
