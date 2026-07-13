"""CLI helpers for future ClickUp-triggered speckit implement starts."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from typing import Sequence


@dataclass(frozen=True)
class ClickUpTriggerRequest:
    """Normalized request envelope for future ClickUp-triggered implement work."""

    feature_id: str
    task_id: str
    clickup_task_id: str
    actor: str
    dry_run: bool


def build_parser() -> argparse.ArgumentParser:
    """Build the scaffold CLI parser."""
    parser = argparse.ArgumentParser(
        description="Prepare a ClickUp-triggered speckit implement request scaffold."
    )
    parser.add_argument("--feature-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--clickup-task-id", required=True)
    parser.add_argument("--actor", default="clickup")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Reserved for the future ledger-gated execution path.",
    )
    return parser


def parse_request(argv: Sequence[str]) -> tuple[ClickUpTriggerRequest, bool]:
    """Parse argv into a normalized scaffold request."""
    args = build_parser().parse_args(list(argv))
    request = ClickUpTriggerRequest(
        feature_id=args.feature_id,
        task_id=args.task_id,
        clickup_task_id=args.clickup_task_id,
        actor=args.actor,
        dry_run=not args.execute,
    )
    return request, bool(args.json)


def render_response(
    request: ClickUpTriggerRequest,
    *,
    mapping_count: int = 1,
    gate_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    """Render a deterministic trigger response for scaffold and gate-only flows."""
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


def main(argv: Sequence[str] | None = None) -> int:
    """Run the scaffold trigger CLI."""
    request, as_json = parse_request(argv if argv is not None else sys.argv[1:])
    payload = render_response(request)
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"Scaffolded ClickUp trigger request for {request.feature_id}/{request.task_id} "
            f"(dry_run={request.dry_run})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
