"""Unit tests for scripts/speckit_implement_gate.py."""

from __future__ import annotations

import argparse
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


speckit_implement_gate = _load_script_module(
    "speckit_implement_gate", "speckit_implement_gate.py"
)


def _preflight_args(
    feature_dir: Path, tasks_file: Path, hud_path: Path | None
) -> argparse.Namespace:
    return argparse.Namespace(
        feature_dir=str(feature_dir),
        task_id="T048",
        tasks_file=str(tasks_file),
        hud_path=str(hud_path) if hud_path else None,
        json=True,
    )


def test_task_preflight_returns_feature_branch_stale_when_task_exists_on_main(
    tmp_path: Path, monkeypatch
) -> None:
    feature_dir = tmp_path / "specs" / "019-token-efficiency-docs"
    feature_dir.mkdir(parents=True)
    tasks_file = feature_dir / "tasks.md"
    tasks_file.write_text("- [X] T047 previous task\n", encoding="utf-8")
    hud_path = feature_dir / "huds" / "T048.md"
    hud_path.parent.mkdir(parents=True)
    hud_path.write_text("# HUD T048\n", encoding="utf-8")

    monkeypatch.setattr(speckit_implement_gate, "_task_exists_on_main", lambda *_: True)

    exit_code, payload = speckit_implement_gate._task_preflight(
        _preflight_args(feature_dir, tasks_file, hud_path)
    )
    assert exit_code == 2
    assert payload["ok"] is False
    assert payload["reasons"] == ["feature_branch_stale"]
    assert payload["task_present_in_tasks_file"] is False
    assert payload["task_present_in_main"] is True


def test_task_preflight_returns_task_not_found_when_task_missing_everywhere(
    tmp_path: Path, monkeypatch
) -> None:
    feature_dir = tmp_path / "specs" / "019-token-efficiency-docs"
    feature_dir.mkdir(parents=True)
    tasks_file = feature_dir / "tasks.md"
    tasks_file.write_text("- [X] T047 previous task\n", encoding="utf-8")
    hud_path = feature_dir / "huds" / "T048.md"
    hud_path.parent.mkdir(parents=True)
    hud_path.write_text("# HUD T048\n", encoding="utf-8")

    monkeypatch.setattr(speckit_implement_gate, "_task_exists_on_main", lambda *_: False)

    exit_code, payload = speckit_implement_gate._task_preflight(
        _preflight_args(feature_dir, tasks_file, hud_path)
    )
    assert exit_code == 2
    assert payload["ok"] is False
    assert payload["reasons"] == ["task_not_found_in_tasks_md"]
    assert payload["task_present_in_tasks_file"] is False
    assert payload["task_present_in_main"] is False


def test_task_preflight_passes_when_task_exists_locally(tmp_path: Path) -> None:
    feature_dir = tmp_path / "specs" / "019-token-efficiency-docs"
    feature_dir.mkdir(parents=True)
    tasks_file = feature_dir / "tasks.md"
    tasks_file.write_text("- [ ] T048 new task\n", encoding="utf-8")
    hud_path = feature_dir / "huds" / "T048.md"
    hud_path.parent.mkdir(parents=True)
    hud_path.write_text("# HUD T048\n", encoding="utf-8")

    exit_code, payload = speckit_implement_gate._task_preflight(
        _preflight_args(feature_dir, tasks_file, hud_path)
    )
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["reasons"] == []
    assert payload["task_present_in_tasks_file"] is True
    assert payload["task_present_in_main"] is None


def test_task_preflight_defaults_hud_to_feature_local_path(tmp_path: Path) -> None:
    feature_dir = tmp_path / "specs" / "019-token-efficiency-docs"
    feature_dir.mkdir(parents=True)
    tasks_file = feature_dir / "tasks.md"
    tasks_file.write_text("- [ ] T048 new task\n", encoding="utf-8")
    default_hud_path = feature_dir / "huds" / "T048.md"
    default_hud_path.parent.mkdir(parents=True)
    default_hud_path.write_text("# HUD T048\n", encoding="utf-8")

    exit_code, payload = speckit_implement_gate._task_preflight(
        _preflight_args(feature_dir, tasks_file, None)
    )
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["hud_path"] == str(default_hud_path.resolve())
