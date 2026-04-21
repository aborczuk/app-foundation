"""Unit tests for markdown doc shape validation."""

from __future__ import annotations

import importlib.util
import re
import subprocess
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


def _token_footprint(markdown_text: str) -> int:
    """Count whitespace-delimited tokens in markdown text."""
    return len(re.findall(r"\S+", markdown_text))


def _read_git_blob(pathspec: str) -> str:
    """Return the contents of a git blob from the current repository history."""
    completed = subprocess.run(
        ["git", "show", pathspec],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


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


def test_command_doc_token_footprint_reduction() -> None:
    """The migrated solution command doc should stay smaller than the pre-trim baseline."""
    repo_root = Path(__file__).resolve().parents[2]
    solution_doc = repo_root / ".claude" / "commands" / "speckit.solution.md"

    current_text = solution_doc.read_text(encoding="utf-8")
    repeated_text = solution_doc.read_text(encoding="utf-8")
    baseline_text = _read_git_blob("7c578d9:.claude/commands/speckit.plan.md")

    current_tokens = _token_footprint(current_text)
    repeated_tokens = _token_footprint(repeated_text)
    baseline_tokens = _token_footprint(baseline_text)

    payload = validator.validate_markdown_doc_shape(markdown_file=solution_doc)

    assert payload["ok"] is True
    assert payload["matched_shape"] == "compact_expanded"
    assert current_tokens == repeated_tokens
    assert current_tokens * 10 <= baseline_tokens * 7
