#!/usr/bin/env python3
"""Scaffold and finalize the generative solution phase from plan design slices."""

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
DEFAULT_TASKING_CHAIN = Path(__file__).resolve().parent / "speckit_tasking_chain.py"
DEFAULT_TASKING_RUNNER = Path(__file__).resolve().parent / "speckit_tasking_codex_runner.py"
DEFAULT_TASKS_GATE = Path(__file__).resolve().parent / "speckit_tasks_gate.py"
DEFAULT_TASK_LEDGER = Path(__file__).resolve().parent / "task_ledger.py"
DEFAULT_HUDS = Path(__file__).resolve().parent / "speckit_remake_huds.py"
DEFAULT_ACCEPTANCE = (
    Path(__file__).resolve().parent.parent / ".specify" / "scripts" / "acceptance-test-scaffold.py"
)
DEFAULT_TASKS_TEMPLATE = Path(__file__).resolve().parent.parent / ".specify" / "templates" / "tasks-template.md"
DEFAULT_SPEC_ARTIFACT = "spec.json"
LEGACY_ROUTING_ARTIFACT = "routing.json"


def _build_command_parser() -> argparse.ArgumentParser:
    """Build the subcommand parser for scaffold and finalize operations."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser(
        "prepare-tasking",
        help="Validate plan.md and scaffold tasks.md for the generative solution command",
    )
    prepare.add_argument("--feature-id", required=True, help="Feature ID, e.g. 023")
    prepare.add_argument("--json", action="store_true", help="Emit JSON result on stdout")

    finalize = subparsers.add_parser(
        "finalize",
        help="Validate tasks.md, run deterministic stabilization, and emit the event request envelope",
    )
    finalize.add_argument("--feature-id", required=True, help="Feature ID, e.g. 023")
    finalize.add_argument("--phase", default="solution", help="Phase label for runtime result storage")
    finalize.add_argument("--correlation-id", required=True, help="Run-scoped correlation id")
    finalize.add_argument("--json", action="store_true", help="Emit JSON result on stdout")
    return parser


def _build_legacy_parser() -> argparse.ArgumentParser:
    """Preserve the legacy finalize-style CLI for direct callers and older tests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-id", required=True, help="Feature ID, e.g. 023")
    parser.add_argument("--phase", default="solution", help="Phase label for runtime result storage")
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


def _resolve_feature_dir(repo_root: Path, feature_id: str) -> Path:
    """Resolve the feature directory directly from specs/ without branch gating."""
    matches = sorted((repo_root / "specs").glob(f"{feature_id}-*"))
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise RuntimeError(f"feature_dir_missing:{feature_id}")
    raise RuntimeError(f"feature_dir_ambiguous:{feature_id}")


def _resolve_solution_paths(feature_id: str) -> tuple[Path, Path, Path]:
    """Resolve repo, feature, and artifact paths for the requested feature id."""
    repo_root = Path(__file__).resolve().parent.parent
    feature_dir = _resolve_feature_dir(repo_root, feature_id)
    return repo_root, feature_dir, feature_dir / "plan.md"


def _resolve_spec_artifact(feature_dir: Path) -> Path:
    """Return the stable plan-produced spec-details artifact path."""
    spec_path = feature_dir / DEFAULT_SPEC_ARTIFACT
    if spec_path.exists():
        return spec_path
    return feature_dir / LEGACY_ROUTING_ARTIFACT


def _runtime_result_path(phase: str, correlation_id: str) -> Path:
    """Return the runtime result path for a finalized solution run."""
    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / ".speckit" / "runtime" / phase / f"{correlation_id}.json"


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


def _extract_design_slice_labels(plan_path: Path) -> list[str]:
    """Extract design-slice labels to seed the tasks scaffold with plan context."""
    text = plan_path.read_text(encoding="utf-8")
    match = re.search(
        r"^## Design Slices\s*$([\s\S]*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE,
    )
    if not match:
        return []
    section = match.group(1)
    labels = re.findall(r"^###\s+(.+?)\s*$", section, re.MULTILINE)
    return [label.strip() for label in labels if label.strip()]


