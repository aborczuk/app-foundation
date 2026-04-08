"""QA loop coordination primitives for Phase 2 behavior wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .config import ControlPlaneRuntimeConfig


@dataclass(frozen=True)
class QaLoopConfig:
    """Resolved QA-loop configuration used by orchestration/policy layers."""

    trigger_status: str
    build_status: str
    pass_status: str
    max_failures: int


QaAttemptResult = Literal["pass", "fail", "missing_criteria", "dispatch_failed"]
QaTransition = Literal["advance", "rework", "blocked_human_required", "awaiting_metadata_fix"]


@dataclass(frozen=True)
class QaTransitionDecision:
    """Result of evaluating one QA attempt outcome against streak thresholds."""

    transition: QaTransition
    reason_code: str
    consecutive_failures: int
    blocked_human_required: bool


def resolve_qa_loop_config(runtime_config: ControlPlaneRuntimeConfig) -> QaLoopConfig:
    """Build QA-loop settings from runtime config with final defensive validation."""
    if runtime_config.qa_max_failures <= 0:
        raise ValueError("qa_max_failures must be > 0.")
    return QaLoopConfig(
        trigger_status=runtime_config.qa_trigger_status,
        build_status=runtime_config.qa_build_status,
        pass_status=runtime_config.qa_pass_status,
        max_failures=runtime_config.qa_max_failures,
    )


def evaluate_qa_attempt(
    *,
    result: QaAttemptResult,
    current_consecutive_failures: int,
    config: QaLoopConfig,
) -> QaTransitionDecision:
    """Evaluate one QA attempt and return next transition + streak state."""
    if current_consecutive_failures < 0:
        raise ValueError("current_consecutive_failures must be >= 0.")
    if config.max_failures <= 0:
        raise ValueError("max_failures must be > 0.")

    if result == "pass":
        return QaTransitionDecision(
            transition="advance",
            reason_code="qa_passed",
            consecutive_failures=0,
            blocked_human_required=False,
        )

    if result == "fail":
        next_failures = current_consecutive_failures + 1
        if next_failures >= config.max_failures:
            return QaTransitionDecision(
                transition="blocked_human_required",
                reason_code="qa_blocked_after_retries",
                consecutive_failures=next_failures,
                blocked_human_required=True,
            )
        return QaTransitionDecision(
            transition="rework",
            reason_code="qa_failed_to_build",
            consecutive_failures=next_failures,
            blocked_human_required=False,
        )

    if result == "missing_criteria":
        return QaTransitionDecision(
            transition="awaiting_metadata_fix",
            reason_code="missing_criteria",
            consecutive_failures=current_consecutive_failures,
            blocked_human_required=False,
        )

    return QaTransitionDecision(
        transition="awaiting_metadata_fix",
        reason_code="dispatch_failed",
        consecutive_failures=current_consecutive_failures,
        blocked_human_required=False,
    )


def reset_failures_for_manual_unblock() -> QaTransitionDecision:
    """Return deterministic reset state after explicit human unblock action."""
    return QaTransitionDecision(
        transition="rework",
        reason_code="manual_unblock_reset",
        consecutive_failures=0,
        blocked_human_required=False,
    )


__all__ = [
    "QaAttemptResult",
    "QaLoopConfig",
    "QaTransition",
    "QaTransitionDecision",
    "evaluate_qa_attempt",
    "reset_failures_for_manual_unblock",
    "resolve_qa_loop_config",
]
