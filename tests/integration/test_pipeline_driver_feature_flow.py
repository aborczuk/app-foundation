"""Integration-level skeleton tests for deterministic pipeline driver flow."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


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


pipeline_driver_state = _load_script_module("pipeline_driver_state", "pipeline_driver_state.py")


def test_resolve_phase_state_skeleton() -> None:
    state = pipeline_driver_state.resolve_phase_state(
        "999",
        pipeline_state={"phase": "setup", "blocked": False, "drift_detected": False},
    )
    assert state["feature_id"] == "999"
    assert state["phase"] == "setup"
    assert state["blocked"] is False
