#!/usr/bin/env python3
"""Contracts for deterministic pipeline-driver step envelopes.

This module intentionally starts minimal. Later tasks expand validation,
reason-code enforcement, and schema compatibility.
"""

from __future__ import annotations

from typing import Any, Mapping

SUPPORTED_SCHEMA_VERSIONS: set[str] = {"1.0.0"}


def _require_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("step result envelope must be a JSON object")
    return value


def parse_step_result(step_result: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    """Parse and minimally validate a step-result envelope.

    Required top-level routing fields:
    - schema_version
    - ok
    - exit_code
    - correlation_id
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

    return {
        "schema_version": schema_version,
        "ok": ok,
        "exit_code": exit_code,
        "correlation_id": correlation_id,
        "gate": payload.get("gate"),
        "reasons": payload.get("reasons", []),
        "error_code": payload.get("error_code"),
        "next_phase": payload.get("next_phase"),
        "debug_path": payload.get("debug_path"),
    }

