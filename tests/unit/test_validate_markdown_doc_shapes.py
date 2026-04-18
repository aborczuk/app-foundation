"""Unit tests for markdown doc shape validation."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script_module(module_name: str, script_name: str):
    """Load a script module directly from the scripts directory."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load_script_module(
    "validate_markdown_doc_shapes", "validate_markdown_doc_shapes.py"
)


def test_validate_markdown_doc_shape_accepts_compact_expanded(tmp_path: Path) -> None:
    """The new compact/expanded command-doc shape should validate cleanly."""
    doc = tmp_path / "doc.md"
    doc.write_text(
        "\n".join(
            [
                "# Title",
                "## User Input",
                "## Compact Contract (Load First)",
                "## Expanded Guidance (Load On Demand)",
                "## Behavior rules",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = validator.validate_markdown_doc_shape(markdown_file=doc)

    assert payload["ok"] is True
    assert payload["matched_shape"] == "compact_expanded"
    assert payload["headings"] == [
        "User Input",
        "Compact Contract (Load First)",
        "Expanded Guidance (Load On Demand)",
        "Behavior rules",
    ]


def test_validate_markdown_doc_shape_reports_legacy_mismatch(tmp_path: Path) -> None:
    """A legacy command doc should fail the compact/expanded shape check."""
    doc = tmp_path / "doc.md"
    doc.write_text(
        "\n".join(
            [
                "# Title",
                "## User Input",
                "## Purpose",
                "## Outline",
                "## Behavior rules",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = validator.validate_markdown_doc_shape(markdown_file=doc, shape="compact_expanded")

    assert payload["ok"] is False
    assert payload["reasons"] == ["shape_mismatch"]
    assert payload["matched_shape"] is None
