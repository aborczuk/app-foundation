"""Unit tests for scripts/speckit_behavioral_qa.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module(module_name: str, script_name: str):
    """Load a repo script as an importable module for unit testing."""
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


speckit_behavioral_qa = _load_script_module(
    "speckit_behavioral_qa", "speckit_behavioral_qa.py"
)


def test_read_tasks_acceptance_uses_independent_test_from_task_phase(tmp_path: Path) -> None:
    """Behavioral QA should read task acceptance from the task phase in tasks.md."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(
        "\n".join(
            [
                "## Story 1",
                "",
                "**Independent Test**: The app factory exposes one dedicated Tetris mount seam and preserves existing endpoints.",
                "",
                "- [ ] T001 Add Tetris mount seam",
                "",
                "## Story 2",
                "",
                "**Independent Test**: Another story acceptance.",
                "",
                "- [ ] T002 Different task",
            ]
        ),
        encoding="utf-8",
    )

    acceptance = speckit_behavioral_qa._read_tasks_acceptance(tasks_file, "T001")

    assert acceptance == (
        "The app factory exposes one dedicated Tetris mount seam and preserves existing endpoints."
    )


def test_read_tasks_acceptance_prefers_acceptance_criteria_section(tmp_path: Path) -> None:
    """Behavioral QA should prefer explicit acceptance criteria over phase test text."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(
        "\n".join(
            [
                "## Story 1",
                "",
                "**Independent Test**: Older fallback text.",
                "",
                "### Acceptance Criteria",
                "",
                "- The adapter scaffold exists.",
                "- The trigger scaffold exists.",
                "",
                "- [ ] T001 Add scaffold seams",
            ]
        ),
        encoding="utf-8",
    )

    acceptance = speckit_behavioral_qa._read_tasks_acceptance(tasks_file, "T001")

    assert acceptance == "The adapter scaffold exists. The trigger scaffold exists."


def test_read_tasks_acceptance_falls_back_to_task_description(tmp_path: Path) -> None:
    """Behavioral QA should synthesize a minimal acceptance string when phase criteria are absent."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(
        "\n".join(
            [
                "## Phase 1",
                "",
                "- [ ] T001 Create the Composio transport scaffold",
            ]
        ),
        encoding="utf-8",
    )

    acceptance = speckit_behavioral_qa._read_tasks_acceptance(tasks_file, "T001")

    assert acceptance == "Complete T001 Create the Composio transport scaffold"


def test_payload_test_runs_accepts_explicit_evidence() -> None:
    """Behavioral QA should accept valid payload-provided test evidence."""
    payload = {
        "test_runs": [
            {
                "command": "uv run --no-sync python scripts/pytest_guard.py run -- tests/unit/test_tetris_engine.py",
                "exit_code": 0,
                "output": "1 passed",
            }
        ]
    }

    normalized = speckit_behavioral_qa._payload_test_runs(payload)

    assert normalized == payload["test_runs"]


def test_check_acceptance_in_diff_accepts_markdown_artifact_tasks(tmp_path: Path) -> None:
    """Behavioral QA should scan markdown artifacts for artifact-only acceptance checks."""
    artifact = tmp_path / "artifact.md"
    artifact.write_text(
        "This completed generator-valid artifact preserves explicit constraints, "
        "current docstrings, and implement-ready acceptance criteria.\n",
        encoding="utf-8",
    )

    ok, findings = speckit_behavioral_qa._check_acceptance_in_diff(
        tmp_path,
        ["artifact.md"],
        (
            "The solution artifacts preserve explicit constraints and implement-ready "
            "acceptance criteria while current docstrings stay generator-valid."
        ),
    )

    assert ok is True
    assert findings == []
