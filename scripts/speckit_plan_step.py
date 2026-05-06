#!/usr/bin/env python3
"""Scaffold and validate the combined speckit.plan workflow."""

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

DEFAULT_SCAFFOLD = REPO_ROOT / ".specify" / "scripts" / "pipeline-scaffold.py"
PLAN_COMPLETION_MARKER = "## Plan Completion Summary"
BASE_TEMPLATE_SECTIONS = ("Triage", "Strategy Contract", "Internal Discovery")
DISCOVERY_MAX_TERMS = 5
FILE_PATH_RE = re.compile(r"^file_path:\s*(?P<path>.+)$", re.MULTILINE)
JSON_FENCE_RE = re.compile(r"```json\s*(?P<body>.*?)```", re.IGNORECASE | re.DOTALL)
ALLOWED_TSHIRT_SIZES = {"xs", "s", "m", "l", "xl"}
ALLOWED_RISK_LEVELS = {"low", "medium", "high"}
CANONICAL_DOMAINS = (
    "api integration",
    "data modeling",
    "storage",
    "caching",
    "client/UI",
    "edge delivery",
    "compute",
    "networking",
    "environment",
    "observability",
    "resilience",
    "testing",
    "identity",
    "security",
    "build pipeline",
    "ops governance",
    "code patterns",
)
DOMAIN_ALIAS_MAP = {domain.lower(): domain for domain in CANONICAL_DOMAINS}
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


def _plan_template_path() -> Path:
    """Return the combined-plan template that documents all possible sections."""
    return REPO_ROOT / ".specify" / "templates" / "plan-template.md"


def _default_contract() -> dict[str, Any]:
    """Return the empty strategy contract used before generative triage fills it."""
    return {
        "triage": {
            "duplicate": False,
            "duplicate_reason": "",
            "duplicate_matches": [],
            "tshirt_size": "",
            "risk_level": "",
        },
        "domains": {
            "relevant": [],
            "reasoning": {},
        },
        "strategy": {
            "external_research": False,
            "architecture_strategy": False,
            "architecture_diagram": False,
            "expanded_design_notes": False,
            "strategy_reason": "",
        },
        "risk": {
            "overall": "",
            "requirement_clarity": "",
            "repo_uncertainty": "",
            "external_dependency_uncertainty": "",
            "state_data_migration_risk": "",
            "runtime_side_effect_risk": "",
            "human_operator_dependency": "",
        },
    }


def _normalize_risk_level(value: Any) -> str:
    """Normalize a low/medium/high risk label or return an empty string."""
    normalized = str(value or "").strip().lower()
    if normalized and normalized not in ALLOWED_RISK_LEVELS:
        raise RuntimeError(f"invalid_risk_level:{normalized}")
    return normalized


def _normalize_domain_name(value: Any) -> str:
    """Normalize one constitution domain label to its canonical spelling."""
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    normalized = DOMAIN_ALIAS_MAP.get(candidate.lower())
    if normalized is None:
        raise RuntimeError(f"invalid_domain:{candidate}")
    return normalized


def _compat_strategy_from_legacy_routing(routing: Mapping[str, Any]) -> dict[str, Any]:
    """Map the legacy level-based routing contract into the strategy shape."""
    plan_level = str(routing.get("plan_level") or "").strip().lower()
    sketch_level = str(routing.get("sketch_level") or "").strip().lower()
    return {
        "external_research": bool(routing.get("external_research", False)),
        "architecture_strategy": bool(routing.get("architecture_diagram", False))
        or plan_level == "comprehensive",
        "architecture_diagram": bool(routing.get("architecture_diagram", False))
        or plan_level == "comprehensive",
        "expanded_design_notes": sketch_level == "expanded",
        "strategy_reason": str(routing.get("routing_reason") or "").strip(),
    }


