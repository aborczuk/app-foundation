from __future__ import annotations

from pathlib import Path

from scripts import hook_edit_paths


def test_collect_changed_paths_keeps_new_repo_local_targets() -> None:
    """The shared helper should keep new repo-local targets even before they exist."""
    root = Path(__file__).resolve().parents[2]
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "specs/999-example/spec.md",
            "content": "# Example\n",
        },
    }

    changed_paths = hook_edit_paths.collect_changed_paths(payload, root=root)

    assert changed_paths == [root / "specs/999-example/spec.md"]


def test_direct_edit_branch_guard_paths_exempts_spec_and_governance_markdown() -> None:
    """The shared helper should exempt only the allowed Markdown documentation roots."""
    root = Path(__file__).resolve().parents[2]
    exempt_paths = [
        root / "specs/999-example/spec.md",
        root / "docs/governance/example.md",
    ]
    guarded_paths = [
        root / "docs/notes/example.md",
        root / "src/example.py",
    ]

    assert hook_edit_paths.direct_edit_branch_guard_paths(exempt_paths, root=root) == []
    assert hook_edit_paths.direct_edit_branch_guard_paths(guarded_paths, root=root) == guarded_paths
