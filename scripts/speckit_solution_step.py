#!/usr/bin/env python3
"""Deterministic solution orchestrator for sketch -> tasking -> approval."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from bootstrap_session import bootstrap_session
from task_ledger import parse_task_definitions

SCHEMA_VERSION = "1.0.0"
DEFAULT_RUNNER = Path(__file__).resolve().parent / "speckit_codex_handoff_runner.py"
DEFAULT_PREREQUISITES = Path(__file__).resolve().parent.parent / ".specify" / "scripts" / "python" / "check_prerequisites.py"
DEFAULT_TASKING_CHAIN = Path(__file__).resolve().parent / "speckit_tasking_chain.py"
DEFAULT_TASKING_RUNNER = Path(__file__).resolve().parent / "speckit_tasking_codex_runner.py"
DEFAULT_TASKS_GATE = Path(__file__).resolve().parent / "speckit_tasks_gate.py"
DEFAULT_TASK_LEDGER = Path(__file__).resolve().parent / "task_ledger.py"
DEFAULT_HUDS = Path(__file__).resolve().parent / "speckit_remake_huds.py"
DEFAULT_ACCEPTANCE = Path(__file__).resolve().parent.parent / ".specify" / "scripts" / "acceptance-test-scaffold.py"
DEFAULT_PIPELINE_LEDGER = Path(__file__).resolve().parent / "pipeline_ledger.py"

TASKING_INSTRUCTIONS = """Decompose the approved plan.md design slices into tasks.md.
Anchor every non-[H] task to a concrete file/symbol seam from the slice.
Preserve ordering and dependencies from the plan's design-slice contract.
Keep the task descriptions implementation-usable and ready for estimate/breakdown stabilization.
Do not run estimate/breakdown, registration, HUD generation, or acceptance scaffolding here."""


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the solution orchestrator."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-id", required=True, help="Feature ID, e.g. 023")
    parser.add_argument("--phase", default="solution", help="Phase label for the top-level run")
    parser.add_argument("--correlation-id", required=True, help="Run-scoped correlation id")
    parser.add_argument("--json", action="store_true", help="Emit JSON result on stdout")
    return parser


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    input_payload: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command with captured output and deterministic environment inheritance."""
    return subprocess.run(
        command,
        cwd=cwd,
        input=input_payload,
        text=True,
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )


def _run_json_command(
    command: list[str],
    *,
    cwd: Path,
    input_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a command that emits JSON and return the parsed payload."""
    payload_text = json.dumps(input_payload, sort_keys=True) if input_payload is not None else None
    completed = _run_command(command, cwd=cwd, input_payload=payload_text)
    stdout = completed.stdout.strip()
    if completed.returncode != 0:
        raise RuntimeError(
            json.dumps(
                {
                    "command": command,
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                },
                sort_keys=True,
            )
        )
    if not stdout:
        return {}
    parsed = json.loads(stdout)
    if not isinstance(parsed, dict):
        raise RuntimeError("expected JSON object result")
    return parsed


def _load_prerequisites(repo_root: Path) -> dict[str, Any]:
    """Load the repo's feature workspace paths from the prerequisites helper."""
    completed = _run_command([sys.executable, str(DEFAULT_PREREQUISITES), "--json"], cwd=repo_root)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "check_prerequisites_failed")
    payload = json.loads(completed.stdout or "{}")
    if not isinstance(payload, dict):
        raise RuntimeError("invalid prerequisites payload")
    return payload


