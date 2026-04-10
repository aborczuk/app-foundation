"""Unit-level skeleton tests for scripts/pipeline_driver.py."""

from __future__ import annotations

import importlib.util
import json
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


pipeline_driver = _load_script_module("pipeline_driver", "pipeline_driver.py")


def test_main_outputs_minimal_step_result(capsys) -> None:
    exit_code = pipeline_driver.main(["--feature-id", "019", "--phase", "setup"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["feature_id"] == "019"
    assert payload["step_result"]["exit_code"] == 0
