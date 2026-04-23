#!/usr/bin/env python3
"""Contracts and manifest routing helpers for the deterministic pipeline driver."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import yaml

SUPPORTED_SCHEMA_VERSIONS: set[str] = {"1.0.0"}
CANONICAL_DRIVER_MODES: set[str] = {"deterministic", "generative", "legacy"}
DRIVER_MODE_ALIASES: dict[str, str] = {
    "deterministic": "deterministic",
    "script": "deterministic",
    "mapped": "deterministic",
    "generative": "generative",
    "llm": "generative",
    "template": "generative",
    "legacy": "legacy",
    "passthrough": "legacy",
    "unmanaged": "legacy",
}
STATUS_KEYS: tuple[str, str, str] = ("done", "next", "blocked")
STATUS_PREFIXES: dict[str, str] = {
    "done": "Done:",
    "next": "Next:",
    "blocked": "Blocked:",
}

# Shared route/error contract constants for deterministic routing
ROUTE_GATES: set[str] = {
    "command_not_driver_managed",
    "artifact_validation",
    "approval_required",
    "planreview_questions",
}

ERROR_CODES: set[str] = {
    "step_timeout",
    "invalid_exit_code",
    "missing_step_result",
    "invalid_json_result",
    "invalid_step_result",
    "exit_code_mismatch",
    "correlation_id_mismatch",
    "script_timeout",
}

ARTIFACT_VALIDATION_REASONS: set[str] = {
    "artifact_not_created",
    "artifact_unreadable",
    "artifact_empty_or_minimal",
    "completion_marker_not_found",
}


def _resolve_default_manifest_path() -> Path:
    """Return the canonical manifest path at repository root."""
    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / "command-manifest.yaml"


def _require_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("step result envelope must be a JSON object")
    return value


def parse_step_result(step_result: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    """Parse and validate a step-result envelope with canonical schema.

    Required top-level routing fields:
    - schema_version
    - ok
    - exit_code
    - correlation_id

    Conditional required fields (based on exit_code):
    - exit_code=0 (success): requires next_phase
    - exit_code=1 (blocked): requires gate and reasons (validated against registry)
    - exit_code=2 (error): requires error_code and debug_path
    """
    payload = _require_mapping(step_result)

    schema_version = payload.get("schema_version")
    ok = payload.get("ok")
    exit_code = payload.get("exit_code")
    correlation_id = payload.get("correlation_id")

    if not isinstance(schema_version, str) or not schema_version:
        raise ValueError("missing required field: schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported schema_version: {schema_version}")
    if not isinstance(ok, bool):
        raise ValueError("missing required boolean field: ok")
    if not isinstance(exit_code, int) or exit_code not in (0, 1, 2):
        raise ValueError("exit_code must be one of: 0, 1, 2")
    if not isinstance(correlation_id, str) or not correlation_id:
        raise ValueError("missing required field: correlation_id")

    # Validate conditional required fields based on exit_code
    gate = payload.get("gate")
    reasons = payload.get("reasons", [])
    error_code = payload.get("error_code")
    next_phase = payload.get("next_phase")
    debug_path = payload.get("debug_path")

    if exit_code == 0:
        # Success: requires next_phase
        if next_phase is None:
            raise ValueError("exit_code=0 (success) requires next_phase field")
        if ok is not True:
            raise ValueError("exit_code=0 (success) requires ok=True")
    elif exit_code == 1:
        # Blocked: requires gate and reasons
        if not isinstance(gate, str) or not gate:
            raise ValueError("exit_code=1 (blocked) requires gate field (non-empty string)")
        if not isinstance(reasons, list) or not reasons:
            raise ValueError("exit_code=1 (blocked) requires reasons field (non-empty list)")
        if ok is not False:
            raise ValueError("exit_code=1 (blocked) requires ok=False")

        # Validate reason codes against registry
        validation_errors = validate_reason_codes(
            {"exit_code": exit_code, "gate": gate, "reasons": reasons}
        )
        if validation_errors:
            raise ValueError(f"reason code validation failed: {'; '.join(validation_errors)}")

    elif exit_code == 2:
        # Error: requires error_code and debug_path
        if not isinstance(error_code, str) or not error_code:
            raise ValueError("exit_code=2 (error) requires error_code field (non-empty string)")
        if not isinstance(debug_path, str) or not debug_path:
            raise ValueError("exit_code=2 (error) requires debug_path field (non-empty string)")
        if ok is not False:
            raise ValueError("exit_code=2 (error) requires ok=False")

    return {
        "schema_version": schema_version,
        "ok": ok,
        "exit_code": exit_code,
        "correlation_id": correlation_id,
        "gate": gate,
        "reasons": reasons,
        "error_code": error_code,
        "next_phase": next_phase,
        "debug_path": debug_path,
    }


def normalize_driver_mode(raw_mode: Any) -> str:
    """Normalize manifest-provided driver mode to canonical routing labels."""
    if raw_mode is None:
        return "legacy"
    if not isinstance(raw_mode, str):
        raise ValueError(f"driver mode must be a string, got: {type(raw_mode).__name__}")

    normalized = raw_mode.strip().lower()
    if not normalized:
        return "legacy"
    if normalized not in DRIVER_MODE_ALIASES:
        allowed = ", ".join(sorted(set(DRIVER_MODE_ALIASES)))
        raise ValueError(f"unsupported driver mode '{raw_mode}'; expected one of: {allowed}")
    return DRIVER_MODE_ALIASES[normalized]


def _normalize_script_path(manifest_path: Path, raw_path: Any) -> str | None:
    if raw_path is None:
        return None
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("driver script path must be a non-empty string when provided")

    script_path = Path(raw_path.strip())
    if script_path.is_absolute():
        return str(script_path)

    manifest_dir = manifest_path.parent
    if manifest_dir.name == ".specify":
        base_dir = manifest_dir.parent
    else:
        base_dir = manifest_dir
    return str((base_dir / script_path).resolve())


def _normalize_string_list(value: Any, *, field_name: str, command_id: str) -> list[str]:
    """Normalize a manifest list of non-empty strings."""
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list: {command_id}")

    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} entries must be non-empty strings: {command_id}")
        normalized.append(item.strip())
    return normalized


def _normalize_freeform_metadata(value: Any) -> Any:
    """Recursively trim manifest metadata while preserving nested shape."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [_normalize_freeform_metadata(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _normalize_freeform_metadata(item) for key, item in value.items()}
    return deepcopy(value)


