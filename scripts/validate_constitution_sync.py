#!/usr/bin/env python3
"""Check that constitution-related docs and manifests stay in sync."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    """Return the repository root inferred from this script location."""
    return Path(__file__).resolve().parents[1]


def _run_command_script_coverage(repo_root: Path) -> int:
    """Run the command/script coverage validator and surface its output."""
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "validate_command_script_coverage.py"), "--json"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("PASS: command/script coverage validator")
        return 0

    print("ERROR: command/script coverage validator failed.", file=sys.stderr)
    if result.stdout:
        print(result.stdout, file=sys.stderr, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    return result.returncode


def _base_ref(repo_root: Path, requested: str | None) -> str | None:
    """Resolve the reference that should be compared against HEAD."""
    if requested:
        return requested

    for candidate in ("origin/main", "main"):
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", candidate],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return candidate
    return None


def _changed_files(repo_root: Path, base_ref: str) -> list[str]:
    """Return the changed files relative to the provided base reference."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--name-only", f"{base_ref}...HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _matches_prefix(paths: list[str], prefixes: tuple[str, ...]) -> list[str]:
    """Return the subset of paths that start with any of the given prefixes."""
    return [path for path in paths if path.startswith(prefixes)]


def main(argv: list[str]) -> int:
    """Run the constitution sync gate."""
    repo_root = _repo_root()
    requested_ref = argv[0] if argv else None
    base_ref = _base_ref(repo_root, requested_ref)
    if base_ref is None:
        print("ERROR: base ref not found: origin/main or main", file=sys.stderr)
        print("Hint: pass an explicit ref, e.g. scripts/validate_constitution_sync.py main", file=sys.stderr)
        return 2

    if subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", base_ref],
        check=False,
        capture_output=True,
        text=True,
    ).returncode != 0:
        print(f"ERROR: base ref not found: {base_ref}", file=sys.stderr)
        print("Hint: pass an explicit ref, e.g. scripts/validate_constitution_sync.py main", file=sys.stderr)
        return 2

    if _run_command_script_coverage(repo_root) != 0:
        return 1

    changed_files = _changed_files(repo_root, base_ref)
    if not changed_files:
        print(f"PASS: no changes vs {base_ref}")
        return 0

    governance_surface_changes = _matches_prefix(changed_files, (".claude/commands/", ".specify/templates/"))
    if not governance_surface_changes:
        print("PASS: no changes under .claude/commands/** or .specify/templates/**")
        return 0

    constitution_changed = "constitution.md" in changed_files
    if not constitution_changed:
        print("ERROR: governance surfaces changed but constitution was not updated.", file=sys.stderr)
        print(file=sys.stderr)
        print("Changed governance-surface files:", file=sys.stderr)
        for path in governance_surface_changes:
            print(path, file=sys.stderr)
        print(file=sys.stderr)
        print("Required file missing from diff:", file=sys.stderr)
        print("  constitution.md", file=sys.stderr)
        print(file=sys.stderr)
        print("Action: update constitution (version/sync impact as appropriate) in same change.", file=sys.stderr)
        return 1

    if "constitution-changelog.md" in changed_files:
        print("PASS: governance surfaces changed; constitution and changelog both updated.")
        return 0

    print("ERROR: constitution.md changed but constitution-changelog.md was not updated.", file=sys.stderr)
    print(file=sys.stderr)
    print("Action: append a SYNC IMPACT REPORT entry to constitution-changelog.md in the same change.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
