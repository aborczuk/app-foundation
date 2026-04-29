#!/usr/bin/env python3
"""Validate documentation graph coverage and stale literal references."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    """Return the repository root inferred from this script location."""
    return Path(__file__).resolve().parents[1]


def _pass(message: str) -> None:
    """Print a passing validation line."""
    print(f"PASS: {message}")


def _fail(message: str) -> None:
    """Print a validation failure line."""
    print(f"ERROR: {message}", file=sys.stderr)


def _assert_exists(repo_root: Path, path: str, checks_run: list[int], failures: list[int]) -> None:
    """Record whether a required file exists."""
    checks_run[0] += 1
    if (repo_root / path).is_file():
        _pass(f"required file exists: {path}")
    else:
        failures[0] += 1
        _fail(f"required file missing: {path}")


def _assert_not_exists(repo_root: Path, path: str, reason: str, checks_run: list[int], failures: list[int]) -> None:
    """Record whether an obsolete file path is absent."""
    checks_run[0] += 1
    if not (repo_root / path).is_file():
        _pass(f"anti-regression: {reason}")
    else:
        failures[0] += 1
        _fail(f"anti-regression VIOLATION: {reason} (file exists at {path})")


def _run_command_coverage_validator(repo_root: Path, checks_run: list[int], failures: list[int]) -> None:
    """Run the command/script coverage validator and capture its output."""
    checks_run[0] += 1
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "validate_command_script_coverage.py"), "--json"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        _pass("command/script coverage validator")
        return

    failures[0] += 1
    _fail("command/script coverage validator failed")
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")


def _run_forbidden_literal_check(
    repo_root: Path,
    label: str,
    literal: str,
    scope_paths: list[str],
    checks_run: list[int],
    failures: list[int],
) -> None:
    """Search scoped text files for a forbidden literal."""
    checks_run[0] += 1
    hits: list[str] = []
    for scope in scope_paths:
        scope_root = repo_root / scope
        if not scope_root.exists():
            continue
        if scope_root.is_file():
            candidates = [scope_root]
        else:
            candidates = [path for path in scope_root.rglob("*") if path.is_file()]
        for path in candidates:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if literal in line:
                    hits.append(f"{path.relative_to(repo_root)}:{lineno}:{line}")

    if hits:
        failures[0] += 1
        _fail(label)
        for hit in hits:
            print(hit)
        return

    _pass(label)


def _manual_block(repo_root: Path) -> str:
    """Extract the manual-additions block from CLAUDE.md."""
    claude_path = repo_root / "CLAUDE.md"
    if not claude_path.is_file():
        return ""

    lines = claude_path.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index("<!-- MANUAL ADDITIONS START -->")
        end = lines.index("<!-- MANUAL ADDITIONS END -->")
    except ValueError:
        return ""
    return "\n".join(lines[start : end + 1])


def main(argv: list[str]) -> int:
    """Run the documentation graph validation suite."""
    repo_root = _repo_root()
    failures = [0]
    checks_run = [0]

    _assert_exists(repo_root, "docs/governance/doc-graph.yaml", checks_run, failures)
    _assert_exists(repo_root, "constitution.md", checks_run, failures)
    _assert_exists(repo_root, "CLAUDE.md", checks_run, failures)
    _assert_exists(repo_root, "catalog.yaml", checks_run, failures)
    _run_command_coverage_validator(repo_root, checks_run, failures)
    _assert_exists(repo_root, "command-manifest.yaml", checks_run, failures)
    _assert_not_exists(
        repo_root,
        ".specify/command-manifest.yaml",
        "legacy manifest path removed and not reintroduced",
        checks_run,
        failures,
    )

    _run_forbidden_literal_check(
        repo_root,
        "no stale .specify/templates/commands/ references in propagation logic",
        ".specify/templates/commands/",
        [".claude/commands", ".specify/templates"],
        checks_run,
        failures,
    )

    checks_run[0] += 1
    manual_block = _manual_block(repo_root)
    if manual_block:
        pattern = re.compile(
            r"^### (Human-First Decisions|Security First|Reuse|Separation of Concerns \(SoC\)|"
            r"Observability and Fail Gracefully|Local Database Transaction Integrity \(ACID\)|"
            r"Test-Driven Development \(TDD\)|Documentation as a First-Class Standard|Parsimony|"
            r"Reuse Over Invention|Composability and Modularity|Keep It Simple, Stupid \(KISS\) & YAGNI|"
            r"The SOLID Principles|Don't Repeat Yourself \(DRY\))"
        )
        principle_hits = [
            line
            for line in manual_block.splitlines()
            if pattern.match(line)
        ]
        if principle_hits:
            failures[0] += 1
            _fail("CLAUDE.md manual block duplicates principle headings owned by constitution")
            for hit in principle_hits:
                print(hit)
        else:
            _pass("CLAUDE.md manual block avoids constitution principle-heading duplication")

    print()
    print(f"Doc graph validation checks: {checks_run[0]}")
    if failures[0] > 0:
        print(f"Doc graph validation FAILED: {failures[0]} issue(s).", file=sys.stderr)
        return 1

    print("Doc graph validation PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
