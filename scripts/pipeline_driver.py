#!/usr/bin/env python3
"""Deterministic pipeline driver entrypoint (skeleton)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping, Sequence

from pipeline_driver_contracts import parse_step_result
from pipeline_driver_state import resolve_phase_state


def _runtime_failure_result(
    *,
    correlation_id: str,
    error_code: str,
    reason: str,
    stdout: str,
    stderr: str,
    process_exit_code: int | None,
    timed_out: bool,
    debug_path: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "ok": False,
        "exit_code": 2,
        "correlation_id": correlation_id,
        "gate": None,
        "reasons": [reason],
        "error_code": error_code,
        "next_phase": None,
        "debug_path": debug_path,
        "stdout": stdout,
        "stderr": stderr,
        "process_exit_code": process_exit_code,
        "timed_out": timed_out,
    }


def _execute_command(
    command: Sequence[str],
    *,
    timeout_seconds: int,
    cwd: str | Path | None,
    env: Mapping[str, str],
    input_payload: str | None,
) -> dict[str, Any]:
    process = subprocess.Popen(
        list(command),
        cwd=str(cwd) if cwd is not None else None,
        env=dict(env),
        stdin=subprocess.PIPE if input_payload is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        stdout, stderr = process.communicate(input=input_payload, timeout=timeout_seconds)
        return {
            "exit_code": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        return {
            "exit_code": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": True,
        }


def _runtime_sidecar_path(correlation_id: str, sidecar_dir: str | Path) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", correlation_id).strip("_")
    if not safe_name:
        safe_name = "runtime_failure"
    directory = Path(sidecar_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{safe_name}.runtime.json"


def handle_runtime_failure(
    command: Sequence[str],
    *,
    correlation_id: str,
    timeout_seconds: int,
    cwd: str | Path | None = None,
    env_overrides: Mapping[str, str] | None = None,
    input_payload: str | None = None,
    error_code: str,
    reason: str,
    initial_stdout: str,
    initial_stderr: str,
    initial_exit_code: int | None,
    initial_timed_out: bool,
    sidecar_dir: str | Path = ".speckit/runtime-failures",
) -> dict[str, Any]:
    """Run one verbose rerun and persist deterministic runtime diagnostics."""

    rerun_env = os.environ.copy()
    if env_overrides:
        rerun_env.update({str(key): str(value) for key, value in env_overrides.items()})
    rerun_env["SPECKIT_VERBOSE"] = "1"

    rerun_result = _execute_command(
        command,
        timeout_seconds=timeout_seconds,
        cwd=cwd,
        env=rerun_env,
        input_payload=input_payload,
    )

    sidecar_payload = {
        "schema_version": "1.0.0",
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "correlation_id": correlation_id,
        "error_code": error_code,
        "reason": reason,
        "command": list(command),
        "initial": {
            "exit_code": initial_exit_code,
            "timed_out": initial_timed_out,
            "stdout": initial_stdout,
            "stderr": initial_stderr,
        },
        "rerun": rerun_result,
    }
    sidecar_path = _runtime_sidecar_path(correlation_id, sidecar_dir)
    sidecar_path.write_text(json.dumps(sidecar_payload, indent=2, sort_keys=True), encoding="utf-8")

    return _runtime_failure_result(
        correlation_id=correlation_id,
        error_code=error_code,
        reason=reason,
        stdout=initial_stdout,
        stderr=initial_stderr,
        process_exit_code=initial_exit_code,
        timed_out=initial_timed_out,
        debug_path=str(sidecar_path),
    )


def run_step(
    command: Sequence[str],
    *,
    timeout_seconds: int,
    correlation_id: str,
    cwd: str | Path | None = None,
    env_overrides: Mapping[str, str] | None = None,
    input_payload: str | None = None,
    sidecar_dir: str | Path = ".speckit/runtime-failures",
) -> dict[str, Any]:
    """Execute a deterministic step script and route by canonical exit semantics."""

    if not command:
        raise ValueError("command must include at least one token")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be a positive integer")
    if not correlation_id:
        raise ValueError("correlation_id is required")

    process_env = os.environ.copy()
    if env_overrides:
        process_env.update({str(key): str(value) for key, value in env_overrides.items()})

    execution = _execute_command(
        command,
        timeout_seconds=timeout_seconds,
        cwd=cwd,
        env=process_env,
        input_payload=input_payload,
    )
    stdout = str(execution["stdout"])
    stderr = str(execution["stderr"])
    exit_code = execution["exit_code"]
    timed_out = bool(execution["timed_out"])

    if timed_out:
        return handle_runtime_failure(
            command,
            correlation_id=correlation_id,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            env_overrides=env_overrides,
            input_payload=input_payload,
            error_code="step_timeout",
            reason="step_timeout",
            initial_stdout=stdout,
            initial_stderr=stderr,
            initial_exit_code=exit_code,
            initial_timed_out=True,
            sidecar_dir=sidecar_dir,
        )

    if exit_code not in (0, 1, 2):
        return handle_runtime_failure(
            command,
            correlation_id=correlation_id,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            env_overrides=env_overrides,
            input_payload=input_payload,
            error_code="invalid_exit_code",
            reason="invalid_exit_code",
            initial_stdout=stdout,
            initial_stderr=stderr,
            initial_exit_code=exit_code,
            initial_timed_out=False,
            sidecar_dir=sidecar_dir,
        )

    payload_text = stdout.strip()
    if not payload_text:
        return handle_runtime_failure(
            command,
            correlation_id=correlation_id,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            env_overrides=env_overrides,
            input_payload=input_payload,
            error_code="missing_step_result",
            reason="missing_step_result",
            initial_stdout=stdout,
            initial_stderr=stderr,
            initial_exit_code=exit_code,
            initial_timed_out=False,
            sidecar_dir=sidecar_dir,
        )

    try:
        envelope = json.loads(payload_text)
    except json.JSONDecodeError:
        return handle_runtime_failure(
            command,
            correlation_id=correlation_id,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            env_overrides=env_overrides,
            input_payload=input_payload,
            error_code="invalid_json_result",
            reason="invalid_json_result",
            initial_stdout=stdout,
            initial_stderr=stderr,
            initial_exit_code=exit_code,
            initial_timed_out=False,
            sidecar_dir=sidecar_dir,
        )

    try:
        parsed = parse_step_result(envelope)
    except ValueError:
        return handle_runtime_failure(
            command,
            correlation_id=correlation_id,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            env_overrides=env_overrides,
            input_payload=input_payload,
            error_code="invalid_step_result",
            reason="invalid_step_result",
            initial_stdout=stdout,
            initial_stderr=stderr,
            initial_exit_code=exit_code,
            initial_timed_out=False,
            sidecar_dir=sidecar_dir,
        )

    if parsed["exit_code"] != exit_code:
        return handle_runtime_failure(
            command,
            correlation_id=correlation_id,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            env_overrides=env_overrides,
            input_payload=input_payload,
            error_code="exit_code_mismatch",
            reason="exit_code_mismatch",
            initial_stdout=stdout,
            initial_stderr=stderr,
            initial_exit_code=exit_code,
            initial_timed_out=False,
            sidecar_dir=sidecar_dir,
        )

    if parsed["correlation_id"] != correlation_id:
        return handle_runtime_failure(
            command,
            correlation_id=correlation_id,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            env_overrides=env_overrides,
            input_payload=input_payload,
            error_code="correlation_id_mismatch",
            reason="correlation_id_mismatch",
            initial_stdout=stdout,
            initial_stderr=stderr,
            initial_exit_code=exit_code,
            initial_timed_out=False,
            sidecar_dir=sidecar_dir,
        )

    result = dict(parsed)
    result["stdout"] = stdout
    result["stderr"] = stderr
    result["process_exit_code"] = exit_code
    result["timed_out"] = False
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic pipeline steps")
    parser.add_argument("--feature-id", required=True, help="Feature id, e.g. 019")
    parser.add_argument(
        "--phase",
        default="setup",
        help="Requested phase label (placeholder; validated in later tasks)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    phase_state = resolve_phase_state(
        args.feature_id,
        pipeline_state={"phase": args.phase},
    )

    step_result = parse_step_result(
        {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": f"{args.feature_id}:{args.phase}:skeleton",
            "next_phase": phase_state["phase"],
        }
    )
    print(
        json.dumps(
            {
                "feature_id": args.feature_id,
                "phase_state": phase_state,
                "step_result": step_result,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
