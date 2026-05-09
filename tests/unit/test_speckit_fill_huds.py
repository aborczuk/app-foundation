"""Tests for scaffold-preserving HUD fill helper."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    """Import the HUD fill helper as a module."""
    module_path = Path("scripts/speckit_fill_huds.py")
    spec = importlib.util.spec_from_file_location("testable_speckit_fill_huds", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_hud(path: Path) -> None:
    """Create a minimal scaffold-like HUD file for update tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """---
feature_id: "029"
task_id: "T001"
task_summary: "Old summary"
primary_edit_seam: null
related_paths: ["src/demo.py"]
---

# HUD: T001 - Old summary

## Objective

Old objective.

## Relevant Domains

- [FILL: domains]

## Proposed Solution

- [FILL: solution]

## Touched Symbols

### Modify

- `src/demo.py` - [FILL: modify]

### Create

- None.

## Dependencies

- None.
""",
        encoding="utf-8",
    )


def test_apply_updates_frontmatter_title_and_sections(tmp_path: Path, monkeypatch) -> None:
    """The helper should preserve scaffold headings while updating content in place."""
    module = _load_module()
    feature_dir = tmp_path / "029-demo"
    hud_path = feature_dir / "huds" / "T001.md"
    _write_hud(hud_path)
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps(
            {
                "frontmatter": {
                    "task_summary": "New summary",
                    "primary_edit_seam": "src/demo.py:build_demo",
                },
                "title": "# HUD: T001 - New summary",
                "sections": {
                    "Relevant Domains": "- `IV. Test Driven Verification First`: keep the seam testable.",
                    "Proposed Solution": "- Implement `src/demo.py:build_demo` and keep the scaffold structure intact.",
                    "Touched Symbols": "### Modify\n\n- `src/demo.py` - implement `build_demo`.\n\n### Create\n\n- None.",
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = module.main(
        [
            "--feature-dir",
            str(feature_dir),
            "--payload-file",
            str(payload_path),
            "--task-id",
            "T001",
        ]
    )

    assert exit_code == 0
    content = hud_path.read_text(encoding="utf-8")
    assert 'task_summary: "New summary"' in content
    assert 'primary_edit_seam: "src/demo.py:build_demo"' in content
    assert "# HUD: T001 - New summary" in content
    assert "- `IV. Test Driven Verification First`: keep the seam testable." in content
    assert "## Dependencies" in content
    assert "[FILL:" not in content


def test_apply_updates_supports_bulk_payloads(tmp_path: Path, monkeypatch) -> None:
    """The helper should update multiple HUDs from a bulk task payload."""
    module = _load_module()
    feature_dir = tmp_path / "029-demo"
    _write_hud(feature_dir / "huds" / "T001.md")
    _write_hud(feature_dir / "huds" / "T002.md")
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps(
            {
                "tasks": {
                    "T001": {"sections": {"Relevant Domains": "- T001 body"}},
                    "T002": {"sections": {"Relevant Domains": "- T002 body"}},
                }
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = module.main(
        [
            "--feature-dir",
            str(feature_dir),
            "--payload-file",
            str(payload_path),
        ]
    )

    assert exit_code == 0
    assert "- T001 body" in (feature_dir / "huds" / "T001.md").read_text(encoding="utf-8")
    assert "- T002 body" in (feature_dir / "huds" / "T002.md").read_text(encoding="utf-8")
