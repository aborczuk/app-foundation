#!/usr/bin/env python3
"""Deterministic estimate/breakdown chain for tasking stabilization."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TASK_ID_RE = re.compile(r"\bT\d{3}\b")
HIGH_POINT_RE = re.compile(r"\b(8|13)\b")


@dataclass(frozen=True)
class CommandResult:
    """Result for one external command execution."""

    command: str
    exit_code: int
    stdout: str
    stderr: str


def _run_command(command: str, *, cwd: Path) -> CommandResult:
    """Run a shell command and return deterministic captured output."""
    tokens = shlex.split(command)
    if not tokens:
        raise ValueError("empty_command")
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", str((cwd / ".uv-cache").resolve()))
    completed = subprocess.run(
        tokens,
        cwd=str(cwd),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult(
        command=command,
        exit_code=int(completed.returncode),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _extract_high_point_tasks(estimates_text: str) -> list[str]:
    """Return unique task IDs that still appear with 8/13-point values."""
    high_point_tasks: list[str] = []
    for line in estimates_text.splitlines():
        if not HIGH_POINT_RE.search(line):
            continue
        task_match = TASK_ID_RE.search(line)
        if task_match:
            task_id = task_match.group(0)
            if task_id not in high_point_tasks:
                high_point_tasks.append(task_id)
    return high_point_tasks


def _build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for tasking chain stabilization."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-dir", required=True)
    parser.add_argument("--tasks-file", default=None)
    parser.add_argument("--estimates-file", default=None)
    parser.add_argument("--estimate-command", default="")
    parser.add_argument("--breakdown-command", default="")
    parser.add_argument("--max-rounds", type=int, default=4)
    parser.add_argument("--json", action="store_true")
    return parser


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    """Resolve feature/tasks/estimates paths from CLI args."""
    feature_dir = Path(args.feature_dir).resolve()
    tasks_file = Path(args.tasks_file).resolve() if args.tasks_file else feature_dir / "tasks.md"
    estimates_file = (
        Path(args.estimates_file).resolve() if args.estimates_file else feature_dir / "estimates.md"
    )
    return feature_dir, tasks_file, estimates_file


def _fail(reasons: list[str], *, command_results: list[CommandResult]) -> dict[str, Any]:
    """Build deterministic failure payload."""
    return {
        "ok": False,
        "reasons": reasons,
        "command_results": [
            {
                "command": result.command,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            for result in command_results
        ],
    }


def run_chain(args: argparse.Namespace) -> dict[str, Any]:
    """Execute estimate -> optional breakdown -> estimate loop until stabilized."""
    feature_dir, tasks_file, estimates_file = _resolve_paths(args)
    command_results: list[CommandResult] = []

    if not feature_dir.exists():
        return _fail(["missing_feature_dir"], command_results=command_results)
    if not tasks_file.exists():
        return _fail(["missing_tasks_file"], command_results=command_results)
    if args.max_rounds <= 0:
        return _fail(["invalid_max_rounds"], command_results=command_results)

    estimate_command = str(args.estimate_command or "").strip()
    breakdown_command = str(args.breakdown_command or "").strip()

    if not estimate_command and not estimates_file.exists():
        return _fail(["missing_estimate_command", "missing_estimates_file"], command_results=command_results)

    rounds = 0
    if estimate_command:
        first_estimate = _run_command(estimate_command, cwd=feature_dir)
        command_results.append(first_estimate)
        if first_estimate.exit_code != 0:
            return _fail(["estimate_command_failed"], command_results=command_results)
        rounds += 1

    if not estimates_file.exists():
        return _fail(["missing_estimates_file"], command_results=command_results)

    while True:
        estimates_text = estimates_file.read_text(encoding="utf-8")
        high_point_tasks = _extract_high_point_tasks(estimates_text)
        if not high_point_tasks:
            return {
                "ok": True,
                "reasons": [],
                "rounds": rounds,
                "high_point_tasks": [],
                "command_results": [
                    {
                        "command": result.command,
                        "exit_code": result.exit_code,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
                    for result in command_results
                ],
            }

        if not breakdown_command:
            return _fail(
                ["breakdown_required", "missing_breakdown_command"],
                command_results=command_results,
            )
        if not estimate_command:
            return _fail(
                ["breakdown_required", "missing_estimate_command"],
                command_results=command_results,
            )
        if rounds >= args.max_rounds:
            return _fail(
                ["max_rounds_exceeded", "high_point_tasks_remain"],
                command_results=command_results,
            )

        breakdown_result = _run_command(breakdown_command, cwd=feature_dir)
        command_results.append(breakdown_result)
        if breakdown_result.exit_code != 0:
            return _fail(["breakdown_command_failed"], command_results=command_results)

        estimate_result = _run_command(estimate_command, cwd=feature_dir)
        command_results.append(estimate_result)
        if estimate_result.exit_code != 0:
            return _fail(["estimate_command_failed"], command_results=command_results)
        rounds += 1


def main(argv: list[str] | None = None) -> int:
    """Run tasking chain stabilization and emit deterministic result payload."""
    args = _build_parser().parse_args(argv)
    payload = run_chain(args)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if payload.get("ok"):
            print(
                " ".join(
                    [
                        "status=PASS",
                        f"rounds={payload.get('rounds', 0)}",
                        "high_point_tasks=0",
                    ]
                )
            )
        else:
            print(f"status=FAIL reasons={','.join(payload.get('reasons', []))}")
    return 0 if bool(payload.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
