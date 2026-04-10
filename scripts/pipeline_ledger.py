#!/usr/bin/env python3
"""Append-only pipeline ledger tooling for feature-level phase audit trails.

Scope: feature-level phase events (plan_started, plan_approved, solution_approved, etc.)
This is distinct from task_ledger.py, which is task-scoped (T001 format).

Two-ledger hierarchy:
  pipeline-ledger.jsonl — feature-level, no task_id, uses phase field
  task-ledger.jsonl     — task-level, requires task_id (T001 format)

Pipeline events bracket feature-level phases; task events bracket per-task implementation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

try:
    import yaml
except ImportError:
    yaml = None

DEFAULT_LEDGER = Path(".speckit/pipeline-ledger.jsonl")
FEATURE_ID_RE = re.compile(r"^\d{3}$")


def _load_manifest_events() -> tuple[set[str], dict[str, set[str]]]:
    """Load valid events and required fields from command-manifest.yaml.

    Returns: (VALID_PIPELINE_EVENTS, REQUIRED_BY_PIPELINE_EVENT)
    Falls back to hardcoded set if manifest is missing or unparseable.
    """
    manifest_path = Path(__file__).parent.parent / ".specify" / "command-manifest.yaml"

    if not manifest_path.exists() or yaml is None:
        # Fallback to hardcoded values
        valid = {
            "backlog_registered",
            "spec_clarified",
            "research_completed",
            "plan_started",
            "planreview_completed",
            "feasibility_spike_completed",
            "feasibility_spike_failed",
            "plan_approved",
            "tasking_completed",
            "sketch_completed",
            "estimation_completed",
            "solutionreview_completed",
            "solution_approved",
            "analysis_completed",
            "e2e_generated",
            "feature_closed",
        }
        required = {
            "feasibility_spike_completed": {"spike_artifact", "fq_count"},
            "feasibility_spike_failed": {"failed_fq"},
            "plan_approved": {"feasibility_required"},
            "solution_approved": {"task_count", "story_count", "estimate_points"},
            "analysis_completed": {"critical_count"},
            "e2e_generated": {"e2e_artifact"},
            "planreview_completed": {"fq_count", "questions_asked"},
            "solutionreview_completed": {"critical_count", "high_count"},
        }
        return valid, required

    try:
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        # Extract events from commands
        valid = set()
        required = {}

        for cmd_def in manifest.get("commands", {}).values():
            for emit in cmd_def.get("emits", []):
                event_name = emit.get("event", "")
                if event_name:
                    valid.add(event_name)
                    req_fields = emit.get("required_fields", [])
                    if req_fields:
                        required[event_name] = set(req_fields)

        # Add manual events
        for event_name in manifest.get("manual_events", {}):
            valid.add(event_name)

        return valid, required
    except Exception as e:
        print(f"WARNING: Failed to load manifest: {e}. Using fallback.", file=sys.stderr)
        # Return hardcoded fallback values
        valid = {
            "backlog_registered",
            "spec_clarified",
            "research_completed",
            "plan_started",
            "planreview_completed",
            "feasibility_spike_completed",
            "feasibility_spike_failed",
            "plan_approved",
            "tasking_completed",
            "sketch_completed",
            "estimation_completed",
            "solutionreview_completed",
            "solution_approved",
            "analysis_completed",
            "e2e_generated",
            "feature_closed",
        }
        required = {
            "feasibility_spike_completed": {"spike_artifact", "fq_count"},
            "feasibility_spike_failed": {"failed_fq"},
            "plan_approved": {"feasibility_required"},
            "solution_approved": {"task_count", "story_count", "estimate_points"},
            "analysis_completed": {"critical_count"},
            "e2e_generated": {"e2e_artifact"},
            "planreview_completed": {"fq_count", "questions_asked"},
            "solutionreview_completed": {"critical_count", "high_count"},
        }
        return valid, required


VALID_PIPELINE_EVENTS, REQUIRED_BY_PIPELINE_EVENT = _load_manifest_events()

# Ordered pipeline phases — each event is a valid "next" from one or more predecessors.
# The pipeline is not strictly linear (feasibility is conditional; clarify is optional).
ALLOWED_PIPELINE_TRANSITIONS: dict[str, set[str | None]] = {
    "backlog_registered": {None},
    "spec_clarified": {"backlog_registered", "spec_clarified"},
    "research_completed": {"backlog_registered", "spec_clarified"},
    "plan_started": {"research_completed"},
    "planreview_completed": {"plan_started", "planreview_completed"},
    "feasibility_spike_completed": {"planreview_completed"},
    "feasibility_spike_failed": {"planreview_completed", "feasibility_spike_failed"},
    "plan_approved": {"planreview_completed", "feasibility_spike_completed"},
    "tasking_completed": {"plan_approved", "tasking_completed"},
    "sketch_completed": {"tasking_completed", "sketch_completed"},
    "estimation_completed": {"sketch_completed", "estimation_completed"},
    "solutionreview_completed": {"estimation_completed", "solutionreview_completed"},
    "solution_approved": {"solutionreview_completed"},
    "analysis_completed": {"solution_approved"},
    "e2e_generated": {"analysis_completed"},  # e2e MUST follow analysis (enforces analysis is required before impl)
    "feature_closed": {"e2e_generated"},
}


@dataclass
class PipelineState:
    """Runtime state for a single feature moving through pipeline phases."""

    last_event: str | None = None
    approved_plan: bool = False
    approved_solution: bool = False
    analysis_clean: bool = False


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fail(message: str) -> NoReturn:
    """Print an error and terminate with exit status 1."""
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def ensure_feature_id(feature_id: str) -> None:
    """Assert feature_id matches the canonical NNN format."""
    if not FEATURE_ID_RE.match(feature_id):
        fail(f"Invalid feature_id {feature_id!r}. Expected format NNN, e.g. 018.")


def resolve_actor(explicit_actor: str | None) -> str:
    """Resolve actor identity from explicit flag or known environment variables."""
    actor = (explicit_actor or "").strip()
    if actor:
        return actor
    for env_var in ("SPECKIT_AGENT_ID", "CODEX_AGENT_ID", "GITHUB_ACTOR", "USER"):
        value = (os.environ.get(env_var) or "").strip()
        if value:
            return value
    return "unknown"


def read_events(path: Path) -> list[dict[str, Any]]:
    """Load pipeline ledger events from JSONL."""
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for idx, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                fail(f"{path}:{idx}: invalid JSON ({exc})")
            payload["_line"] = idx
            events.append(payload)
    return events


def validate_event_shape(event: dict[str, Any], *, line_hint: str) -> list[str]:
    """Validate required fields and per-event shape constraints."""
    errors: list[str] = []
    event_name = str(event.get("event", "")).strip()
    feature_id = str(event.get("feature_id", "")).strip()
    timestamp = str(event.get("timestamp_utc", "")).strip()

    if event_name not in VALID_PIPELINE_EVENTS:
        errors.append(f"{line_hint}: invalid pipeline event {event_name!r}")
    if not FEATURE_ID_RE.match(feature_id):
        errors.append(f"{line_hint}: invalid feature_id {feature_id!r}")
    if not timestamp:
        errors.append(f"{line_hint}: missing timestamp_utc")
    if "task_id" in event:
        errors.append(
            f"{line_hint}: pipeline events must not contain task_id — "
            "use task-ledger.jsonl for task-scoped events"
        )

    required_fields = REQUIRED_BY_PIPELINE_EVENT.get(event_name, set())
    for field_name in required_fields:
        value = event.get(field_name)
        if value is None or str(value).strip() == "":
            errors.append(
                f"{line_hint}: event {event_name!r} missing required field {field_name!r}"
            )

    if event_name == "analysis_completed":
        try:
            count = int(event.get("critical_count", -1))
        except (TypeError, ValueError):
            count = -1
        if count != 0:
            errors.append(
                f"{line_hint}: analysis_completed.critical_count must be 0 to emit "
                f"(got {event.get('critical_count')!r})"
            )

    return errors


def validate_sequence(
    events: list[dict[str, Any]],
) -> tuple[list[str], dict[str, PipelineState]]:
    """Validate pipeline event ordering and derive per-feature state."""
    errors: list[str] = []
    feature_states: dict[str, PipelineState] = {}

    for idx, event in enumerate(events, start=1):
        line_no = event.get("_line", idx)
        line_hint = f"line {line_no}"

        shape_errors = validate_event_shape(event, line_hint=line_hint)
        if shape_errors:
            errors.extend(shape_errors)
            continue

        feature_id = str(event["feature_id"])
        event_name = str(event["event"])

        state = feature_states.setdefault(feature_id, PipelineState())

        allowed_prev = ALLOWED_PIPELINE_TRANSITIONS.get(event_name, set())
        if state.last_event not in allowed_prev:
            errors.append(
                f"{line_hint}: invalid pipeline transition for feature {feature_id}: "
                f"{state.last_event!r} -> {event_name!r}"
            )

        if event_name == "plan_approved":
            state.approved_plan = True
        elif event_name == "solution_approved":
            state.approved_solution = True
        elif event_name == "analysis_completed":
            state.analysis_clean = True

        state.last_event = event_name

    return errors, feature_states


def cmd_append(args: argparse.Namespace) -> None:
    """Append one validated immutable pipeline event to the ledger."""
    ledger_path = Path(args.file)
    ensure_feature_id(args.feature_id)

    if args.event not in VALID_PIPELINE_EVENTS:
        fail(
            f"Invalid pipeline event {args.event!r}. "
            f"Valid events: {sorted(VALID_PIPELINE_EVENTS)}"
        )

    existing = read_events(ledger_path)

    event: dict[str, Any] = {
        "timestamp_utc": args.timestamp_utc or utc_now_iso(),
        "feature_id": args.feature_id,
        "phase": args.phase or "",
        "event": args.event,
        "actor": resolve_actor(args.actor),
    }

    optional_values = {
        "fq_count": args.fq_count,
        "questions_asked": args.questions_asked,
        "spike_artifact": args.spike_artifact,
        "failed_fq": args.failed_fq,
        "feasibility_required": args.feasibility_required,
        "task_count": args.task_count,
        "story_count": args.story_count,
        "estimate_points": args.estimate_points,
        "tasks_sketched": args.tasks_sketched,
        "acceptance_tests_written": args.acceptance_tests_written,
        "critical_count": args.critical_count,
        "high_count": args.high_count,
        "e2e_artifact": args.e2e_artifact,
        "details": args.details,
    }
    for key, value in optional_values.items():
        if value is None:
            continue
        event[key] = value

    provisional = [dict(item) for item in existing] + [dict(event)]
    errors, _ = validate_sequence(provisional)
    if errors:
        print("ERROR: append rejected due to pipeline sequence validation failure:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        raise SystemExit(1)

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")

    print(f"Appended pipeline event {args.event} for feature {args.feature_id}")


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate an existing pipeline ledger and print a concise feature summary."""
    ledger_path = Path(args.file)
    events = read_events(ledger_path)
    if not events:
        print(f"No pipeline events found at {ledger_path}.")
        return

    errors, feature_states = validate_sequence(events)
    if errors:
        print("Pipeline ledger validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Pipeline ledger validation passed ({len(events)} events).")
    for feature_id in sorted(feature_states):
        state = feature_states[feature_id]
        print(
            f"- feature {feature_id}: last_event={state.last_event!r} "
            f"plan_approved={state.approved_plan} "
            f"solution_approved={state.approved_solution} "
            f"analysis_clean={state.analysis_clean}"
        )