def _run_codex_action(
    *,
    repo_root: Path,
    feature_id: str,
    phase: str,
    correlation_id: str,
    task_action: str,
    feature_dir: Path,
    instructions: str,
    output_template_path: Path,
    completion_marker: str = "",
    resume_session: bool = False,
    retry_index: int = 0,
    qa_feedback: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the generic Codex action runner for one solution substep."""
    payload = {
        "feature_id": feature_id,
        "phase": phase,
        "correlation_id": correlation_id,
        "handoff": {
            "feature_dir": str(feature_dir),
            "repo_root": str(repo_root),
            "step_name": f"speckit.{phase}",
            "task_action": task_action,
            "output_template_path": str(output_template_path),
            "completion_marker": completion_marker,
            "instructions": instructions,
            "resume_session": resume_session,
            "retry_index": retry_index,
            "qa_feedback": dict(qa_feedback) if qa_feedback else None,
        },
    }
    completed = _run_command(
        [sys.executable, str(DEFAULT_RUNNER)],
        cwd=repo_root,
        input_payload=json.dumps(payload, sort_keys=True),
    )
    stdout = completed.stdout.strip()
    if completed.returncode != 0:
        raise RuntimeError(
            json.dumps(
                {
                    "command": [sys.executable, str(DEFAULT_RUNNER)],
                    "phase": phase,
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                },
                sort_keys=True,
            )
        )
    if not stdout:
        raise RuntimeError("codex runner produced no JSON result")
    parsed = json.loads(stdout)
    if not isinstance(parsed, dict):
        raise RuntimeError("codex runner result must be a JSON object")
    return parsed


def _append_pipeline_event(
    *,
    repo_root: Path,
    feature_id: str,
    phase: str,
    event: str,
    fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a pipeline event through the ledger CLI and return the parsed result."""
    command = [
        sys.executable,
        str(DEFAULT_PIPELINE_LEDGER),
        "append",
        "--feature-id",
        feature_id,
        "--phase",
        phase,
        "--event",
        event,
        "--actor",
        "solution_step",
    ]
    for key, value in (fields or {}).items():
        if value is None:
            continue
        option = f"--{key.replace('_', '-')}"
        command.extend([option, str(value)])
    completed = _run_command(command, cwd=repo_root)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"pipeline append failed for {event}")
    return {"ok": True, "stdout": completed.stdout, "stderr": completed.stderr}


def _run_tasking_stabilization(
    *,
    repo_root: Path,
    feature_dir: Path,
    json_mode: bool = True,
) -> dict[str, Any]:
    """Run the tasking estimate/breakdown stabilization chain."""
    estimate_command = (
        f"{sys.executable} {DEFAULT_TASKING_RUNNER} --mode estimate --feature-dir {feature_dir!s} --json"
    )
    breakdown_command = (
        f"{sys.executable} {DEFAULT_TASKING_RUNNER} --mode breakdown --feature-dir {feature_dir!s} --json"
    )
    command = [
        sys.executable,
        str(DEFAULT_TASKING_CHAIN),
        "--feature-dir",
        str(feature_dir),
        "--estimate-command",
        estimate_command,
        "--breakdown-command",
        breakdown_command,
    ]
    if json_mode:
        command.append("--json")
    completed = _run_command(command, cwd=repo_root)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "tasking_chain_failed")
    parsed = json.loads(completed.stdout or "{}")
    if not isinstance(parsed, dict):
        raise RuntimeError("tasking chain must return JSON")
    return parsed


def _run_tasks_gate(*, repo_root: Path, feature_dir: Path) -> dict[str, Any]:
    """Run the deterministic task-format gate."""
    command = [
        sys.executable,
        str(DEFAULT_TASKS_GATE),
        "validate-format",
        "--tasks-file",
        str(feature_dir / "tasks.md"),
        "--json",
    ]
    completed = _run_command(command, cwd=repo_root)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "tasks_gate_failed")
    parsed = json.loads(completed.stdout or "{}")
    if not isinstance(parsed, dict):
        raise RuntimeError("tasks gate must return JSON")
    return parsed


def _register_tasks(*, repo_root: Path, feature_dir: Path, feature_id: str) -> dict[str, Any]:
    """Register missing tasks in the task ledger."""
    command = [
        sys.executable,
        str(DEFAULT_TASK_LEDGER),
        "register",
        "--tasks-file",
        str(feature_dir / "tasks.md"),
        "--feature-id",
        feature_id,
        "--json",
    ]
    completed = _run_command(command, cwd=repo_root)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "task_registration_failed")
    parsed = json.loads(completed.stdout or "{}")
    if not isinstance(parsed, dict):
        raise RuntimeError("task registration must return JSON")
    return parsed


