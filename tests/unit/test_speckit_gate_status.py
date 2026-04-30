"""Unit tests for scripts/speckit_gate_status.py."""

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


speckit_gate_status = _load_script_module("speckit_gate_status", "speckit_gate_status.py")


def test_implement_report_requires_task_hud(tmp_path: Path) -> None:
    """Implement gates should only require at least one task HUD."""
    repo_root = tmp_path
    feature_dir = repo_root / "specs" / "019-token-efficiency-docs"
    feature_dir.mkdir(parents=True)
    hud_path = feature_dir / "huds" / "T048.md"
    hud_path.parent.mkdir(parents=True)
    hud_path.write_text("# HUD T048\n", encoding="utf-8")

    report, exit_code = speckit_gate_status._implement_report(feature_dir, repo_root)

    assert exit_code == 0
    assert report["ok"] is True
    assert report["hard_block_reasons"] == []
    assert report["task_huds"]["directory_exists"] is True
    assert report["task_huds"]["count"] == 1
    assert report["task_huds"]["entries"] == [str(hud_path)]


def test_implement_report_blocks_without_task_hud(tmp_path: Path) -> None:
    """Implement gates should block when no task HUD exists."""
    repo_root = tmp_path
    feature_dir = repo_root / "specs" / "019-token-efficiency-docs"
    feature_dir.mkdir(parents=True)

    report, exit_code = speckit_gate_status._implement_report(feature_dir, repo_root)

    assert exit_code == 2
    assert report["ok"] is False
    assert report["hard_block_reasons"] == ["missing_task_hud"]
    assert report["task_huds"]["directory_exists"] is False
    assert report["task_huds"]["count"] == 0
    assert report["task_huds"]["entries"] == []
