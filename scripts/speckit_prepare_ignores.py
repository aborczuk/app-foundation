#!/usr/bin/env python3
"""Ensure common ignore files exist with baseline patterns for active tooling."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

IGNORE_RULES: dict[str, tuple[str, ...]] = {
    ".gitignore": (
        "__pycache__/",
        "*.pyc",
        ".venv/",
        "venv/",
        ".env",
        ".env.*",
        "dist/",
        "build/",
        ".DS_Store",
        "*.tmp",
    ),
    ".dockerignore": (
        ".git/",
        "node_modules/",
        "dist/",
        "build/",
        "__pycache__/",
        "*.pyc",
        ".venv/",
        ".env",
        ".env.*",
    ),
    ".eslintignore": (
        "node_modules/",
        "dist/",
        "build/",
        "coverage/",
    ),
    ".prettierignore": (
        "node_modules/",
        "dist/",
        "build/",
        "coverage/",
    ),
    ".npmignore": (
        "node_modules/",
        "tests/",
        "__pycache__/",
        "*.pyc",
        ".env",
        ".env.*",
    ),
    ".terraformignore": (
        ".terraform/",
        "*.tfstate",
        "*.tfstate.*",
        "*.tfvars",
        ".terraform.lock.hcl",
    ),
    ".helmignore": (
        ".DS_Store",
        "*.swp",
        "*.tmp",
        "charts/*/tmp/",
        "secrets/",
    ),
}


def _json_print(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"ok={payload['ok']} mode={payload['mode']}")
    for row in payload["results"]:
        print(
            f"- {row['file']}: created={row['created']} appended={len(row['appended_patterns'])}"
        )
    for warning in payload["warnings"]:
        print(f"WARN: {warning}")


def _command_succeeds(cmd: list[str], cwd: Path) -> bool:
    run = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    return run.returncode == 0


def _has_any(repo_root: Path, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if any(repo_root.glob(pattern)):
            return True
    return False


def _plan_mentions_docker(plan_file: Path) -> bool:
    if not plan_file.exists():
        return False
    text = plan_file.read_text(encoding="utf-8", errors="ignore")
    return "docker" in text.lower()


def _ensure_patterns(path: Path, patterns: tuple[str, ...]) -> tuple[bool, list[str]]:
    created = not path.exists()
    existing_lines: list[str] = []
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()

    existing_set = {line.strip() for line in existing_lines if line.strip()}
    appended = [pattern for pattern in patterns if pattern not in existing_set]
    if not appended and not created:
        return (False, [])

    if created:
        lines = ["# Managed by scripts/speckit_prepare_ignores.py", *patterns]
    else:
        lines = [*existing_lines]
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.extend(appended)

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return (created, appended)


def _build_targets(repo_root: Path, plan_file: Path) -> list[str]:
    targets: list[str] = []
    if _command_succeeds(["git", "rev-parse", "--git-dir"], repo_root):
        targets.append(".gitignore")

    if _has_any(repo_root, ("Dockerfile", "Dockerfile.*", "**/Dockerfile", "**/Dockerfile.*")) or _plan_mentions_docker(plan_file):
        targets.append(".dockerignore")

    if _has_any(repo_root, (".eslintrc", ".eslintrc.*", "**/.eslintrc", "**/.eslintrc.*")):
        targets.append(".eslintignore")

    if _has_any(repo_root, (".prettierrc", ".prettierrc.*", "**/.prettierrc", "**/.prettierrc.*")):
        targets.append(".prettierignore")

    if _has_any(repo_root, ("package.json", ".npmrc", "**/package.json", "**/.npmrc")):
        targets.append(".npmignore")

    if _has_any(repo_root, ("*.tf", "**/*.tf")):
        targets.append(".terraformignore")

    if _has_any(repo_root, ("Chart.yaml", "**/Chart.yaml")):
        targets.append(".helmignore")

    return targets


def main(argv: list[str] | None = None) -> int:
    """Run deterministic ignore-file setup and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--plan-file", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    plan_file = Path(args.plan_file).resolve() if args.plan_file else repo_root / "plan.md"

    warnings: list[str] = []
    results: list[dict[str, Any]] = []

    if _has_any(repo_root, ("eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "**/eslint.config.js", "**/eslint.config.mjs", "**/eslint.config.cjs")):
        warnings.append("eslint_config_detected: verify eslint.config.* ignores include generated/build paths")

    for target in _build_targets(repo_root, plan_file):
        ignore_file = repo_root / target
        created, appended = _ensure_patterns(ignore_file, IGNORE_RULES[target])
        results.append(
            {
                "file": target,
                "created": created,
                "appended_patterns": appended,
            }
        )

    payload: dict[str, Any] = {
        "mode": "ensure_ignores",
        "repo_root": str(repo_root),
        "plan_file": str(plan_file),
        "results": results,
        "warnings": warnings,
        "ok": True,
    }
    _json_print(payload, as_json=bool(args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
