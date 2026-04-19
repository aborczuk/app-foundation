#!/usr/bin/env python3
"""Deterministic gate checks for /speckit.implement execution."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

TASK_LINE_RE = re.compile(r"^\s*-\s*\[(?P<state>[ xX])\]\s+(?P<task_id>T\d{3})\b")
CHECKBOX_RE = re.compile(r"^\s*-\s*\[(?P<state>[ xX])\]")
PHASE_HEADER_RE = re.compile(r"^\s*##\s+(?P<title>.+?)\s*$")


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _string_list(value: Any, allow_empty: bool = False) -> bool:
    if not isinstance(value, list):
        return False
    if not allow_empty and len(value) == 0:
        return False
    return all(_nonempty_string(item) for item in value)


def _json_print(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    status = "ok" if payload.get("ok") else "blocked"
    print(f"status={status}")
    reasons = payload.get("reasons", [])
    if reasons:
        print("reasons=" + ",".join(str(reason) for reason in reasons))


def _exit_payload(ok: bool, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    payload["ok"] = ok
    return (0 if ok else 2, payload)


def _find_task_in_text(tasks_content: str, task_id: str) -> bool:
    pattern = re.compile(rf"^\s*-\s*\[[ xX]\]\s+{re.escape(task_id)}\b")
    for line in tasks_content.splitlines():
        if pattern.match(line):
            return True
    return False


def _find_task_in_tasks_file(tasks_file: Path, task_id: str) -> bool:
    return _find_task_in_text(tasks_file.read_text(encoding="utf-8"), task_id)


def _task_exists_on_main(tasks_file: Path, task_id: str) -> bool | None:
    """Return task presence from main branch tasks file, or None if unavailable."""
    repo_root = Path(__file__).resolve().parent.parent
    try:
        relative_tasks = tasks_file.resolve().relative_to(repo_root)
    except ValueError:
        return None

    result = subprocess.run(
        ["git", "show", f"main:{relative_tasks.as_posix()}"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return _find_task_in_text(result.stdout, task_id)


def _task_preflight(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    """Validate that implement-time artifacts exist before task execution begins."""
    feature_dir = Path(args.feature_dir).resolve()
    tasks_file = Path(args.tasks_file).resolve() if args.tasks_file else feature_dir / "tasks.md"
    hud_path = (
        Path(args.hud_path).resolve()
        if args.hud_path
        else feature_dir / "huds" / f"{args.task_id}.md"
    )
    hud_path = hud_path.resolve()
    reasons: list[str] = []
    task_present_in_tasks_file: bool | None = None
    task_present_in_main: bool | None = None

    if not feature_dir.exists():
        reasons.append("missing_feature_dir")
    if not tasks_file.exists():
        reasons.append("missing_tasks_md")
    if tasks_file.exists():
        task_present_in_tasks_file = _find_task_in_tasks_file(tasks_file, args.task_id)
        if not task_present_in_tasks_file:
            task_present_in_main = _task_exists_on_main(tasks_file, args.task_id)
            if task_present_in_main:
                reasons.append("feature_branch_stale")
            else:
                reasons.append("task_not_found_in_tasks_md")
    if not hud_path.exists():
        reasons.append("missing_hud")

    payload: dict[str, Any] = {
        "mode": "task_preflight",
        "feature_dir": str(feature_dir),
        "task_id": args.task_id,
        "tasks_file": str(tasks_file),
        "hud_path": str(hud_path),
        "task_present_in_tasks_file": task_present_in_tasks_file,
        "task_present_in_main": task_present_in_main,
        "reasons": reasons,
    }
    return _exit_payload(len(reasons) == 0, payload)


def _validate_test_runs(data: dict[str, Any], reasons: list[str], warnings: list[str]) -> None:
    test_runs = data.get("test_runs")
    legacy_test_commands = data.get("test_commands")

    if test_runs is None:
        if legacy_test_commands is None:
            reasons.append("missing_test_runs")
            return
        if not _string_list(legacy_test_commands, allow_empty=False):
            reasons.append("invalid_legacy_test_commands")
            return
        warnings.append("legacy_test_commands_used")
        return

    if not isinstance(test_runs, list) or len(test_runs) == 0:
        reasons.append("invalid_test_runs")
        return

    for idx, run in enumerate(test_runs):
        if not isinstance(run, dict):
            reasons.append(f"invalid_test_runs_item_{idx}")
            continue
        if not _nonempty_string(run.get("command")):
            reasons.append(f"invalid_test_runs_command_{idx}")
        if not isinstance(run.get("exit_code"), int):
            reasons.append(f"invalid_test_runs_exit_code_{idx}")
        if "output" in run and not isinstance(run.get("output"), str):
            reasons.append(f"invalid_test_runs_output_{idx}")


def _offline_qa_payload(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    payload_path = Path(args.payload_file).resolve()
    reasons: list[str] = []
    warnings: list[str] = []

    if not payload_path.exists():
        return _exit_payload(
            False,
            {
                "mode": "validate_offline_qa_payload",
                "payload_file": str(payload_path),
                "reasons": ["missing_payload_file"],
                "warnings": [],
            },
        )

    try:
        data = json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _exit_payload(
            False,
            {
                "mode": "validate_offline_qa_payload",
                "payload_file": str(payload_path),
                "reasons": ["invalid_payload_json"],
                "warnings": [],
            },
        )

    for field in ("feature_id", "task_id", "hud_path", "diff"):
        if not _nonempty_string(data.get(field)):
            reasons.append(f"invalid_{field}")

    if not _string_list(data.get("acceptance_criteria"), allow_empty=False):
        reasons.append("invalid_acceptance_criteria")
    if not _string_list(data.get("quality_guards"), allow_empty=False):
        reasons.append("invalid_quality_guards")
    if not _string_list(data.get("changed_files"), allow_empty=False):
        reasons.append("invalid_changed_files")
    if "known_risks" in data and not _string_list(data.get("known_risks"), allow_empty=True):
        reasons.append("invalid_known_risks")

    hud_path = Path(data.get("hud_path") or "")
    if _nonempty_string(data.get("hud_path")) and not hud_path.exists():
        reasons.append("missing_hud_path")

    _validate_test_runs(data, reasons, warnings)

    payload: dict[str, Any] = {
        "mode": "validate_offline_qa_payload",
        "payload_file": str(payload_path),
        "reasons": reasons,
        "warnings": warnings,
    }
    return _exit_payload(len(reasons) == 0, payload)


def _validate_task_evidence(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    reasons: list[str] = []
    task_kind = args.task_kind

    tests_passed = args.tests_passed == "pass"
    smoke_exit = args.smoke_exit
    live_check_exit = args.live_check_exit

    if not tests_passed:
        reasons.append("tests_not_passing")

    if task_kind == "module":
        if smoke_exit is None:
            reasons.append("missing_smoke_exit")
        elif smoke_exit != 0:
            reasons.append("smoke_check_failed")

    if task_kind == "integration":
        if live_check_exit is None:
            reasons.append("missing_live_check_exit")
        elif live_check_exit != 0:
            reasons.append("live_check_failed")

    for guard_name in (
        "state_safety",
        "transaction_integrity",
        "async_safety",
        "observability",
    ):
        value = getattr(args, guard_name)
        if value == "fail":
            reasons.append(f"{guard_name}_failed")

    payload: dict[str, Any] = {
        "mode": "validate_task_evidence",
        "task_kind": task_kind,
        "tests_passed": tests_passed,
        "smoke_exit": smoke_exit,
        "live_check_exit": live_check_exit,
        "state_safety": args.state_safety,
        "transaction_integrity": args.transaction_integrity,
        "async_safety": args.async_safety,
        "observability": args.observability,
        "reasons": reasons,
    }
    return _exit_payload(len(reasons) == 0, payload)


def _find_phase_window(tasks_file: Path, phase_name: str) -> tuple[int, int] | None:
    lines = tasks_file.read_text(encoding="utf-8").splitlines()
    start_idx: int | None = None
    normalized_target = phase_name.strip().lower()

    for idx, line in enumerate(lines):
        match = PHASE_HEADER_RE.match(line)
        if not match:
            continue
        title = match.group("title").strip()
        if title.lower() == normalized_target:
            start_idx = idx
            break
    if start_idx is None:
        return None

    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        if PHASE_HEADER_RE.match(lines[idx]):
            end_idx = idx
            break
    return (start_idx, end_idx)


def _count_open_tasks(lines: list[str]) -> list[str]:
    open_task_ids: list[str] = []
    for line in lines:
        match = TASK_LINE_RE.match(line)
        if not match:
            continue
        if match.group("state").strip() == "":
            open_task_ids.append(match.group("task_id"))
    return open_task_ids


def _find_matching_e2e_scripts(repo_root: Path, feature_dir: Path) -> list[str]:
    scripts_dir = repo_root / "scripts"
    feature_name = feature_dir.name
    normalized = feature_name.replace("-", "_")

    exact = scripts_dir / f"e2e_{normalized}.sh"
    if exact.exists():
        return [str(exact)]

    feature_id = feature_name.split("-", 1)[0]
    if feature_id.isdigit():
        matches = sorted(scripts_dir.glob(f"e2e_{feature_id}_*.sh"))
    else:
        matches = sorted(scripts_dir.glob(f"e2e_*{normalized}*.sh"))
    return [str(path) for path in matches]


def _phase_gate(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    feature_dir = Path(args.feature_dir).resolve()
    tasks_file = feature_dir / "tasks.md"
    reasons: list[str] = []

    if not feature_dir.exists():
        reasons.append("missing_feature_dir")
    if not tasks_file.exists():
        reasons.append("missing_tasks_md")
        return _exit_payload(
            False,
            {
                "mode": "phase_gate",
                "feature_dir": str(feature_dir),
                "phase_name": args.phase_name,
                "phase_type": args.phase_type,
                "reasons": reasons,
            },
        )

    window = _find_phase_window(tasks_file, args.phase_name)
    if window is None:
        reasons.append("phase_not_found")
        return _exit_payload(
            False,
            {
                "mode": "phase_gate",
                "feature_dir": str(feature_dir),
                "phase_name": args.phase_name,
                "phase_type": args.phase_type,
                "reasons": reasons,
            },
        )

    lines = tasks_file.read_text(encoding="utf-8").splitlines()
    start_idx, end_idx = window
    phase_lines = lines[start_idx + 1 : end_idx]
    open_task_ids = _count_open_tasks(phase_lines)
    if open_task_ids:
        reasons.append("open_tasks_in_phase")

    if args.layer1 != "pass":
        reasons.append("layer1_not_pass")
    if args.layer2 != "pass":
        reasons.append("layer2_not_pass")

    if args.phase_type == "story":
        if args.layer3 != "pass":
            reasons.append("layer3_not_pass_for_story_phase")
        e2e_doc = feature_dir / "e2e.md"
        e2e_scripts = _find_matching_e2e_scripts(Path(__file__).resolve().parent.parent, feature_dir)
        if not e2e_doc.exists():
            reasons.append("missing_e2e_md")
        if not e2e_scripts:
            reasons.append("missing_e2e_script")

    payload: dict[str, Any] = {
        "mode": "phase_gate",
        "feature_dir": str(feature_dir),
        "phase_name": args.phase_name,
        "phase_type": args.phase_type,
        "open_task_ids": open_task_ids,
        "layer1": args.layer1,
        "layer2": args.layer2,
        "layer3": args.layer3,
        "reasons": reasons,
    }
    return _exit_payload(len(reasons) == 0, payload)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    task_preflight = subparsers.add_parser(
        "task-preflight", help="Validate per-task prerequisites before coding."
    )
    task_preflight.add_argument("--feature-dir", required=True)
    task_preflight.add_argument("--task-id", required=True)
    task_preflight.add_argument("--tasks-file")
    task_preflight.add_argument("--hud-path")
    task_preflight.add_argument("--json", action="store_true")

    offline_payload = subparsers.add_parser(
        "validate-offline-qa-payload",
        help="Validate offline QA handoff payload schema and required fields.",
    )
    offline_payload.add_argument("--payload-file", required=True)
    offline_payload.add_argument("--json", action="store_true")

    task_evidence = subparsers.add_parser(
        "validate-task-evidence", help="Validate task evidence gates by task kind."
    )
    task_evidence.add_argument("--task-kind", choices=("logic", "module", "integration"), required=True)
    task_evidence.add_argument("--tests-passed", choices=("pass", "fail"), required=True)
    task_evidence.add_argument("--smoke-exit", type=int)
    task_evidence.add_argument("--live-check-exit", type=int)
    task_evidence.add_argument("--state-safety", choices=("pass", "fail", "na"), default="na")
    task_evidence.add_argument(
        "--transaction-integrity", choices=("pass", "fail", "na"), default="na"
    )
    task_evidence.add_argument("--async-safety", choices=("pass", "fail", "na"), default="na")
    task_evidence.add_argument("--observability", choices=("pass", "fail", "na"), default="na")
    task_evidence.add_argument("--json", action="store_true")

    phase_gate = subparsers.add_parser(
        "phase-gate", help="Validate phase-close gate layers and open tasks."
    )
    phase_gate.add_argument("--feature-dir", required=True)
    phase_gate.add_argument("--phase-name", required=True)
    phase_gate.add_argument("--phase-type", choices=("setup", "foundational", "story", "polish"), required=True)
    phase_gate.add_argument("--layer1", choices=("pass", "fail", "blocked"), required=True)
    phase_gate.add_argument("--layer2", choices=("pass", "fail", "blocked"), required=True)
    phase_gate.add_argument("--layer3", choices=("pass", "fail", "blocked", "na"), default="na")
    phase_gate.add_argument("--json", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute selected deterministic gate and return a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.subcommand == "task-preflight":
        exit_code, payload = _task_preflight(args)
    elif args.subcommand == "validate-offline-qa-payload":
        exit_code, payload = _offline_qa_payload(args)
    elif args.subcommand == "validate-task-evidence":
        exit_code, payload = _validate_task_evidence(args)
    elif args.subcommand == "phase-gate":
        exit_code, payload = _phase_gate(args)
    else:
        parser.error(f"Unknown subcommand: {args.subcommand}")
        return 2

    _json_print(payload, bool(getattr(args, "json", False)))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