def _generate_huds(*, repo_root: Path, feature_dir: Path) -> dict[str, Any]:
    """Generate or refresh task HUD artifacts from the settled task graph."""
    command = [
        sys.executable,
        str(DEFAULT_HUDS),
        "--feature-dir",
        str(feature_dir),
    ]
    completed = _run_command(command, cwd=repo_root)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "hud_generation_failed")
    return {"stdout": completed.stdout, "stderr": completed.stderr}


def _generate_acceptance_tests(*, repo_root: Path, feature_dir: Path) -> dict[str, Any]:
    """Generate acceptance test scaffolding from tasks.md."""
    command = [
        sys.executable,
        str(DEFAULT_ACCEPTANCE),
        "--tasks-file",
        str(feature_dir / "tasks.md"),
    ]
    completed = _run_command(command, cwd=repo_root)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "acceptance_scaffold_failed")
    return {"stdout": completed.stdout, "stderr": completed.stderr}


def _count_stories(tasks_file: Path) -> int:
    """Count the story sections in tasks.md."""
    story_heading = re.compile(r"^##\s+.*User Story\b", re.IGNORECASE)
    count = 0
    for line in tasks_file.read_text(encoding="utf-8").splitlines():
        if story_heading.match(line):
            count += 1
    return count


def _estimate_points(estimates_file: Path) -> int:
    """Extract total settled estimate points from estimates.md."""
    content = estimates_file.read_text(encoding="utf-8")
    total_match = re.search(r"\*\*Total Points\*\*:\s*(\d+)", content)
    if total_match:
        return int(total_match.group(1))
    row_total = 0
    for line in content.splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) < 4 or not cells[1].startswith("T"):
            continue
        try:
            row_total += int(cells[2])
        except ValueError:
            continue
    return row_total


def _stage_and_commit(repo_root: Path, commit_message: str) -> dict[str, Any]:
    """Commit all pending solution-step changes with a deterministic Git identity."""
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "speckit")
    env.setdefault("GIT_AUTHOR_EMAIL", "speckit@example.com")
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])

    add_run = subprocess.run(["git", "add", "-A"], cwd=repo_root, text=True, capture_output=True, check=False, env=env)
    if add_run.returncode != 0:
        raise RuntimeError(add_run.stderr.strip() or "git_add_failed")

    diff_run = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if diff_run.returncode != 0:
        raise RuntimeError(diff_run.stderr.strip() or "git_diff_failed")

    changed_files = [line.strip() for line in diff_run.stdout.splitlines() if line.strip()]
    if not changed_files:
        return {"commit_sha": None, "changed_files": []}

    commit_run = subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if commit_run.returncode != 0:
        raise RuntimeError(commit_run.stderr.strip() or "git_commit_failed")

    sha_run = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if sha_run.returncode != 0:
        raise RuntimeError(sha_run.stderr.strip() or "git_rev_parse_failed")
    return {"commit_sha": sha_run.stdout.strip(), "changed_files": changed_files}


