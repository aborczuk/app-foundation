#!/usr/bin/env python3
"""Append-only task ledger tooling for task-level implementation/QA audit trails.

This script is designed for per-agent delivery with optional task parallelism:
- One active task per actor/agent at a time.
- Every meaningful transition is logged as an immutable JSONL event.
- A new start is blocked only for the same actor when their prior task is still open.
- `[P]` tasks can be started concurrently by different actors when dependency gates pass.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

DEFAULT_LEDGER = Path(".speckit/task-ledger.jsonl")
TASK_ID_RE = re.compile(r"^T\d{3}$")
FEATURE_ID_RE = re.compile(r"^\d{3}$")
TASK_LINE_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s+(T\d{3})\b")
INDEXABLE_SUFFIXES = {".py", ".pyi"}

AUTO_CODEGRAPH_INDEX_ENV = "SPECKIT_AUTO_CODEGRAPH_INDEX"
AUTO_CODEGRAPH_INDEX_STRICT_ENV = "SPECKIT_AUTO_CODEGRAPH_INDEX_STRICT"

VERDICT_PASS = "YES_TO_MERGE"
VERDICT_FAIL = "FIX_REQUIRED"
VALID_VERDICTS = {VERDICT_PASS, VERDICT_FAIL}
VALID_CI_STATUS = {"pass", "fail"}

VALID_EVENTS = {
    "task_started",
    "discovery_completed",
    "lld_recorded",            # 3+ point task: HUD read + sketch validated, ready to implement
    "quality_guards_passed",
    "functional_goal_achieved",
    "tests_failed",
    "tests_passed",
    "story_red_committed",     # Per-story: failing acceptance test committed (RED step)
    "story_green_passed",      # Per-story: acceptance test now passing (GREEN step)
    "human_action_started",    # [H] task: human acknowledged and started external action
    "human_action_verified",   # [H] task: human action confirmed complete (terminal for [H] tasks)
    "checkpoint_passed",       # implement → checkpoint: phase validation gate passed
    "e2e_passed",              # implement → e2e-run: E2E run passed
    "offline_qa_started",
    "offline_qa_passed",
    "offline_qa_failed",
    "commit_created",
    "pr_opened",
    "ci_completed",
    "qa_verdict",
    "fix_started",
    "fix_completed",
    "merge_approved",
    "merged",
    "task_closed",
}

REQUIRED_BY_EVENT = {
    "commit_created": {"commit_sha"},
    "pr_opened": {"pr_number"},
    "ci_completed": {"ci_run_id", "status"},
    "qa_verdict": {"qa_run_id", "verdict"},
    "merged": {"merge_sha"},
    "story_red_committed": {"commit_sha", "story_id"},
    "story_green_passed": {"story_id", "commit_sha"},
    "human_action_verified": {"verification_method"},
    "checkpoint_passed": {"phase_id", "claims_passed"},
    "e2e_passed": {"e2e_run_id"},
}

ALLOWED_TRANSITIONS = {
    "task_started": {None},
    "discovery_completed": {"task_started", "discovery_completed"},
    "lld_recorded": {"discovery_completed"},
    "quality_guards_passed": {"discovery_completed", "lld_recorded"},
    "functional_goal_achieved": {"discovery_completed", "lld_recorded", "quality_guards_passed"},
    "tests_failed": {
        "task_started", "discovery_completed", "lld_recorded", "quality_guards_passed",
        "functional_goal_achieved", "tests_failed", "fix_started", "fix_completed"
    },
    "tests_passed": {
        "discovery_completed", "lld_recorded", "quality_guards_passed",
        "functional_goal_achieved", "tests_failed", "fix_completed"
    },
    "story_red_committed": {"task_started", "discovery_completed", "lld_recorded"},
    "story_green_passed": {"story_red_committed", "tests_passed"},
    "human_action_started": {"task_started"},
    "human_action_verified": {"human_action_started"},
    "checkpoint_passed": {"tests_passed", "offline_qa_passed"},
    "e2e_passed": {"tests_passed", "offline_qa_passed"},
    "offline_qa_started": {"commit_created"},
    "offline_qa_passed": {"offline_qa_started"},
    "offline_qa_failed": {"offline_qa_started"},
    "commit_created": {"tests_passed", "offline_qa_passed", "fix_completed"},
    "pr_opened": {"commit_created", "pr_opened"},
    "ci_completed": {"commit_created", "pr_opened"},
    "qa_verdict": {"ci_completed"},
    "fix_started": {"qa_verdict", "offline_qa_failed"},
    "fix_completed": {"fix_started"},
    "merge_approved": {"qa_verdict"},
    "merged": {"merge_approved"},
    "task_closed": {"offline_qa_passed", "merged", "human_action_verified", "e2e_passed"},
}


@dataclass
class TaskState:
    """Mutable validation state for a single task while replaying ledger events."""

    started: bool = False
    closed: bool = False
    owner_actor: str | None = None
    last_event: str | None = None
    last_ci_status: str | None = None
    last_qa_verdict: str | None = None
    commits: int = 0
    has_pr: bool = False
    has_merge_approved: bool = False
    has_merged: bool = False
    has_offline_qa_passed: bool = False
    has_discovery_completed: bool = False
    has_lld_recorded: bool = False
    has_quality_guards_passed: bool = False
    has_functional_goal_achieved: bool = False
    has_human_action_verified: bool = False
    has_e2e_passed: bool = False


@dataclass
class FeatureState:
    """Per-feature runtime view of task states and active tasks by actor."""

    active_tasks_by_actor: dict[str, str] = field(default_factory=dict)
    tasks: dict[str, TaskState] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskDefinition:
    """Parsed task metadata from tasks.md ordering and parallel markers."""

    task_id: str
    is_parallel: bool


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fail(message: str) -> NoReturn:
    """Print an error and terminate with exit status 1."""
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def ensure_task_id(task_id: str) -> None:
    """Assert task_id matches the canonical TNNN format."""
    if not TASK_ID_RE.match(task_id):
        fail(f"Invalid task_id {task_id!r}. Expected format TNNN, e.g. T001.")


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
    """Load ledger events from JSONL while preserving original line numbers."""
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
    """Validate required event fields and per-event shape constraints."""
    errors: list[str] = []
    event_name = str(event.get("event", "")).strip()
    feature_id = str(event.get("feature_id", "")).strip()
    task_id = str(event.get("task_id", "")).strip()
    timestamp = str(event.get("timestamp_utc", "")).strip()

    if event_name not in VALID_EVENTS:
        errors.append(f"{line_hint}: invalid event {event_name!r}")
    if not FEATURE_ID_RE.match(feature_id):
        errors.append(f"{line_hint}: invalid feature_id {feature_id!r}")
    if not TASK_ID_RE.match(task_id):
        errors.append(f"{line_hint}: invalid task_id {task_id!r}")
    if not timestamp:
        errors.append(f"{line_hint}: missing timestamp_utc")

    required_fields = REQUIRED_BY_EVENT.get(event_name, set())
    for field_name in required_fields:
        value = event.get(field_name)
        if value is None or str(value).strip() == "":
            errors.append(
                f"{line_hint}: event {event_name!r} "
                f"missing required field {field_name!r}"
            )

    if event_name == "qa_verdict":
        verdict = str(event.get("verdict", "")).strip()
        if verdict not in VALID_VERDICTS:
            errors.append(
                f"{line_hint}: qa_verdict.verdict must be one of "
                f"{sorted(VALID_VERDICTS)}, got {verdict!r}"
            )

    if event_name == "ci_completed":
        status = str(event.get("status", "")).strip().lower()
        if status not in VALID_CI_STATUS:
            errors.append(
                f"{line_hint}: ci_completed.status must be one of "
                f"{sorted(VALID_CI_STATUS)}, got {status!r}"
            )

    return errors


def validate_sequence(events: list[dict[str, Any]]) -> tuple[list[str], dict[str, FeatureState]]:
    """Validate event ordering rules and derive feature/task runtime state."""
    errors: list[str] = []
    feature_states: dict[str, FeatureState] = {}

    for idx, event in enumerate(events, start=1):
        line_no = event.get("_line", idx)
        line_hint = f"line {line_no}"

        shape_errors = validate_event_shape(event, line_hint=line_hint)
        if shape_errors:
            errors.extend(shape_errors)
            continue

        feature_id = str(event["feature_id"])
        task_id = str(event["task_id"])
        event_name = str(event["event"])
        verdict = str(event.get("verdict", "")).strip()
        event_actor = resolve_actor(event.get("actor"))

        feature_state = feature_states.setdefault(feature_id, FeatureState())
        task_state = feature_state.tasks.setdefault(task_id, TaskState())

        if event_name == "task_started":
            active_for_actor = feature_state.active_tasks_by_actor.get(event_actor)
            if active_for_actor and active_for_actor != task_id:
                errors.append(
                    f"{line_hint}: cannot start {task_id} for actor {event_actor!r} while "
                    f"{active_for_actor} is still open (feature {feature_id})"
                )
            if task_state.closed:
                errors.append(f"{line_hint}: cannot restart closed task {task_id}")
            if task_state.started and not task_state.closed:
                errors.append(f"{line_hint}: duplicate task_started for open task {task_id}")

        else:
            if not task_state.started:
                errors.append(
                    f"{line_hint}: event {event_name!r} "
                    f"before task_started for {task_id}"
                )
            if task_state.closed:
                errors.append(f"{line_hint}: event {event_name!r} after task_closed for {task_id}")

        # VERSIONED GOVERNANCE: Historical tasks ( < T050 ) followed Protocol V1.
        is_v1 = False
        try:
            task_num = int(task_id[1:]) if task_id.startswith("T") else 0
            if task_num < 50:
                is_v1 = True
        except ValueError:
            pass

        allowed_prev = ALLOWED_TRANSITIONS.get(event_name, set())
        if not is_v1 and task_state.last_event not in allowed_prev:
            errors.append(
                f"{line_hint}: invalid transition for {task_id}: "
                f"{task_state.last_event!r} -> {event_name!r}"
            )

        if (
            event_name == "fix_started"
            and task_state.last_qa_verdict != VERDICT_FAIL
            and task_state.last_event != "offline_qa_failed"
        ):
            errors.append(
                f"{line_hint}: fix_started requires previous qa_verdict={VERDICT_FAIL} "
                f"or offline_qa_failed, got qa_verdict={task_state.last_qa_verdict!r}"
            )
        if event_name == "merge_approved" and task_state.last_qa_verdict != VERDICT_PASS:
            errors.append(
                f"{line_hint}: merge_approved requires previous qa_verdict={VERDICT_PASS}, "
                f"got {task_state.last_qa_verdict!r}"
            )
        if event_name == "qa_verdict" and task_state.last_ci_status != "pass":
            errors.append(
                f"{line_hint}: qa_verdict requires previous ci_completed.status='pass', "
                f"got {task_state.last_ci_status!r}"
            )
        if event_name == "task_closed":
            can_close = (
                task_state.has_merged
                or task_state.has_offline_qa_passed
                or task_state.has_human_action_verified
                or task_state.has_e2e_passed
            )
            if not can_close:
                errors.append(
                    f"{line_hint}: task_closed requires one of "
                    f"merged/offline_qa_passed/human_action_verified/e2e_passed for {task_id}"
                )
            
            # VERSIONED GOVERNANCE: Enforce Protocol V2 requirements for T050+.
            # Tasks T001-T049 (Protocol V1) are exempt from quality/functional state checks.
            is_v1 = False
            try:
                task_num = int(task_id[1:]) if task_id.startswith("T") else 0
                if task_num < 50:
                    is_v1 = True
            except ValueError:
                pass
                
            if not is_v1:
                if not task_state.has_quality_guards_passed or not task_state.has_functional_goal_achieved:
                    errors.append(
                        f"{line_hint}: task_closed requires both quality_guards_passed "
                        f"and functional_goal_achieved for {task_id}"
                    )

        if event_name == "task_started":
            task_state.started = True
            task_state.owner_actor = event_actor
            feature_state.active_tasks_by_actor[event_actor] = task_id
        elif event_name == "discovery_completed":
            task_state.has_discovery_completed = True
        elif event_name == "lld_recorded":
            task_state.has_lld_recorded = True
        elif event_name == "quality_guards_passed":
            task_state.has_quality_guards_passed = True
        elif event_name == "functional_goal_achieved":
            task_state.has_functional_goal_achieved = True
        elif event_name == "human_action_verified":
            task_state.has_human_action_verified = True
        elif event_name == "e2e_passed":
            task_state.has_e2e_passed = True
        elif event_name == "commit_created":
            task_state.commits += 1
        elif event_name == "pr_opened":
            task_state.has_pr = True
        elif event_name == "ci_completed":
            task_state.last_ci_status = str(event.get("status", "")).strip().lower()
        elif event_name == "qa_verdict":
            task_state.last_qa_verdict = verdict
        elif event_name == "offline_qa_passed":
            task_state.has_offline_qa_passed = True
        elif event_name == "merge_approved":
            task_state.has_merge_approved = True
        elif event_name == "merged":
            task_state.has_merged = True
        elif event_name == "task_closed":
            task_state.closed = True
            owner_actor = task_state.owner_actor
            if owner_actor and feature_state.active_tasks_by_actor.get(owner_actor) == task_id:
                del feature_state.active_tasks_by_actor[owner_actor]
            elif feature_state.active_tasks_by_actor.get(event_actor) == task_id:
                del feature_state.active_tasks_by_actor[event_actor]

        task_state.last_event = event_name

    return errors, feature_states


def parse_task_definitions(path: Path) -> list[TaskDefinition]:
    """Parse ordered task IDs and `[P]` flags from tasks.md."""
    if not path.exists():
        fail(f"tasks.md not found: {path}")
    ordered: list[TaskDefinition] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            match = TASK_LINE_RE.match(line)
            if not match:
                continue
            task_id = match.group(1)
            if task_id in seen:
                continue
            seen.add(task_id)
            ordered.append(
                TaskDefinition(
                    task_id=task_id,
                    is_parallel="[P]" in line,
                )
            )
    if not ordered:
        fail(f"No task IDs found in {path}")
    return ordered


def ordered_tasks_from_markdown(path: Path) -> list[str]:
    """Return ordered task IDs parsed from a tasks.md file."""
    return [definition.task_id for definition in parse_task_definitions(path)]


def latest_attempt(events: list[dict[str, Any]], feature_id: str, task_id: str) -> int:
    """Return the latest attempt number recorded for a task, defaulting to 1."""
    attempts: list[int] = []
    for event in events:
        if event.get("feature_id") != feature_id or event.get("task_id") != task_id:
            continue
        raw = event.get("attempt")
        if raw is None:
            continue
        try:
            attempts.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not attempts:
        return 1
    return max(attempts)


def env_enabled(raw_value: str | None, *, default: bool) -> bool:
    """Parse boolean-style env vars with common truthy/falsey values."""
    if raw_value is None:
        return default
    value = raw_value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def repo_root() -> Path:
    """Return the repository root inferred from this script location."""
    return Path(__file__).resolve().parent.parent


def latest_commit_for_attempt(
    events: list[dict[str, Any]],
    *,
    feature_id: str,
    task_id: str,
    attempt: int,
) -> str | None:
    """Return the most recent commit SHA for a task attempt, if present."""
    for event in reversed(events):
        if event.get("feature_id") != feature_id or event.get("task_id") != task_id:
            continue
        try:
            event_attempt = int(event.get("attempt", 0))
        except (TypeError, ValueError):
            continue
        if event_attempt != attempt or event.get("event") != "commit_created":
            continue
        commit_sha = str(event.get("commit_sha", "")).strip()
        if commit_sha:
            return commit_sha
    return None


def changed_paths_for_commit(root: Path, commit_sha: str) -> list[Path]:
    """Return repository-relative file paths touched by a commit."""
    result = subprocess.run(
        [
            "git",
            "show",
            "--name-only",
            "--pretty=format:",
            "--diff-filter=ACMRTUXB",
            commit_sha,
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(stderr or f"git show failed for commit {commit_sha}")

    paths: list[Path] = []
    for line in result.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        paths.append(Path(rel))
    return paths


def index_targets_for_codegraph(changed_paths: list[Path]) -> list[Path]:
    """Filter changed paths down to deduplicated Python targets for indexing."""
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in changed_paths:
        if path.suffix not in INDEXABLE_SUFFIXES:
            continue
        key = path.as_posix()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def run_codegraph_index(root: Path, target: Path) -> tuple[int, str]:
    """Run incremental cgc index for one target path and return code/output."""
    env = os.environ.copy()
    env.setdefault("UV_NO_CACHE", "1")
    env.setdefault("DEFAULT_DATABASE", "kuzudb")
    env.setdefault("KUZUDB_PATH", str(root / ".codegraph" / "kuzudb"))
    result = subprocess.run(
        ["uv", "run", "cgc", "index", target.as_posix()],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode, output


def maybe_auto_index_codegraph(
    *,
    events: list[dict[str, Any]],
    feature_id: str,
    task_id: str,
    attempt: int,
    event_name: str,
) -> None:
    """Auto-index commit-touched Python files after task_closed when enabled."""
    if event_name != "task_closed":
        return
    if not env_enabled(os.environ.get(AUTO_CODEGRAPH_INDEX_ENV), default=True):
        return

    strict = env_enabled(os.environ.get(AUTO_CODEGRAPH_INDEX_STRICT_ENV), default=False)
    root = repo_root()
    commit_sha = latest_commit_for_attempt(
        events,
        feature_id=feature_id,
        task_id=task_id,
        attempt=attempt,
    )
    if not commit_sha:
        message = (
            f"CodeGraph hook skipped for {feature_id}:{task_id}: "
            "no commit_created SHA found for this attempt."
        )
        if strict:
            fail(message)
        print(f"WARNING: {message}", file=sys.stderr)
        return

    try:
        changed = changed_paths_for_commit(root, commit_sha)
    except RuntimeError as exc:
        message = (
            f"CodeGraph hook failed for {feature_id}:{task_id} commit {commit_sha}: {exc}"
        )
        if strict:
            fail(message)
        print(f"WARNING: {message}", file=sys.stderr)
        return

    targets = index_targets_for_codegraph(changed)
    if not targets:
        print(
            f"CodeGraph hook: no Python paths to index for {commit_sha}.",
            file=sys.stderr,
        )
        return

    failures: list[tuple[Path, str]] = []
    for target in targets:
        code, output = run_codegraph_index(root, target)
        if code != 0:
            failures.append((target, output))

    if failures:
        summary = (
            f"CodeGraph hook indexed {len(targets) - len(failures)}/{len(targets)} "
            f"paths for commit {commit_sha}."
        )
        if strict:
            details = "; ".join(f"{path}: {out}" for path, out in failures[:3])
            fail(f"{summary} Failures: {details}")
        print(f"WARNING: {summary}", file=sys.stderr)
        for path, out in failures[:3]:
            print(f"WARNING: index failed for {path}: {out}", file=sys.stderr)
        return

    print(
        f"CodeGraph hook: indexed {len(targets)} Python path(s) for commit {commit_sha}.",
        file=sys.stderr,
    )


def cmd_append(args: argparse.Namespace) -> None:
    """Append one validated immutable event to the ledger."""
    ledger_path = Path(args.file)
    ensure_feature_id(args.feature_id)
    ensure_task_id(args.task_id)

    if args.event not in VALID_EVENTS:
        fail(f"Invalid event {args.event!r}. Valid events: {sorted(VALID_EVENTS)}")

    existing = read_events(ledger_path)
    if args.attempt is not None:
        attempt = args.attempt
    else:
        current = latest_attempt(existing, args.feature_id, args.task_id)
        if args.event == "fix_started":
            attempt = current + 1
        else:
            attempt = current

    event: dict[str, Any] = {
        "timestamp_utc": args.timestamp_utc or utc_now_iso(),
        "feature_id": args.feature_id,
        "task_id": args.task_id,
        "attempt": attempt,
        "event": args.event,
        "actor": resolve_actor(args.actor),
    }

    optional_values = {
        "status": args.status,
        "verdict": args.verdict,
        "details": args.details,
        "commit_sha": args.commit_sha,
        "merge_sha": args.merge_sha,
        "pr_number": args.pr_number,
        "ci_run_id": args.ci_run_id,
        "qa_run_id": args.qa_run_id,
        "clickup_item_id": args.clickup_item_id,
        "story_id": args.story_id,
        "e2e_run_id": args.e2e_run_id,
        "phase_id": args.phase_id,
        "claims_passed": args.claims_passed,
        "verification_method": args.verification_method,
    }
    for key, value in optional_values.items():
        if value is None:
            continue
        event[key] = value

    if args.metadata_json:
        try:
            metadata_obj = json.loads(args.metadata_json)
        except json.JSONDecodeError as exc:
            fail(f"Invalid metadata JSON: {exc}")
        event["metadata"] = metadata_obj

    provisional = [dict(item) for item in existing] + [dict(event)]
    errors, _ = validate_sequence(provisional)
    if errors:
        print("ERROR: append rejected due to sequence validation failure:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        raise SystemExit(1)

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")

    print(f"Appended {args.event} for {args.feature_id}:{args.task_id} (attempt={attempt})")
    maybe_auto_index_codegraph(
        events=provisional,
        feature_id=args.feature_id,
        task_id=args.task_id,
        attempt=attempt,
        event_name=args.event,
    )


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate an existing ledger and print a concise feature summary."""
    ledger_path = Path(args.file)
    events = read_events(ledger_path)
    if not events:
        print(f"No events found at {ledger_path}.")
        return

    errors, feature_states = validate_sequence(events)
    if errors:
        print("Task ledger validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Task ledger validation passed ({len(events)} events).")
    for feature_id in sorted(feature_states):
        feature = feature_states[feature_id]
        closed = [tid for tid, st in feature.tasks.items() if st.closed]
        open_tasks = [tid for tid, st in feature.tasks.items() if st.started and not st.closed]
        active_pairs = sorted(
            feature.active_tasks_by_actor.items(),
            key=lambda pair: pair[0],
        )
        active_summary = (
            ", ".join(f"{actor}:{task}" for actor, task in active_pairs)
            if active_pairs
            else "none"
        )
        print(
            f"- feature {feature_id}: closed={len(closed)} open={len(open_tasks)} "
            f"active={active_summary}"
        )


