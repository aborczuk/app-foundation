#!/usr/bin/env python3
"""Python entrypoint for setup-plan workflow with shell-compatible output."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from common import (
    check_feature_branch,
    find_feature_dir_by_prefix,
    get_current_branch,
    get_repo_root,
)
from common import (
    has_git as common_has_git,
)


def _build_paths(script_path: Path) -> dict[str, str]:
    repo_root = get_repo_root(script_path)
    branch = get_current_branch(repo_root)
    has_git_repo = common_has_git(repo_root)
    feature_dir = find_feature_dir_by_prefix(repo_root, branch)
    return {
        "REPO_ROOT": str(repo_root),
        "CURRENT_BRANCH": branch,
        "HAS_GIT": "true" if has_git_repo else "false",
        "FEATURE_DIR": str(feature_dir),
        "FEATURE_SPEC": str(feature_dir / "spec.md"),
        "IMPL_PLAN": str(feature_dir / "plan.md"),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--json", action="store_true", dest="json_mode")
    parser.add_argument("--help", "-h", action="store_true", dest="help_mode")
    parser.add_argument("extra", nargs="*")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """CLI entrypoint for the setup-plan workflow."""
    args = _parse_args(argv)
    if args.help_mode:
        print("Usage: setup-plan.sh [--json]")
        print("  --json    Output results in JSON format")
        print("  --help    Show this help message")
        return 0

    script_path = Path(__file__)
    paths = _build_paths(script_path)
    try:
        check_feature_branch(paths["CURRENT_BRANCH"], paths["HAS_GIT"] == "true")
    except SystemExit:
        return 1

    feature_dir = Path(paths["FEATURE_DIR"])
    impl_plan = Path(paths["IMPL_PLAN"])
    repo_root = Path(paths["REPO_ROOT"])
    feature_dir.mkdir(parents=True, exist_ok=True)

    template = repo_root / ".specify" / "templates" / "plan-template.md"
    if template.is_file():
        shutil.copyfile(template, impl_plan)
        print(f"Copied plan template to {impl_plan}")
    else:
        print(f"Warning: Plan template not found at {template}")
        impl_plan.touch()

    if args.json_mode:
        print(
            (
                '{"FEATURE_SPEC":"%s","IMPL_PLAN":"%s","SPECS_DIR":"%s",'
                '"BRANCH":"%s","HAS_GIT":"%s"}'
            )
            % (
                paths["FEATURE_SPEC"],
                paths["IMPL_PLAN"],
                paths["FEATURE_DIR"],
                paths["CURRENT_BRANCH"],
                paths["HAS_GIT"],
            )
        )
    else:
        print(f"FEATURE_SPEC: {paths['FEATURE_SPEC']}")
        print(f"IMPL_PLAN: {paths['IMPL_PLAN']}")
        print(f"SPECS_DIR: {paths['FEATURE_DIR']}")
        print(f"BRANCH: {paths['CURRENT_BRANCH']}")
        print(f"HAS_GIT: {paths['HAS_GIT']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