def _normalize_artifact_contract(
    artifact: Mapping[str, Any],
    *,
    command_id: str,
) -> dict[str, Any]:
    """Normalize a single artifact contract from a manifest route."""
    normalized: dict[str, Any] = {}
    for key, value in artifact.items():
        if key == "consumed_by":
            normalized[key] = _normalize_string_list(
                value,
                field_name="artifact.consumed_by",
                command_id=command_id,
            )
        elif isinstance(value, str):
            normalized[key] = value.strip()
        elif isinstance(value, list):
            normalized[key] = _normalize_freeform_metadata(value)
        elif isinstance(value, Mapping):
            normalized[key] = _normalize_freeform_metadata(value)
        else:
            normalized[key] = deepcopy(value)
    return normalized


def _normalize_emit_contract(
    emit: Mapping[str, Any],
    *,
    command_id: str,
) -> dict[str, Any]:
    """Normalize a single emit contract from a manifest route."""
    event_name = emit.get("event")
    if not isinstance(event_name, str) or not event_name.strip():
        raise ValueError(f"emit.event must be a non-empty string: {command_id}")

    required_fields = emit.get("required_fields", [])
    normalized = {
        "event": event_name.strip(),
        "required_fields": _normalize_string_list(
            required_fields,
            field_name="emit.required_fields",
            command_id=command_id,
        ),
    }
    for key, value in emit.items():
        if key in {"event", "required_fields"}:
            continue
        normalized[key] = _normalize_freeform_metadata(value)
    return normalized


