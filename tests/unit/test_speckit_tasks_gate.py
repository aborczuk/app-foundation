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


def test_validate_format_allows_ordered_breakdown_task_ids(tmp_path: Path) -> None:
    """The mandated a/b breakdown suffixes are valid task identifiers."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(
        "\n".join(
            [
                "## Phase 1: Setup",
                "- [ ] T001 [US1] First task in src/app.py",
                "- [ ] T002a [US1] Follow-on task in src/app.py",
                "- [ ] T002b [US1] Finish split work in src/app.py",
                "- [ ] T003 [US1] Next task in src/app.py",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code, payload = speckit_tasks_gate._validate(tasks_file)

    assert exit_code == 0
    assert payload["ok"] is True


def test_validate_format_rejects_incomplete_breakdown_task_ids(tmp_path: Path) -> None:
    """A split must contain the required ordered a/b or a/b/c suffixes."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(
        "\n".join(
            [
                "## Phase 1: Setup",
                "- [ ] T001a [US1] Incomplete split in src/app.py",
                "- [ ] T002 [US1] Next task in src/app.py",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code, payload = speckit_tasks_gate._validate(tasks_file)

    assert exit_code == 2
    assert payload["ok"] is False
    assert any(error["code"] == "non_sequential_task_ids" for error in payload["errors"])


def test_validate_format_accepts_repository_root_file_paths(tmp_path: Path) -> None:
    """Root-level manifest paths satisfy the concrete-seam requirement."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(
        "## Phase 1: Setup\n- [ ] T001 [US1] Update command-manifest.yaml route ownership.\n",
        encoding="utf-8",
    )

    exit_code, payload = speckit_tasks_gate._validate(tasks_file)

    assert exit_code == 0
    assert payload["ok"] is True