def cmd_validate_manifest(args: argparse.Namespace) -> None:
    """Validate the command manifest: templates exist, events are declared, etc."""
    if not yaml:
        fail("PyYAML is required to validate manifest. Install with: pip install pyyaml")

    manifest_path = Path(__file__).parent.parent / ".specify" / "command-manifest.yaml"
    template_dir = Path(__file__).parent.parent / ".specify" / "templates"

    if not manifest_path.exists():
        fail(f"Manifest not found: {manifest_path}")

    try:
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)
    except Exception as e:
        fail(f"Failed to parse manifest: {e}")

    errors = []

    # Check 1: All declared templates exist
    for cmd_name, cmd_def in manifest.get("commands", {}).items():
        for artifact in cmd_def.get("artifacts", []):
            template_name = artifact.get("template", "")
            if template_name and template_name != "":  # Skip empty templates (LLM-generated)
                template_path = template_dir / template_name
                if not template_path.exists():
                    errors.append(
                        f"Command '{cmd_name}': template missing: {template_name}"
                    )

    # Check 2: All events are reachable in ALLOWED_PIPELINE_TRANSITIONS
    declared_events = set()
    for cmd_def in manifest.get("commands", {}).values():
        for emit in cmd_def.get("emits", []):
            event = emit.get("event", "")
            if event:
                declared_events.add(event)

    for event in declared_events:
        if event not in ALLOWED_PIPELINE_TRANSITIONS:
            errors.append(
                f"Event '{event}' declared in manifest but not in ALLOWED_PIPELINE_TRANSITIONS"
            )

    # Check 3: Manual events are also in ALLOWED_PIPELINE_TRANSITIONS
    for event in manifest.get("manual_events", {}):
        if event not in ALLOWED_PIPELINE_TRANSITIONS:
            errors.append(
                f"Manual event '{event}' not in ALLOWED_PIPELINE_TRANSITIONS"
            )

    if errors:
        print("Manifest validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Manifest validation passed.")
    print(f"- Commands: {len(manifest.get('commands', {}))}")
    print(f"- Events declared: {len(declared_events)}")
    print(f"- Templates: {len(list(template_dir.glob('*.md'))) + len(list(template_dir.glob('*.sh')))}")