def _feature_display_name(feature_dir: Path) -> str:
    """Convert the feature directory name into a human-readable feature title."""
    slug = feature_dir.name.split("-", 1)[1] if "-" in feature_dir.name else feature_dir.name
    return slug.replace("-", " ")


def _render_tasks_scaffold(feature_dir: Path, plan_path: Path) -> str:
    """Render the initial tasks.md scaffold from the documented template."""
    template = DEFAULT_TASKS_TEMPLATE.read_text(encoding="utf-8")
    feature_name = _feature_display_name(feature_dir)
    feature_slug = feature_dir.name
    rendered = template.replace("[FEATURE NAME]", feature_name)
    rendered = rendered.replace("/specs/[###-feature-name]/", f"/specs/{feature_slug}/")
    rendered = rendered.replace(
        "plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/",
        "plan.md (required), spec.md (required for user stories)",
    )
    rendered = rendered.replace(
        "Generate `tasks.md` from an approved `sketch.md`",
        "Generate `tasks.md` from an approved `plan.md` design-slice set",
    )
    slice_labels = _extract_design_slice_labels(plan_path)
    if not slice_labels:
        return rendered
    slice_block = "\n".join(f"- {label}" for label in slice_labels)
    return (
        f"{rendered}\n\n## Plan Design Slice Index\n\n"
        "Use these plan slices as the authoritative tasking inputs:\n\n"
        f"{slice_block}\n"
    )


def prepare_tasking(feature_id: str) -> dict[str, Any]:
    """Validate the plan artifact and scaffold tasks.md for generative completion."""
    repo_root, feature_dir, plan_path = _resolve_solution_paths(feature_id)
    tasks_path = feature_dir / "tasks.md"
    spec_path = _resolve_spec_artifact(feature_dir)
    _validate_plan_design_slices(plan_path)
    if not spec_path.is_file():
        raise RuntimeError("spec_artifact_missing")
    tasks_path.write_text(_render_tasks_scaffold(feature_dir, plan_path), encoding="utf-8")
    return {
        "ok": True,
        "feature_dir": str(feature_dir),
        "plan_artifact": str(plan_path),
        "spec_artifact": str(spec_path),
        "tasks_artifact": str(tasks_path),
        "scaffolded_from_template": str(DEFAULT_TASKS_TEMPLATE),
        "repo_root": str(repo_root),
    }


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


def _validate_huds(*, repo_root: Path, feature_dir: Path) -> dict[str, Any]:
    """Validate completed task HUD artifacts before task registration handoff."""
    command = [
        sys.executable,
        str(DEFAULT_HUDS),
        "validate",
        "--feature-dir",
        str(feature_dir),
        "--json",
    ]
    completed = _run_command(command, cwd=repo_root)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "hud_validation_failed")
    parsed = json.loads(completed.stdout or "{}")
    if not isinstance(parsed, dict):
        raise RuntimeError("hud validation must return JSON")
    return parsed


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


def _validate_tasks_artifact(tasks_path: Path) -> None:
    """Require a tasks artifact before deterministic stabilization can begin."""
    if not tasks_path.is_file():
        raise RuntimeError("tasks_artifact_missing")


def _event_request(*, task_count: int, story_count: int, estimate_points: int) -> dict[str, Any]:
    """Build the driver-owned solution event request payload."""
    return {
        "event": "solution_approved",
        "fields": {
            "task_count": task_count,
            "story_count": story_count,
            "estimate_points": estimate_points,
        },
    }


