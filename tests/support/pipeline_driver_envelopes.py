"""Shared step-result envelope helpers for pipeline-driver tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def build_step_result_envelope(
    *,
    ok: bool,
    exit_code: int,
    correlation_id: str,
    next_phase: str | None = None,
    gate: str | None = None,
    reasons: Sequence[str] | None = None,
    error_code: str | None = None,
    debug_path: str | None = None,
    schema_version: str = "1.0.0",
) -> dict[str, object]:
    """Build a canonical runner-adapter step-result payload for tests."""
    payload: dict[str, object] = {
        "schema_version": schema_version,
        "ok": ok,
        "exit_code": exit_code,
        "correlation_id": correlation_id,
    }
    if next_phase is not None:
        payload["next_phase"] = next_phase
    if gate is not None:
        payload["gate"] = gate
    if reasons is not None:
        payload["reasons"] = list(reasons)
    if error_code is not None:
        payload["error_code"] = error_code
    if debug_path is not None:
        payload["debug_path"] = debug_path
    return payload


def assert_step_result_envelope(
    result: Mapping[str, object],
    *,
    ok: bool,
    exit_code: int,
    next_phase: str | None,
    gate: str | None = None,
    reasons: Sequence[str] | None = None,
    error_code: str | None = None,
    debug_path: str | None = None,
) -> None:
    """Assert the canonical runner-adapter step-result contract."""
    assert result["schema_version"] == "1.0.0"
    assert result["ok"] is ok
    assert result["exit_code"] == exit_code
    assert result["next_phase"] == next_phase
    assert result["gate"] == gate
    assert result["reasons"] == list(reasons or [])
    assert result["error_code"] == error_code
    assert result["debug_path"] == debug_path
