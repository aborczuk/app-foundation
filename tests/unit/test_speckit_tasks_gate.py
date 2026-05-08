"""Unit tests for scripts/speckit_tasks_gate.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module(module_name: str, script_name: str):
    """Load a script module from the repo's scripts directory."""
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


speckit_tasks_gate = _load_script_module("speckit_tasks_gate", "speckit_tasks_gate.py")


def test_validate_format_rejects_noncanonical_task_like_ids(tmp_path: Path) -> None:
    """Task-like checklist lines must use canonical TNNN identifiers."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(
        "\n".join(
            [
                "## Phase 1: Setup",
                "- [ ] T001 First task in src/app.py",
                "- [ ] T001a Follow-on task in src/app.py",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code, payload = speckit_tasks_gate._validate(tasks_file)

    assert exit_code == 2
    assert payload["ok"] is False
    assert any(error["code"] == "invalid_task_line" for error in payload["errors"])