def _ledger_routing_view(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Return a ledger-compatible routing payload derived from the strategy contract."""
    strategy = contract.get("strategy", {})
    domains = contract.get("domains", {})
    triage = contract.get("triage", {})
    risk = contract.get("risk", {})
    relevant_domains = list(domains.get("relevant") or [])
    architecture_strategy = bool(strategy.get("architecture_strategy", False))
    architecture_diagram = bool(strategy.get("architecture_diagram", False))
    expanded_notes = bool(strategy.get("expanded_design_notes", False))
    overall_risk = str(risk.get("overall") or triage.get("risk_level") or "").strip().lower()
    size = str(triage.get("tshirt_size") or "").strip().lower()
    if size in {"l", "xl"}:
        plan_level = "comprehensive"
    elif architecture_strategy or len(relevant_domains) > 1 or overall_risk in {"medium", "high"}:
        plan_level = "core"
    else:
        plan_level = "simple"
    if expanded_notes:
        sketch_level = "expanded"
    elif relevant_domains:
        sketch_level = "core"
    else:
        sketch_level = "compact"
    return {
        "plan_level": plan_level,
        "sketch_level": sketch_level,
        "external_research": bool(strategy.get("external_research", False)),
        "architecture_diagram": architecture_diagram,
        "routing_reason": str(strategy.get("strategy_reason") or "").strip(),
        "relevant_domains": relevant_domains,
    }


def _render_plan_template(*, feature_id: str, feature_dir: Path, spec_file: Path) -> str:
    """Load the documented template and fill its feature metadata placeholders."""
    return (
        _plan_template_path()
        .read_text(encoding="utf-8")
        .replace("[FEATURE_NAME]", feature_dir.name)
        .replace("[FEATURE_ID]", feature_id)
        .replace("[SPEC_FILE_NAME]", spec_file.name)
    )


def _split_markdown_sections(text: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Split a markdown artifact into its preamble and second-level sections."""
    preamble: list[str] = []
    sections: list[tuple[str, str]] = []
    current_heading: str | None = None
    current_body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_heading is not None:
                sections.append((current_heading, "\n".join(current_body).strip()))
            current_heading = line[3:].strip()
            current_body = []
            continue
        if current_heading is None:
            preamble.append(line)
        else:
            current_body.append(line)
    if current_heading is not None:
        sections.append((current_heading, "\n".join(current_body).strip()))
    return preamble, sections


def _render_markdown_sections(
    preamble: list[str], sections: list[tuple[str, str]]
) -> str:
    """Render a markdown artifact from a preamble and ordered section bodies."""
    lines = list(preamble)
    while lines and not lines[-1].strip():
        lines.pop()
    if lines:
        lines.append("")
    for heading, body in sections:
        lines.extend([f"## {heading}", ""])
        if body:
            lines.extend(body.splitlines())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_template_subset(
    *,
    template_text: str,
    keep_sections: list[str],
    overrides: Mapping[str, str],
) -> str:
    """Prune the documented template to the requested headings and body overrides."""
    preamble, sections = _split_markdown_sections(template_text)
    rendered_sections: list[tuple[str, str]] = []
    seen: set[str] = set()
    keep_set = set(keep_sections)
    for heading, body in sections:
        if heading not in keep_set:
            continue
        rendered_sections.append((heading, overrides.get(heading, body)))
        seen.add(heading)
    missing = [heading for heading in keep_sections if heading not in seen]
    if missing:
        raise RuntimeError(f"plan_template_missing_sections:{','.join(missing)}")
    return _render_markdown_sections(preamble, rendered_sections)


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the combined plan helper."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser(
        "prepare-triage",
        help="Scaffold the minimal triage-first plan shell with internal discovery.",
    )
    prepare.add_argument("--feature-id", required=True, help="Feature ID, e.g. 023")

    rewrite = subparsers.add_parser(
        "apply-strategy",
        aliases=["apply-routing"],
        help="Rewrite plan.md with only the sections selected by triage strategy.",
    )
    rewrite.add_argument("--feature-id", required=True, help="Feature ID, e.g. 023")

    finalize = subparsers.add_parser(
        "finalize",
        help="Validate the completed plan and emit the driver event request payload.",
    )
    finalize.add_argument("--feature-id", required=True, help="Feature ID, e.g. 023")
    finalize.add_argument("--phase", default="plan", help="Phase label for the finalized plan")
    finalize.add_argument(
        "--correlation-id",
        required=True,
        help="Run-scoped correlation id used for the runtime result envelope",
    )

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


def _extract_terms(text: str) -> list[str]:
    """Extract a small set of repo-search terms from the spec text."""
    words = re.findall(r"[A-Za-z0-9_-]+", text.lower())
    terms: list[str] = []
    for word in words:
        if word in STOP_WORDS or len(word) < 3:
            continue
        if word not in terms:
            terms.append(word)
        if len(terms) >= DISCOVERY_MAX_TERMS:
            break
    return terms or ["feature"]


