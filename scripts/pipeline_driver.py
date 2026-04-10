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

from pipeline_driver_contracts import parse_step_result, render_status_lines
from pipeline_driver_state import resolve_phase_state


def build_correlation_id(
    feature_id: str,
    step_name: str,
    *,
    run_id: str | None = None,
    timestamp_utc: datetime | None = None,
) -> str:
    """Build a run-scoped correlation ID for step execution and diagnostics."""

    if not feature_id:
        raise ValueError("feature_id is required")
    if not step_name:
        raise ValueError("step_name is required")

    safe_step = re.sub(r"[^A-Za-z0-9_.-]+", "_", step_name).strip("_")
    if not safe_step:
        raise ValueError("step_name must contain at least one valid token character")

    if run_id and run_id.strip():
        safe_run = re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id.strip()).strip("_")
    else:
        effective_time = timestamp_utc or datetime.now(timezone.utc)
        safe_run = (
            "run_"
            + effective_time.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + f"_{feature_id}"
        )

    return f"{safe_run}:{safe_step}"


def validate_generated_artifact(
    artifact_path: str | Path,
    *,
    correlation_id: str,
    completion_marker: str | None = None,
) -> dict[str, Any]:
    """Validate LLM-generated artifacts before success event append.

    Returns {"ok": True} or a blocked step result if validation fails.
    """

    if not artifact_path:
        raise ValueError("artifact_path is required")
    if not correlation_id or not isinstance(correlation_id, str):
        raise ValueError("correlation_id is required")

    artifact = Path(artifact_path)

    # Check artifact exists
    if not artifact.exists():
        return {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 1,
            "correlation_id": correlation_id,
            "gate": "artifact_validation",
            "reasons": ["artifact_not_created"],
            "error_code": None,
            "next_phase": None,
            "debug_path": None,
        }

    # Check artifact has content
    try:
        content = artifact.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 1,
            "correlation_id": correlation_id,
            "gate": "artifact_validation",
            "reasons": ["artifact_unreadable"],
            "error_code": None,
            "next_phase": None,
            "debug_path": None,
        }

    # Check minimum content length
    if not content or len(content.strip()) < 10:
        return {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 1,
            "correlation_id": correlation_id,
            "gate": "artifact_validation",
            "reasons": ["artifact_empty_or_minimal"],
            "error_code": None,
            "next_phase": None,
            "debug_path": None,
        }

    # If completion marker specified, verify it's present
    if completion_marker and isinstance(completion_marker, str):
        if completion_marker not in content:
            return {
                "schema_version": "1.0.0",
                "ok": False,
                "exit_code": 1,
                "correlation_id": correlation_id,
                "gate": "artifact_validation",
                "reasons": ["completion_marker_not_found"],
                "error_code": None,
                "next_phase": None,
                "debug_path": None,
            }

    # Validation passed
    return {"ok": True}


def emit_human_status(
    step_result: dict[str, Any],
    *,
    file=None,
) -> None:
    """Emit compact three-line human status output from step result.

    Suppresses verbose output and emits only the canonical Done/Next/Blocked status contract.
    Uses render_status_lines from pipeline_driver_contracts for canonical formatting.
    """

    exit_code = step_result.get("exit_code")

    if exit_code == 0:
        # Success path: emit done status and next phase
        done_msg = f"Step completed successfully"
        next_msg = f"Next phase: {step_result.get('next_phase', 'unknown')}"
        blocked_msg = "none"
    elif exit_code == 1:
        # Blocked path: emit gate and reasons
        gate = step_result.get("gate", "unknown")
        reasons = step_result.get("reasons", [])
        reason_str = ", ".join(reasons) if reasons else "unknown"
        done_msg = "none"
        next_msg = "none"
        blocked_msg = f"{gate}: {reason_str}"
    elif exit_code == 2:
        # Error path: emit error code
        error_code = step_result.get("error_code", "unknown")
        debug_path = step_result.get("debug_path")
        done_msg = "none"
        next_msg = "none"
        blocked_msg = f"Error: {error_code}" + (f" (debug: {debug_path})" if debug_path else "")
    else:
        done_msg = "none"
        next_msg = "none"
        blocked_msg = "none"

    status_lines = render_status_lines(
        done=done_msg,
        next_step=next_msg,
        blocked=blocked_msg,
    )

    for line in status_lines:
        print(line, file=file)


