"""Unit tests for QA loop configuration scaffolding."""

from __future__ import annotations

from pathlib import Path

from clickup_control_plane.config import ControlPlaneRuntimeConfig, ScopeAllowlist
from clickup_control_plane.qa_loop import (
    evaluate_qa_attempt,
    reset_failures_for_manual_unblock,
    resolve_qa_loop_config,
)


def _runtime_config(*, qa_max_failures: int = 3) -> ControlPlaneRuntimeConfig:
    return ControlPlaneRuntimeConfig(
        clickup_api_token="token",
        clickup_webhook_secret="secret",
        n8n_dispatch_base_url="https://n8n.example/webhook",
        control_plane_db_path=Path(".speckit/control-plane.db"),
        allowlist=ScopeAllowlist(space_ids=("space-1",), list_ids=()),
        qa_trigger_status="Ready for QA",
        qa_build_status="Build",
        qa_pass_status="Done",
        qa_max_failures=qa_max_failures,
    )


def test_resolve_qa_loop_config_uses_runtime_values() -> None:
    runtime = _runtime_config(qa_max_failures=5)
    resolved = resolve_qa_loop_config(runtime)
    assert resolved.trigger_status == "Ready for QA"
    assert resolved.build_status == "Build"
    assert resolved.pass_status == "Done"
    assert resolved.max_failures == 5


def test_resolve_qa_loop_config_rejects_non_positive_failures() -> None:
    runtime = _runtime_config(qa_max_failures=0)
    try:
        resolve_qa_loop_config(runtime)
    except ValueError as exc:
        assert "qa_max_failures must be > 0" in str(exc)
    else:
        raise AssertionError("expected ValueError for qa_max_failures <= 0")


def test_evaluate_qa_attempt_fail_below_threshold_routes_to_rework() -> None:
    config = resolve_qa_loop_config(_runtime_config(qa_max_failures=3))
    decision = evaluate_qa_attempt(
        result="fail",
        current_consecutive_failures=1,
        config=config,
    )
    assert decision.transition == "rework"
    assert decision.reason_code == "qa_failed_to_build"
    assert decision.consecutive_failures == 2
    assert decision.blocked_human_required is False


def test_evaluate_qa_attempt_fail_at_threshold_blocks_human_required() -> None:
    config = resolve_qa_loop_config(_runtime_config(qa_max_failures=3))
    decision = evaluate_qa_attempt(
        result="fail",
        current_consecutive_failures=2,
        config=config,
    )
    assert decision.transition == "blocked_human_required"
    assert decision.reason_code == "qa_blocked_after_retries"
    assert decision.consecutive_failures == 3
    assert decision.blocked_human_required is True


def test_reset_failures_for_manual_unblock_returns_clean_rework_state() -> None:
    decision = reset_failures_for_manual_unblock()
    assert decision.transition == "rework"
    assert decision.reason_code == "manual_unblock_reset"
    assert decision.consecutive_failures == 0
    assert decision.blocked_human_required is False