def _write_debug_payload(path: Path, payload: Mapping[str, Any]) -> None:
    """Write the solution-run debug payload to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _validate_plan_design_slices(plan_path: Path) -> None:
    """Require tasking-ready design slices from the combined plan artifact."""
    if not plan_path.is_file():
        raise RuntimeError("plan_artifact_missing")
    text = plan_path.read_text(encoding="utf-8")
    if "## Design Slices" not in text:
        raise RuntimeError("plan_design_slices_missing")
    if "Implementation Directive" not in text:
        raise RuntimeError("plan_implementation_directive_missing")


def orchestrate_solution(feature_id: str, correlation_id: str, *, phase: str) -> dict[str, Any]:
    """Run the solution ladder from plan design slices through tasking and approval."""
    repo_root = Path(__file__).resolve().parent.parent
    bootstrap_summary = bootstrap_session(repo_root)
    if not bootstrap_summary["bootstrap_ok"]:
        raise RuntimeError(bootstrap_summary["codegraph_detail"] or "session bootstrap failed")
    prereq_payload = _load_prerequisites(repo_root)
    feature_dir = Path(prereq_payload["FEATURE_DIR"])
    plan_path = feature_dir / "plan.md"
    tasks_path = feature_dir / "tasks.md"
    estimates_path = feature_dir / "estimates.md"
    debug_path = repo_root / ".speckit" / "runtime" / "solution" / f"{correlation_id}.json"

    stages: list[dict[str, Any]] = []

    _validate_plan_design_slices(plan_path)

    tasking_result = _run_codex_action(
        repo_root=repo_root,
        feature_id=feature_id,
        phase="tasking",
        correlation_id=f"{correlation_id}:tasking",
        task_action="decompose_tasks",
        feature_dir=feature_dir,
        instructions=TASKING_INSTRUCTIONS,
        output_template_path=tasks_path,
        resume_session=True,
        retry_index=1,
    )
    stages.append({"stage": "tasking", "result": tasking_result})
    if not bool(tasking_result.get("ok", False)):
        raise RuntimeError("tasking_decomposition_failed")
    if not tasks_path.exists():
        raise RuntimeError("tasks_artifact_missing")

    tasking_chain = _run_tasking_stabilization(repo_root=repo_root, feature_dir=feature_dir)
    stages.append({"stage": "tasking_chain", "result": tasking_chain})
    if not bool(tasking_chain.get("ok", False)):
        raise RuntimeError("tasking_stabilization_failed")

    tasks_gate = _run_tasks_gate(repo_root=repo_root, feature_dir=feature_dir)
    stages.append({"stage": "tasks_gate", "result": tasks_gate})
    if not bool(tasks_gate.get("ok", False)):
        raise RuntimeError("tasks_format_gate_failed")

    registration = _register_tasks(repo_root=repo_root, feature_dir=feature_dir, feature_id=feature_id)
    stages.append({"stage": "task_registration", "result": registration})

    huds = _generate_huds(repo_root=repo_root, feature_dir=feature_dir)
    stages.append({"stage": "huds", "result": huds})

    acceptance = _generate_acceptance_tests(repo_root=repo_root, feature_dir=feature_dir)
    stages.append({"stage": "acceptance", "result": acceptance})

    task_count = len(parse_task_definitions(tasks_path))
    story_count = _count_stories(tasks_path)
    estimate_points = _estimate_points(estimates_path) if estimates_path.exists() else 0

    _append_pipeline_event(
        repo_root=repo_root,
        feature_id=feature_id,
        phase="tasking",
        event="tasking_completed",
        fields={"task_count": task_count, "story_count": story_count},
    )
    _append_pipeline_event(
        repo_root=repo_root,
        feature_id=feature_id,
        phase="solution",
        event="solution_approved",
        fields={
            "task_count": task_count,
            "story_count": story_count,
            "estimate_points": estimate_points,
        },
    )

    commit_result = _stage_and_commit(repo_root, f"speckit.solution {feature_id}")
    stages.append({"stage": "commit", "result": commit_result})

    result = {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "exit_code": 0,
        "correlation_id": correlation_id,
        "next_phase": "implement",
        "gate": None,
        "reasons": [],
        "error_code": None,
        "debug_path": str(debug_path),
        "feature_dir": str(feature_dir),
        "plan_artifact": str(plan_path),
        "tasks_artifact": str(tasks_path),
        "task_count": task_count,
        "story_count": story_count,
        "estimate_points": estimate_points,
        "stages": stages,
        "commit_sha": commit_result.get("commit_sha"),
    }
    _write_debug_payload(debug_path, result)
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for deterministic solution orchestration."""
    args = _build_parser().parse_args(argv)
    try:
        result = orchestrate_solution(args.feature_id, args.correlation_id, phase=args.phase)
    except Exception as exc:  # noqa: BLE001
        repo_root = Path(__file__).resolve().parent.parent
        debug_path = repo_root / ".speckit" / "runtime" / "solution" / f"{args.correlation_id}.json"
        failure = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "exit_code": 2,
            "correlation_id": args.correlation_id,
            "gate": "solution_orchestration",
            "reasons": [str(exc) or "solution_orchestration_failed"],
            "error_code": "solution_orchestration_failed",
            "next_phase": None,
            "debug_path": str(debug_path),
        }
        _write_debug_payload(debug_path, failure)
        print(json.dumps(failure, sort_keys=True))
        return 2

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