def load_driver_routes(manifest_path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Load command routing metadata and normalize modes for driver routing.

    Route schema (per command):
    - mode: canonical driver mode (`deterministic`, `generative`, `legacy`)
    - script_path: normalized absolute script path if declared
    - timeout_seconds: optional positive integer
    - scripts: declared script dependencies, trimmed but not re-rooted
    - artifacts: normalized artifact declarations, including consumed_by metadata
    - emits: declared pipeline events for the command
    - emit_contracts: normalized emit declarations, preserving canonical trigger metadata
    """
    resolved_manifest_path = (
        Path(manifest_path).resolve()
        if manifest_path is not None
        else _resolve_default_manifest_path()
    )
    if not resolved_manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {resolved_manifest_path}")

    data = yaml.safe_load(resolved_manifest_path.read_text(encoding="utf-8")) or {}
    commands = data.get("commands", {})
    if not isinstance(commands, Mapping):
        raise ValueError("manifest.commands must be a mapping")

    routes: dict[str, dict[str, Any]] = {}
    for command_id, command_def in commands.items():
        if not isinstance(command_id, str) or not command_id:
            raise ValueError("manifest command id must be a non-empty string")
        if not isinstance(command_def, Mapping):
            raise ValueError(f"manifest command definition must be a mapping: {command_id}")

        driver_block = command_def.get("driver")
        if driver_block is None:
            driver_block = {}
        if not isinstance(driver_block, Mapping):
            raise ValueError(f"manifest driver block must be a mapping: {command_id}")

        driver_mode = driver_block.get("mode")
        top_level_mode = command_def.get("mode")
        if driver_mode is not None and top_level_mode is not None:
            normalized_driver_mode = normalize_driver_mode(driver_mode)
            normalized_top_level_mode = normalize_driver_mode(top_level_mode)
            if normalized_driver_mode != normalized_top_level_mode:
                raise ValueError(f"conflicting driver mode declarations: {command_id}")
            mode = normalized_driver_mode
        else:
            raw_mode = driver_mode if driver_mode is not None else top_level_mode
            mode = normalize_driver_mode(raw_mode)

        raw_script_path = driver_block.get("script_path", driver_block.get("script"))
        script_path = _normalize_script_path(resolved_manifest_path, raw_script_path)

        timeout_seconds = driver_block.get("timeout_seconds")
        if timeout_seconds is not None:
            if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
                raise ValueError(f"timeout_seconds must be a positive integer: {command_id}")

        description = command_def.get("description")
        if description is not None and not isinstance(description, str):
            raise ValueError(f"manifest description must be a string: {command_id}")
        normalized_description = description.strip() if isinstance(description, str) else None

        scripts = command_def.get("scripts")
        normalized_scripts: list[str] | None = None
        if scripts is not None:
            normalized_scripts = _normalize_string_list(
                scripts,
                field_name="manifest scripts",
                command_id=command_id,
            )

        artifacts = command_def.get("artifacts")
        normalized_artifacts: list[dict[str, Any]] | None = None
        if artifacts is not None:
            if not isinstance(artifacts, list):
                raise ValueError(f"manifest artifacts must be a list: {command_id}")
            normalized_artifacts = []
            for artifact in artifacts:
                if not isinstance(artifact, Mapping):
                    raise ValueError(f"artifact entry must be a mapping: {command_id}")
                normalized_artifacts.append(
                    _normalize_artifact_contract(artifact, command_id=command_id)
                )

        emits = command_def.get("emits", [])
        if not isinstance(emits, list):
            raise ValueError(f"manifest emits must be a list: {command_id}")
        emit_events = []
        emit_contracts = []
        for emit in emits:
            if not isinstance(emit, Mapping):
                raise ValueError(f"emit entry must be a mapping: {command_id}")
            normalized_contract = _normalize_emit_contract(emit, command_id=command_id)
            emit_events.append(normalized_contract["event"])
            emit_contracts.append(normalized_contract)

        canonical_trigger = (
            driver_block.get("canonical_trigger")
            if driver_block.get("canonical_trigger") is not None
            else command_def.get("canonical_trigger")
        )
        if canonical_trigger is None:
            canonical_trigger = driver_block.get("trigger")
        if canonical_trigger is None:
            canonical_trigger = command_def.get("trigger")

        route: dict[str, Any] = {
            "mode": mode,
            "script_path": script_path,
            "timeout_seconds": timeout_seconds,
            "driver_managed": mode != "legacy",
            "emits": emit_events,
            "emit_contracts": emit_contracts,
        }
        if normalized_description is not None:
            route["description"] = normalized_description
        if normalized_scripts is not None:
            route["scripts"] = normalized_scripts
        if normalized_artifacts is not None:
            route["artifacts"] = normalized_artifacts
        if canonical_trigger is not None:
            route["canonical_trigger"] = _normalize_freeform_metadata(canonical_trigger)

        routes[command_id] = route

    return routes


def _normalize_status_value(raw_value: Any) -> str:
    if not isinstance(raw_value, str):
        return "none"
    normalized = raw_value.strip()
    return normalized if normalized else "none"


def render_status_lines(
    *,
    done: str | None,
    next_step: str | None,
    blocked: str | None = None,
) -> list[str]:
    """Render the strict three-line human status contract in canonical order."""
    status_values = {
        "done": _normalize_status_value(done),
        "next": _normalize_status_value(next_step),
        "blocked": _normalize_status_value(blocked),
    }
    return [f"{STATUS_PREFIXES[key]} {status_values[key]}" for key in STATUS_KEYS]


def load_reason_code_registry(
    registry_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load the deterministic reason-code registry.

    Returns mapping of {gate_name -> {reasons: [...]}, ...}
    """
    resolved_path = (
        Path(registry_path).resolve()
        if registry_path is not None
        else (Path(__file__).resolve().parent.parent / "docs" / "governance" / "gate-reason-codes.yaml")
    )

    if not resolved_path.exists():
        raise FileNotFoundError(f"reason code registry not found: {resolved_path}")

    data = yaml.safe_load(resolved_path.read_text(encoding="utf-8")) or {}
    gates = data.get("gates", {})
    if not isinstance(gates, Mapping):
        raise ValueError("registry.gates must be a mapping")

    registry: dict[str, Any] = {}
    for gate_name, gate_entry in gates.items():
        if not isinstance(gate_entry, Mapping):
            raise ValueError(f"registry gate entry must be a mapping: {gate_name}")
        reasons = gate_entry.get("reasons", [])
        if not isinstance(reasons, list):
            raise ValueError(f"registry gate reasons must be a list: {gate_name}")
        registry[gate_name] = {
            "description": gate_entry.get("description", ""),
            "reasons": reasons,
        }

    return registry


def validate_reason_codes(
    step_result: dict[str, Any],
    *,
    registry_path: str | Path | None = None,
) -> list[str]:
    """Validate that reason codes in step_result match the registry.

    Returns list of validation errors (empty if valid).
    """
    try:
        registry = load_reason_code_registry(registry_path)
    except (FileNotFoundError, ValueError) as e:
        # Registry loading failed - cannot validate
        return [f"reason code registry load failed: {e}"]

    errors: list[str] = []

    exit_code = step_result.get("exit_code")
    if exit_code == 1:
        # Blocked state: validate gate and reasons
        gate = step_result.get("gate")
        reasons = step_result.get("reasons", [])

        if gate not in registry:
            errors.append(f"unknown gate: {gate}")
        else:
            valid_reasons = set(registry[gate].get("reasons", []))
            for reason in reasons:
                if reason not in valid_reasons:
                    errors.append(f"invalid reason for gate '{gate}': {reason}")

    return errors


def validate_manifest_governance(
    *,
    manifest_path: str | Path,
    canonical_path: str | Path | None = None,
) -> list[str]:
    """Validate manifest version/timestamp coupling for governance invariants.

    In mixed migration mode, manifest divergence can occur silently if only one
    manifest is updated without the other. This validator detects:
    1. Stale timestamps with changed content
    2. Version mismatches between canonical and mirror
    3. Undocumented changes (timestamp not updated)

    Returns list of validation errors (empty if manifest is compliant).
    """
    resolved_manifest = Path(manifest_path).resolve()
    errors: list[str] = []

    if not resolved_manifest.exists():
        return [f"manifest not found: {resolved_manifest}"]

    try:
        manifest_data = yaml.safe_load(resolved_manifest.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return [f"failed to load manifest: {e}"]

    version = manifest_data.get("version")
    last_updated = manifest_data.get("last_updated")

    # Check required metadata fields
    if not version:
        errors.append("missing required field: version")
    if not last_updated:
        errors.append("missing required field: last_updated")

    # If canonical path provided, compare for divergence
    if canonical_path is not None:
        resolved_canonical = Path(canonical_path).resolve()
        if resolved_canonical.exists():
            try:
                canonical_data = yaml.safe_load(
                    resolved_canonical.read_text(encoding="utf-8")
                ) or {}
            except Exception as e:
                errors.append(f"failed to load canonical manifest: {e}")
                return errors

            # Compare commands block (content)
            manifest_commands = manifest_data.get("commands", {})
            canonical_commands = canonical_data.get("commands", {})

            if manifest_commands != canonical_commands:
                # Content diverged
                manifest_ts = manifest_data.get("last_updated")
                canonical_ts = canonical_data.get("last_updated")

                if manifest_ts == canonical_ts:
                    # Timestamp is stale — this is a governance violation
                    errors.append(
                        "manifest content diverged from canonical but timestamp not updated "
                        f"(both at {manifest_ts})"
                    )
                elif manifest_ts and canonical_ts and manifest_ts > canonical_ts:
                    # Timestamp is newer but shouldn't be if mirror only
                    errors.append(
                        f"mirror timestamp {manifest_ts} is newer than canonical {canonical_ts} "
                        "(mirrors should not lead updates)"
                    )

    return errors