def cmd_assert_phase_complete(args: argparse.Namespace) -> None:
    """Assert that a required pipeline phase event has been emitted for a feature."""
    ledger_path = Path(args.file)
    ensure_feature_id(args.feature_id)

    if args.event not in VALID_PIPELINE_EVENTS:
        fail(
            f"Invalid pipeline event {args.event!r}. "
            f"Valid events: {sorted(VALID_PIPELINE_EVENTS)}"
        )

    events = read_events(ledger_path)
    errors, _ = validate_sequence(events)
    if errors:
        print("Pipeline ledger is invalid; cannot assert phase complete:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        raise SystemExit(1)

    matched = [
        e for e in events
        if str(e.get("feature_id")) == args.feature_id
        and str(e.get("event")) == args.event
    ]
    if not matched:
        fail(
            f"Phase gate FAILED: no {args.event!r} event found for feature {args.feature_id} "
            f"in {ledger_path}. Run the required pipeline phase before proceeding."
        )

    print(
        f"Phase gate PASSED: {args.event} found for feature {args.feature_id} "
        f"(recorded at {matched[-1].get('timestamp_utc', 'unknown')})."
    )


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        description=(
            "Append-only pipeline ledger operations for feature-level phase audit trails. "
            "Distinct from task-ledger.jsonl (task-scoped). "
            "Use this for plan_approved, solution_approved, feasibility_spike_completed, etc."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- append ---
    append_p = sub.add_parser("append", help="Append a new immutable pipeline event.")
    append_p.add_argument("--file", default=str(DEFAULT_LEDGER), help="Ledger JSONL path.")
    append_p.add_argument("--feature-id", required=True, help="Feature ID, e.g. 018.")
    append_p.add_argument("--phase", help="Phase label (e.g. plan, solution).")
    append_p.add_argument(
        "--event",
        required=True,
        choices=sorted(VALID_PIPELINE_EVENTS),
        help="Pipeline event name.",
    )
    append_p.add_argument("--actor", help="Actor identifier.")
    append_p.add_argument("--timestamp-utc", help="Override timestamp (ISO-8601 UTC).")
    # Event-specific optional fields
    append_p.add_argument("--fq-count", type=int, help="Number of feasibility questions.")
    append_p.add_argument("--questions-asked", type=int, help="Questions asked during planreview.")
    append_p.add_argument("--spike-artifact", help="Path to spike.md (feasibility_spike_completed).")
    append_p.add_argument("--failed-fq", help="Failed FQ identifier (feasibility_spike_failed).")
    append_p.add_argument(
        "--feasibility-required",
        help="Whether feasibility spike ran (plan_approved). 'true' or 'false'.",
    )
    append_p.add_argument("--task-count", type=int, help="Task count (solution_approved).")
    append_p.add_argument("--story-count", type=int, help="Story count (solution_approved).")
    append_p.add_argument("--estimate-points", type=int, help="Total estimate points (solution_approved).")
    append_p.add_argument("--tasks-sketched", type=int, help="Tasks sketched (sketch_completed).")
    append_p.add_argument("--acceptance-tests-written", type=int, help="Acceptance tests written (sketch_completed).")
    append_p.add_argument("--critical-count", type=int, help="Critical findings count.")
    append_p.add_argument("--high-count", type=int, help="High severity findings count.")
    append_p.add_argument("--e2e-artifact", help="Path to e2e.md (e2e_generated).")
    append_p.add_argument("--details", help="Free-text details for traceability.")
    append_p.set_defaults(func=cmd_append)

    # --- validate ---
    validate_p = sub.add_parser("validate", help="Validate pipeline ledger structure and event sequence.")
    validate_p.add_argument("--file", default=str(DEFAULT_LEDGER), help="Ledger JSONL path.")
    validate_p.set_defaults(func=cmd_validate)

    # --- assert-phase-complete ---
    gate_p = sub.add_parser(
        "assert-phase-complete",
        help="Assert that a required pipeline phase event has been emitted for a feature.",
    )
    gate_p.add_argument("--file", default=str(DEFAULT_LEDGER), help="Ledger JSONL path.")
    gate_p.add_argument("--feature-id", required=True, help="Feature ID, e.g. 018.")
    gate_p.add_argument(
        "--event",
        required=True,
        choices=sorted(VALID_PIPELINE_EVENTS),
        help="Pipeline event that must be present.",
    )
    gate_p.set_defaults(func=cmd_assert_phase_complete)

    # --- validate-manifest ---
    validate_manifest_p = sub.add_parser(
        "validate-manifest",
        help="Validate the command-manifest.yaml: check templates exist, events declared, etc.",
    )
    validate_manifest_p.set_defaults(func=cmd_validate_manifest)

    return parser


def main() -> None:
    """CLI entrypoint that dispatches to the selected subcommand."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
