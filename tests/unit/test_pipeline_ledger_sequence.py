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


def _event(name: str, **fields: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event": name,
        "feature_id": "019",
        "timestamp_utc": "2026-04-09T00:00:00Z",
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


def test_new_solution_sequence_passes() -> None:
    events = _base_prefix() + _new_solution_chain() + [
        _event("analysis_completed", critical_count=0),
        _event("e2e_generated", e2e_artifact="specs/019-token-efficiency-docs/e2e.md"),
        _event("feature_closed"),
    ]
    errors, _ = pipeline_ledger.validate_sequence(events)
    assert errors == []


def test_old_tasking_before_sketch_sequence_fails() -> None:
    events = _base_prefix() + [
        _event("tasking_completed", task_count=12, story_count=3),
        _event("sketch_completed"),
        _event("estimation_completed", estimate_points=21),
        _event("solutionreview_completed", critical_count=0, high_count=0),
        _event("solution_approved", task_count=12, story_count=3, estimate_points=21),
    ]
    errors, _ = pipeline_ledger.validate_sequence(events)
    assert any("invalid pipeline transition" in err for err in errors)


def test_solution_approved_before_analyze_is_allowed() -> None:
    events = _base_prefix() + _new_solution_chain()
    errors, _ = pipeline_ledger.validate_sequence(events)
    assert errors == []


def test_analysis_completed_requires_zero_critical_count() -> None:
    events = _base_prefix() + _new_solution_chain() + [
        _event("analysis_completed", critical_count=1),
    ]
    errors, _ = pipeline_ledger.validate_sequence(events)
    assert any("analysis_completed.critical_count must be 0" in err for err in errors)
