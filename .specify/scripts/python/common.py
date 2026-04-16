#!/usr/bin/env python3
"""Shared shell-compatible helpers for migrated SpecKit entrypoints."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


def run_git(args: list[str], cwd: Path) -> str | None:
    """Run git in `cwd` and return stripped stdout on success."""
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


def get_repo_root(script_path: Path) -> Path:
    """Resolve the repository root with a git-first fallback."""
    cwd = Path.cwd()
    git_root = run_git(["rev-parse", "--show-toplevel"], cwd)
    if git_root:
        return Path(git_root).resolve()

    script_dir = script_path.resolve().parent
    return (script_dir / "../../..").resolve()


def get_current_branch(repo_root: Path) -> str:
    """Resolve the active branch or the latest feature-style spec directory."""
    override = os.environ.get("SPECIFY_FEATURE", "").strip()
    if override:
        return override

    git_branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
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


def has_git(repo_root: Path) -> bool:
    """Return whether git is available at the provided repository root."""
    return run_git(["rev-parse", "--show-toplevel"], repo_root) is not None


def check_feature_branch(branch: str, has_git_repo: bool) -> None:
    """Validate feature branch naming, mirroring the legacy shell contract."""
    if not has_git_repo:
        print("[specify] Warning: Git repository not detected; skipped branch validation", file=sys.stderr)
        return

    if re.match(r"^[0-9]{3}-", branch):
        return

    print(f"ERROR: Not on a feature branch. Current branch: {branch}", file=sys.stderr)
    print("Feature branches should be named like: 001-feature-name", file=sys.stderr)
    raise SystemExit(1)


def find_feature_dir_by_prefix(repo_root: Path, branch_name: str) -> Path:
    """Locate the spec directory for a branch prefix, or fall back to branch name."""
    specs_dir = repo_root / "specs"
    match = re.match(r"^([0-9]{3})-", branch_name)
    if not match:
        return specs_dir / branch_name

    prefix = match.group(1)
    matches = sorted(item.name for item in specs_dir.glob(f"{prefix}-*") if item.is_dir())
    if len(matches) == 0:
        return specs_dir / branch_name
    if len(matches) == 1:
        return specs_dir / matches[0]

    print(
        f"ERROR: Multiple spec directories found with prefix '{prefix}': {' '.join(matches)}",
        file=sys.stderr,
    )
    print("Please ensure only one spec directory exists per numeric prefix.", file=sys.stderr)
    return specs_dir / branch_name
