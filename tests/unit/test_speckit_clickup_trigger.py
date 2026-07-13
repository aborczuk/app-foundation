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
