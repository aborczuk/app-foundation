#!/usr/bin/env python3
"""Deterministic speckit.implement step with observability-first diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import speckit_closeout_task
import speckit_implement_docs
import speckit_offline_qa_handoff
import task_ledger
from bootstrap_session import bootstrap_session

SCHEMA_VERSION = "1.0.0"
IMPLEMENT_GATE = "implement_execution"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_PHASE_TYPE = "story"
DEFAULT_NEXT_PHASE = "closed"
MAX_QA_RETRIES = 3


@dataclass(frozen=True)
class CommandResult:
    """Captured result for a subprocess command used by stage orchestration."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    command: list[str]
    timeout_seconds: int


def _utc_now_iso() -> str:
    """Return current UTC timestamp formatted as canonical ISO-8601 Zulu."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _tail_lines(text: str, count: int = 20) -> list[str]:
    """Return at most the last `count` lines from text for concise diagnostics."""
    if not text:
        return []
    lines = text.splitlines()
    return lines[-count:]


def _sanitize_for_filename(value: str) -> str:
    """Normalize arbitrary text into a filesystem-safe token."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "unknown"


def _default_handoff_runner(repo_root: Path) -> str:
    """Return the canonical local Codex runner command."""
    runner_path = (repo_root / "scripts" / "speckit_codex_handoff_runner.py").resolve()
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(runner_path))}"


def _write_debug_payload(
    *,
    repo_root: Path,
    correlation_id: str,
    payload: dict[str, Any],
) -> str:
    """Persist structured stage diagnostics and return its absolute path."""
    debug_dir = repo_root / ".speckit" / "runtime" / "implement"
    debug_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_sanitize_for_filename(correlation_id)}.json"
    debug_path = (debug_dir / filename).resolve()
    debug_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(debug_path)


def _run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    input_payload: str | None = None,
) -> CommandResult:
    """Execute a subprocess command and capture deterministic routing metadata."""
    proc_input = input_payload if input_payload is None else str(input_payload)
    try:
        completed = subprocess.run(
            [str(part) for part in command],
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            input=proc_input,
        )
        return CommandResult(
            exit_code=int(completed.returncode),
            stdout=str(completed.stdout),
            stderr=str(completed.stderr),
            timed_out=False,
            command=[str(part) for part in command],
            timeout_seconds=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            exit_code=124,
            stdout=str(exc.stdout or ""),
            stderr=str(exc.stderr or ""),
            timed_out=True,
            command=[str(part) for part in command],
            timeout_seconds=timeout_seconds,
        )


