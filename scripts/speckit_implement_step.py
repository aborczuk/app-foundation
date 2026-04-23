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
from typing import Any, Sequence

SCHEMA_VERSION = "1.0.0"
IMPLEMENT_GATE = "implement_execution"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_PHASE_TYPE = "story"
DEFAULT_NEXT_PHASE = "closed"


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
    correlation_id = str(args.correlation_id).strip()
    require_handoff = bool(args.require_handoff or _bool_env("SPECKIT_REQUIRE_HANDOFF"))
    timeout_seconds = max(1, int(args.timeout_seconds))
    stages: list[dict[str, Any]] = []

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
            "handoff_runner_configured": bool(str(args.handoff_runner).strip() or os.environ.get("SPECKIT_HANDOFF_RUNNER", "").strip()),
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

        handoff_runner = str(args.handoff_runner).strip() or str(os.environ.get("SPECKIT_HANDOFF_RUNNER", "")).strip()
        handoff_stage = _start_stage(
            "llm_handoff",
            details={"runner_configured": bool(handoff_runner), "required": require_handoff},
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
        else:
            handoff_cmd = shlex.split(handoff_runner)
            if not handoff_cmd:
                _finish_stage(handoff_stage, status="error", details={"reason": "runner_command_empty"})
                debug_path = _write_debug_payload(
                    repo_root=repo_root,
                    correlation_id=correlation_id,
                    payload={**debug_stub, "result": {"error_stage": "llm_handoff", "error_code": "handoff_runner_empty"}},
                )
                envelope = _build_envelope(
                    correlation_id=correlation_id,
                    exit_code=2,
                    error_code="handoff_runner_empty",
                    debug_path=debug_path,
                )
                print(json.dumps(envelope, sort_keys=True))
                return 2

            handoff_input = {
                "feature_id": str(args.feature_id),
                "phase": str(args.phase),
                "correlation_id": correlation_id,
                "step_name": "speckit.implement",
                "feature_dir": str(feature_dir),
            }
            handoff_run = _run_command(
                handoff_cmd,
                cwd=repo_root,
                timeout_seconds=timeout_seconds,
                input_payload=json.dumps(handoff_input, sort_keys=True),
            )
            handoff_details: dict[str, Any] = {
                "command": handoff_run.command,
                "exit_code": handoff_run.exit_code,
                "timed_out": handoff_run.timed_out,
                "stdout_tail": _tail_lines(handoff_run.stdout),
                "stderr_tail": _tail_lines(handoff_run.stderr),
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

            handoff_payload: dict[str, Any] | None = None
            if handoff_run.stdout.strip():
                try:
                    handoff_payload = _parse_json_payload(handoff_run.stdout)
                except ValueError as exc:
                    _finish_stage(handoff_stage, status="error", details={**handoff_details, "parse_error": str(exc)})
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

        phase_gate_stage = _start_stage("phase_gate")
        stages.append(phase_gate_stage)
        phase_gate_cmd = [
            sys.executable,
            str((repo_root / "scripts" / "speckit_implement_gate.py").resolve()),
            "phase-gate",
            "--feature-dir",
            str(feature_dir),
            "--phase-name",
            str(args.phase),
            "--phase-type",
            str(args.phase_type),
            "--layer1",
            "pass",
            "--layer2",
            "pass",
            "--layer3",
            "pass",
            "--json",
        ]
        phase_gate_run = _run_command(phase_gate_cmd, cwd=repo_root, timeout_seconds=timeout_seconds)
        phase_gate_details: dict[str, Any] = {
            "command": phase_gate_run.command,
            "exit_code": phase_gate_run.exit_code,
            "timed_out": phase_gate_run.timed_out,
            "stdout_tail": _tail_lines(phase_gate_run.stdout),
            "stderr_tail": _tail_lines(phase_gate_run.stderr),
        }
        if phase_gate_run.timed_out:
            _finish_stage(phase_gate_stage, status="error", details=phase_gate_details)
            debug_path = _write_debug_payload(
                repo_root=repo_root,
                correlation_id=correlation_id,
                payload={**debug_stub, "result": {"error_stage": "phase_gate", "error_code": "phase_gate_timeout"}},
            )
            envelope = _build_envelope(
                correlation_id=correlation_id,
                exit_code=2,
                error_code="phase_gate_timeout",
                debug_path=debug_path,
            )
            print(json.dumps(envelope, sort_keys=True))
            return 2

        phase_gate_payload = _parse_json_payload(phase_gate_run.stdout)
        phase_gate_details["report"] = phase_gate_payload
        if phase_gate_run.exit_code != 0 or not bool(phase_gate_payload.get("ok")):
            _finish_stage(phase_gate_stage, status="blocked", details=phase_gate_details)
            debug_path = _write_debug_payload(
                repo_root=repo_root,
                correlation_id=correlation_id,
                payload={**debug_stub, "result": {"blocked_stage": "phase_gate", "gate_report": phase_gate_payload}},
            )
            envelope = _build_envelope(
                correlation_id=correlation_id,
                exit_code=1,
                gate=IMPLEMENT_GATE,
                reasons=["phase_gate_failed"],
                next_phase=None,
                debug_path=debug_path,
            )
            print(json.dumps(envelope, sort_keys=True))
            return 1
        _finish_stage(phase_gate_stage, status="pass", details=phase_gate_details)

        debug_path = _write_debug_payload(
            repo_root=repo_root,
            correlation_id=correlation_id,
            payload={**debug_stub, "result": {"status": "success"}},
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
