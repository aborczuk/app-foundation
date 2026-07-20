"""Unit tests for the ClickUp trigger scaffold CLI."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from scripts import speckit_clickup_trigger as trigger_module
from scripts.speckit_clickup_trigger import (
    DONE_STATUS,
    READY_FOR_IMPLEMENT_STATUS,
    ClickUpTriggerRequest,
    main,
    parse_request,
    render_response,
    resolve_request_mapping,
    status_is_done_signal,
    status_is_start_request,
    write_rejection_feedback,
)
from src.mcp_clickup import SyncManifest
from src.mcp_clickup.manifest import ClickUpTaskMappingError


def test_parse_request_defaults_to_dry_run() -> None:
    """Parsing should keep scaffold requests in dry-run mode unless execute is requested."""
    request, as_json, repo_root, manifest_path = parse_request(
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
    assert repo_root == Path(".").resolve()
    assert manifest_path.name == "clickup-manifest.json"


def test_parse_request_execute_disables_dry_run() -> None:
    """Execute mode should preserve the requested task identity while clearing dry-run mode."""
    request, as_json, _, _ = parse_request(
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
    request, as_json, _, _ = parse_request(["--clickup-task-id", "CU-14", "--json"])

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


def test_status_is_done_signal_only_accepts_done() -> None:
    """Only the exact done signal should be treated as an external closeout claim."""
    assert status_is_done_signal("done") is True
    assert status_is_done_signal("DONE") is True
    assert status_is_done_signal("ready-for-implement") is False


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
    gate = payload["gate"]
    assert isinstance(gate, dict)
    assert gate["task_id"] == "T014"


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
    gate = payload["gate"]
    assert isinstance(gate, dict)
    assert gate["blocking_reason"] == (
        "Cannot start T015; prior task T014 is not closed in the ledger"
    )


def test_render_response_reports_done_drift_when_repo_task_is_open() -> None:
    """A ClickUp done status must not override an open repo task."""
    payload = render_response(
        ClickUpTriggerRequest(
            feature_id="048",
            task_id="T015",
            clickup_task_id="CU-15",
            actor="clickup",
            dry_run=True,
            status=DONE_STATUS,
        ),
        gate_summary={
            "feature_id": "048",
            "task_id": "T015",
            "parallel": False,
            "task_started": True,
            "task_closed": False,
            "blocking_reason": None,
        },
    )

    assert payload["ok"] is False
    assert payload["decision"] == "drift"
    assert payload["reason_code"] == "external_done_repo_open"
    assert payload["ledger_mutation"] is False
    gate = payload["gate"]
    assert isinstance(gate, dict)
    assert gate["task_closed"] is False


def test_render_response_reports_ready_drift_when_repo_task_is_closed() -> None:
    """A ClickUp ready status must not reopen a repo task that is already closed."""
    payload = render_response(
        ClickUpTriggerRequest(
            feature_id="048",
            task_id="T015",
            clickup_task_id="CU-15",
            actor="clickup",
            dry_run=True,
            status=READY_FOR_IMPLEMENT_STATUS,
        ),
        gate_summary={
            "feature_id": "048",
            "task_id": "T015",
            "parallel": False,
            "task_started": True,
            "task_closed": True,
            "blocking_reason": None,
        },
    )

    assert payload["ok"] is False
    assert payload["decision"] == "drift"
    assert payload["reason_code"] == "external_ready_repo_closed"
    assert payload["ledger_mutation"] is False
    gate = payload["gate"]
    assert isinstance(gate, dict)
    assert gate["task_closed"] is True


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


class _RecordingReporter:
    """Minimal async reporter for trigger rejection feedback tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object | None]]] = []

    async def update_task(
        self,
        task_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            (
                task_id,
                {"name": name, "description": description, "status": status},
            )
        )
        return {"id": task_id}


