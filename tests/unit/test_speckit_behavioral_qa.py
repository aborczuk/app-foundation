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


def test_read_hud_supports_current_hud_shape(tmp_path: Path) -> None:
    """The parser should read acceptance criteria and file symbol from current HUDs."""
    hud_path = tmp_path / "T001.md"
    hud_path.write_text(
        "\n".join(
            [
                "# HUD: T001",
                "",
                "## Relevant Domains",
                "",
                "- Runtime Surface: keep one mount seam.",
                "",
                "## Primary Edit Seam",
                "",
                "**File:Symbol**: `src/clickup_control_plane/app.py:create_app`",
                "",
                "## Acceptance Criteria",
                "",
                "- The app factory exposes one dedicated Tetris mount seam.",
                "- Existing control-plane endpoints keep their behavior.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    parsed = speckit_behavioral_qa._read_hud(hud_path)

    assert parsed["file_symbol"] == "src/clickup_control_plane/app.py:create_app"
    assert parsed["acceptance_criteria"] == (
        "The app factory exposes one dedicated Tetris mount seam.\n"
        "Existing control-plane endpoints keep their behavior."
    )
    assert parsed["quality_guards"] == ["Runtime Surface: keep one mount seam."]


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
