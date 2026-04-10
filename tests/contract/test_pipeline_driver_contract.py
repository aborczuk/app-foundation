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
        }
    )
    assert parsed["schema_version"] == "1.0.0"
    assert parsed["exit_code"] == 0


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