def test_write_rejection_feedback_updates_clickup_task_description() -> None:
    """Blocked requests should produce one operator-visible rejection update."""
    reporter = _RecordingReporter()
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

    result = asyncio.run(
        write_rejection_feedback(
            reporter,
            ClickUpTriggerRequest(
                feature_id="048",
                task_id="T015",
                clickup_task_id="CU-15",
                actor="clickup",
                dry_run=False,
                status=READY_FOR_IMPLEMENT_STATUS,
            ),
            payload,
        )
    )

    assert result["feedback_written"] is True
    assert reporter.calls == [
        (
            "CU-15",
            {
                "name": None,
                "description": "task_not_startable: Cannot start T015; prior task T014 is not closed in the ledger",
                "status": None,
            },
        )
    ]


def test_write_rejection_feedback_handles_ambiguous_mapping_rejection() -> None:
    """Ambiguous mapping rejections should still write a clear operator-visible feedback update."""
    reporter = _RecordingReporter()
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

    result = asyncio.run(
        write_rejection_feedback(
            reporter,
            ClickUpTriggerRequest(
                feature_id="048",
                task_id="T016",
                clickup_task_id="CU-16",
                actor="clickup",
                dry_run=False,
                status=READY_FOR_IMPLEMENT_STATUS,
            ),
            payload,
        )
    )

    assert result["feedback_written"] is True
    assert reporter.calls == [
        (
            "CU-16",
            {
                "name": None,
                "description": "ambiguous_mapping: trigger request was rejected by repo-side gating",
                "status": None,
            },
        )
    ]


def test_main_execute_starts_explicit_task(monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Execute mode should route an explicit request through the mutating start seam."""
    monkeypatch.setattr(
        trigger_module,
        "_start_request",
        lambda *, repo_root, request: {
            "feature_id": request.feature_id,
            "task_id": request.task_id,
            "task_action": "started",
            "task_attempt": 1,
            "parallel": False,
            "task_owner_actor": request.actor,
        },
    )

    exit_code = main(
        [
            "--feature-id",
            "048",
            "--task-id",
            "T015",
            "--clickup-task-id",
            "CU-15",
            "--execute",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "trigger_execute"
    assert payload["decision"] == "started"
    assert payload["ledger_mutation"] is True


def test_main_dry_run_reports_gate_summary(monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Dry-run ready requests should surface the non-mutating gate result for the resolved task."""
    monkeypatch.setattr(
        trigger_module,
        "_resolve_gate_summary",
        lambda *, repo_root, request: {
            "feature_id": request.feature_id,
            "task_id": request.task_id,
            "parallel": False,
            "task_started": False,
            "task_closed": False,
            "blocking_reason": None,
        },
    )

    exit_code = main(
        [
            "--feature-id",
            "048",
            "--task-id",
            "T015",
            "--clickup-task-id",
            "CU-15",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "trigger_gate"
    assert payload["decision"] == "eligible"


def test_render_response_ignores_non_ready_status() -> None:
    """Non-actionable status updates should be ignored before any repo gate evaluation."""
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
    assert payload["reason_code"] == "non_actionable_status"
    assert payload["ledger_mutation"] is False


def test_main_done_status_reports_gate_drift(monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Done-status requests should stay non-mutating and surface repo-vs-ClickUp drift."""
    monkeypatch.setattr(
        trigger_module,
        "_resolve_gate_summary",
        lambda *, repo_root, request: {
            "feature_id": request.feature_id,
            "task_id": request.task_id,
            "parallel": False,
            "task_started": True,
            "task_closed": False,
            "blocking_reason": None,
        },
    )

    exit_code = main(
        [
            "--feature-id",
            "048",
            "--task-id",
            "T015",
            "--clickup-task-id",
            "CU-15",
            "--status",
            DONE_STATUS,
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "trigger_gate"
    assert payload["decision"] == "drift"
    assert payload["reason_code"] == "external_done_repo_open"


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
