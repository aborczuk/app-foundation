"""Unit tests for the ClickUp trigger scaffold CLI."""

from __future__ import annotations

import json

import pytest

from scripts.speckit_clickup_trigger import ClickUpTriggerRequest, main, parse_request, render_response


def test_parse_request_defaults_to_dry_run() -> None:
    """Parsing should keep scaffold requests in dry-run mode unless execute is requested."""
    request, as_json = parse_request(
        ["--feature-id", "048", "--task-id", "T002", "--clickup-task-id", "CU-2", "--json"]
    )

    assert request == ClickUpTriggerRequest(
        feature_id="048",
        task_id="T002",
        clickup_task_id="CU-2",
        actor="clickup",
        dry_run=True,
    )
    assert as_json is True


def test_parse_request_execute_disables_dry_run() -> None:
    """Execute mode should preserve the requested task identity while clearing dry-run mode."""
    request, as_json = parse_request(
        ["--feature-id", "048", "--task-id", "T014", "--clickup-task-id", "CU-14", "--execute"]
    )

    assert request == ClickUpTriggerRequest(
        feature_id="048",
        task_id="T014",
        clickup_task_id="CU-14",
        actor="clickup",
        dry_run=False,
    )
    assert as_json is False


def test_render_response_reports_scaffold_mode() -> None:
    """The scaffold response should advertise the deferred execution path."""
    payload = render_response(
        ClickUpTriggerRequest(
            feature_id="048",
            task_id="T002",
            clickup_task_id="CU-2",
            actor="clickup",
            dry_run=True,
        )
    )

    assert payload["ok"] is True
    assert payload["mode"] == "scaffold"
    assert "Ledger-gated ClickUp trigger execution" in str(payload["next_step"])


def test_render_response_reports_eligible_gate_summary() -> None:
    """An eligible gate summary should stay non-mutating while advertising readiness."""
    payload = render_response(
        ClickUpTriggerRequest(
            feature_id="048",
            task_id="T014",
            clickup_task_id="CU-14",
            actor="clickup",
            dry_run=False,
        ),
        gate_summary={
            "feature_id": "048",
            "task_id": "T014",
            "parallel": False,
            "task_started": False,
            "task_closed": False,
            "blocking_reason": None,
        },
    )

    assert payload["ok"] is True
    assert payload["mode"] == "trigger_gate"
    assert payload["decision"] == "eligible"
    assert payload["ledger_mutation"] is False
    assert payload["gate"]["task_id"] == "T014"


def test_render_response_reports_blocked_gate_summary() -> None:
    """A blocked gate summary should preserve the repo reason without pretending work started."""
    payload = render_response(
        ClickUpTriggerRequest(
            feature_id="048",
            task_id="T015",
            clickup_task_id="CU-15",
            actor="clickup",
            dry_run=False,
        ),
        gate_summary={
            "feature_id": "048",
            "task_id": "T015",
            "parallel": False,
            "task_started": False,
            "task_closed": False,
            "blocking_reason": "Cannot start T015; prior task T014 is not closed in the ledger",
        },
    )

    assert payload["ok"] is False
    assert payload["decision"] == "blocked"
    assert payload["reason_code"] == "task_not_startable"
    assert payload["ledger_mutation"] is False
    assert payload["gate"]["blocking_reason"] == (
        "Cannot start T015; prior task T014 is not closed in the ledger"
    )


def test_render_response_rejects_ambiguous_mapping() -> None:
    """Ambiguous ClickUp mappings should be rejected before any ledger mutation is considered."""
    payload = render_response(
        ClickUpTriggerRequest(
            feature_id="048",
            task_id="T016",
            clickup_task_id="CU-16",
            actor="clickup",
            dry_run=False,
        ),
        mapping_count=2,
    )

    assert payload["ok"] is False
    assert payload["decision"] == "rejected"
    assert payload["reason_code"] == "ambiguous_mapping"
    assert payload["mapping_count"] == 2
    assert payload["ledger_mutation"] is False


def test_main_emits_json_payload(capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI should print a deterministic JSON scaffold payload."""
    exit_code = main(
        ["--feature-id", "048", "--task-id", "T002", "--clickup-task-id", "CU-2", "--json"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["request"]["task_id"] == "T002"
    assert payload["request"]["dry_run"] is True
