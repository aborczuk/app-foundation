"""Contract-level skeleton tests for step-result envelope parsing."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


def _load_script_module(module_name: str, script_name: str):
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


contracts = _load_script_module("pipeline_driver_contracts", "pipeline_driver_contracts.py")


def test_parse_step_result_accepts_minimal_envelope() -> None:
    parsed = contracts.parse_step_result(
        {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": "019:setup:test",
            "next_phase": "plan",
        }
    )
    assert parsed["schema_version"] == "1.0.0"
    assert parsed["exit_code"] == 0
    assert parsed["next_phase"] == "plan"


def test_parse_step_result_rejects_missing_schema_version() -> None:
    with pytest.raises(ValueError):
        contracts.parse_step_result(
            {
                "ok": True,
                "exit_code": 0,
                "correlation_id": "019:setup:test",
            }
        )


def test_render_status_lines_strict_three_line_contract() -> None:
    lines = contracts.render_status_lines(
        done="plan gate passed",
        next_step="run speckit.solution",
        blocked="none",
    )
    assert lines == [
        "Done: plan gate passed",
        "Next: run speckit.solution",
        "Blocked: none",
    ]
    assert tuple(contracts.STATUS_KEYS) == ("done", "next", "blocked")


def test_render_status_lines_normalizes_empty_values() -> None:
    lines = contracts.render_status_lines(done="", next_step=None, blocked="   ")
    assert lines == [
        "Done: none",
        "Next: none",
        "Blocked: none",
    ]


def test_step_result_schema_success_requires_next_phase() -> None:
    """Exit code 0 (success) requires next_phase field."""
    parsed = contracts.parse_step_result(
        {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": "019:plan:T001",
            "next_phase": "sketch",
        }
    )
    assert parsed["exit_code"] == 0
    assert parsed["ok"] is True
    assert parsed["next_phase"] == "sketch"


def test_step_result_schema_blocked_requires_gate_and_reasons() -> None:
    """Exit code 1 (blocked) requires gate and reasons fields."""
    parsed = contracts.parse_step_result(
        {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 1,
            "correlation_id": "019:plan:T001",
            "gate": "artifact_validation",
            "reasons": ["artifact_empty_or_minimal"],
        }
    )
    assert parsed["exit_code"] == 1
    assert parsed["ok"] is False
    assert parsed["gate"] == "artifact_validation"
    assert parsed["reasons"] == ["artifact_empty_or_minimal"]


def test_step_result_schema_error_requires_error_code_and_debug_path() -> None:
    """Exit code 2 (error) requires error_code and debug_path fields."""
    parsed = contracts.parse_step_result(
        {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 2,
            "correlation_id": "019:sketch:T005",
            "error_code": "script_timeout",
            "debug_path": ".speckit/failures/019_T005_attempt_1.json",
        }
    )
    assert parsed["exit_code"] == 2
    assert parsed["ok"] is False
    assert parsed["error_code"] == "script_timeout"
    assert parsed["debug_path"] == ".speckit/failures/019_T005_attempt_1.json"


def test_step_result_schema_version_routing() -> None:
    """Schema version must match a supported version."""
    with pytest.raises(ValueError) as exc_info:
        contracts.parse_step_result(
            {
                "schema_version": "2.0.0",
                "ok": True,
                "exit_code": 0,
                "correlation_id": "019:plan:T001",
            }
        )
    assert "unsupported schema_version" in str(exc_info.value)


def test_step_result_exit_code_only_accepts_0_1_2() -> None:
    """Exit code must be exactly 0, 1, or 2."""
    for invalid_code in [-1, 3, 127, "0", None]:
        with pytest.raises(ValueError) as exc_info:
            contracts.parse_step_result(
                {
                    "schema_version": "1.0.0",
                    "ok": True,
                    "exit_code": invalid_code,
                    "correlation_id": "019:plan:T001",
                }
            )
        assert "exit_code must be one of: 0, 1, 2" in str(exc_info.value)
