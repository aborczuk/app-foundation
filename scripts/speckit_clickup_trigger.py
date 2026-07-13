"""Scaffold CLI for future ClickUp-triggered speckit implement starts."""

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


def render_response(request: ClickUpTriggerRequest) -> dict[str, object]:
    """Render a deterministic scaffold response without invoking repo gates yet."""
    return {
        "ok": True,
        "mode": "scaffold",
        "request": asdict(request),
        "next_step": (
            "Ledger-gated ClickUp trigger execution is intentionally deferred to later "
            "feature 048 tasks."
        ),
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
