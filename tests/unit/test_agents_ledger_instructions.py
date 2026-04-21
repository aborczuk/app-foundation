"""Smoke tests for AGENTS.md ledger instructions and the live CLI shape."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def _load_pipeline_ledger_module():
    """Load the pipeline ledger script so the test can verify its parser shape."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "pipeline_ledger.py"
    spec = importlib.util.spec_from_file_location("pipeline_ledger", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_task_ledger_module():
    """Load the task ledger script so the test can verify its parser shape."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "task_ledger.py"
    spec = importlib.util.spec_from_file_location("task_ledger", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _subcommand_help(parser: argparse.ArgumentParser, command: str) -> str:
    """Return the formatted help text for one parser subcommand."""
    subparser_actions = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(subparser_actions) == 1
    return subparser_actions[0].choices[command].format_help()


def test_agents_ledger_instructions_match_ledger_clis() -> None:
    """Keep the AGENTS.md ledger instructions aligned with the real CLIs."""
    agents_text = Path(__file__).resolve().parents[2].joinpath("AGENTS.md").read_text(
        encoding="utf-8"
    )
    pipeline_ledger = _load_pipeline_ledger_module()
    task_ledger = _load_task_ledger_module()
    pipeline_validate_help = _subcommand_help(pipeline_ledger.build_parser(), "validate")
    pipeline_gate_help = _subcommand_help(pipeline_ledger.build_parser(), "assert-phase-complete")
    task_validate_help = _subcommand_help(task_ledger.build_parser(), "validate")
    task_gate_help = _subcommand_help(task_ledger.build_parser(), "assert-can-start")

    assert "uv run python scripts/pipeline_ledger.py validate" in agents_text
    assert "uv run python scripts/task_ledger.py validate --file .speckit/task-ledger.jsonl" in agents_text
    assert "--feature-id <FEATURE_ID> --phase <PHASE_NAME>" not in agents_text
    assert "--feature-id <FEATURE_ID>" in agents_text
    assert "--task-id <TASK_ID>" in agents_text

    assert "--file FILE" in pipeline_validate_help
    assert "--feature-id FEATURE_ID" in pipeline_gate_help
    assert "--event" in pipeline_gate_help
    assert "--phase" not in pipeline_gate_help

    assert "--file FILE" in task_validate_help
    assert "--tasks-file TASKS_FILE" in task_gate_help
    assert "--feature-id FEATURE_ID" in task_gate_help
    assert "--task-id TASK_ID" in task_gate_help


def test_agents_reading_instructions_prioritize_headings_and_help() -> None:
    """Keep the markdown and script-reading workflow explicit in AGENTS.md."""
    agents_text = Path(__file__).resolve().parents[2].joinpath("AGENTS.md").read_text(
        encoding="utf-8"
    )

    assert "read_markdown_headings" in agents_text
    assert "read_markdown_section" in agents_text
    assert "exact heading title" in agents_text
    assert "--help" in agents_text


def test_agents_edit_instructions_require_batch_validation_loop() -> None:
    """Keep the edit workflow explicit about tests, LSP, and Ruff validation."""
    agents_text = Path(__file__).resolve().parents[2].joinpath("AGENTS.md").read_text(
        encoding="utf-8"
    )

    assert "Any code edit that changes behavior" in agents_text
    assert "documentation explaining the function or work" in agents_text
    assert "After each edit batch, run a validation loop" in agents_text
    assert "targeted tests for the touched behavior" in agents_text
    assert "codebase-lsp diagnostics" in agents_text
    assert "uv run ruff check" in agents_text
    assert "Do not advance past an edit batch" in agents_text
    assert "uv run python scripts/hook_refresh_indexes.py" in agents_text
    assert "changed-path JSON payload on stdin" in agents_text
    assert "Commit once per completed edit unit" in agents_text
    assert "small, well-described commits are the basic unit of maintainable code" in agents_text
    assert "commit and push so the branch is synced" in agents_text
    assert "one coherent edit unit" in agents_text
    assert "Edit-done checklist" in agents_text
    assert "targeted tests for the touched behavior" in agents_text
    assert "codebase-lsp diagnostics for touched Python files" in agents_text
    assert "uv run ruff check" in agents_text
    assert "commit the coherent edit unit" in agents_text
    assert "push so the branch is synced" in agents_text
