#!/usr/bin/env python3
"""Deterministic pipeline driver entrypoint (skeleton)."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
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
    """Emit compact three-line human status output to stderr.

    Suppresses verbose output and emits only the canonical Done/Next/Blocked status contract.
    Uses render_status_lines from pipeline_driver_contracts for canonical formatting.
    Defaults to stderr so stdout remains clean for JSON consumers (--json flag).
    """
    import sys
    if file is None:
        file = sys.stderr
    exit_code = step_result.get("exit_code")

    if exit_code == 0:
        # Success path: emit done status and next phase
        done_msg = "Step completed successfully"
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
            "command_not_in_migration_scope",
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


def _collect_generated_artifact_metadata(
    artifact_path: str | Path,
    *,
    completion_marker: str | None = None,
) -> dict[str, Any]:
    artifact = Path(artifact_path)
    metadata: dict[str, Any] = {
        "path": str(artifact),
        "exists": artifact.exists(),
        "size_bytes": None,
        "line_count": None,
        "completion_marker": completion_marker,
    }
    if artifact.exists():
        try:
            content = artifact.read_text(encoding="utf-8")
            metadata["size_bytes"] = len(content.encode("utf-8"))
            metadata["line_count"] = len(content.splitlines())
        except (OSError, UnicodeDecodeError):
            metadata["size_bytes"] = None
            metadata["line_count"] = None
    return metadata


def run_generative_handoff(
    handoff: Mapping[str, Any],
    *,
    feature_id: str,
    phase: str,
    correlation_id: str,
    timeout_seconds: int = 300,
    handoff_runner: str | None = None,
    cwd: str | Path | None = None,
    sidecar_dir: str | Path = ".speckit/runtime-failures",
) -> dict[str, Any]:
    """Execute the generative handoff adapter and capture generated artifact metadata."""
    if not isinstance(handoff, Mapping):
        raise ValueError("handoff must be a mapping")
    if not correlation_id:
        raise ValueError("correlation_id is required")

    runner_spec = handoff_runner or os.environ.get("SPECKIT_HANDOFF_RUNNER", "")
    artifact_path = str(handoff.get("output_template_path") or "")
    completion_marker = handoff.get("completion_marker")
    if not isinstance(completion_marker, str):
        completion_marker = None

    # Backward-compatible mode: no runner configured, return explicit handoff with metadata probe.
    if not runner_spec.strip():
        return {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": correlation_id,
            "next_phase": phase,
            "gate": None,
            "reasons": [],
            "error_code": None,
            "debug_path": None,
            "handoff": dict(handoff),
            "handoff_execution": "not_configured",
            "generated_artifact": _collect_generated_artifact_metadata(
                artifact_path or ".",
                completion_marker=completion_marker,
            ),
        }

    command = shlex.split(runner_spec)
    if not command:
        raise ValueError("handoff_runner produced empty command")

    payload = {
        "feature_id": feature_id,
        "phase": phase,
        "correlation_id": correlation_id,
        "handoff": dict(handoff),
    }
    execution = _execute_command(
        command,
        timeout_seconds=timeout_seconds,
        cwd=cwd,
        env=os.environ,
        input_payload=json.dumps(payload, sort_keys=True),
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
            env_overrides=None,
            input_payload=json.dumps(payload, sort_keys=True),
            error_code="step_timeout",
            reason="step_timeout",
            initial_stdout=stdout,
            initial_stderr=stderr,
            initial_exit_code=exit_code,
            initial_timed_out=True,
            sidecar_dir=sidecar_dir,
        )

    if exit_code != 0:
        return handle_runtime_failure(
            command,
            correlation_id=correlation_id,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            env_overrides=None,
            input_payload=json.dumps(payload, sort_keys=True),
            error_code="invalid_exit_code",
            reason="invalid_exit_code",
            initial_stdout=stdout,
            initial_stderr=stderr,
            initial_exit_code=exit_code,
            initial_timed_out=False,
            sidecar_dir=sidecar_dir,
        )

    runner_payload: dict[str, Any] = {}
    if stdout.strip():
        try:
            parsed_payload = json.loads(stdout)
            if isinstance(parsed_payload, dict):
                runner_payload = parsed_payload
        except json.JSONDecodeError:
            return handle_runtime_failure(
                command,
                correlation_id=correlation_id,
                timeout_seconds=timeout_seconds,
                cwd=cwd,
                env_overrides=None,
                input_payload=json.dumps(payload, sort_keys=True),
                error_code="invalid_json_result",
                reason="invalid_json_result",
                initial_stdout=stdout,
                initial_stderr=stderr,
                initial_exit_code=exit_code,
                initial_timed_out=False,
                sidecar_dir=sidecar_dir,
            )

    runner_artifact = runner_payload.get("artifact_path")
    if isinstance(runner_artifact, str) and runner_artifact.strip():
        artifact_path = runner_artifact.strip()
    if not artifact_path:
        artifact_path = str(handoff.get("output_template_path") or ".")
    if "completion_marker" in runner_payload and isinstance(runner_payload["completion_marker"], str):
        completion_marker = runner_payload["completion_marker"]

    return {
        "schema_version": "1.0.0",
        "ok": True,
        "exit_code": 0,
        "correlation_id": correlation_id,
        "next_phase": phase,
        "gate": None,
        "reasons": [],
        "error_code": None,
        "debug_path": None,
        "handoff": dict(handoff),
        "handoff_execution": "executed",
        "generated_artifact": _collect_generated_artifact_metadata(
            artifact_path,
            completion_marker=completion_marker,
        ),
    }


def append_pipeline_success_event(
    *,
    feature_id: str,
    phase: str,
    command_id: str | None,
    actor: str = "pipeline_driver",
    manifest_path: str | Path | None = None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    """Append the manifest-declared success event for a completed step."""
    from pipeline_driver_contracts import load_driver_routes

    if not command_id:
        return {"ok": True, "appended": False, "event": None}

    routes = load_driver_routes(manifest_path)
    route = routes.get(command_id)
    if not isinstance(route, Mapping):
        return {"ok": True, "appended": False, "event": None}

    emit_contracts = route.get("emit_contracts")
    if isinstance(emit_contracts, list):
        selected_event: str | None = None
        for contract in emit_contracts:
            if not isinstance(contract, Mapping):
                continue
            event_name = contract.get("event")
            required_fields = contract.get("required_fields", [])
            if (
                isinstance(event_name, str)
                and event_name.strip()
                and isinstance(required_fields, list)
                and len(required_fields) == 0
            ):
                selected_event = event_name.strip()
                break
    else:
        selected_event = None

    if selected_event is None:
        emits = route.get("emits")
        if isinstance(emits, list) and emits:
            first_emit = emits[0]
            if isinstance(first_emit, str) and first_emit.strip():
                selected_event = first_emit.strip()

    if not selected_event:
        return {"ok": True, "appended": False, "event": None}

    ledger_script = Path(__file__).resolve().parent / "pipeline_ledger.py"
    command = [
        sys.executable,
        str(ledger_script),
        "append",
        "--feature-id",
        feature_id,
        "--phase",
        phase,
        "--event",
        selected_event,
        "--actor",
        actor,
        "--details",
        f"driver success append for {command_id}",
    ]
    execution = _execute_command(
        command,
        timeout_seconds=timeout_seconds,
        cwd=Path(__file__).resolve().parent.parent,
        env=os.environ,
        input_payload=None,
    )
    process_exit_code = execution.get("exit_code")
    timed_out = bool(execution.get("timed_out"))
    stdout = str(execution.get("stdout") or "")
    stderr = str(execution.get("stderr") or "")

    if timed_out:
        return {
            "ok": False,
            "appended": False,
            "event": selected_event,
            "error_code": "pipeline_event_append_timeout",
            "stdout": stdout,
            "stderr": stderr,
            "process_exit_code": process_exit_code,
            "timed_out": True,
        }
    if process_exit_code != 0:
        return {
            "ok": False,
            "appended": False,
            "event": selected_event,
            "error_code": "pipeline_event_append_failed",
            "stdout": stdout,
            "stderr": stderr,
            "process_exit_code": process_exit_code,
            "timed_out": False,
        }

    return {
        "ok": True,
        "appended": True,
        "event": selected_event,
        "stdout": stdout,
        "stderr": stderr,
        "process_exit_code": process_exit_code,
        "timed_out": False,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic pipeline steps")
    parser.add_argument("--feature-id", required=True, help="Feature id, e.g. 019")
    parser.add_argument(
        "--phase",
        default="setup",
        help="Phase to execute, e.g. 'plan', 'sketch', 'implement'",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan mode: resolve phase state without executing steps or mutating ledgers",
    )
    parser.add_argument(
        "--approval-token",
        default=None,
        help="Approval token for breakpointed steps (format: scope:secret)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit full JSON step result in addition to compact three-line status",
    )
    parser.add_argument(
        "--handoff-runner",
        default=None,
        help="Optional command used to execute generative handoff payloads (stdin JSON).",
    )
    return parser


def validate_coverage_for_migration(
    *,
    routes: dict[str, dict[str, Any]],
    feature_dir: Path | str,
    coverage_report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate command coverage in mixed migration mode.

    In mixed migration mode, some commands are driver-managed and others legacy.
    This function detects which commands are uncovered (not in driver manifest
    and lacking explicit legacy mode).

    Returns:
    {
        "ok": bool,  # True if all commands have defined mode or coverage is acceptable
        "uncovered": [...],  # Commands not in any manifest or without mode metadata
        "coverage_gaps": [...],  # Gaps between driver-managed and legacy coverage
        "migration_status": {...},  # Per-command status
    }
    """
    if isinstance(feature_dir, str):
        feature_dir = Path(feature_dir)

    uncovered = []
    coverage_gaps = []
    migration_status = {}

    # Analyze routes for coverage gaps
    for cmd_id, route_meta in routes.items():
        driver_managed = route_meta.get("driver_managed", False)
        mode = route_meta.get("mode", "legacy")

        if mode == "legacy" and not driver_managed:
            # Legacy command is acceptable (explicitly not migrated yet)
            migration_status[cmd_id] = {
                "status": "legacy_acceptable",
                "mode": mode,
            }
        elif mode in ("deterministic", "generative") and driver_managed:
            # Driver-managed command is acceptable
            migration_status[cmd_id] = {
                "status": "driver_managed",
                "mode": mode,
            }
        else:
            # Uncovered or ambiguous state
            uncovered.append(cmd_id)
            migration_status[cmd_id] = {
                "status": "uncovered",
                "mode": mode,
                "reason": "Ambiguous migration state",
            }

    return {
        "ok": len(uncovered) == 0,
        "uncovered": uncovered,
        "coverage_gaps": coverage_gaps,
        "migration_status": migration_status,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Orchestrate deterministic pipeline driver for feature phase execution."""
    args = _build_parser().parse_args(argv)

    # 1. Resolve ledger-authoritative phase state
    phase_state = resolve_phase_state(
        args.feature_id,
        pipeline_state={"phase": args.phase, "dry_run": args.dry_run},
    )
    correlation_id = build_correlation_id(args.feature_id, args.phase)

    # 2. Blocked by drift — surface immediately, no execution
    if phase_state.get("blocked") and not args.dry_run:
        drift_reasons = phase_state.get("drift_reasons") or ["phase_hint_conflicts_with_ledger"]
        step_result: dict[str, Any] = {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 1,
            "correlation_id": correlation_id,
            "gate": "phase_drift",
            "reasons": drift_reasons,
            "error_code": None,
            "next_phase": None,
            "debug_path": None,
        }
        emit_human_status(step_result)
        if args.output_json:
            print(json.dumps({"feature_id": args.feature_id, "phase_state": phase_state, "step_result": step_result}, sort_keys=True))
        return 1

    # 3. Dry-run: resolve and report state, no execution
    if args.dry_run:
        step_result = {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": correlation_id,
            "next_phase": phase_state["phase"],
            "gate": None,
            "reasons": [],
            "error_code": None,
            "debug_path": None,
        }
        emit_human_status(step_result)
        if args.output_json:
            print(json.dumps({
                "feature_id": args.feature_id,
                "phase_state": phase_state,
                "step_result": step_result,
                "dry_run_mode": True,
                "note": "No ledger events or artifacts were persisted (dry-run mode)",
            }, sort_keys=True))
        return 0

    # 4. Resolve step mapping from manifest
    mapping = resolve_step_mapping(args.phase, correlation_id=correlation_id)

    # 5. Check approval breakpoint before execution
    approval_result = enforce_approval_breakpoint(
        args.phase,
        approval_token=args.approval_token,
        correlation_id=correlation_id,
    )
    if not approval_result.get("ok"):
        step_result = approval_result
        emit_human_status(step_result)
        if args.output_json:
            print(json.dumps({"feature_id": args.feature_id, "phase_state": phase_state, "step_result": step_result}, sort_keys=True))
        return 1

    # 6. Dispatch based on mapping type
    mapping_type = mapping.get("type")

    if mapping_type == "deterministic":
        route = mapping["route"]
        script_path = route.get("script_path")
        timeout = int(route.get("timeout_seconds") or 300)
        if not script_path:
            step_result = route_legacy_step(mapping, correlation_id=correlation_id)
        else:
            step_result = run_step(
                [script_path],
                timeout_seconds=timeout,
                correlation_id=correlation_id,
            )

    elif mapping_type == "generative":
        handoff = mapping["handoff"]
        step_result = run_generative_handoff(
            handoff,
            feature_id=args.feature_id,
            phase=args.phase,
            correlation_id=correlation_id,
            handoff_runner=args.handoff_runner,
        )
        if int(step_result.get("exit_code", 1)) == 0:
            generated_artifact = step_result.get("generated_artifact")
            artifact_path: str | Path | None = None
            completion_marker: str | None = None
            if isinstance(generated_artifact, Mapping):
                artifact_candidate = generated_artifact.get("path")
                if isinstance(artifact_candidate, str) and artifact_candidate.strip():
                    artifact_path = artifact_candidate.strip()
                marker_candidate = generated_artifact.get("completion_marker")
                if isinstance(marker_candidate, str) and marker_candidate.strip():
                    completion_marker = marker_candidate.strip()

            if artifact_path is None:
                handoff_output = handoff.get("output_template_path")
                if isinstance(handoff_output, str) and handoff_output.strip():
                    artifact_path = handoff_output.strip()
            if completion_marker is None:
                handoff_marker = handoff.get("completion_marker")
                if isinstance(handoff_marker, str) and handoff_marker.strip():
                    completion_marker = handoff_marker.strip()

            validation_result = validate_generated_artifact(
                artifact_path or "",
                correlation_id=correlation_id,
                completion_marker=completion_marker,
            )
            if not validation_result.get("ok"):
                validation_result["handoff"] = handoff
                validation_result["handoff_execution"] = step_result.get("handoff_execution")
                validation_result["generated_artifact"] = generated_artifact
                step_result = validation_result
            else:
                append_result = append_pipeline_success_event(
                    feature_id=args.feature_id,
                    phase=args.phase,
                    command_id=mapping.get("command_id"),
                )
                if not append_result.get("ok"):
                    step_result = {
                        "schema_version": "1.0.0",
                        "ok": False,
                        "exit_code": 2,
                        "correlation_id": correlation_id,
                        "gate": None,
                        "reasons": ["pipeline_event_append_failed"],
                        "error_code": append_result.get("error_code", "pipeline_event_append_failed"),
                        "next_phase": None,
                        "debug_path": None,
                    }
                else:
                    phase_state = resolve_phase_state(
                        args.feature_id,
                        pipeline_state={"phase": args.phase, "dry_run": False},
                    )
                    resolved_next_phase = phase_state.get("phase")
                    if not isinstance(resolved_next_phase, str) or not resolved_next_phase:
                        resolved_next_phase = args.phase
                    step_result["next_phase"] = resolved_next_phase
                    step_result["pipeline_event"] = append_result.get("event")
                step_result["artifact_validation"] = {
                    "ok": True,
                    "artifact_path": str(artifact_path),
                }

    else:
        # legacy or unknown — route_legacy_step returns a blocked result
        step_result = route_legacy_step(mapping, correlation_id=correlation_id)

    # 7. Emit compact three-line human status
    emit_human_status(step_result)

    # 8. Optionally emit full JSON for programmatic consumers
    if args.output_json:
        print(json.dumps({
            "feature_id": args.feature_id,
            "phase_state": phase_state,
            "step_result": step_result,
        }, sort_keys=True))

    return int(step_result.get("exit_code", 1))


if __name__ == "__main__":
    raise SystemExit(main())
