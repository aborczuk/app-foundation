"""Unit tests for the ClickUp trigger scaffold CLI."""

from __future__ import annotations

import json

import pytest

from scripts.speckit_clickup_trigger import (
    READY_FOR_IMPLEMENT_STATUS,
    ClickUpTriggerRequest,
    main,
    parse_request,
    render_response,
    resolve_request_mapping,
    status_is_start_request,
)
from src.mcp_clickup import SyncManifest
from src.mcp_clickup.manifest import ClickUpTaskMappingError


def test_parse_request_defaults_to_dry_run() -> None:
    """Parsing should keep scaffold requests in dry-run mode unless execute is requested."""
    request, as_json, manifest_path = parse_request(
        ["--feature-id", "048", "--task-id", "T002", "--clickup-task-id", "CU-2", "--json"]
    )

    assert request == ClickUpTriggerRequest(
        clickup_task_id="CU-2",
        feature_id="048",
        task_id="T002",
        actor="clickup",
        dry_run=True,
        status=READY_FOR_IMPLEMENT_STATUS,
    )
    assert as_json is True
    assert manifest_path.name == "clickup-manifest.json"


def test_parse_request_execute_disables_dry_run() -> None:
    """Execute mode should preserve the requested task identity while clearing dry-run mode."""
    request, as_json, _ = parse_request(
        ["--feature-id", "048", "--task-id", "T014", "--clickup-task-id", "CU-14", "--execute"]
    )

    assert request == ClickUpTriggerRequest(
        clickup_task_id="CU-14",
        feature_id="048",
        task_id="T014",
        actor="clickup",
        dry_run=False,
        status=READY_FOR_IMPLEMENT_STATUS,
    )
    assert as_json is False


def test_parse_request_allows_manifest_backed_mapping_resolution() -> None:
    """Feature and task ids may be omitted when the ClickUp task id will drive manifest lookup."""
    request, as_json, _ = parse_request(["--clickup-task-id", "CU-14", "--json"])

    assert request == ClickUpTriggerRequest(
        clickup_task_id="CU-14",
        feature_id="",
        task_id="",
        actor="clickup",
        dry_run=True,
        status=READY_FOR_IMPLEMENT_STATUS,
    )
    assert as_json is True


def test_parse_request_rejects_partial_explicit_mapping() -> None:
    """Explicit feature/task routing must provide both identifiers together."""
    with pytest.raises(SystemExit, match="feature_id_and_task_id_must_be_provided_together"):
        parse_request(["--feature-id", "048", "--clickup-task-id", "CU-14"])


def test_status_is_start_request_only_accepts_ready_for_implement() -> None:
    """Only the dedicated ready-for-implement transition should request repo work."""
    assert status_is_start_request("ready-for-implement") is True
    assert status_is_start_request("READY-FOR-IMPLEMENT") is True
    assert status_is_start_request("in progress") is False


def test_render_response_reports_scaffold_mode() -> None:
    """The scaffold response should advertise the deferred execution path."""
    payload = render_response(
        ClickUpTriggerRequest(
            feature_id="048",
            task_id="T002",
            clickup_task_id="CU-2",
            actor="clickup",
            dry_run=True,
            status=READY_FOR_IMPLEMENT_STATUS,
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
            status=READY_FOR_IMPLEMENT_STATUS,
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
            status=READY_FOR_IMPLEMENT_STATUS,
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
            status=READY_FOR_IMPLEMENT_STATUS,
        ),
        mapping_count=2,
    )

    assert payload["ok"] is False
    assert payload["decision"] == "rejected"
    assert payload["reason_code"] == "ambiguous_mapping"
    assert payload["mapping_count"] == 2
    assert payload["ledger_mutation"] is False


def test_render_response_ignores_non_ready_status() -> None:
    """Non-ready status updates should be ignored before any repo gate evaluation."""
    payload = render_response(
        ClickUpTriggerRequest(
            clickup_task_id="CU-16",
            feature_id="048",
            task_id="T016",
            actor="clickup",
            dry_run=False,
            status="in progress",
        )
    )

    assert payload["ok"] is True
    assert payload["decision"] == "ignored"
    assert payload["reason_code"] == "non_start_status"
    assert payload["ledger_mutation"] is False


def test_resolve_request_mapping_uses_manifest_subtask_id() -> None:
    """Manifest task projection metadata should resolve the ClickUp task back to repo ids."""
    manifest = SyncManifest(
        version="1",
        workspace_id="w1",
        space_id="s1",
        task_projection_meta={
            "048:T014": {
                "feature_num": "048",
                "task_id": "T014",
                "subtask_id": "CU-14",
                "title": "Resolve task mapping",
            }
        },
    )

    resolved = resolve_request_mapping(
        ClickUpTriggerRequest(
            clickup_task_id="CU-14",
            actor="clickup",
            dry_run=False,
            status=READY_FOR_IMPLEMENT_STATUS,
        ),
        manifest,
    )

    assert resolved.feature_id == "048"
    assert resolved.task_id == "T014"
    assert resolved.clickup_task_id == "CU-14"


def test_resolve_request_mapping_rejects_ambiguous_manifest_matches() -> None:
    """Multiple manifest matches for one ClickUp task id must fail explicitly."""
    manifest = SyncManifest(
        version="1",
        workspace_id="w1",
        space_id="s1",
        task_projection_meta={
            "048:T014": {"feature_num": "048", "task_id": "T014", "subtask_id": "CU-14"},
            "048:T015": {"feature_num": "048", "task_id": "T015", "subtask_id": "CU-14"},
        },
    )

    with pytest.raises(ClickUpTaskMappingError, match="ambiguous_mapping:CU-14"):
        resolve_request_mapping(
            ClickUpTriggerRequest(
                clickup_task_id="CU-14",
                actor="clickup",
                dry_run=False,
                status=READY_FOR_IMPLEMENT_STATUS,
            ),
            manifest,
        )


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