def _parse_json_payload(raw: str) -> dict[str, Any]:
    """Parse JSON output into a mapping or raise a ValueError with context."""
    try:
        parsed = json.loads(raw.strip() or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_json:{exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("json_payload_not_object")
    return parsed


def _resolve_feature_dir(repo_root: Path, feature_id: str) -> Path:
    """Resolve feature directory from exact slug or numeric feature prefix."""
    specs_root = repo_root / "specs"
    if not specs_root.is_dir():
        raise ValueError("missing_specs_root")

    explicit = specs_root / feature_id
    if explicit.is_dir():
        return explicit.resolve()

    candidates = sorted(path for path in specs_root.glob(f"{feature_id}-*") if path.is_dir())
    if not candidates:
        raise ValueError("feature_not_found")
    if len(candidates) > 1:
        raise ValueError(
            "feature_id_ambiguous:" + ",".join(path.name for path in candidates[:5])
        )
    return candidates[0].resolve()


def _task_ledger_path(repo_root: Path) -> Path:
    """Return the canonical task ledger path for the repository."""
    return (repo_root / ".speckit" / "task-ledger.jsonl").resolve()


def _resolve_commit_sha(
    repo_root: Path,
    *,
    timeout_seconds: int,
    handoff_payload: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Resolve the commit SHA for closeout, preferring handoff output when available."""
    if handoff_payload is not None:
        candidate = str(handoff_payload.get("commit_sha") or "").strip()
        if candidate:
            return candidate, "handoff_payload"

    commit_run = _run_command(["git", "rev-parse", "HEAD"], cwd=repo_root, timeout_seconds=timeout_seconds)
    if commit_run.timed_out:
        raise ValueError("commit_sha_resolution_timeout")
    if commit_run.exit_code != 0:
        raise ValueError("commit_sha_unavailable")

    commit_sha = commit_run.stdout.strip()
    if not commit_sha:
        raise ValueError("commit_sha_unavailable")
    return commit_sha, "git_head"


def _run_offline_qa_handoff(
    *,
    feature_id: str,
    task_id: str,
    attempt: int,
) -> dict[str, Any]:
    """Run the offline QA handoff helper and return its payload."""
    return speckit_offline_qa_handoff.run_offline_qa_handoff(
        feature_id=feature_id,
        task_id=task_id,
        attempt=attempt,
    )


def _build_handoff_input(
    *,
    feature_id: str,
    phase: str,
    correlation_id: str,
    feature_dir: Path,
    repo_root: Path,
    task_context: Mapping[str, Any],
    resume_session: bool,
    retry_index: int,
    qa_feedback: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build the JSON payload for the Codex handoff runner."""
    payload: dict[str, Any] = {
        "feature_id": feature_id,
        "phase": phase,
        "correlation_id": correlation_id,
        "step_name": "speckit.implement",
        "feature_dir": str(feature_dir),
        "repo_root": str(repo_root),
        "task_id": task_context["next_task_id"],
        "task_attempt": task_context["task_attempt"],
        "task_action": task_context["task_action"],
        "task_registered": task_context["task_registered"],
        "task_parallel": task_context["task_parallel"],
        "resume_session": resume_session,
        "retry_index": retry_index,
    }
    if qa_feedback is not None:
        payload["qa_feedback"] = dict(qa_feedback)
    return payload


def _run_handoff_round(
    *,
    repo_root: Path,
    feature_id: str,
    phase: str,
    correlation_id: str,
    feature_dir: Path,
    task_context: Mapping[str, Any],
    handoff_runner: str,
    timeout_seconds: int,
    resume_session: bool,
    retry_index: int,
    qa_feedback: Mapping[str, Any] | None,
) -> tuple[CommandResult, dict[str, Any]]:
    """Execute one Codex handoff round and return its raw result."""
    handoff_cmd = shlex.split(handoff_runner)
    if not handoff_cmd:
        raise ValueError("runner_command_empty")

    handoff_input = _build_handoff_input(
        feature_id=feature_id,
        phase=phase,
        correlation_id=correlation_id,
        feature_dir=feature_dir,
        repo_root=repo_root,
        task_context=task_context,
        resume_session=resume_session,
        retry_index=retry_index,
        qa_feedback=qa_feedback,
    )
    handoff_run = _run_command(
        handoff_cmd,
        cwd=repo_root,
        timeout_seconds=timeout_seconds,
        input_payload=json.dumps(handoff_input, sort_keys=True),
    )
    return handoff_run, handoff_input


def _closeout_task(
    *,
    feature_id: str,
    task_id: str,
    tasks_file: Path,
    ledger_path: Path,
    commit_sha: str,
    qa_run_id: str,
    qa_result_path: Path,
    actor: str,
) -> speckit_closeout_task.CloseoutResult:
    """Run canonical closeout through the dedicated helper module."""
    return speckit_closeout_task.closeout_task(
        feature_id=feature_id,
        task_id=task_id,
        tasks_file=tasks_file,
        ledger_file=ledger_path,
        commit_sha=commit_sha,
        qa_run_id=qa_run_id,
        qa_result_path=qa_result_path,
        actor=actor,
    )


def _update_implementation_docs(
    *,
    feature_dir: Path,
    correlation_id: str,
    task_context: dict[str, Any],
    commit_sha: str,
    qa_run_id: str,
    closeout_result: dict[str, Any],
) -> dict[str, Any]:
    """Record deterministic implement notes after a successful closeout."""
    task_id = str(task_context["next_task_id"])
    task_action = str(task_context["task_action"])
    task_attempt = int(task_context["task_attempt"])
    entry_id = f"{correlation_id}:{task_id}:docs"
    request = speckit_implement_docs.UpdateRequest(
        feature_dir=feature_dir,
        entry_id=entry_id,
        runbook_notes=(
            f"Closed out task {task_id} ({task_action}, attempt {task_attempt}) at commit {commit_sha}.",
        ),
        decision_log_entries=(
            f"Task {task_id} reached closeout after offline QA run {qa_run_id}.",
            f"Closeout next_action={closeout_result['next_action']} next_task_id={closeout_result['next_task_id'] or 'none'}.",
        ),
    )
    return speckit_implement_docs.apply_update(request)


def _select_next_registered_task(
    *,
    repo_root: Path,
    feature_dir: Path,
    feature_id: str,
    actor: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Select the next registered task and start or resume it."""
    ledger_path = _task_ledger_path(repo_root)
    tasks_file = feature_dir / "tasks.md"
    if not tasks_file.exists():
        raise ValueError("missing_tasks_md")

    feature_state = task_ledger.feature_state_for(ledger_path, feature_id)
    if not any(task_state.registered for task_state in feature_state.tasks.values()):
        raise ValueError("task_registration_required")

    task_definitions = task_ledger.parse_task_definitions(tasks_file)
    next_task_id: str | None = None
    task_state: task_ledger.TaskState | None = None
    task_action: str | None = None
    task_parallel = False
    blocked_owner_actor: str | None = None

    for definition in task_definitions:
        candidate_state = feature_state.tasks.get(definition.task_id)
        if candidate_state is None or not candidate_state.registered or candidate_state.closed:
            continue
        if candidate_state.started:
            owner_actor = candidate_state.owner_actor or "unknown"
            if owner_actor == actor:
                next_task_id = definition.task_id
                task_state = candidate_state
                task_action = "resumed"
                task_parallel = definition.is_parallel
                break
            if blocked_owner_actor is None:
                blocked_owner_actor = owner_actor
            continue
        _, blocking_reason = task_ledger.evaluate_start_task(
            feature_state=feature_state,
            task_definitions=task_definitions,
            feature_id=feature_id,
            task_id=definition.task_id,
            actor=actor,
        )
        if blocking_reason is None:
            next_task_id = definition.task_id
            task_state = candidate_state
            task_action = "started"
            task_parallel = definition.is_parallel
            break

    if next_task_id is None or task_state is None or task_action is None:
        if blocked_owner_actor is not None:
            raise ValueError(f"task_owned_by_other_actor:{blocked_owner_actor}")
        raise ValueError("no_registered_open_tasks")

    if task_action == "started":
        task_ledger.assert_can_start_task(
            ledger_path,
            tasks_file,
            feature_id,
            next_task_id,
            actor=actor,
        )
        task_ledger.append_task_started_event(
            ledger_path,
            feature_id,
            next_task_id,
            actor=actor,
            details=f"queued by {correlation_id}",
        )
        feature_state = task_ledger.feature_state_for(ledger_path, feature_id)
        task_state = feature_state.tasks.get(next_task_id)
        if task_state is None:
            raise ValueError("task_state_missing_after_start")

    events = task_ledger.read_events(ledger_path)
    attempt = task_ledger.latest_attempt(events, feature_id, next_task_id)
    return {
        "ledger_path": str(ledger_path),
        "tasks_file": str(tasks_file),
        "next_task_id": next_task_id,
        "task_action": task_action,
        "task_attempt": attempt,
        "task_registered": bool(task_state.registered),
        "task_started": bool(task_state.started),
        "task_closed": bool(task_state.closed),
        "task_owner_actor": task_state.owner_actor or actor,
        "task_parallel": task_parallel,
    }


def _resolve_explicit_task_start_gate(
    *,
    repo_root: Path,
    feature_dir: Path,
    feature_id: str,
    task_id: str,
    actor: str,
) -> dict[str, Any]:
    """Return a repo-aware non-mutating start-gate summary for one explicit task."""
    ledger_path = _task_ledger_path(repo_root)
    tasks_file = feature_dir / "tasks.md"
    if not tasks_file.exists():
        raise ValueError("missing_tasks_md")

    summary = task_ledger.explicit_task_start_gate(
        ledger_path,
        tasks_file,
        feature_id,
        task_id,
        actor=actor,
    )
    summary.update(
        {
            "ledger_path": str(ledger_path),
            "tasks_file": str(tasks_file),
        }
    )
    return summary


def _start_explicit_task_request(
    *,
    repo_root: Path,
    feature_dir: Path,
    feature_id: str,
    task_id: str,
    actor: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Start or resume one explicit task using the same ledger rules as normal implement flow."""
    ledger_path = _task_ledger_path(repo_root)
    tasks_file = feature_dir / "tasks.md"
    if not tasks_file.exists():
        raise ValueError("missing_tasks_md")
    summary = task_ledger.explicit_task_start_or_resume(
        ledger_path,
        tasks_file,
        feature_id,
        task_id,
        actor=actor,
        details=f"queued by {correlation_id}",
    )
    summary.update(
        {
            "ledger_path": str(ledger_path),
            "tasks_file": str(tasks_file),
        }
    )
    return summary


def _ensure_implement_branch(repo_root: Path, feature_dir: Path, *, timeout_seconds: int) -> dict[str, Any]:
    """Create or activate the implementation branch for the feature."""
    branch_name = feature_dir.name

    current_branch_run = _run_command(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        timeout_seconds=timeout_seconds,
    )
    if current_branch_run.timed_out:
        raise ValueError("branch_current_timeout")
    if current_branch_run.exit_code != 0:
        raise ValueError("branch_current_lookup_failed")
    current_branch = current_branch_run.stdout.strip()

    branch_list_run = _run_command(
        ["git", "branch", "--list", branch_name],
        cwd=repo_root,
        timeout_seconds=timeout_seconds,
    )
    if branch_list_run.timed_out:
        raise ValueError("branch_list_timeout")
    if branch_list_run.exit_code != 0:
        raise ValueError("branch_list_failed")
    branch_exists = bool(branch_list_run.stdout.strip())

    if current_branch == branch_name:
        return {
            "branch_name": branch_name,
            "current_branch": current_branch,
            "branch_exists": branch_exists,
            "status": "already_checked_out",
        }

    if branch_exists:
        switch_run = _run_command(
            ["git", "switch", branch_name],
            cwd=repo_root,
            timeout_seconds=timeout_seconds,
        )
        if switch_run.timed_out:
            raise ValueError("branch_switch_timeout")
        if switch_run.exit_code != 0:
            raise ValueError("branch_switch_failed")
        return {
            "branch_name": branch_name,
            "current_branch": current_branch,
            "branch_exists": True,
            "status": "switched",
        }

    if current_branch != "main":
        raise ValueError("implement_branch_requires_main")

    create_run = _run_command(
        ["git", "switch", "-c", branch_name],
        cwd=repo_root,
        timeout_seconds=timeout_seconds,
    )
    if create_run.timed_out:
        raise ValueError("branch_create_timeout")
    if create_run.exit_code != 0:
        raise ValueError("branch_create_failed")
    return {
        "branch_name": branch_name,
        "current_branch": current_branch,
        "branch_exists": False,
        "status": "created",
    }


def _start_stage(name: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Initialize an observability stage envelope before command execution."""
    return {
        "name": name,
        "status": "running",
        "started_utc": _utc_now_iso(),
        "duration_ms": None,
        "details": dict(details or {}),
        "_t0": time.perf_counter(),
    }


def _finish_stage(stage: dict[str, Any], *, status: str, details: dict[str, Any] | None = None) -> None:
    """Finalize a stage with duration and optional details update."""
    elapsed_ms = int((time.perf_counter() - float(stage["_t0"])) * 1000)
    stage["status"] = status
    stage["ended_utc"] = _utc_now_iso()
    stage["duration_ms"] = elapsed_ms
    if details:
        merged = dict(stage.get("details", {}))
        merged.update(details)
        stage["details"] = merged
    stage.pop("_t0", None)


def _bool_env(name: str) -> bool:
    """Interpret environment variable as a boolean flag."""
    raw = str(os.environ.get(name, "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for deterministic implement step execution."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-id", required=True)
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--phase", default="implement")
    parser.add_argument("--phase-type", choices=("setup", "foundational", "story", "polish"), default=DEFAULT_PHASE_TYPE)
    parser.add_argument("--next-phase", default=DEFAULT_NEXT_PHASE)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--handoff-runner", default="")
    parser.add_argument("--require-handoff", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def _build_envelope(
    *,
    correlation_id: str,
    exit_code: int,
    next_phase: str | None = None,
    gate: str | None = None,
    reasons: list[str] | None = None,
    error_code: str | None = None,
    debug_path: str | None = None,
) -> dict[str, Any]:
    """Create canonical step-result envelope matching parse_step_result contract."""
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": exit_code == 0,
        "exit_code": int(exit_code),
        "correlation_id": correlation_id,
        "gate": gate,
        "reasons": list(reasons or []),
        "error_code": error_code,
        "next_phase": next_phase,
        "debug_path": debug_path,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run deterministic implement orchestration and emit one JSON envelope."""
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    repo_root = Path(args.repo_root).resolve()
    bootstrap_summary = bootstrap_session(repo_root)
    if not bootstrap_summary["bootstrap_ok"]:
        raise RuntimeError(bootstrap_summary["codegraph_detail"] or "session bootstrap failed")
    correlation_id = str(args.correlation_id).strip()
    require_handoff = bool(args.require_handoff or _bool_env("SPECKIT_REQUIRE_HANDOFF"))
    timeout_seconds = max(1, int(args.timeout_seconds))
    actor_name = task_ledger.resolve_actor(None)
    stages: list[dict[str, Any]] = []
    handoff_runner = str(args.handoff_runner).strip() or str(os.environ.get("SPECKIT_HANDOFF_RUNNER", "")).strip()
    if not handoff_runner:
        handoff_runner = _default_handoff_runner(repo_root)

    debug_stub: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "timestamp_utc": _utc_now_iso(),
        "correlation_id": correlation_id,
        "feature_id": str(args.feature_id),
        "phase": str(args.phase),
        "stages": stages,
            "config": {
                "phase_type": str(args.phase_type),
                "next_phase": str(args.next_phase),
                "require_handoff": require_handoff,
                "handoff_runner_configured": bool(handoff_runner),
                "actor": actor_name,
            },
        }

    feature_dir: Path | None = None
    try:
        resolve_stage = _start_stage("resolve_feature_dir")
        stages.append(resolve_stage)
        try:
            feature_dir = _resolve_feature_dir(repo_root, str(args.feature_id).strip())
            _finish_stage(resolve_stage, status="pass", details={"feature_dir": str(feature_dir)})
        except ValueError as exc:
            _finish_stage(resolve_stage, status="blocked", details={"reason": str(exc)})
            debug_path = _write_debug_payload(
                repo_root=repo_root,
                correlation_id=correlation_id,
                payload={**debug_stub, "result": {"blocked_stage": "resolve_feature_dir", "reason": str(exc)}},
            )
            envelope = _build_envelope(
                correlation_id=correlation_id,
                exit_code=1,
                gate=IMPLEMENT_GATE,
                reasons=["feature_not_found"],
                next_phase=None,
                debug_path=debug_path,
            )
            print(json.dumps(envelope, sort_keys=True))
            return 1

        gate_stage = _start_stage("gate_status")
        stages.append(gate_stage)
        gate_cmd = [
            sys.executable,
            str((repo_root / "scripts" / "speckit_gate_status.py").resolve()),
            "--mode",
            "implement",
            "--feature-dir",
            str(feature_dir),
            "--json",
        ]
        gate_run = _run_command(gate_cmd, cwd=repo_root, timeout_seconds=timeout_seconds)
        gate_details: dict[str, Any] = {
            "command": gate_run.command,
            "exit_code": gate_run.exit_code,
            "timed_out": gate_run.timed_out,
            "stdout_tail": _tail_lines(gate_run.stdout),
            "stderr_tail": _tail_lines(gate_run.stderr),
        }
        if gate_run.timed_out:
            _finish_stage(gate_stage, status="error", details=gate_details)
            debug_path = _write_debug_payload(
                repo_root=repo_root,
                correlation_id=correlation_id,
                payload={**debug_stub, "result": {"error_stage": "gate_status", "error_code": "gate_status_timeout"}},
            )
            envelope = _build_envelope(
                correlation_id=correlation_id,
                exit_code=2,
                error_code="gate_status_timeout",
                debug_path=debug_path,
            )
            print(json.dumps(envelope, sort_keys=True))
            return 2

        gate_payload = _parse_json_payload(gate_run.stdout)
        gate_details["report"] = gate_payload
        if gate_run.exit_code != 0 or not bool(gate_payload.get("ok")):
            _finish_stage(gate_stage, status="blocked", details=gate_details)
            debug_path = _write_debug_payload(
                repo_root=repo_root,
                correlation_id=correlation_id,
                payload={**debug_stub, "result": {"blocked_stage": "gate_status", "gate_report": gate_payload}},
            )
            envelope = _build_envelope(
                correlation_id=correlation_id,
                exit_code=1,
                gate=IMPLEMENT_GATE,
                reasons=["gate_status_failed"],
                next_phase=None,
                debug_path=debug_path,
            )
            print(json.dumps(envelope, sort_keys=True))
            return 1
        _finish_stage(gate_stage, status="pass", details=gate_details)

        branch_stage = _start_stage("branch_setup", details={"feature_branch": feature_dir.name})
        stages.append(branch_stage)
        try:
            branch_details = _ensure_implement_branch(repo_root, feature_dir, timeout_seconds=timeout_seconds)
        except ValueError as exc:
            _finish_stage(branch_stage, status="blocked", details={"reason": str(exc)})
            debug_path = _write_debug_payload(
                repo_root=repo_root,
                correlation_id=correlation_id,
                payload={
                    **debug_stub,
                    "result": {"blocked_stage": "branch_setup", "reason": str(exc)},
                },
            )
            envelope = _build_envelope(
                correlation_id=correlation_id,
                exit_code=1,
                gate=IMPLEMENT_GATE,
                reasons=["implement_branch_setup_failed"],
                next_phase=None,
                debug_path=debug_path,
            )
            print(json.dumps(envelope, sort_keys=True))
            return 1
        _finish_stage(branch_stage, status="pass", details=branch_details)

        session_warm = False
        while True:
            task_queue_stage = _start_stage("task_queue", details={"actor": actor_name, "feature_branch": feature_dir.name})
            stages.append(task_queue_stage)
            try:
                task_context = _select_next_registered_task(
                    repo_root=repo_root,
                    feature_dir=feature_dir,
                    feature_id=str(args.feature_id).strip(),
                    actor=actor_name,
                    correlation_id=correlation_id,
                )
            except SystemExit:
                _finish_stage(task_queue_stage, status="blocked", details={"reason": "task_queue_failed"})
                debug_path = _write_debug_payload(
                    repo_root=repo_root,
                    correlation_id=correlation_id,
                    payload={
                        **debug_stub,
                        "result": {"blocked_stage": "task_queue", "reason": "task_queue_failed"},
                    },
                )
                envelope = _build_envelope(
                    correlation_id=correlation_id,
                    exit_code=1,
                    gate=IMPLEMENT_GATE,
                    reasons=["task_queue_failed"],
                    next_phase=None,
                    debug_path=debug_path,
                )
                print(json.dumps(envelope, sort_keys=True))
                return 1
            except ValueError as exc:
                reason = str(exc) or "task_queue_failed"
                _finish_stage(task_queue_stage, status="blocked", details={"reason": reason})
                debug_path = _write_debug_payload(
                    repo_root=repo_root,
                    correlation_id=correlation_id,
                    payload={**debug_stub, "result": {"blocked_stage": "task_queue", "reason": reason}},
                )
                envelope = _build_envelope(
                    correlation_id=correlation_id,
                    exit_code=1,
                    gate=IMPLEMENT_GATE,
                    reasons=[reason],
                    next_phase=None,
                    debug_path=debug_path,
                )
                print(json.dumps(envelope, sort_keys=True))
                return 1
            _finish_stage(task_queue_stage, status="pass", details=task_context)
    
            retry_index = 0
            qa_feedback: Mapping[str, Any] | None = None
            while True:
                resume_session = session_warm
                handoff_payload: dict[str, Any] | None = None
                commit_sha = ""
                commit_source = ""
                qa_run_id = ""
                qa_result_path = Path("")
                closeout_payload: dict[str, Any] | None = None
                docs_payload: dict[str, Any] | None = None
                handoff_stage = _start_stage(
                    f"llm_handoff_round_{retry_index + 1}",
                    details={
                        "runner_configured": bool(handoff_runner),
                        "required": require_handoff,
                        "task_id": task_context["next_task_id"],
                        "task_action": task_context["task_action"],
                        "task_attempt": task_context["task_attempt"],
                        "resume_session": session_warm,
                        "retry_index": retry_index,
                    },
                )
                stages.append(handoff_stage)
                if not handoff_runner:
                    if require_handoff:
                        _finish_stage(
                            handoff_stage,
                            status="blocked",
                            details={"reason": "handoff_runner_not_configured"},
                        )
                        debug_path = _write_debug_payload(
                            repo_root=repo_root,
                            correlation_id=correlation_id,
                            payload={**debug_stub, "result": {"blocked_stage": "llm_handoff", "reason": "handoff_runner_not_configured"}},
                        )
                        envelope = _build_envelope(
                            correlation_id=correlation_id,
                            exit_code=1,
                            gate=IMPLEMENT_GATE,
                            reasons=["llm_runner_not_configured"],
                            next_phase=None,
                            debug_path=debug_path,
                        )
                        print(json.dumps(envelope, sort_keys=True))
                        return 1
                    _finish_stage(handoff_stage, status="skipped", details={"reason": "runner_not_configured"})
                    handoff_payload = None
                else:
                    try:
                        handoff_run, handoff_input = _run_handoff_round(
                            repo_root=repo_root,
                            feature_id=str(args.feature_id).strip(),
                            phase=str(args.phase),
                            correlation_id=correlation_id,
                            feature_dir=feature_dir,
                            task_context=task_context,
                            handoff_runner=handoff_runner,
                            timeout_seconds=timeout_seconds,
                            resume_session=resume_session,
                            retry_index=retry_index,
                            qa_feedback=qa_feedback,
                        )
                    except ValueError as exc:
                        reason = str(exc) or "handoff_runner_empty"
                        _finish_stage(handoff_stage, status="error", details={"reason": reason})
                        debug_path = _write_debug_payload(
                            repo_root=repo_root,
                            correlation_id=correlation_id,
                            payload={**debug_stub, "result": {"error_stage": "llm_handoff", "error_code": reason}},
                        )
                        envelope = _build_envelope(
                            correlation_id=correlation_id,
                            exit_code=2,
                            error_code=reason,
                            debug_path=debug_path,
                        )
                        print(json.dumps(envelope, sort_keys=True))
                        return 2
    
                    handoff_details: dict[str, Any] = {
                        "command": handoff_run.command,
                        "exit_code": handoff_run.exit_code,
                        "timed_out": handoff_run.timed_out,
                        "stdout_tail": _tail_lines(handoff_run.stdout),
                        "stderr_tail": _tail_lines(handoff_run.stderr),
                        "runner_log_path": None,
                        "resume_session": resume_session,
                        "retry_index": retry_index,
                        "input": handoff_input,
                    }
                    if handoff_run.timed_out:
                        _finish_stage(handoff_stage, status="blocked", details=handoff_details)
                        debug_path = _write_debug_payload(
                            repo_root=repo_root,
                            correlation_id=correlation_id,
                            payload={**debug_stub, "result": {"blocked_stage": "llm_handoff", "reason": "handoff_timeout"}},
                        )
                        envelope = _build_envelope(
                            correlation_id=correlation_id,
                            exit_code=1,
                            gate=IMPLEMENT_GATE,
                            reasons=["llm_handoff_failed"],
                            next_phase=None,
                            debug_path=debug_path,
                        )
                        print(json.dumps(envelope, sort_keys=True))
                        return 1
    
                    handoff_payload = None
                    if handoff_run.stdout.strip():
                        try:
                            handoff_payload = _parse_json_payload(handoff_run.stdout)
                        except ValueError as exc:
                            _finish_stage(
                                handoff_stage,
                                status="error",
                                details={**handoff_details, "parse_error": str(exc)},
                            )
                            debug_path = _write_debug_payload(
                                repo_root=repo_root,
                                correlation_id=correlation_id,
                                payload={**debug_stub, "result": {"error_stage": "llm_handoff", "error_code": "handoff_invalid_json"}},
                            )
                            envelope = _build_envelope(
                                correlation_id=correlation_id,
                                exit_code=2,
                                error_code="handoff_invalid_json",
                                debug_path=debug_path,
                            )
                            print(json.dumps(envelope, sort_keys=True))
                            return 2
                    handoff_details["runner_log_path"] = (
                        handoff_payload.get("runner_log_path") if isinstance(handoff_payload, Mapping) else None
                    )

                    if handoff_run.exit_code != 0 or (handoff_payload is not None and handoff_payload.get("ok") is False):
                        _finish_stage(
                            handoff_stage,
                            status="blocked",
                            details={**handoff_details, "payload": handoff_payload},
                        )
                        debug_path = _write_debug_payload(
                            repo_root=repo_root,
                            correlation_id=correlation_id,
                            payload={**debug_stub, "result": {"blocked_stage": "llm_handoff", "payload": handoff_payload}},
                        )
                        envelope = _build_envelope(
                            correlation_id=correlation_id,
                            exit_code=1,
                            gate=IMPLEMENT_GATE,
                            reasons=["llm_handoff_failed"],
                            next_phase=None,
                            debug_path=debug_path,
                        )
                        print(json.dumps(envelope, sort_keys=True))
                        return 1
                    _finish_stage(handoff_stage, status="pass", details={**handoff_details, "payload": handoff_payload})
                    session_warm = True

                commit_stage = _start_stage(
                    f"commit_resolution_round_{retry_index + 1}",
                    details={
                        "task_id": task_context["next_task_id"],
                        "task_attempt": task_context["task_attempt"],
                        "retry_index": retry_index,
                    },
                )
                stages.append(commit_stage)
                try:
                    commit_sha, commit_source = _resolve_commit_sha(
                        repo_root,
                        timeout_seconds=timeout_seconds,
                        handoff_payload=handoff_payload,
                    )
                except ValueError as exc:
                    reason = str(exc) or "commit_sha_unavailable"
                    _finish_stage(commit_stage, status="blocked", details={"reason": reason})
                    debug_path = _write_debug_payload(
                        repo_root=repo_root,
                        correlation_id=correlation_id,
                        payload={**debug_stub, "result": {"blocked_stage": "commit_resolution", "reason": reason}},
                    )
                    envelope = _build_envelope(
                        correlation_id=correlation_id,
                        exit_code=1,
                        gate=IMPLEMENT_GATE,
                        reasons=[reason],
                        next_phase=None,
                        debug_path=debug_path,
                    )
                    print(json.dumps(envelope, sort_keys=True))
                    return 1
                _finish_stage(
                    commit_stage,
                    status="pass",
                    details={"commit_sha": commit_sha, "source": commit_source},
                )
    
                task_id = str(task_context["next_task_id"])
                task_attempt = int(task_context["task_attempt"])
    
                offline_qa_stage = _start_stage(
                    f"offline_qa_handoff_round_{retry_index + 1}",
                    details={
                        "task_id": task_id,
                        "task_attempt": task_attempt,
                        "retry_index": retry_index,
                    },
                )
                stages.append(offline_qa_stage)
                try:
                    qa_payload = _run_offline_qa_handoff(
                        feature_id=str(args.feature_id).strip(),
                        task_id=task_id,
                        attempt=task_attempt,
                    )
                except ValueError as exc:
                    reason = str(exc) or "offline_qa_handoff_failed"
                    _finish_stage(offline_qa_stage, status="blocked", details={"reason": reason})
                    debug_path = _write_debug_payload(
                        repo_root=repo_root,
                        correlation_id=correlation_id,
                        payload={**debug_stub, "result": {"blocked_stage": "offline_qa_handoff", "reason": reason}},
                    )
                    envelope = _build_envelope(
                        correlation_id=correlation_id,
                        exit_code=1,
                        gate=IMPLEMENT_GATE,
                        reasons=[reason],
                        next_phase=None,
                        debug_path=debug_path,
                    )
                    print(json.dumps(envelope, sort_keys=True))
                    return 1
    
                qa_result_file_raw = str(qa_payload.get("result_file") or "").strip()
                qa_run_id = str(qa_payload.get("qa_run_id") or "").strip()
                qa_result_verdict = str(qa_payload.get("result_verdict") or "").strip().upper()
                if not qa_result_file_raw:
                    _finish_stage(
                        offline_qa_stage,
                        status="blocked",
                        details={**qa_payload, "reason": "offline_qa_result_file_missing"},
                    )
                    debug_path = _write_debug_payload(
                        repo_root=repo_root,
                        correlation_id=correlation_id,
                        payload={
                            **debug_stub,
                            "result": {
                                "blocked_stage": "offline_qa_handoff",
                                "reason": "offline_qa_result_file_missing",
                                "payload": qa_payload,
                            },
                        },
                    )
                    envelope = _build_envelope(
                        correlation_id=correlation_id,
                        exit_code=1,
                        gate=IMPLEMENT_GATE,
                        reasons=["offline_qa_result_file_missing"],
                        next_phase=None,
                        debug_path=debug_path,
                    )
                    print(json.dumps(envelope, sort_keys=True))
                    return 1
                if not qa_run_id:
                    _finish_stage(
                        offline_qa_stage,
                        status="blocked",
                        details={**qa_payload, "reason": "offline_qa_run_id_missing"},
                    )
                    debug_path = _write_debug_payload(
                        repo_root=repo_root,
                        correlation_id=correlation_id,
                        payload={
                            **debug_stub,
                            "result": {
                                "blocked_stage": "offline_qa_handoff",
                                "reason": "offline_qa_run_id_missing",
                                "payload": qa_payload,
                            },
                        },
                    )
                    envelope = _build_envelope(
                        correlation_id=correlation_id,
                        exit_code=1,
                        gate=IMPLEMENT_GATE,
                        reasons=["offline_qa_run_id_missing"],
                        next_phase=None,
                        debug_path=debug_path,
                    )
                    print(json.dumps(envelope, sort_keys=True))
                    return 1
    
                qa_passed = qa_result_verdict == "PASS" and bool(qa_payload.get("ok", False))
                qa_result_path = Path(qa_result_file_raw)
                if qa_passed:
                    _finish_stage(offline_qa_stage, status="pass", details=qa_payload)
                    break
    
                reason = "offline_qa_failed"
                _finish_stage(
                    offline_qa_stage,
                    status="blocked",
                    details={
                        **qa_payload,
                        "reason": reason,
                        "retry_index": retry_index,
                        "resume_session": bool(handoff_runner),
                        "will_retry": retry_index < MAX_QA_RETRIES - 1 and bool(handoff_runner),
                    },
                )
                if retry_index >= MAX_QA_RETRIES - 1 or not handoff_runner:
                    debug_path = _write_debug_payload(
                        repo_root=repo_root,
                        correlation_id=correlation_id,
                        payload={
                            **debug_stub,
                            "result": {
                                "blocked_stage": "offline_qa_handoff",
                                "reason": reason,
                                "payload": qa_payload,
                            },
                        },
                    )
                    envelope = _build_envelope(
                        correlation_id=correlation_id,
                        exit_code=1,
                        gate=IMPLEMENT_GATE,
                        reasons=[reason],
                        next_phase=None,
                        debug_path=debug_path,
                    )
                    print(json.dumps(envelope, sort_keys=True))
                    return 1
    
                resume_session = True
                qa_feedback = qa_payload
                retry_index += 1
                continue
    
            closeout_stage = _start_stage(
                "closeout",
                details={
                    "task_id": task_id,
                    "task_attempt": task_attempt,
                    "qa_run_id": qa_run_id,
                    "commit_sha": commit_sha,
                },
            )
            stages.append(closeout_stage)
            try:
                closeout_result = _closeout_task(
                    feature_id=str(args.feature_id).strip(),
                    task_id=task_id,
                    tasks_file=Path(task_context["tasks_file"]),
                    ledger_path=Path(task_context["ledger_path"]),
                    commit_sha=commit_sha,
                    qa_run_id=qa_run_id,
                    qa_result_path=qa_result_path,
                    actor=actor_name,
                )
            except ValueError as exc:
                reason = str(exc) or "task_closeout_failed"
                _finish_stage(closeout_stage, status="blocked", details={"reason": reason})
                debug_path = _write_debug_payload(
                    repo_root=repo_root,
                    correlation_id=correlation_id,
                    payload={**debug_stub, "result": {"blocked_stage": "closeout", "reason": reason}},
                )
                envelope = _build_envelope(
                    correlation_id=correlation_id,
                    exit_code=1,
                    gate=IMPLEMENT_GATE,
                    reasons=[reason],
                    next_phase=None,
                    debug_path=debug_path,
                )
                print(json.dumps(envelope, sort_keys=True))
                return 1
    
            closeout_payload = json.loads(closeout_result.to_json())
            if not closeout_result.ok:
                reason = "offline_qa_failed" if closeout_result.qa_verdict and closeout_result.qa_verdict != "PASS" else "task_closeout_failed"
                _finish_stage(closeout_stage, status="blocked", details={"reason": reason, "result": closeout_payload})
                debug_path = _write_debug_payload(
                    repo_root=repo_root,
                    correlation_id=correlation_id,
                    payload={**debug_stub, "result": {"blocked_stage": "closeout", "reason": reason, "closeout": closeout_payload}},
                )
                envelope = _build_envelope(
                    correlation_id=correlation_id,
                    exit_code=1,
                    gate=IMPLEMENT_GATE,
                    reasons=[reason],
                    next_phase=None,
                    debug_path=debug_path,
                )
                print(json.dumps(envelope, sort_keys=True))
                return 1
            _finish_stage(closeout_stage, status="pass", details=closeout_payload)
            assert closeout_payload is not None
    
            docs_stage = _start_stage(
                "docs_update",
                details={
                    "task_id": task_id,
                    "commit_sha": commit_sha,
                    "qa_run_id": qa_run_id,
                },
            )
            stages.append(docs_stage)
            try:
                docs_payload = _update_implementation_docs(
                    feature_dir=feature_dir,
                    correlation_id=correlation_id,
                    task_context=task_context,
                    commit_sha=commit_sha,
                    qa_run_id=qa_run_id,
                    closeout_result=closeout_payload,
                )
            except ValueError as exc:
                reason = str(exc) or "implement_docs_failed"
                _finish_stage(docs_stage, status="blocked", details={"reason": reason})
                debug_path = _write_debug_payload(
                    repo_root=repo_root,
                    correlation_id=correlation_id,
                    payload={**debug_stub, "result": {"blocked_stage": "docs_update", "reason": reason}},
                )
                envelope = _build_envelope(
                    correlation_id=correlation_id,
                    exit_code=1,
                    gate=IMPLEMENT_GATE,
                    reasons=[reason],
                    next_phase=None,
                    debug_path=debug_path,
                )
                print(json.dumps(envelope, sort_keys=True))
                return 1
            _finish_stage(docs_stage, status="pass", details=docs_payload)
    
            task_gate_stage = _start_stage("task_gate")
            stages.append(task_gate_stage)
            task_gate_cmd = [
                sys.executable,
                str((repo_root / "scripts" / "speckit_implement_gate.py").resolve()),
                "task-gate",
                "--feature-dir",
                str(feature_dir),
                "--json",
            ]
            task_gate_run = _run_command(task_gate_cmd, cwd=repo_root, timeout_seconds=timeout_seconds)
            task_gate_details: dict[str, Any] = {
                "command": task_gate_run.command,
                "exit_code": task_gate_run.exit_code,
                "timed_out": task_gate_run.timed_out,
                "stdout_tail": _tail_lines(task_gate_run.stdout),
                "stderr_tail": _tail_lines(task_gate_run.stderr),
            }
            if task_gate_run.timed_out:
                _finish_stage(task_gate_stage, status="error", details=task_gate_details)
                debug_path = _write_debug_payload(
                    repo_root=repo_root,
                    correlation_id=correlation_id,
                    payload={**debug_stub, "result": {"error_stage": "task_gate", "error_code": "task_gate_timeout"}},
                )
                envelope = _build_envelope(
                    correlation_id=correlation_id,
                    exit_code=2,
                    error_code="task_gate_timeout",
                    debug_path=debug_path,
                )
                print(json.dumps(envelope, sort_keys=True))
                return 2
    
            task_gate_payload = _parse_json_payload(task_gate_run.stdout)
            task_gate_details["report"] = task_gate_payload
            if task_gate_run.exit_code != 0 or not bool(task_gate_payload.get("ok")):
                _finish_stage(task_gate_stage, status="blocked", details=task_gate_details)
                debug_path = _write_debug_payload(
                    repo_root=repo_root,
                    correlation_id=correlation_id,
                    payload={**debug_stub, "result": {"blocked_stage": "task_gate", "gate_report": task_gate_payload}},
                )
                envelope = _build_envelope(
                    correlation_id=correlation_id,
                    exit_code=1,
                    gate=IMPLEMENT_GATE,
                    reasons=["task_gate_failed"],
                    next_phase=None,
                    debug_path=debug_path,
                )
                print(json.dumps(envelope, sort_keys=True))
                return 1
            _finish_stage(task_gate_stage, status="pass", details=task_gate_details)
            if task_gate_payload.get("continuation_task_id"):
                session_warm = True
                continue
    
            debug_path = _write_debug_payload(
                repo_root=repo_root,
                correlation_id=correlation_id,
                payload={
                    **debug_stub,
                    "result": {
                        "status": "success",
                        "task_id": task_id,
                        "task_attempt": task_attempt,
                        "commit_sha": commit_sha,
                        "qa_run_id": qa_run_id,
                    },
                },
            )
            envelope = _build_envelope(
                correlation_id=correlation_id,
                exit_code=0,
                next_phase=str(args.next_phase),
                debug_path=debug_path,
            )
            print(json.dumps(envelope, sort_keys=True))
            return 0

    except Exception as exc:  # pragma: no cover - defensive envelope fallback
        fallback_path = _write_debug_payload(
            repo_root=repo_root,
            correlation_id=correlation_id or "unknown",
            payload={
                **debug_stub,
                "result": {
                    "status": "error",
                    "error_code": "implement_step_unhandled_exception",
                    "exception": str(exc),
                },
            },
        )
        envelope = _build_envelope(
            correlation_id=correlation_id or "unknown",
            exit_code=2,
            error_code="implement_step_unhandled_exception",
            debug_path=fallback_path,
        )
        print(json.dumps(envelope, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
