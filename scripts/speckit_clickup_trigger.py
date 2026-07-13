"""CLI helpers for future ClickUp-triggered speckit implement starts."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Protocol, Sequence

from scripts import speckit_implement_step
from src.mcp_clickup import SyncManifest
from src.mcp_clickup.composio_adapter import ComposioClickUpAdapter
from src.mcp_clickup.manifest import ClickUpTaskMappingError, load_manifest, resolve_task_projection_mapping

READY_FOR_IMPLEMENT_STATUS = "ready-for-implement"


@dataclass(frozen=True)
class ClickUpTriggerRequest:
    """Normalized request envelope for future ClickUp-triggered implement work."""

    clickup_task_id: str
    feature_id: str = ""
    task_id: str = ""
    actor: str = "clickup"
    dry_run: bool = True
    status: str = READY_FOR_IMPLEMENT_STATUS


class TriggerRejectionReporter(Protocol):
    """Minimal contract for writing trigger rejection feedback back to ClickUp."""

    async def update_task(
        self,
        task_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Update one ClickUp task with rejection feedback."""


def build_parser() -> argparse.ArgumentParser:
    """Build the scaffold CLI parser."""
    parser = argparse.ArgumentParser(
        description="Prepare a ClickUp-triggered speckit implement request scaffold."
    )
    parser.add_argument("--clickup-task-id", required=True)
    parser.add_argument("--feature-id")
    parser.add_argument("--task-id")
    parser.add_argument("--actor", default="clickup")
    parser.add_argument("--status", default=READY_FOR_IMPLEMENT_STATUS)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--manifest-path",
        default=".speckit/clickup-manifest.json",
        help="Manifest path used when feature/task ids must be resolved from the ClickUp task id.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Reserved for the future ledger-gated execution path.",
    )
    return parser


def status_is_start_request(status: str) -> bool:
    """Return whether the external status transition should count as a start request."""
    return str(status).strip().lower() == READY_FOR_IMPLEMENT_STATUS


def _resolve_manifest_path(manifest_path: str) -> Path:
    """Normalize the manifest path used for ClickUp-task mapping lookups."""
    return Path(manifest_path).expanduser().resolve()


def parse_request(argv: Sequence[str]) -> tuple[ClickUpTriggerRequest, bool, Path, Path]:
    """Parse argv into a normalized scaffold request."""
    args = build_parser().parse_args(list(argv))
    feature_id = str(args.feature_id or "").strip()
    task_id = str(args.task_id or "").strip()
    if bool(feature_id) != bool(task_id):
        raise SystemExit("feature_id_and_task_id_must_be_provided_together")
    request = ClickUpTriggerRequest(
        clickup_task_id=args.clickup_task_id,
        feature_id=feature_id,
        task_id=task_id,
        actor=args.actor,
        dry_run=not args.execute,
        status=str(args.status).strip(),
    )
    return (
        request,
        bool(args.json),
        Path(str(args.repo_root)).expanduser().resolve(),
        _resolve_manifest_path(str(args.manifest_path)),
    )


def resolve_request_mapping(
    request: ClickUpTriggerRequest,
    manifest: SyncManifest,
) -> ClickUpTriggerRequest:
    """Fill missing repo identifiers from manifest task projection metadata."""
    if request.feature_id and request.task_id:
        return request
    mapping = resolve_task_projection_mapping(manifest, request.clickup_task_id)
    return replace(
        request,
        feature_id=str(mapping.get("feature_num", "")).strip(),
        task_id=str(mapping.get("task_id", "")).strip(),
    )


