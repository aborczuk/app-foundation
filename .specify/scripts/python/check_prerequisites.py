#!/usr/bin/env python3
"""Python entrypoint for check-prerequisites with shell-compatible contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from bootstrap_session import bootstrap_session  # noqa: E402
from common import (  # noqa: E402
    check_feature_branch,
    find_feature_dir_by_prefix,
    get_current_branch,
    get_repo_root,
    has_git,
)


def _help_text() -> str:
    """Return the CLI help text for the prerequisite checker."""
    return """Usage: check_prerequisites.py [OPTIONS]

Consolidated prerequisite checking for Spec-Driven Development workflow.

OPTIONS:
  --json              Output in JSON format
  --require-tasks     Require tasks.md to exist (for implementation phase)
  --include-tasks     Include tasks.md in AVAILABLE_DOCS list
  --paths-only        Only output path variables (no prerequisite validation)
  --help, -h          Show this help message

EXAMPLES:
  # Check task prerequisites (plan.md required)
  ./check_prerequisites.py --json

  # Check implementation prerequisites (plan.md + tasks.md required)
  ./check_prerequisites.py --json --require-tasks --include-tasks

  # Get feature paths only (no validation)
  ./check_prerequisites.py --paths-only
  """


def _parse_args(argv: list[str]) -> tuple[bool, bool, bool, bool]:
    """Parse prerequisite checker flags from argv."""
    json_mode = False
    require_tasks = False
    include_tasks = False
    paths_only = False

    for arg in argv:
        if arg == "--json":
            json_mode = True
        elif arg == "--require-tasks":
            require_tasks = True
        elif arg == "--include-tasks":
            include_tasks = True
        elif arg == "--paths-only":
            paths_only = True
        elif arg in {"--help", "-h"}:
            print(_help_text())
            raise SystemExit(0)
        else:
            print(f"ERROR: Unknown option '{arg}'. Use --help for usage information.", file=sys.stderr)
            raise SystemExit(1)

    return json_mode, require_tasks, include_tasks, paths_only


def _get_feature_paths(script_path: Path) -> dict[str, str]:
    """Build the canonical feature path map for the active branch."""
    repo_root = get_repo_root(script_path)
    branch = get_current_branch(repo_root)
    has_git_repo = has_git(repo_root)
    feature_dir = find_feature_dir_by_prefix(repo_root, branch)

    return {
        "REPO_ROOT": str(repo_root),
        "CURRENT_BRANCH": branch,
        "HAS_GIT": "true" if has_git_repo else "false",
        "FEATURE_DIR": str(feature_dir),
        "FEATURE_SPEC": str(feature_dir / "spec.md"),
        "IMPL_PLAN": str(feature_dir / "plan.md"),
        "TASKS": str(feature_dir / "tasks.md"),
        "RESEARCH": str(feature_dir / "research.md"),
        "DATA_MODEL": str(feature_dir / "data-model.md"),
        "QUICKSTART": str(feature_dir / "quickstart.md"),
        "CONTRACTS_DIR": str(feature_dir / "contracts"),
    }


def _check_file(path: Path, label: str) -> str:
    """Render a checkmark line for a required file path."""
    return f"  \u2713 {label}" if path.is_file() else f"  \u2717 {label}"


def _check_dir(path: Path, label: str) -> str:
    """Render a checkmark line for a required non-empty directory."""
    if path.is_dir() and any(path.iterdir()):
        return f"  \u2713 {label}"
    return f"  \u2717 {label}"


def main(argv: list[str]) -> int:
    """CLI entrypoint for the check-prerequisites workflow."""
    bootstrap_session(Path(__file__).resolve().parents[3])
    json_mode, require_tasks, include_tasks, paths_only = _parse_args(argv)
    script_path = Path(__file__)
    paths = _get_feature_paths(script_path)

    check_feature_branch(paths["CURRENT_BRANCH"], paths["HAS_GIT"] == "true")

    feature_dir = Path(paths["FEATURE_DIR"])
    impl_plan = Path(paths["IMPL_PLAN"])
    tasks = Path(paths["TASKS"])
    research = Path(paths["RESEARCH"])
    data_model = Path(paths["DATA_MODEL"])
    quickstart = Path(paths["QUICKSTART"])
    contracts_dir = Path(paths["CONTRACTS_DIR"])

    if paths_only:
        if json_mode:
            payload = {
                "REPO_ROOT": paths["REPO_ROOT"],
                "BRANCH": paths["CURRENT_BRANCH"],
                "FEATURE_DIR": paths["FEATURE_DIR"],
                "FEATURE_SPEC": paths["FEATURE_SPEC"],
                "IMPL_PLAN": paths["IMPL_PLAN"],
                "TASKS": paths["TASKS"],
            }
            print(json.dumps(payload, separators=(",", ":")))
        else:
            print(f"REPO_ROOT: {paths['REPO_ROOT']}")
            print(f"BRANCH: {paths['CURRENT_BRANCH']}")
            print(f"FEATURE_DIR: {paths['FEATURE_DIR']}")
            print(f"FEATURE_SPEC: {paths['FEATURE_SPEC']}")
            print(f"IMPL_PLAN: {paths['IMPL_PLAN']}")
            print(f"TASKS: {paths['TASKS']}")
        return 0

    if not feature_dir.is_dir():
        print(f"ERROR: Feature directory not found: {feature_dir}", file=sys.stderr)
        print("Run /speckit.specify first to create the feature structure.", file=sys.stderr)
        return 1

    if not impl_plan.is_file():
        print(f"ERROR: plan.md not found in {feature_dir}", file=sys.stderr)
        print("Run /speckit.plan first to create the implementation plan.", file=sys.stderr)
        return 1

    if require_tasks and not tasks.is_file():
        print(f"ERROR: tasks.md not found in {feature_dir}", file=sys.stderr)
        print("Run /speckit.tasks first to create the task list.", file=sys.stderr)
        return 1

    docs: list[str] = []
    if research.is_file():
        docs.append("research.md")
    if data_model.is_file():
        docs.append("data-model.md")
    if contracts_dir.is_dir() and any(contracts_dir.iterdir()):
        docs.append("contracts/")
    if quickstart.is_file():
        docs.append("quickstart.md")
    if include_tasks and tasks.is_file():
        docs.append("tasks.md")

    if json_mode:
        payload = {"FEATURE_DIR": str(feature_dir), "AVAILABLE_DOCS": docs}
        print(json.dumps(payload, separators=(",", ":")))
        return 0

    print(f"FEATURE_DIR:{feature_dir}")
    print("AVAILABLE_DOCS:")
    print(_check_file(research, "research.md"))
    print(_check_file(data_model, "data-model.md"))
    print(_check_dir(contracts_dir, "contracts/"))
    print(_check_file(quickstart, "quickstart.md"))
    if include_tasks:
        print(_check_file(tasks, "tasks.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
