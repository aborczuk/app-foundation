"""Unit tests for deterministic tasking estimate/breakdown chain."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module(module_name: str, script_name: str):
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tasking_chain = _load_script_module("speckit_tasking_chain", "speckit_tasking_chain.py")


def test_chain_passes_when_estimates_already_stable(tmp_path: Path) -> None:
    """Existing estimates with no 8/13 tasks should pass without commands."""
    feature_dir = tmp_path / "feature"
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "tasks.md").write_text("- [ ] T001 sample task ./file.py\n", encoding="utf-8")
    (feature_dir / "estimates.md").write_text("T001 | 3\n", encoding="utf-8")
    args = tasking_chain._build_parser().parse_args(
        ["--feature-dir", str(feature_dir), "--json"]
    )

    payload = tasking_chain.run_chain(args)

    assert payload["ok"] is True
    assert payload["high_point_tasks"] == []
    assert payload["command_results"] == []


def test_chain_requires_breakdown_command_when_high_points_remain(tmp_path: Path) -> None:
    """High-point tasks require configured breakdown command for stabilization."""
    feature_dir = tmp_path / "feature"
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "tasks.md").write_text("- [ ] T001 sample task ./file.py\n", encoding="utf-8")
    (feature_dir / "estimates.md").write_text("T001 | 8\n", encoding="utf-8")
    args = tasking_chain._build_parser().parse_args(
        ["--feature-dir", str(feature_dir), "--json"]
    )

    payload = tasking_chain.run_chain(args)

    assert payload["ok"] is False
    assert "breakdown_required" in payload["reasons"]
    assert "missing_breakdown_command" in payload["reasons"]


def test_chain_fails_without_estimate_command_and_artifact(tmp_path: Path) -> None:
    """Missing estimates artifact and missing estimate command should fail."""
    feature_dir = tmp_path / "feature"
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "tasks.md").write_text("- [ ] T001 sample task ./file.py\n", encoding="utf-8")
    args = tasking_chain._build_parser().parse_args(
        ["--feature-dir", str(feature_dir), "--json"]
    )

    payload = tasking_chain.run_chain(args)

    assert payload["ok"] is False
    assert "missing_estimate_command" in payload["reasons"]
    assert "missing_estimates_file" in payload["reasons"]