def cmd_assert_can_start(args: argparse.Namespace) -> None:
    """Enforce dependency and per-actor start gates before task execution."""
    ledger_path = Path(args.file)
    tasks_file = Path(args.tasks_file)

    ensure_feature_id(args.feature_id)
    ensure_task_id(args.task_id)

    events = read_events(ledger_path)
    errors, feature_states = validate_sequence(events)
    if errors:
        print("Ledger is invalid; cannot assert task start gate:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        raise SystemExit(1)

    task_definitions = parse_task_definitions(tasks_file)
    order = [definition.task_id for definition in task_definitions]
    if args.task_id not in order:
        fail(f"Task {args.task_id} not found in ordered task list from {tasks_file}")

    actor = resolve_actor(args.actor)
    feature_state = feature_states.get(args.feature_id, FeatureState())
    active_for_actor = feature_state.active_tasks_by_actor.get(actor)
    if active_for_actor and active_for_actor != args.task_id:
        fail(
            f"Cannot start {args.task_id}; actor {actor!r} already has open task "
            f"{active_for_actor} in feature {args.feature_id}"
        )

    current_state = feature_state.tasks.get(args.task_id)
    if current_state and current_state.closed:
        fail(f"Cannot start {args.task_id}; it is already closed in the ledger")
    if current_state and current_state.started and not current_state.closed:
        owner = current_state.owner_actor or "unknown"
        fail(
            f"Cannot start {args.task_id}; it is already started by actor {owner!r} "
            "and not yet closed"
        )

    task_lookup = {definition.task_id: definition for definition in task_definitions}
    current_definition = task_lookup[args.task_id]
    current_index = order.index(args.task_id)
    preceding = task_definitions[:current_index]
    if current_definition.is_parallel:
        blocking_prior = [
            definition.task_id for definition in preceding if not definition.is_parallel
        ]
    else:
        blocking_prior = [definition.task_id for definition in preceding]

    for prior in blocking_prior:
        prior_state = feature_state.tasks.get(prior)
        if not prior_state or not prior_state.closed:
            fail(
                f"Cannot start {args.task_id}; prior task {prior} is not closed in the ledger"
            )

    if not current_definition.is_parallel:
        open_other_tasks = sorted(
            task_id
            for task_id, state in feature_state.tasks.items()
            if task_id != args.task_id and state.started and not state.closed
        )
        if open_other_tasks:
            fail(
                f"Cannot start non-parallel task {args.task_id}; open tasks remain: "
                f"{', '.join(open_other_tasks)}"
            )

    print(
        f"Start gate passed for feature {args.feature_id} task {args.task_id} "
        f"(actor={actor!r}, parallel={current_definition.is_parallel})."
    )


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        description="Append-only task ledger operations for per-agent task flow."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    append_p = sub.add_parser("append", help="Append a new immutable event.")
    append_p.add_argument("--file", default=str(DEFAULT_LEDGER), help="Ledger JSONL path.")
    append_p.add_argument("--feature-id", required=True, help="Feature ID, e.g. 018.")
    append_p.add_argument("--task-id", required=True, help="Task ID, e.g. T001.")
    append_p.add_argument(
        "--event",
        required=True,
        choices=sorted(VALID_EVENTS),
        help="Event name.",
    )
    append_p.add_argument("--attempt", type=int, help="Attempt number (auto-derived when omitted).")
    append_p.add_argument("--actor", help="Actor identifier.")
    append_p.add_argument("--status", help="Generic status (commonly for ci_completed).")
    append_p.add_argument("--verdict", help=f"QA verdict ({VERDICT_PASS}|{VERDICT_FAIL}).")
    append_p.add_argument("--details", help="Free-text details for traceability.")
    append_p.add_argument("--commit-sha", help="Commit SHA for commit_created.")
    append_p.add_argument("--merge-sha", help="Merge commit SHA for merged.")
    append_p.add_argument("--pr-number", help="PR number for pr_opened.")
    append_p.add_argument("--ci-run-id", help="CI run ID for ci_completed.")
    append_p.add_argument("--qa-run-id", help="QA run ID for qa_verdict.")
    append_p.add_argument("--clickup-item-id", help="Optional ClickUp item id for mapping.")
    append_p.add_argument("--story-id", help="Story ID for story_red_committed/story_green_passed.")
    append_p.add_argument("--e2e-run-id", help="E2E run ID for e2e_passed.")
    append_p.add_argument("--phase-id", help="Phase ID for checkpoint_passed.")
    append_p.add_argument("--claims-passed", help="Claims summary for checkpoint_passed.")
    append_p.add_argument("--verification-method", help="Verification method for human_action_verified.")
    append_p.add_argument("--metadata-json", help="Arbitrary JSON metadata object.")
    append_p.add_argument("--timestamp-utc", help="Override timestamp (ISO-8601 UTC).")
    append_p.set_defaults(func=cmd_append)

    validate_p = sub.add_parser("validate", help="Validate ledger structure and event sequence.")
    validate_p.add_argument("--file", default=str(DEFAULT_LEDGER), help="Ledger JSONL path.")
    validate_p.set_defaults(func=cmd_validate)

    gate_p = sub.add_parser(
        "assert-can-start",
        help="Assert per-agent gate: dependencies and actor constraints before starting a task.",
    )
    gate_p.add_argument("--file", default=str(DEFAULT_LEDGER), help="Ledger JSONL path.")
    gate_p.add_argument("--tasks-file", required=True, help="Path to tasks.md for task order.")
    gate_p.add_argument("--feature-id", required=True, help="Feature ID, e.g. 018.")
    gate_p.add_argument("--task-id", required=True, help="Task ID, e.g. T001.")
    gate_p.add_argument(
        "--actor",
        help="Agent/actor identity used for per-agent start gating "
        "(defaults to SPECKIT_AGENT_ID/CODEX_AGENT_ID/GITHUB_ACTOR/USER).",
    )
    gate_p.set_defaults(func=cmd_assert_can_start)

    return parser


def main() -> None:
    """CLI entrypoint that dispatches to the selected subcommand."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