def _run_uv_command(
    args: list[str],
    *,
    env: dict[str, str],
    input_payload: str | None = None,
    timeout_seconds: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one repo-local uv command with bounded captured output."""
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        input=input_payload,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=timeout_seconds,
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
    """Create the manifest-declared plan artifact before triage writing begins."""
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
    """Write the initial triage-only scaffold used by the plan command."""
    discovery_body = "\n\n".join(_render_discovery_result(result) for result in discovery)
    template_text = _render_plan_template(
        feature_id=feature_id,
        feature_dir=feature_dir,
        spec_file=spec_file,
    )
    plan_file.write_text(
        _render_template_subset(
            template_text=template_text,
            keep_sections=list(BASE_TEMPLATE_SECTIONS),
            overrides={
                "Triage": "\n".join(
                    [
                        "- duplicate: [true/false]",
                        "- t_shirt_size: [xs/s/m/l/xl]",
                        "- risk_level: [low/medium/high]",
                        "- reason: [Generative decision based on spec and discovery.]",
                    ]
                ),
                "Strategy Contract": "\n".join(
                    [
                        "```json",
                        _render_contract(_default_contract()),
                        "```",
                    ]
                ),
                "Internal Discovery": discovery_body or "- No internal discovery results recorded.",
            },
        ),
        encoding="utf-8",
    )


def _extract_contract(plan_file: Path) -> dict[str, Any]:
    """Load the combined strategy contract from plan.md."""
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
    """Normalize the triage contract into stable strategy, domain, and risk values."""
    triage_raw = contract.get("triage", {})
    strategy_raw = contract.get("strategy", {})
    legacy_routing_raw = contract.get("routing", {})
    domains_raw = contract.get("domains", {})
    risk_raw = contract.get("risk", {})
    triage = dict(triage_raw) if isinstance(triage_raw, Mapping) else {}
    strategy = dict(strategy_raw) if isinstance(strategy_raw, Mapping) else {}
    legacy_routing = dict(legacy_routing_raw) if isinstance(legacy_routing_raw, Mapping) else {}
    if not strategy and legacy_routing:
        strategy = _compat_strategy_from_legacy_routing(legacy_routing)
    domains = dict(domains_raw) if isinstance(domains_raw, Mapping) else {}
    risk = dict(risk_raw) if isinstance(risk_raw, Mapping) else {}
    tshirt_size = str(triage.get("tshirt_size") or "").strip().lower()
    if tshirt_size and tshirt_size not in ALLOWED_TSHIRT_SIZES:
        raise RuntimeError(f"invalid_tshirt_size:{tshirt_size}")
    relevant_domains = [
        domain
        for domain in (_normalize_domain_name(value) for value in list(domains.get("relevant") or []))
        if domain
    ]
    domain_reasoning_raw = domains.get("reasoning", {})
    domain_reasoning_input = (
        dict(domain_reasoning_raw) if isinstance(domain_reasoning_raw, Mapping) else {}
    )
    domain_reasoning: dict[str, str] = {}
    for key, value in domain_reasoning_input.items():
        normalized_domain = _normalize_domain_name(key)
        if not normalized_domain:
            continue
        domain_reasoning[normalized_domain] = str(value or "").strip()
    return {
        "triage": {
            "duplicate": bool(triage.get("duplicate", False)),
            "duplicate_reason": str(triage.get("duplicate_reason") or "").strip(),
            "duplicate_matches": list(triage.get("duplicate_matches") or []),
            "tshirt_size": tshirt_size,
            "risk_level": _normalize_risk_level(triage.get("risk_level") or risk.get("overall")),
        },
        "domains": {
            "relevant": list(dict.fromkeys(relevant_domains)),
            "reasoning": domain_reasoning,
        },
        "strategy": {
            "external_research": bool(strategy.get("external_research", False)),
            "architecture_strategy": bool(strategy.get("architecture_strategy", False)),
            "architecture_diagram": bool(strategy.get("architecture_diagram", False)),
            "expanded_design_notes": bool(strategy.get("expanded_design_notes", False)),
            "strategy_reason": str(strategy.get("strategy_reason") or "").strip(),
        },
        "risk": {
            "overall": _normalize_risk_level(risk.get("overall") or triage.get("risk_level")),
            "requirement_clarity": _normalize_risk_level(risk.get("requirement_clarity")),
            "repo_uncertainty": _normalize_risk_level(risk.get("repo_uncertainty")),
            "external_dependency_uncertainty": _normalize_risk_level(
                risk.get("external_dependency_uncertainty")
            ),
            "state_data_migration_risk": _normalize_risk_level(risk.get("state_data_migration_risk")),
            "runtime_side_effect_risk": _normalize_risk_level(risk.get("runtime_side_effect_risk")),
            "human_operator_dependency": _normalize_risk_level(risk.get("human_operator_dependency")),
        },
    }


def _selected_sections(contract: Mapping[str, Any]) -> list[str]:
    """Return the plan sections required by the triage strategy decision."""
    strategy = contract.get("strategy", {})
    sections = [
        "Summary",
        "Relevant Domains",
        "Internal Research",
        "Design Slices",
        "Plan Completion Summary",
    ]
    if bool(strategy.get("external_research", False)):
        sections.insert(sections.index("Design Slices"), "External Research")
    if bool(strategy.get("architecture_strategy", False)) or bool(
        strategy.get("architecture_diagram", False)
    ):
        sections.insert(sections.index("Design Slices"), "Architecture Strategy")
    if bool(strategy.get("architecture_diagram", False)):
        sections.insert(sections.index("Design Slices"), "Architecture Diagram")
    if bool(strategy.get("expanded_design_notes", False)):
        sections.insert(sections.index("Design Slices"), "Expanded Design Notes")
    return list(dict.fromkeys(sections))


def _render_contract(contract: Mapping[str, Any]) -> str:
    """Render the combined routing contract as formatted JSON."""
    return json.dumps(dict(contract), indent=2, sort_keys=True)


def _extract_section_body(plan_file: Path, heading: str) -> str:
    """Extract one markdown section body from the current plan artifact."""
    lines = plan_file.read_text(encoding="utf-8").splitlines()
    heading_line = f"## {heading}"
    in_section = False
    body: list[str] = []
    for line in lines:
        if line == heading_line:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            body.append(line)
    return "\n".join(body).strip()


def _write_selected_scaffold(
    *,
    feature_id: str,
    feature_dir: Path,
    spec_file: Path,
    plan_file: Path,
    discovery_body: str,
    contract: Mapping[str, Any],
) -> list[str]:
    """Rewrite plan.md with only the sections selected by triage."""
    sections = _selected_sections(contract)
    triage = contract.get("triage", {})
    strategy = contract.get("strategy", {})
    template_text = _render_plan_template(
        feature_id=feature_id,
        feature_dir=feature_dir,
        spec_file=spec_file,
    )
    plan_file.write_text(
        _render_template_subset(
            template_text=template_text,
            keep_sections=[*BASE_TEMPLATE_SECTIONS, *sections],
            overrides={
                "Triage": "\n".join(
                    [
                        f"- duplicate: {str(bool(triage.get('duplicate'))).lower()}",
                        f"- t_shirt_size: {triage.get('tshirt_size') or ''}",
                        f"- risk_level: {triage.get('risk_level') or ''}",
                        f"- reason: {triage.get('duplicate_reason') or strategy.get('strategy_reason') or ''}",
                    ]
                ),
                "Strategy Contract": "\n".join(
                    [
                        "```json",
                        _render_contract(contract),
                        "```",
                    ]
                ),
                "Internal Discovery": discovery_body or "- No internal discovery results recorded.",
            },
        ),
        encoding="utf-8",
    )
    return sections


def _validate_plan_completion(plan_file: Path) -> None:
    """Require the final plan artifact to include the completion summary heading."""
    if PLAN_COMPLETION_MARKER not in plan_file.read_text(encoding="utf-8"):
        raise RuntimeError("plan_completion_summary_missing")


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
    strategy = contract.get("strategy", {})
    if str(triage.get("risk_level") or "").strip().lower() == "high":
        return True
    if str(triage.get("tshirt_size") or "").strip().lower() in {"l", "xl"}:
        return True
    if bool(strategy.get("external_research", False)) or bool(
        strategy.get("architecture_strategy", False)
    ):
        return True
    return any(str(value).strip().lower() == "high" for value in risk.values())


def _event_request(event: str, *, contract: Mapping[str, Any]) -> dict[str, Any]:
    """Build the driver-owned pipeline event request for this plan outcome."""
    ledger_routing = _ledger_routing_view(contract)
    fields: dict[str, Any] = {
        "details": json.dumps(
            {
                "triage": contract.get("triage", {}),
                "domains": contract.get("domains", {}),
                "strategy": contract.get("strategy", {}),
            },
            sort_keys=True,
        ),
        "routing": ledger_routing,
        "risk": dict(contract.get("risk", {})),
        "triage": dict(contract.get("triage", {})),
    }
    if event == "plan_approved":
        fields["feasibility_required"] = _feasibility_required(contract)
    return {"event": event, "fields": fields}


def _runtime_result_path(phase: str, correlation_id: str) -> Path:
    """Return the runtime result path for a finalized combined plan step."""
    return REPO_ROOT / ".speckit" / "runtime" / phase / f"{correlation_id}.json"


def _write_debug_payload(path: Path, payload: Mapping[str, Any]) -> None:
    """Write a plan-run runtime payload to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def prepare_triage(feature_id: str) -> dict[str, Any]:
    """Scaffold the triage-first plan shell and embed bounded internal discovery."""
    bootstrap_summary = bootstrap_session(REPO_ROOT)
    if not bootstrap_summary["bootstrap_ok"]:
        raise RuntimeError(bootstrap_summary["codegraph_detail"] or "session_bootstrap_failed")

    feature_dir, spec_file, plan_file = _resolve_feature_paths(feature_id)
    spec_text = _load_spec_description(spec_file)
    env = _build_uv_env()
    terms = _extract_terms(spec_text or feature_dir.name)
    discovery = _run_discovery(terms, env)
    _scaffold_manifest_plan(feature_dir)
    _write_triage_scaffold(
        feature_id=feature_id,
        feature_dir=feature_dir,
        spec_file=spec_file,
        plan_file=plan_file,
        discovery=discovery,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "command": "prepare-triage",
        "feature_id": feature_id,
        "feature_dir": str(feature_dir),
        "plan_artifact": str(plan_file),
        "discovery_terms": terms,
        "discovery_count": len(discovery),
        "completion_marker": PLAN_COMPLETION_MARKER,
    }


def apply_strategy(feature_id: str) -> dict[str, Any]:
    """Rewrite plan.md so it contains only the sections selected by triage strategy."""
    feature_dir, spec_file, plan_file = _resolve_feature_paths(feature_id)
    contract = _normalize_contract(_extract_contract(plan_file))
    if bool(contract["triage"]["duplicate"]):
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "command": "apply-strategy",
            "feature_id": feature_id,
            "feature_dir": str(feature_dir),
            "plan_artifact": str(plan_file),
            "duplicate": True,
            "rewritten": False,
            "selected_sections": [],
        }

    discovery_body = _extract_section_body(plan_file, "Internal Discovery")
    sections = _write_selected_scaffold(
        feature_id=feature_id,
        feature_dir=feature_dir,
        spec_file=spec_file,
        plan_file=plan_file,
        discovery_body=discovery_body,
        contract=contract,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "command": "apply-strategy",
        "feature_id": feature_id,
        "feature_dir": str(feature_dir),
        "plan_artifact": str(plan_file),
        "duplicate": False,
        "rewritten": True,
        "selected_sections": sections,
        "domains": contract["domains"],
        "strategy": contract["strategy"],
        "triage": contract["triage"],
        "risk": contract["risk"],
    }


