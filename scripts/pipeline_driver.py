#!/usr/bin/env python3
"""Deterministic pipeline driver entrypoint (skeleton)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
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
        "debug_path": None,
        "stdout": stdout,
        "stderr": stderr,
        "process_exit_code": process_exit_code,
        "timed_out": timed_out,
    }


def run_step(
    command: Sequence[str],
    *,
    timeout_seconds: int,
    correlation_id: str,
    cwd: str | Path | None = None,
    env_overrides: Mapping[str, str] | None = None,
    input_payload: str | None = None,
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

    process = subprocess.Popen(
        list(command),
        cwd=str(cwd) if cwd is not None else None,
        env=process_env,
        stdin=subprocess.PIPE if input_payload is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        stdout, stderr = process.communicate(input=input_payload, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        return _runtime_failure_result(
            correlation_id=correlation_id,
            error_code="step_timeout",
            reason="step_timeout",
            stdout=stdout,
            stderr=stderr,
            process_exit_code=process.returncode,
            timed_out=True,
        )

    exit_code = process.returncode
    if exit_code not in (0, 1, 2):
        return _runtime_failure_result(
            correlation_id=correlation_id,
            error_code="invalid_exit_code",
            reason="invalid_exit_code",
            stdout=stdout,
            stderr=stderr,
            process_exit_code=exit_code,
            timed_out=False,
        )

    payload_text = stdout.strip()
    if not payload_text:
        return _runtime_failure_result(
            correlation_id=correlation_id,
            error_code="missing_step_result",
            reason="missing_step_result",
            stdout=stdout,
            stderr=stderr,
            process_exit_code=exit_code,
            timed_out=False,
        )

    try:
        envelope = json.loads(payload_text)
    except json.JSONDecodeError:
        return _runtime_failure_result(
            correlation_id=correlation_id,
            error_code="invalid_json_result",
            reason="invalid_json_result",
            stdout=stdout,
            stderr=stderr,
            process_exit_code=exit_code,
            timed_out=False,
        )

    try:
        parsed = parse_step_result(envelope)
    except ValueError:
        return _runtime_failure_result(
            correlation_id=correlation_id,
            error_code="invalid_step_result",
            reason="invalid_step_result",
            stdout=stdout,
            stderr=stderr,
            process_exit_code=exit_code,
            timed_out=False,
        )

    if parsed["exit_code"] != exit_code:
        return _runtime_failure_result(
            correlation_id=correlation_id,
            error_code="exit_code_mismatch",
            reason="exit_code_mismatch",
            stdout=stdout,
            stderr=stderr,
            process_exit_code=exit_code,
            timed_out=False,
        )

    if parsed["correlation_id"] != correlation_id:
        return _runtime_failure_result(
            correlation_id=correlation_id,
            error_code="correlation_id_mismatch",
            reason="correlation_id_mismatch",
            stdout=stdout,
            stderr=stderr,
            process_exit_code=exit_code,
            timed_out=False,
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
