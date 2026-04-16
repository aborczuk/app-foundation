#!/usr/bin/env python3
"""Python entrypoint for check-prerequisites with shell-compatible contract."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _help_text() -> str:
    return """Usage: check-prerequisites.sh [OPTIONS]

Consolidated prerequisite checking for Spec-Driven Development workflow.

OPTIONS:
  --json              Output in JSON format
  --require-tasks     Require tasks.md to exist (for implementation phase)
  --include-tasks     Include tasks.md in AVAILABLE_DOCS list
  --paths-only        Only output path variables (no prerequisite validation)
  --help, -h          Show this help message

EXAMPLES:
  # Check task prerequisites (plan.md required)
  ./check-prerequisites.sh --json
  
  # Check implementation prerequisites (plan.md + tasks.md required)
  ./check-prerequisites.sh --json --require-tasks --include-tasks
  
  # Get feature paths only (no validation)
  ./check-prerequisites.sh --paths-only
  """


def _run_git(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip()


def _parse_args(argv: list[str]) -> tuple[bool, bool, bool, bool]:
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


def _get_repo_root(script_path: Path) -> Path:
    cwd = Path.cwd()
    git_root = _run_git(["rev-parse", "--show-toplevel"], cwd)
    if git_root:
        return Path(git_root).resolve()

    script_dir = script_path.resolve().parent
    return (script_dir / "../../..").resolve()


def _get_current_branch(repo_root: Path) -> str:
    override = os.environ.get("SPECIFY_FEATURE", "").strip()
    if override:
        return override

    git_branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    if git_branch:
        return git_branch

    specs_dir = repo_root / "specs"
    highest = -1
    latest_feature = ""
    if specs_dir.is_dir():
        for candidate in specs_dir.iterdir():
            if not candidate.is_dir():
                continue
            match = re.match(r"^([0-9]{3})-", candidate.name)
            if not match:
                continue
            number = int(match.group(1), 10)
            if number > highest:
                highest = number
                latest_feature = candidate.name

    if latest_feature:
        return latest_feature
    return "main"


def _has_git(repo_root: Path) -> bool:
    return _run_git(["rev-parse", "--show-toplevel"], repo_root) is not None


def _check_feature_branch(branch: str, has_git_repo: bool) -> None:
    if not has_git_repo:
        print("[specify] Warning: Git repository not detected; skipped branch validation", file=sys.stderr)
        return

    if re.match(r"^[0-9]{3}-", branch):
        return

    print(f"ERROR: Not on a feature branch. Current branch: {branch}", file=sys.stderr)
    print("Feature branches should be named like: 001-feature-name", file=sys.stderr)
    raise SystemExit(1)


def _find_feature_dir_by_prefix(repo_root: Path, branch_name: str) -> Path:
    specs_dir = repo_root / "specs"
    match = re.match(r"^([0-9]{3})-", branch_name)
    if not match:
        return specs_dir / branch_name

    prefix = match.group(1)
    matches = [item.name for item in specs_dir.glob(f"{prefix}-*") if item.is_dir()]
    matches.sort()

    if len(matches) == 0:
        return specs_dir / branch_name
    if len(matches) == 1:
        return specs_dir / matches[0]

    print(f"ERROR: Multiple spec directories found with prefix '{prefix}': {' '.join(matches)}", file=sys.stderr)
    print("Please ensure only one spec directory exists per numeric prefix.", file=sys.stderr)
    return specs_dir / branch_name


def _get_feature_paths(script_path: Path) -> dict[str, str]:
    repo_root = _get_repo_root(script_path)
    branch = _get_current_branch(repo_root)
    has_git_repo = _has_git(repo_root)
    feature_dir = _find_feature_dir_by_prefix(repo_root, branch)

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
    return f"  \u2713 {label}" if path.is_file() else f"  \u2717 {label}"


def _check_dir(path: Path, label: str) -> str:
    if path.is_dir() and any(path.iterdir()):
        return f"  \u2713 {label}"
    return f"  \u2717 {label}"


def main(argv: list[str]) -> int:
    json_mode, require_tasks, include_tasks, paths_only = _parse_args(argv)
    script_path = Path(__file__)
    paths = _get_feature_paths(script_path)

    _check_feature_branch(paths["CURRENT_BRANCH"], paths["HAS_GIT"] == "true")

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
