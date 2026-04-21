"""Pipeline ledger transition tests for sketch-first solution sequencing."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import pytest


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


def test_append_rejects_invalid_order_before_mutation(tmp_path: Path) -> None:
    ledger_path = tmp_path / "pipeline-ledger.jsonl"
    args = SimpleNamespace(
        file=str(ledger_path),
        feature_id="019",
        phase="closed",
        event="feature_closed",
        actor="codex",
        timestamp_utc="2026-04-10T00:00:00Z",
        fq_count=None,
        questions_asked=None,
        spike_artifact=None,
        failed_fq=None,
        feasibility_required=None,
        task_count=None,
        story_count=None,
        estimate_points=None,
        tasks_sketched=None,
        acceptance_tests_written=None,
        critical_count=None,
        high_count=None,
        e2e_artifact=None,
        details=None,
    )

    with pytest.raises(SystemExit) as excinfo:
        pipeline_ledger.cmd_append(args)

    assert excinfo.value.code == 1
    assert not ledger_path.exists()


def test_append_rejects_partial_write_and_preserves_state(tmp_path: Path) -> None:
    ledger_path = tmp_path / "pipeline-ledger.jsonl"
    initial_events = [
        _event("backlog_registered", timestamp="2026-04-10T00:00:00Z"),
        _event("research_completed", timestamp="2026-04-10T00:01:00Z"),
    ]
    original_payload = "\n".join(
        json.dumps(event, sort_keys=True) for event in initial_events
    ) + "\n"
    ledger_path.write_text(original_payload, encoding="utf-8")
    args = SimpleNamespace(
        file=str(ledger_path),
        feature_id="019",
        phase="closed",
        event="feature_closed",
        actor="codex",
        timestamp_utc="2026-04-10T00:02:00Z",
        fq_count=None,
        questions_asked=None,
        spike_artifact=None,
        failed_fq=None,
        feasibility_required=None,
        task_count=None,
        story_count=None,
        estimate_points=None,
        tasks_sketched=None,
        acceptance_tests_written=None,
        critical_count=None,
        high_count=None,
        e2e_artifact=None,
        details=None,
    )

    with pytest.raises(SystemExit) as excinfo:
        pipeline_ledger.cmd_append(args)

    assert excinfo.value.code == 1
    assert ledger_path.read_text(encoding="utf-8") == original_payload
    errors, state = pipeline_ledger.validate_sequence(initial_events)
    assert errors == []
    assert state["019"].last_event == "research_completed"


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


def test_cmd_validate_manifest_routes_task_events_to_task_ledger(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest_path = tmp_path / "command-manifest.yaml"
    manifest_path.write_text(
        """version: "1.0.0"
last_updated: "2026-04-10T00:00:00Z"
commands:
  speckit.plan:
    description: "plan"
    mode: deterministic
    emits:
      - event: plan_started
        required_fields: []
  speckit.closeout:
    description: "close a task"
    mode: legacy
    emits:
      - event: tests_passed
        required_fields: []
      - event: commit_created
        required_fields:
          - commit_sha
      - event: offline_qa_started
        required_fields: []
      - event: offline_qa_passed
        required_fields:
          - qa_run_id
      - event: task_closed
        required_fields: []
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(pipeline_ledger, "_resolve_manifest_path", lambda: manifest_path)

    pipeline_ledger.cmd_validate_manifest(SimpleNamespace())


@pytest.mark.parametrize(
    ("manifest_body", "expected_fragment"),
    [
        (
            """version: "1.0.0"
last_updated: "2026-04-10T00:00:00Z"
commands:
  speckit.unknown:
    description: "unknown"
    mode: deterministic
    emits:
      - event: made_up_event
        required_fields: []
""",
            "not in pipeline or task ledger transition rules",
        ),
        (
            """version: "1.0.0"
last_updated: "2026-04-10T00:00:00Z"
commands:
  speckit.plan:
    description: "plan"
    mode: deterministic
    emits:
      - event: plan_started
        required_fields: []
manual_events:
  tests_passed: {}
""",
            "Manual event 'tests_passed' not in ALLOWED_PIPELINE_TRANSITIONS",
        ),
    ],
)
def test_cmd_validate_manifest_rejects_wrong_domain_events(
    tmp_path: Path,
    monkeypatch,
    capsys,
    manifest_body: str,
    expected_fragment: str,
) -> None:
    manifest_path = tmp_path / "command-manifest.yaml"
    manifest_path.write_text(manifest_body, encoding="utf-8")

    monkeypatch.setattr(pipeline_ledger, "_resolve_manifest_path", lambda: manifest_path)

    with pytest.raises(SystemExit):
        pipeline_ledger.cmd_validate_manifest(SimpleNamespace())

    captured = capsys.readouterr()
    assert expected_fragment in captured.err
