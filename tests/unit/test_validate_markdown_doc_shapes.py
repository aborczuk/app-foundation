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


def test_validate_markdown_doc_shape_rejects_executable_gate_append_procedures(
    tmp_path: Path,
) -> None:
    """Compact docs with gate/append procedures should be rejected."""
    doc = tmp_path / "doc.md"
    doc.write_text(
        "\n".join(
            [
                "# Title",
                "## User Input",
                "## Compact Contract (Load First)",
                "1. Run `uv run python scripts/speckit_gate_status.py --mode implement --feature-dir \"$FEATURE_DIR\" --json`.",
                "2. Run `uv run python scripts/speckit_prepare_ignores.py --repo-root . --plan-file \"$FEATURE_DIR/plan.md\" --json`.",
                "3. Execute tasks in order, using the task gate and ledger flow defined below.",
                "## Expanded Guidance (Load On Demand)",
                "## Behavior rules",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = validator.validate_markdown_doc_shape(markdown_file=doc)

    assert payload["ok"] is False
    assert payload["reasons"] == ["executable_procedures_detected"]
    assert payload["matched_shape"] == "compact_expanded"
    assert payload["forbidden_markers"] == [
        "speckit_gate_status.py",
        "speckit_prepare_ignores.py",
        "task gate and ledger flow",
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


def test_validate_markdown_doc_shape_enforces_required_command_set() -> None:
    """Required command docs should validate cleanly when enforcement is enabled."""
    repo_root = Path(__file__).resolve().parents[2]
    seed_doc = repo_root / ".claude" / "commands" / "speckit.run.md"

    payload = validator.validate_markdown_doc_shape(
        markdown_file=seed_doc,
        enforce_required_command_set=True,
        repo_root=repo_root,
    )

    assert payload["ok"] is True
    assert payload["required_command_docs"] is not None
    assert payload["required_command_docs"]["missing_docs"] == []
    assert payload["required_command_docs"]["shape_failures"] == []
    assert payload["required_command_docs"]["marker_failures"] == []


def test_validate_markdown_doc_shape_reports_missing_required_docs(tmp_path: Path) -> None:
    """Enforcement should fail deterministically when required docs are missing."""
    repo_root = tmp_path
    command_dir = repo_root / ".claude" / "commands"
    command_dir.mkdir(parents=True, exist_ok=True)
    (repo_root / "command-manifest.yaml").write_text("commands: {}\n", encoding="utf-8")
    seed_doc = command_dir / "speckit.run.md"
    seed_doc.write_text(
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

    payload = validator.validate_markdown_doc_shape(
        markdown_file=seed_doc,
        enforce_required_command_set=True,
        repo_root=repo_root,
    )

    assert payload["ok"] is False
    assert "required_command_docs_missing" in payload["reasons"]
    assert payload["required_command_docs"] is not None
    assert "speckit.tasking" in payload["required_command_docs"]["missing_docs"]
    assert "speckit.implement" in payload["required_command_docs"]["missing_docs"]