def _load_spec_details(feature_dir: Path) -> dict[str, Any]:
    """Load the stable spec.json artifact produced by the plan phase."""
    spec_path = _resolve_spec_artifact(feature_dir)
    if not spec_path.is_file():
        return {}
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def finalize_solution(feature_id: str, correlation_id: str, *, phase: str = "solution") -> dict[str, Any]:
    """Validate, stabilize, and finalize the generative solution artifact set."""
    repo_root, feature_dir, plan_path = _resolve_solution_paths(feature_id)
    bootstrap_summary = bootstrap_session(repo_root)
    if not bootstrap_summary["bootstrap_ok"]:
        raise RuntimeError(bootstrap_summary["codegraph_detail"] or "session bootstrap failed")

    tasks_path = feature_dir / "tasks.md"
    estimates_path = feature_dir / "estimates.md"
    debug_path = _runtime_result_path(phase, correlation_id)

    _validate_plan_design_slices(plan_path)
    _validate_tasks_artifact(tasks_path)

    stages: list[dict[str, Any]] = []

    tasking_chain = _run_tasking_stabilization(repo_root=repo_root, feature_dir=feature_dir)
    stages.append({"stage": "tasking_chain", "result": tasking_chain})
    if not bool(tasking_chain.get("ok", False)):
        raise RuntimeError("tasking_stabilization_failed")

    tasks_gate = _run_tasks_gate(repo_root=repo_root, feature_dir=feature_dir)
    stages.append({"stage": "tasks_gate", "result": tasks_gate})
    if not bool(tasks_gate.get("ok", False)):
        raise RuntimeError("tasks_format_gate_failed")

    huds = _validate_huds(repo_root=repo_root, feature_dir=feature_dir)
    stages.append({"stage": "huds_validate", "result": huds})
    if not bool(huds.get("ok", False)):
        raise RuntimeError("hud_validation_failed")

    registration = _register_tasks(repo_root=repo_root, feature_dir=feature_dir, feature_id=feature_id)
    stages.append({"stage": "task_registration", "result": registration})

    acceptance = _generate_acceptance_tests(repo_root=repo_root, feature_dir=feature_dir)
    stages.append({"stage": "acceptance", "result": acceptance})

    task_count = len(parse_task_definitions(tasks_path))
    story_count = _count_stories(tasks_path)
    estimate_points = _estimate_points(estimates_path) if estimates_path.exists() else 0
    spec_details = _load_spec_details(feature_dir)

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
        "spec_artifact": str(_resolve_spec_artifact(feature_dir)),
        "tasks_artifact": str(tasks_path),
        "task_count": task_count,
        "story_count": story_count,
        "estimate_points": estimate_points,
        "stages": stages,
        "pipeline_event_request": _event_request(
            task_count=task_count,
            story_count=story_count,
            estimate_points=estimate_points,
        ),
    }
    result["pipeline_event_request"]["fields"].update(
        {
            "routing": dict(spec_details.get("routing", {})),
            "triage": dict(spec_details.get("triage", {})),
            "risk": dict(spec_details.get("risk", {})),
            "domains": dict(spec_details.get("domains", {})),
            "strategy": dict(spec_details.get("strategy", {})),
            "design_slices": list(spec_details.get("design_slices", [])),
            "spec_json_path": str(_resolve_spec_artifact(feature_dir)),
        }
    )
    _write_debug_payload(debug_path, result)
    return result


def orchestrate_solution(feature_id: str, correlation_id: str, *, phase: str) -> dict[str, Any]:
    """Preserve the legacy entrypoint name while delegating to finalize_solution."""
    return finalize_solution(feature_id, correlation_id, phase=phase)


def main(argv: list[str] | None = None) -> int:
    """Dispatch scaffold/finalize subcommands and preserve the legacy finalize CLI."""
    args_list = list(argv) if argv is not None else sys.argv[1:]
    if args_list and args_list[0] in {"prepare-tasking", "finalize"}:
        args = _build_command_parser().parse_args(args_list)
        if args.command == "prepare-tasking":
            result = prepare_tasking(args.feature_id)
        else:
            result = finalize_solution(args.feature_id, args.correlation_id, phase=args.phase)
        if args.json:
            print(json.dumps(result, sort_keys=True))
        return 0

    args = _build_legacy_parser().parse_args(args_list)
    result = finalize_solution(args.feature_id, args.correlation_id, phase=args.phase)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    return int(result.get("exit_code", 1))


if __name__ == "__main__":
    raise SystemExit(main())