def drill_down_failure(
    step_result: dict[str, Any],
    *,
    feature_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Provide detailed diagnostics for a failed step.

    For error paths (exit_code=2), reads the sidecar debug file and returns full diagnostic context.
    For blocked paths (exit_code=1), returns gate and reasons with contract validation.
    """
    from pipeline_driver_contracts import validate_reason_codes

    exit_code = step_result.get("exit_code")
    debug_path = step_result.get("debug_path")

    if exit_code == 2 and debug_path:
        # Error path: try to load sidecar diagnostics
        debug_file = Path(debug_path)
        if debug_file.exists():
            try:
                sidecar_data = json.loads(debug_file.read_text(encoding="utf-8"))
                return {
                    "success": True,
                    "exit_code": exit_code,
                    "error_code": step_result.get("error_code"),
                    "debug_path": debug_path,
                    "sidecar_data": sidecar_data,
                    "message": f"Full diagnostics available at {debug_path}",
                }
            except (OSError, json.JSONDecodeError):
                return {
                    "success": False,
                    "exit_code": exit_code,
                    "error_code": step_result.get("error_code"),
                    "debug_path": debug_path,
                    "message": f"Could not read sidecar diagnostics at {debug_path}",
                }
        else:
            return {
                "success": False,
                "exit_code": exit_code,
                "error_code": step_result.get("error_code"),
                "debug_path": debug_path,
                "message": f"Sidecar diagnostics file not found: {debug_path}",
            }
    elif exit_code == 1:
        # Blocked path: return gate and reasons with validation
        gate = step_result.get("gate")
        reasons = step_result.get("reasons", [])

        # Validate reason codes
        validation_errors = validate_reason_codes(step_result)
        diagnostic = {
            "success": True,
            "exit_code": exit_code,
            "gate": gate,
            "reasons": reasons,
            "message": "Step blocked - review gate and reasons above",
        }
        if validation_errors:
            diagnostic["reason_code_errors"] = validation_errors

        return diagnostic
    else:
        return {
            "success": False,
            "exit_code": exit_code,
            "message": "No diagnostics available for this step result",
        }


def enforce_approval_breakpoint(
    step_name: str,
    *,
    approval_token: str | None = None,
    breakpoint_config: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Enforce configurable approval breakpoints for security-sensitive steps.

    Returns a blocked result if approval is required but token not present/valid.
    Returns {"ok": True} if step is approved or not breakpointed.
    """

    if not step_name:
        raise ValueError("step_name is required")

    if not breakpoint_config:
        # No breakpoint configured for this step
        return {"ok": True, "breakpoint_enforced": False}

    if not isinstance(breakpoint_config, dict):
        return {"ok": True, "breakpoint_enforced": False}

    step_breakpoints = breakpoint_config.get("steps", {})
    if step_name not in step_breakpoints:
        # Step not in breakpoint config
        return {"ok": True, "breakpoint_enforced": False}

    breakpoint_entry = step_breakpoints[step_name]
    if not isinstance(breakpoint_entry, dict):
        return {"ok": True, "breakpoint_enforced": False}

    if not bool(breakpoint_entry.get("enabled", False)):
        # Breakpoint disabled for this step
        return {"ok": True, "breakpoint_enforced": False}

    # Breakpoint is enabled for this step
    required_scope = breakpoint_entry.get("required_scope")
    if not approval_token:
        # No approval token provided - block
        return {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 1,
            "correlation_id": correlation_id or "unknown",
            "gate": "approval_required",
            "reasons": [f"breakpoint_scope:{required_scope}"],
            "error_code": None,
            "next_phase": None,
            "debug_path": None,
        }

    # Token provided - validate it (simple scope check)
    token_scope = approval_token.split(":")[0] if approval_token else None
    if token_scope != required_scope:
        # Token scope mismatch - block
        return {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 1,
            "correlation_id": correlation_id or "unknown",
            "gate": "approval_required",
            "reasons": ["approval_token_scope_mismatch"],
            "error_code": None,
            "next_phase": None,
            "debug_path": None,
        }

    # Token valid - approve
    return {"ok": True, "breakpoint_enforced": True, "approval_granted": True}


def route_legacy_step(
    mapping_result: dict[str, Any],
    *,
    correlation_id: str,
) -> dict[str, Any]:
    """Handle legacy routing for non-driver-managed phases.

    Returns a blocked step result for phases not yet migrated to driver control,
    supporting incremental migration mode (FR-007, SC-004).
    """

    if not isinstance(mapping_result, dict):
        raise ValueError("mapping_result must be a dict")
    if not correlation_id or not isinstance(correlation_id, str):
        raise ValueError("correlation_id is required")

    mapping_type = mapping_result.get("type")
    if mapping_type != "legacy":
        raise ValueError(f"route_legacy_step only handles legacy type, got: {mapping_type}")

    command_id = mapping_result.get("command_id", "unknown")
    reason = mapping_result.get("reason", "unmapped_command")

    # Return a blocked state for non-migrated phases
    # This allows mixed-mode migration where some phases use driver and others don't
    return {
        "schema_version": "1.0.0",
        "ok": False,
        "exit_code": 1,
        "correlation_id": correlation_id,
        "gate": "command_not_driver_managed",
        "reasons": [
            f"command_not_in_migration_scope",
            f"legacy_fallback:{reason}",
        ],
        "error_code": None,
        "next_phase": None,
        "debug_path": None,
    }


def resolve_step_mapping(
    phase: str,
    *,
    manifest_path: str | Path | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Resolve command routing for the given phase.

    Returns either:
    - Deterministic: {"type": "deterministic", "route": {...}, "command_id": "..."}
    - Generative: {"type": "generative", "handoff": {...}}
    - Legacy: {"type": "legacy", "command_id": "..."}
    """
    from pipeline_driver_contracts import load_driver_routes

    if not phase or not isinstance(phase, str):
        raise ValueError("phase must be a non-empty string")

    # Determine command_id from phase: "plan" -> "speckit.plan"
    command_id = f"speckit.{phase}"

    # Load driver routes from manifest
    try:
        routes = load_driver_routes(manifest_path)
    except FileNotFoundError:
        # No manifest found, use legacy routing
        return {
            "type": "legacy",
            "command_id": command_id,
            "reason": "manifest_not_found",
        }

    # Look up the command in routes
    route = routes.get(command_id)
    if route is None:
        # Command not in manifest, use legacy routing
        return {
            "type": "legacy",
            "command_id": command_id,
            "reason": "command_not_in_manifest",
        }

    # Determine routing based on mode
    mode = route.get("mode")
    if mode == "deterministic":
        return {
            "type": "deterministic",
            "command_id": command_id,
            "route": route,
        }
    elif mode == "generative":
        # Create handoff template for generative steps
        handoff_id = (
            f"handoff_{command_id.replace('.', '_')}"
            if correlation_id is None
            else f"handoff_{correlation_id.split(':')[0]}"
        )
        return {
            "type": "generative",
            "command_id": command_id,
            "handoff": {
                "handoff_id": handoff_id,
                "step_name": command_id,
                "required_inputs": [],  # Will be populated by caller based on phase
                "output_template_path": "",  # Will be populated by caller
                "completion_marker": "",  # Will be populated by caller
                "correlation_id": correlation_id or "",
            },
        }
    else:
        # Legacy or unknown mode
        return {
            "type": "legacy",
            "command_id": command_id,
            "reason": f"unsupported_mode_{mode}",
        }


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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan mode: resolve phase state without mutating ledgers or artifacts",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    phase_state = resolve_phase_state(
        args.feature_id,
        pipeline_state={"phase": args.phase, "dry_run": args.dry_run},
    )

    correlation_id = build_correlation_id(args.feature_id, args.phase)
    step_result = parse_step_result(
        {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": correlation_id,
            "next_phase": phase_state["phase"],
        }
    )

    output = {
        "feature_id": args.feature_id,
        "phase_state": phase_state,
        "step_result": step_result,
    }

    if args.dry_run:
        output["dry_run_mode"] = True
        output["note"] = "No ledger events or artifacts were persisted (dry-run mode)"

    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