def render_response(
    request: ClickUpTriggerRequest,
    *,
    mapping_count: int = 1,
    gate_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    """Render a deterministic trigger response for scaffold and gate-only flows."""
    if not status_is_start_request(request.status):
        return {
            "ok": True,
            "mode": "trigger_gate",
            "decision": "ignored",
            "reason_code": "non_start_status",
            "ledger_mutation": False,
            "request": asdict(request),
            "next_step": "Ignore ClickUp status transitions unless they enter ready-for-implement.",
        }

    if mapping_count != 1:
        return {
            "ok": False,
            "mode": "trigger_gate",
            "decision": "rejected",
            "reason_code": "ambiguous_mapping",
            "mapping_count": mapping_count,
            "ledger_mutation": False,
            "request": asdict(request),
            "next_step": "Resolve ClickUp-to-repo mapping ambiguity before starting implement work.",
        }

    if gate_summary is None:
        return {
            "ok": True,
            "mode": "scaffold",
            "request": asdict(request),
            "next_step": (
                "Ledger-gated ClickUp trigger execution is intentionally deferred to later "
                "feature 048 tasks."
            ),
        }

    blocking_reason = str(gate_summary.get("blocking_reason") or "").strip() or None
    gate_payload = {
        "feature_id": str(gate_summary.get("feature_id") or request.feature_id),
        "task_id": str(gate_summary.get("task_id") or request.task_id),
        "parallel": bool(gate_summary.get("parallel", False)),
        "task_started": bool(gate_summary.get("task_started", False)),
        "task_closed": bool(gate_summary.get("task_closed", False)),
        "blocking_reason": blocking_reason,
    }
    if blocking_reason is not None:
        return {
            "ok": False,
            "mode": "trigger_gate",
            "decision": "blocked",
            "reason_code": "task_not_startable",
            "ledger_mutation": False,
            "request": asdict(request),
            "gate": gate_payload,
            "next_step": "Keep the ClickUp task out of implement until the repo gate reports eligible.",
        }
    return {
        "ok": True,
        "mode": "trigger_gate",
        "decision": "eligible",
        "ledger_mutation": False,
        "request": asdict(request),
        "gate": gate_payload,
        "next_step": "Route this request into the normal repo implement flow.",
    }


def render_started_response(
    request: ClickUpTriggerRequest,
    *,
    start_summary: dict[str, Any],
) -> dict[str, object]:
    """Render a deterministic start-or-resume result for one explicit trigger request."""
    return {
        "ok": True,
        "mode": "trigger_execute",
        "decision": str(start_summary.get("task_action") or "started"),
        "ledger_mutation": str(start_summary.get("task_action")) == "started",
        "request": asdict(request),
        "start": {
            "feature_id": str(start_summary.get("feature_id") or request.feature_id),
            "task_id": str(start_summary.get("task_id") or request.task_id),
            "task_action": str(start_summary.get("task_action") or ""),
            "task_attempt": int(start_summary.get("task_attempt") or 0),
            "parallel": bool(start_summary.get("parallel", False)),
            "task_owner_actor": str(start_summary.get("task_owner_actor") or request.actor),
        },
        "next_step": "Continue normal repo implement orchestration from the started task.",
    }


def _rejection_message(payload: dict[str, object]) -> str:
    """Build one operator-visible rejection message from a trigger payload."""
    reason_code = str(payload.get("reason_code") or "trigger_rejected")
    gate = payload.get("gate")
    if isinstance(gate, dict):
        blocking_reason = str(gate.get("blocking_reason") or "").strip()
        if blocking_reason:
            return f"{reason_code}: {blocking_reason}"
    return f"{reason_code}: trigger request was rejected by repo-side gating"


async def write_rejection_feedback(
    reporter: TriggerRejectionReporter | ComposioClickUpAdapter,
    request: ClickUpTriggerRequest,
    payload: dict[str, object],
) -> dict[str, object]:
    """Write one blocked or ambiguous trigger rejection back to the ClickUp task."""
    result = await reporter.update_task(
        request.clickup_task_id,
        description=_rejection_message(payload),
    )
    response = dict(result)
    response["feedback_written"] = True
    response["clickup_task_id"] = request.clickup_task_id
    return response


def _resolve_gate_summary(
    *,
    repo_root: Path,
    request: ClickUpTriggerRequest,
) -> dict[str, Any]:
    """Resolve the explicit task gate summary for one request."""
    feature_dir = speckit_implement_step._resolve_feature_dir(repo_root, request.feature_id)
    return speckit_implement_step._resolve_explicit_task_start_gate(
        repo_root=repo_root,
        feature_dir=feature_dir,
        feature_id=request.feature_id,
        task_id=request.task_id,
        actor=request.actor,
    )


def _start_request(
    *,
    repo_root: Path,
    request: ClickUpTriggerRequest,
) -> dict[str, Any]:
    """Start or resume one explicit request through the normal ledger-owned seam."""
    feature_dir = speckit_implement_step._resolve_feature_dir(repo_root, request.feature_id)
    return speckit_implement_step._start_explicit_task_request(
        repo_root=repo_root,
        feature_dir=feature_dir,
        feature_id=request.feature_id,
        task_id=request.task_id,
        actor=request.actor,
        correlation_id=f"clickup:{request.clickup_task_id}",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the scaffold trigger CLI."""
    request, as_json, repo_root, manifest_path = parse_request(argv if argv is not None else sys.argv[1:])
    resolved_request = request
    if status_is_start_request(request.status) and (not request.feature_id or not request.task_id):
        if not manifest_path.exists():
            payload = {
                "ok": False,
                "mode": "trigger_gate",
                "decision": "rejected",
                "reason_code": "manifest_missing",
                "ledger_mutation": False,
                "request": asdict(request),
                "manifest_path": str(manifest_path),
            }
        else:
            try:
                resolved_request = resolve_request_mapping(request, load_manifest(manifest_path))
                if resolved_request.dry_run:
                    payload = render_response(
                        resolved_request,
                        gate_summary=_resolve_gate_summary(repo_root=repo_root, request=resolved_request),
                    )
                else:
                    payload = render_started_response(
                        resolved_request,
                        start_summary=_start_request(repo_root=repo_root, request=resolved_request),
                    )
            except ClickUpTaskMappingError as exc:
                reason_code, _, clickup_task_id = str(exc).partition(":")
                mapping_count = 2 if reason_code == "ambiguous_mapping" else 0
                payload = render_response(request, mapping_count=mapping_count)
                payload["clickup_task_id"] = clickup_task_id
                payload["manifest_path"] = str(manifest_path)
    else:
        if status_is_start_request(resolved_request.status) and resolved_request.feature_id and resolved_request.task_id:
            if resolved_request.dry_run:
                payload = render_response(
                    resolved_request,
                    gate_summary=_resolve_gate_summary(repo_root=repo_root, request=resolved_request),
                )
            else:
                payload = render_started_response(
                    resolved_request,
                    start_summary=_start_request(repo_root=repo_root, request=resolved_request),
                )
        else:
            payload = render_response(resolved_request)
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"Scaffolded ClickUp trigger request for "
            f"{resolved_request.feature_id or '?'}:{resolved_request.task_id or '?'} "
            f"(dry_run={resolved_request.dry_run}, status={resolved_request.status})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
