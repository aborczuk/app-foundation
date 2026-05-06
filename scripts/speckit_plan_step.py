#!/usr/bin/env python3
"""Combined speckit plan step with triage, research, plan, and design slices."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "1.0.0"
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from bootstrap_session import bootstrap_session  # noqa: E402

DEFAULT_RUNNER = Path(__file__).resolve().parent / "speckit_codex_handoff_runner.py"
DEFAULT_SCAFFOLD = REPO_ROOT / ".specify" / "scripts" / "pipeline-scaffold.py"
PLAN_COMPLETION_MARKER = "Plan Completion Summary"
DISCOVERY_MAX_TERMS = 5
FILE_PATH_RE = re.compile(r"^file_path:\s*(?P<path>.+)$", re.MULTILINE)
JSON_FENCE_RE = re.compile(r"```json\s*(?P<body>.*?)```", re.IGNORECASE | re.DOTALL)
ALLOWED_TSHIRT_SIZES = {"xs", "s", "m", "l", "xl"}
STOP_WORDS = {
    "a",
    "an",
    "and",
    "app",
    "as",
    "at",
    "build",
    "browser",
    "feature",
    "for",
    "from",
    "game",
    "into",
    "make",
    "of",
    "on",
    "or",
    "playable",
    "the",
    "to",
    "up",
    "with",
}


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the combined plan step."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-id", required=True, help="Feature ID, e.g. 023")
    parser.add_argument("--phase", default="plan", help="Phase label for the top-level run")
    parser.add_argument("--correlation-id", required=True, help="Run-scoped correlation id")
    parser.add_argument("--handoff-runner", default=None, help="Optional Codex handoff runner path")
    parser.add_argument("--json", action="store_true", help="Emit JSON result on stdout")
    return parser


def _build_uv_env() -> dict[str, str]:
    """Return the repo-local environment for plan discovery workflows."""
    from uv_env import repo_uv_env

    os.environ.update(repo_uv_env())
    return os.environ.copy()


def _feature_dir_candidates(feature_id: str) -> list[Path]:
    """Return candidate feature directories for an exact or numeric feature id."""
    specs_dir = REPO_ROOT / "specs"
    if not specs_dir.is_dir():
        return []
    exact = specs_dir / feature_id
    if exact.is_dir():
        return [exact]
    prefix_match = re.match(r"^(?P<prefix>\d+)", feature_id.strip())
    if not prefix_match:
        return []
    prefix = prefix_match.group("prefix")
    candidates = [
        path
        for path in specs_dir.iterdir()
        if path.is_dir() and (path.name == prefix or path.name.startswith(f"{prefix}-"))
    ]
    return sorted(candidates, key=lambda path: path.name)


def _resolve_feature_paths(feature_id: str) -> tuple[Path, Path, Path]:
    """Resolve the feature directory, spec file, and combined plan file."""
    candidates = _feature_dir_candidates(feature_id)
    if not candidates:
        raise RuntimeError(f"feature_dir_not_found:{feature_id}")
    feature_dir = candidates[0].resolve()
    spec_file = feature_dir / "spec.md"
    if not spec_file.is_file():
        raise RuntimeError(f"spec_file_not_found:{spec_file}")
    return feature_dir, spec_file.resolve(), (feature_dir / "plan.md").resolve()


def _load_spec_description(spec_file: Path) -> str:
    """Load the spec text used for triage and planning context."""
    return spec_file.read_text(encoding="utf-8").strip()


def _extract_terms(description: str) -> list[str]:
    """Derive compact code-discovery terms from the spec text."""
    terms: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]*", description):
        normalized = token.strip("-").lower()
        if len(normalized) < 3 or normalized in STOP_WORDS:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        terms.append(normalized)
        if len(terms) >= DISCOVERY_MAX_TERMS:
            break
    return terms or ["feature"]


def _run_uv_command(command: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run a repo-local command with captured output."""
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def _run_discovery(terms: list[str], env: dict[str, str]) -> list[dict[str, Any]]:
    """Run bounded internal discovery through read_code context lookups."""
    def lookup(term: str) -> dict[str, Any]:
        completed = _run_uv_command(
            ["uv", "run", "python", "scripts/read_code.py", "context", term],
            env=env,
        )
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        return {
            "term": term,
            "exit_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "has_matches": completed.returncode == 0 and "No context found" not in stdout,
        }

    with ThreadPoolExecutor(max_workers=min(len(terms), DISCOVERY_MAX_TERMS)) as executor:
        return list(executor.map(lookup, terms))