def apply_routing(feature_id: str) -> dict[str, Any]:
    """Preserve backward compatibility for older callers using apply-routing."""
    return apply_strategy(feature_id)


def finalize_plan(feature_id: str, correlation_id: str, *, phase: str = "plan") -> dict[str, Any]:
    """Validate the final plan artifact and emit the driver event request envelope."""
    feature_dir, _, plan_file = _resolve_feature_paths(feature_id)
    contract = _normalize_contract(_extract_contract(plan_file))
    _validate_plan_completion(plan_file)
    debug_path = _runtime_result_path(phase, correlation_id)

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
            "domains": contract["domains"],
            "strategy": contract["strategy"],
            "risk": contract["risk"],
            "pipeline_event_request": _event_request("duplicate_marked", contract=contract),
        }
        _write_debug_payload(debug_path, result)
        return result

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
        "domains": contract["domains"],
        "strategy": contract["strategy"],
        "risk": contract["risk"],
        "pipeline_event_request": _event_request("plan_approved", contract=contract),
    }
    _write_debug_payload(debug_path, result)
    return result


def main(argv: list[str] | None = None) -> int:
    """Dispatch the combined plan helper subcommands."""
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "prepare-triage":
            result = prepare_triage(args.feature_id)
        elif args.command in {"apply-strategy", "apply-routing"}:
            result = apply_strategy(args.feature_id)
        elif args.command == "finalize":
            result = finalize_plan(
                args.feature_id,
                args.correlation_id,
                phase=args.phase,
            )
        else:
            raise RuntimeError(f"unsupported_plan_command:{args.command}")
    except Exception as exc:  # noqa: BLE001
        debug_path = None
        correlation_id = getattr(args, "correlation_id", None)
        phase = getattr(args, "phase", "plan")
        if isinstance(correlation_id, str) and correlation_id:
            debug_path = _runtime_result_path(phase, correlation_id)
        failure = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "exit_code": 2,
            "command": args.command,
            "correlation_id": correlation_id or "",
            "gate": "plan_helper",
            "reasons": [str(exc) or "plan_helper_failed"],
            "error_code": "plan_helper_failed",
            "next_phase": None,
            "debug_path": str(debug_path) if debug_path is not None else None,
        }
        if debug_path is not None:
            _write_debug_payload(debug_path, failure)
        print(json.dumps(failure, sort_keys=True))
        return 2

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
