"""Pipeline ledger transition tests for sketch-first solution sequencing."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any


def _load_pipeline_ledger_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "pipeline_ledger.py"
    spec = importlib.util.spec_from_file_location("pipeline_ledger", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pipeline_ledger = _load_pipeline_ledger_module()


def _event(name: str, *, timestamp: str = "2026-04-10T00:00:00Z", **fields: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event": name,
        "feature_id": "019",
        "timestamp_utc": timestamp,
        "phase": "solution",
    }
    event.update(fields)
    return event


def _base_prefix() -> list[dict[str, Any]]:
    return [
        _event("backlog_registered"),
        _event("research_completed"),
        _event("plan_started"),
        _event("planreview_completed", fq_count=0, questions_asked=0),
        _event(
            "feasibility_spike_completed",
            spike_artifact="specs/019-token-efficiency-docs/spike.md",
            fq_count=0,
        ),
        _event("plan_approved", feasibility_required="true"),
    ]


def _new_solution_chain() -> list[dict[str, Any]]:
    return [
        _event("sketch_completed"),
        _event("solutionreview_completed", critical_count=0, high_count=0),
        _event("estimation_completed", estimate_points=21),
        _event("tasking_completed", task_count=12, story_count=3),
        _event("solution_approved", task_count=12, story_count=3, estimate_points=21),
    ]


def assert_transition_result(
    events: list[dict[str, Any]],
    *expected_error_fragments: str,
) -> tuple[list[str], dict[str, Any]]:
    """Validate a transition sequence and assert any expected error fragments."""
    errors, state = pipeline_ledger.validate_sequence(events)
    if expected_error_fragments:
        for fragment in expected_error_fragments:
            assert any(fragment in error for error in errors)
    else:
        assert errors == []
    return errors, state


def test_new_solution_sequence_passes() -> None:
    events = _base_prefix() + _new_solution_chain() + [
        _event("analysis_completed", critical_count=0),
        _event("e2e_generated", e2e_artifact="specs/019-token-efficiency-docs/e2e.md"),
        _event("feature_closed"),
    ]
    errors, _ = assert_transition_result(events)


def test_old_tasking_before_sketch_sequence_fails() -> None:
    events = _base_prefix() + [
        _event("tasking_completed", task_count=12, story_count=3),
        _event("sketch_completed"),
        _event("estimation_completed", estimate_points=21),
        _event("solutionreview_completed", critical_count=0, high_count=0),
        _event("solution_approved", task_count=12, story_count=3, estimate_points=21),
    ]
    errors, _ = assert_transition_result(events, "invalid pipeline transition")


def test_pre_cutover_old_tasking_before_sketch_sequence_passes() -> None:
    events = _base_prefix() + [
        _event(
            "tasking_completed",
            timestamp="2026-04-09T23:59:59Z",
            task_count=12,
            story_count=3,
        ),
        _event("sketch_completed", timestamp="2026-04-09T23:59:59Z"),
        _event(
            "estimation_completed",
            timestamp="2026-04-09T23:59:59Z",
            estimate_points=21,
        ),
        _event(
            "solutionreview_completed",
            timestamp="2026-04-09T23:59:59Z",
            critical_count=0,
            high_count=0,
        ),
        _event(
            "solution_approved",
            timestamp="2026-04-09T23:59:59Z",
            task_count=12,
            story_count=3,
            estimate_points=21,
        ),
    ]
    errors, _ = assert_transition_result(events)


def test_solution_approved_before_analyze_is_allowed() -> None:
    events = _base_prefix() + _new_solution_chain()
    errors, _ = assert_transition_result(events)


def test_analysis_completed_requires_zero_critical_count() -> None:
    events = _base_prefix() + _new_solution_chain() + [
        _event("analysis_completed", critical_count=1),
    ]
    errors, _ = assert_transition_result(events, "analysis_completed.critical_count must be 0")