def _extract_file_paths(output: str) -> list[str]:
    """Extract file paths from read_code output blocks."""
    return [match.group("path").strip() for match in FILE_PATH_RE.finditer(output)]


def _render_discovery_result(result: Mapping[str, Any]) -> str:
    """Render one discovery result for inclusion inside plan.md."""
    term = str(result.get("term") or "unknown")
    stdout = str(result.get("stdout") or "").strip()
    stderr = str(result.get("stderr") or "").strip()
    paths = _extract_file_paths("\n".join([stdout, stderr]))
    lines = [
        f"### Term: {term}",
        "",
        f"- matches: {str(bool(result.get('has_matches'))).lower()}",
        f"- exit_code: {int(result.get('exit_code') or 0)}",
    ]
    if paths:
        lines.append("- files:")
        lines.extend(f"  - `{path}`" for path in paths[:10])
    if stderr:
        lines.extend(["", "stderr:", "```text", stderr[:2000], "```"])
    if stdout and not paths:
        lines.extend(["", "stdout:", "```text", stdout[:2000], "```"])
    return "\n".join(lines).strip()


def _scaffold_manifest_plan(feature_dir: Path) -> None:
    """Create the manifest-declared plan artifact before plan filling begins."""
    completed = _run_uv_command(
        [
            "uv",
            "run",
            "python",
            str(DEFAULT_SCAFFOLD.relative_to(REPO_ROOT)),
            "speckit.plan",
            "--feature-dir",
            str(feature_dir),
            f"FEATURE_NAME={feature_dir.name}",
        ],
        env=_build_uv_env(),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            json.dumps(
                {
                    "error": "plan_scaffold_failed",
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                },
                sort_keys=True,
            )
        )


