"""Unit tests for scripts/speckit_tasking_chain.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module(module_name: str, script_name: str):
    """Load a script module from the repo's scripts directory."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, scripts_dir / script_name)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


speckit_tasking_chain = _load_script_module("speckit_tasking_chain", "speckit_tasking_chain.py")


def test_extract_high_point_tasks_ignores_historical_change_notes() -> None:
    """Only current estimate rows can require a new breakdown round."""
    estimates = "\n".join(
        [
            "| Task ID | Points | Description | Rationale |",
            "| T001 | 5 | Current work | Sized after split. |",
            "| T002a | 8 | Current high work | Requires split. |",
            "- Replaced T009 (8) with T009a (3), T009b (3), and T009c (3).",
            "- No current task scores 8 or 13 points.",
        ]
    )

    assert speckit_tasking_chain._extract_high_point_tasks(estimates) == ["T002a"]
