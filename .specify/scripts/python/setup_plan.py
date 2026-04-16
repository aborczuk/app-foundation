#!/usr/bin/env python3
"""Python entrypoint for setup-plan workflow with shell-compatible output."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _run_git(args: list[str], repo_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return completed.stdout.strip()


def _get_repo_root(script_path: Path) -> Path:
    script_repo_root = script_path.resolve().parents[3]
    root = _run_git(["rev-parse", "--show-toplevel"], script_repo_root)
    if root:
        return Path(root).resolve()
    return script_repo_root


def _get_current_branch(repo_root: Path, specs_dir: Path) -> str:
    override = os.environ.get("SPECIFY_FEATURE", "").strip()
    if override:
        return override

    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    if branch:
        return branch

    highest = -1
    latest = ""
    if specs_dir.is_dir():
        for candidate in specs_dir.iterdir():
            if not candidate.is_dir():
                continue
            match = re.match(r"^([0-9]{3})-", candidate.name)
            if not match:
                continue
            number = int(match.group(1))
            if number > highest:
                highest = number
                latest = candidate.name
    if latest:
        return latest
    return "main"


def _has_git(repo_root: Path) -> bool:
    return _run_git(["rev-parse", "--show-toplevel"], repo_root) is not None


def _check_feature_branch(branch: str, has_git: bool) -> bool:
    if not has_git:
        print("[specify] Warning: Git repository not detected; skipped branch validation", file=sys.stderr)
        return True
    if re.match(r"^[0-9]{3}-", branch):
        return True
    print(f"ERROR: Not on a feature branch. Current branch: {branch}", file=sys.stderr)
    print("Feature branches should be named like: 001-feature-name", file=sys.stderr)
    return False


def _find_feature_dir_by_prefix(repo_root: Path, branch: str) -> Path:
    specs_dir = repo_root / "specs"
    match = re.match(r"^([0-9]{3})-", branch)
    if not match:
        return specs_dir / branch

    prefix = match.group(1)
    matches = sorted(
        [path.name for path in specs_dir.glob(f"{prefix}-*") if path.is_dir()]
    )
    if not matches:
        return specs_dir / branch
    if len(matches) == 1:
        return specs_dir / matches[0]

    print(
        f"ERROR: Multiple spec directories found with prefix '{prefix}': {' '.join(matches)}",
        file=sys.stderr,
    )
    print("Please ensure only one spec directory exists per numeric prefix.", file=sys.stderr)
    return specs_dir / branch


def _build_paths(script_path: Path) -> dict[str, str]:
    repo_root = _get_repo_root(script_path)
    specs_dir = repo_root / "specs"
    branch = _get_current_branch(repo_root, specs_dir)
    has_git = _has_git(repo_root)
    feature_dir = _find_feature_dir_by_prefix(repo_root, branch)
    return {
        "REPO_ROOT": str(repo_root),
        "CURRENT_BRANCH": branch,
        "HAS_GIT": "true" if has_git else "false",
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
    args = _parse_args(argv)
    if args.help_mode:
        print("Usage: setup-plan.sh [--json]")
        print("  --json    Output results in JSON format")
        print("  --help    Show this help message")
        return 0

    script_path = Path(__file__)
    paths = _build_paths(script_path)
    if not _check_feature_branch(paths["CURRENT_BRANCH"], paths["HAS_GIT"] == "true"):
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