def _write_triage_scaffold(
    *,
    feature_id: str,
    feature_dir: Path,
    spec_file: Path,
    plan_file: Path,
    discovery: list[dict[str, Any]],
) -> None:
    """Write the initial combined plan scaffold used for generative triage."""
    discovery_body = "\n\n".join(_render_discovery_result(result) for result in discovery)
    plan_file.write_text(
        "\n".join(
            [
                f"# Combined Plan - {feature_dir.name}",
                "",
                f"_Feature: `{feature_id}`_",
                f"_Source Spec: `{spec_file.name}`_",
                "_Artifact: `plan.md`_",
                "",
                "## Triage",
                "",
                "- duplicate: [true/false]",
                "- t_shirt_size: [xs/s/m/l/xl]",
                "- risk_level: [low/medium/high]",
                "- reason: [Generative decision based on spec and discovery.]",
                "",
                "## Routing Contract",
                "",
                "```json",
                json.dumps(
                    {
                        "triage": {
                            "duplicate": False,
                            "duplicate_reason": "",
                            "duplicate_matches": [],
                            "tshirt_size": "",
                            "risk_level": "",
                        },
                        "routing": {
                            "plan_level": "",
                            "sketch_level": "",
                            "external_research": False,
                            "architecture_diagram": False,
                            "routing_reason": "",
                        },
                        "risk": {
                            "requirement_clarity": "",
                            "repo_uncertainty": "",
                            "external_dependency_uncertainty": "",
                            "state_data_migration_risk": "",
                            "runtime_side_effect_risk": "",
                            "human_operator_dependency": "",
                        },
                    },
                    indent=2,
                    sort_keys=True,
                ),
                "```",
                "",
                "## Internal Discovery",
                "",
                discovery_body or "- No internal discovery results recorded.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _extract_contract(plan_file: Path) -> dict[str, Any]:
    """Load the combined routing contract from plan.md."""
    text = plan_file.read_text(encoding="utf-8")
    for match in JSON_FENCE_RE.finditer(text):
        try:
            payload = json.loads(match.group("body"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("triage"), dict):
            return payload
    raise RuntimeError("combined_plan_contract_missing")


def _normalize_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the generative triage contract into stable values."""
    triage_raw = contract.get("triage", {})
    routing_raw = contract.get("routing", {})
    risk_raw = contract.get("risk", {})
    triage = dict(triage_raw) if isinstance(triage_raw, Mapping) else {}
    routing = dict(routing_raw) if isinstance(routing_raw, Mapping) else {}
    risk = dict(risk_raw) if isinstance(risk_raw, Mapping) else {}
    tshirt_size = str(triage.get("tshirt_size") or "").strip().lower()
    if tshirt_size and tshirt_size not in ALLOWED_TSHIRT_SIZES:
        raise RuntimeError(f"invalid_tshirt_size:{tshirt_size}")
    return {
        "triage": {
            "duplicate": bool(triage.get("duplicate", False)),
            "duplicate_reason": str(triage.get("duplicate_reason") or "").strip(),
            "duplicate_matches": list(triage.get("duplicate_matches") or []),
            "tshirt_size": tshirt_size,
            "risk_level": str(triage.get("risk_level") or "").strip().lower(),
        },
        "routing": {
            "plan_level": str(routing.get("plan_level") or "").strip().lower(),
            "sketch_level": str(routing.get("sketch_level") or "").strip().lower(),
            "external_research": bool(routing.get("external_research", False)),
            "architecture_diagram": bool(routing.get("architecture_diagram", False)),
            "routing_reason": str(routing.get("routing_reason") or "").strip(),
        },
        "risk": {str(key): str(value).strip().lower() for key, value in risk.items()},
    }


def _selected_sections(contract: Mapping[str, Any]) -> list[str]:
    """Return the plan sections required by the triage routing decision."""
    routing = contract.get("routing", {})
    triage = contract.get("triage", {})
    plan_level = str(routing.get("plan_level") or "").strip().lower()
    sketch_level = str(routing.get("sketch_level") or "").strip().lower()
    sections = ["Summary", "Internal Research", "Design Slices", "Plan Completion Summary"]
    if bool(routing.get("external_research")) or plan_level == "comprehensive":
        sections.insert(2, "External Research")
    if bool(routing.get("architecture_diagram")) or plan_level == "comprehensive":
        insert_at = sections.index("Design Slices")
        sections[insert_at:insert_at] = ["Architecture Plan", "Architecture Diagram"]
    if sketch_level == "expanded" or str(triage.get("risk_level") or "") == "high":
        sections.insert(sections.index("Design Slices"), "Expanded Design Notes")
    return list(dict.fromkeys(sections))


def _render_contract(contract: Mapping[str, Any]) -> str:
    """Render the combined routing contract as formatted JSON."""
    return json.dumps(dict(contract), indent=2, sort_keys=True)


def _write_selected_scaffold(
    *,
    feature_id: str,
    feature_dir: Path,
    spec_file: Path,
    plan_file: Path,
    discovery: list[dict[str, Any]],
    contract: Mapping[str, Any],
) -> None:
    """Rewrite plan.md with only the sections selected by triage."""
    sections = _selected_sections(contract)
    triage = contract.get("triage", {})
    discovery_body = "\n\n".join(_render_discovery_result(result) for result in discovery)
    body = [
        f"# Combined Plan - {feature_dir.name}",
        "",
        f"_Feature: `{feature_id}`_",
        f"_Source Spec: `{spec_file.name}`_",
        "_Artifact: `plan.md`_",
        "",
        "## Triage",
        "",
        f"- duplicate: {str(bool(triage.get('duplicate'))).lower()}",
        f"- t_shirt_size: {triage.get('tshirt_size') or ''}",
        f"- risk_level: {triage.get('risk_level') or ''}",
        f"- reason: {triage.get('duplicate_reason') or contract.get('routing', {}).get('routing_reason') or ''}",
        "",
        "## Routing Contract",
        "",
        "```json",
        _render_contract(contract),
        "```",
        "",
        "## Internal Discovery",
        "",
        discovery_body or "- No internal discovery results recorded.",
        "",
    ]
    for section in sections:
        body.extend([f"## {section}", "", "[Fill this section from the spec, discovery, and triage contract.]", ""])
    plan_file.write_text("\n".join(body), encoding="utf-8")


def _build_triage_instructions(spec_text: str, discovery: list[dict[str, Any]]) -> str:
    """Build the generative instructions for duplicate, LOE, and risk triage."""
    discovery_summary = json.dumps(discovery, indent=2, sort_keys=True)
    return f"""
You are executing the first half of speckit.plan.

Edit only FEATURE_DIR/plan.md.
First decide whether the requested spec already exists in this codebase.
If it is a duplicate, mark triage.duplicate=true, cite the matching spec or code paths, and do not add plan/design sections.
If it is not a duplicate, assign t-shirt size generatively from the requested behavior, repo discovery, likely blast radius, risk, and uncertainty.
Do not infer t-shirt size from the number of discovery matches.

Fill only:
- ## Triage
- ## Routing Contract

Use these t-shirt values only: xs, s, m, l, xl.
Use these plan levels only: simple, internal, comprehensive.
Use sketch_level core for simple/internal and expanded for broad or high-risk work.
Set external_research=true only when current repo context is insufficient or external packages/protocols/APIs are material.
Set architecture_diagram=true only when the plan needs cross-component architecture.

Spec:
```text
{spec_text[:12000]}
```

Internal discovery:
```json
{discovery_summary[:20000]}
```
""".strip()


def _build_fill_instructions(spec_text: str, contract: Mapping[str, Any]) -> str:
    """Build the generative instructions for filling selected plan sections."""
    return f"""
You are executing the second half of speckit.plan.

Edit only FEATURE_DIR/plan.md.
The triage-selected section scaffold is already present. Fill only those sections.
Do not create discovery.md, research.md, sketch.md, data-model.md, quickstart.md, or tasks.md.
Do not add extra sections beyond the scaffold unless a blocking contradiction must be recorded.

Every non-duplicate plan must include at least one decomposition-ready design slice in ## Design Slices.
The first design slice must be tasking-ready and include:
- objective
- estimated LOE
- primary seam
- touched files
- touched symbols
- likely net-new files
- reuse / modify / create classification
- constraints and invariants
- dependency relationship
- verification concern
- implementation directive

For the simplest low-risk feature, make exactly one low-estimated design slice.
For comprehensive or high-risk work, include enough slices, architecture detail, and research detail for tasking to avoid inventing architecture.
If architecture_diagram=true, include a Mermaid diagram in ## Architecture Diagram.

Routing contract:
```json
{_render_contract(contract)}
```

Spec:
```text
{spec_text[:12000]}
```
""".strip()


def _run_codex_action(
    *,
    repo_root: Path,
    runner: Path,
    feature_id: str,
    phase: str,
    correlation_id: str,
    task_action: str,
    feature_dir: Path,
    instructions: str,
    output_template_path: Path,
    resume_session: bool = False,
    retry_index: int = 0,
) -> dict[str, Any]:
    """Run the generic Codex action runner for one combined-plan substep."""
    payload = {
        "feature_id": feature_id,
        "phase": phase,
        "correlation_id": correlation_id,
        "handoff": {
            "feature_dir": str(feature_dir),
            "repo_root": str(repo_root),
            "step_name": "speckit.plan",
            "task_action": task_action,
            "output_template_path": str(output_template_path),
            "completion_marker": PLAN_COMPLETION_MARKER,
            "instructions": instructions,
            "resume_session": resume_session,
            "retry_index": retry_index,
        },
    }
    completed = subprocess.run(
        [sys.executable, str(runner)],
        cwd=repo_root,
        input=json.dumps(payload, sort_keys=True),
        text=True,
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            json.dumps(
                {
                    "error": "codex_plan_action_failed",
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                },
                sort_keys=True,
            )
        )
    if not completed.stdout.strip():
        raise RuntimeError("codex_plan_action_missing_result")
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        raise RuntimeError("codex_plan_action_result_not_object")
    return parsed


def _validate_design_slices(plan_file: Path) -> None:
    """Require at least one tasking-ready design slice in a non-duplicate plan."""
    text = plan_file.read_text(encoding="utf-8")
    if "## Design Slices" not in text:
        raise RuntimeError("design_slices_section_missing")
    if "Slice PL-01" not in text:
        raise RuntimeError("design_slice_pl_01_missing")
    if "Implementation Directive" not in text:
        raise RuntimeError("design_slice_implementation_directive_missing")


def _feasibility_required(contract: Mapping[str, Any]) -> bool:
    """Return whether plan approval should record feasibility pressure."""
    triage = contract.get("triage", {})
    risk = contract.get("risk", {})
    routing = contract.get("routing", {})
    if str(triage.get("risk_level") or "").strip().lower() == "high":
        return True
    if str(routing.get("plan_level") or "").strip().lower() == "comprehensive":
        return True
    return any(str(value).strip().lower() == "high" for value in risk.values())


def _event_request(event: str, *, contract: Mapping[str, Any]) -> dict[str, Any]:
    """Build the driver-owned pipeline event request for this plan outcome."""
    fields: dict[str, Any] = {
        "details": json.dumps(
            {
                "triage": contract.get("triage", {}),
                "routing": contract.get("routing", {}),
            },
            sort_keys=True,
        ),
        "routing": dict(contract.get("routing", {})),
        "risk": dict(contract.get("risk", {})),
        "triage": dict(contract.get("triage", {})),
    }
    if event == "plan_approved":
        fields["feasibility_required"] = _feasibility_required(contract)
    return {"event": event, "fields": fields}


def _write_debug_payload(path: Path, payload: Mapping[str, Any]) -> None:
    """Write a plan-run debug payload to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def orchestrate_plan(
    feature_id: str,
    correlation_id: str,
    *,
    phase: str,
    handoff_runner: str | None = None,
) -> dict[str, Any]:
    """Run the combined plan workflow from triage through design slices."""
    bootstrap_summary = bootstrap_session(REPO_ROOT)
    if not bootstrap_summary["bootstrap_ok"]:
        raise RuntimeError(bootstrap_summary["codegraph_detail"] or "session bootstrap failed")

    feature_dir, spec_file, plan_file = _resolve_feature_paths(feature_id)
    debug_path = REPO_ROOT / ".speckit" / "runtime" / "plan" / f"{correlation_id}.json"
    runner = Path(handoff_runner).resolve() if handoff_runner else DEFAULT_RUNNER

    spec_text = _load_spec_description(spec_file)
    env = _build_uv_env()
    discovery = _run_discovery(_extract_terms(spec_text or feature_dir.name), env)

    _scaffold_manifest_plan(feature_dir)
    _write_triage_scaffold(
        feature_id=feature_id,
        feature_dir=feature_dir,
        spec_file=spec_file,
        plan_file=plan_file,
        discovery=discovery,
    )

    stages: list[dict[str, Any]] = []
    triage_result = _run_codex_action(
        repo_root=REPO_ROOT,
        runner=runner,
        feature_id=feature_id,
        phase=phase,
        correlation_id=f"{correlation_id}:triage",
        task_action="triage_combined_plan",
        feature_dir=feature_dir,
        instructions=_build_triage_instructions(spec_text, discovery),
        output_template_path=plan_file,
    )
    stages.append({"stage": "triage", "result": triage_result})
    contract = _normalize_contract(_extract_contract(plan_file))

    if bool(contract["triage"]["duplicate"]):
        result = {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "exit_code": 0,
            "correlation_id": correlation_id,
            "next_phase": "closed",
            "gate": None,
            "reasons": [],
            "error_code": None,
            "debug_path": str(debug_path),
            "feature_dir": str(feature_dir),
            "plan_artifact": str(plan_file),
            "triage": contract["triage"],
            "routing": contract["routing"],
            "risk": contract["risk"],
            "pipeline_event_request": _event_request("duplicate_marked", contract=contract),
            "stages": stages,
        }
        _write_debug_payload(debug_path, result)
        return result

    _write_selected_scaffold(
        feature_id=feature_id,
        feature_dir=feature_dir,
        spec_file=spec_file,
        plan_file=plan_file,
        discovery=discovery,
        contract=contract,
    )
    fill_result = _run_codex_action(
        repo_root=REPO_ROOT,
        runner=runner,
        feature_id=feature_id,
        phase=phase,
        correlation_id=f"{correlation_id}:fill",
        task_action="fill_combined_plan",
        feature_dir=feature_dir,
        instructions=_build_fill_instructions(spec_text, contract),
        output_template_path=plan_file,
        resume_session=True,
        retry_index=1,
    )
    stages.append({"stage": "fill", "result": fill_result})
    contract = _normalize_contract(_extract_contract(plan_file))
    _validate_design_slices(plan_file)

    result = {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "exit_code": 0,
        "correlation_id": correlation_id,
        "next_phase": "solution",
        "gate": None,
        "reasons": [],
        "error_code": None,
        "debug_path": str(debug_path),
        "feature_dir": str(feature_dir),
        "plan_artifact": str(plan_file),
        "triage": contract["triage"],
        "routing": contract["routing"],
        "risk": contract["risk"],
        "pipeline_event_request": _event_request("plan_approved", contract=contract),
        "stages": stages,
    }
    _write_debug_payload(debug_path, result)
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for combined deterministic plan orchestration."""
    args = _build_parser().parse_args(argv)
    try:
        result = orchestrate_plan(
            args.feature_id,
            args.correlation_id,
            phase=args.phase,
            handoff_runner=args.handoff_runner,
        )
    except Exception as exc:  # noqa: BLE001
        debug_path = REPO_ROOT / ".speckit" / "runtime" / "plan" / f"{args.correlation_id}.json"
        failure = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "exit_code": 2,
            "correlation_id": args.correlation_id,
            "gate": "plan_orchestration",
            "reasons": [str(exc) or "plan_orchestration_failed"],
            "error_code": "plan_orchestration_failed",
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
