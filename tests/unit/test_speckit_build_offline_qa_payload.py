"""Unit tests for scripts/speckit_build_offline_qa_payload.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


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


speckit_build_offline_qa_payload = _load_script_module(
    "speckit_build_offline_qa_payload", "speckit_build_offline_qa_payload.py"
)


def test_default_hud_path_is_feature_local() -> None:
    feature_dir = Path("/tmp/specs/023-deterministic-phase-orchestration")
    expected = feature_dir / "huds" / "T004.md"
    actual = speckit_build_offline_qa_payload._default_hud_path(feature_dir, "T004")
    assert actual == expected
