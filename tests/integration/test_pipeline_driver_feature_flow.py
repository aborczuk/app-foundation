"""Integration-level skeleton tests for deterministic pipeline driver flow."""

from __future__ import annotations

def test_resolve_phase_state_skeleton(driver_flow_harness) -> None:
    state = driver_flow_harness.resolve(feature_id="999", phase_hint="setup")
    assert state["feature_id"] == "999"
    assert state["phase"] == "setup"
    assert state["blocked"] is False


def test_reconcile_and_retry_guards(driver_flow_harness) -> None:
    driver_flow_harness.seed_ledger(
        [
            driver_flow_harness.make_event("backlog_registered", "2026-04-10T00:00:00Z"),
            driver_flow_harness.make_event("research_completed", "2026-04-10T00:01:00Z"),
            driver_flow_harness.make_event("plan_started", "2026-04-10T00:02:00Z"),
            driver_flow_harness.make_event(
                "planreview_completed",
                "2026-04-10T00:03:00Z",
                fq_count=0,
                questions_asked=0,
            ),
            driver_flow_harness.make_event(
                "feasibility_spike_completed",
                "2026-04-10T00:04:00Z",
                spike_artifact="specs/019-token-efficiency-docs/spike.md",
                fq_count=0,
            ),
            driver_flow_harness.make_event(
                "plan_approved",
                "2026-04-10T00:05:00Z",
                feasibility_required="false",
            ),
        ]
    )

    drift_state = driver_flow_harness.resolve()
    assert drift_state["drift_detected"] is True
    assert "missing_artifact:plan.md" in drift_state["drift_reasons"]

    (driver_flow_harness.feature_dir / "plan.md").write_text("# plan\n", encoding="utf-8")
    reconciled_state = driver_flow_harness.resolve()
    assert reconciled_state["drift_detected"] is False
    assert reconciled_state["phase"] == "plan"

    first_lock = driver_flow_harness.acquire(owner="worker-a")
    retry_lock = driver_flow_harness.acquire(owner="worker-a")
    blocked_lock = driver_flow_harness.acquire(owner="worker-b")
    assert first_lock["acquired"] is True
    assert retry_lock["acquired"] is True
    assert retry_lock["reused"] is True
    assert blocked_lock["acquired"] is False
    assert blocked_lock["reason"] == "feature_lock_held"
