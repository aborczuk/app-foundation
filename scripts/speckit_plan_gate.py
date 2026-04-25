#!/usr/bin/env python3
"""Deterministic checks for /speckit.plan artifact and section gates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

from spec_routing import load_spec_routing_contract

HEADING_RE = re.compile(r"^\s*(?P<hashes>#{2,6})\s+(?P<title>.+?)\s*$")

RESEARCH_REQUIRED_SECTIONS = (
    "## Zero-Custom-Server Assessment",
    "## Repo Assembly Map",
    "## Package Adoption Options",
    "## Conceptual Patterns",
)

PLAN_REQUIRED_SECTIONS = (
    "## External Ingress + Runtime Readiness Gate",
    "## Constitution Check",
    "## Architecture Flow",
)

STATUS_RE = re.compile(r"(✅\s*Pass|❌\s*Fail|N/A|⚠️\s*Conditional)")
LEGACY_FEATURE_ID_MAX_DEFAULT = 17
LEGACY_SOFT_REASONS = {
    "missing_functional_requirements_section",
    "missing_named_automated_action",
}


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="subcommand", required=True)

    research = sub.add_parser(
        "research-prereq",
        help="Validate research prerequisites, honoring spec-driven routing when provided.",
    )
    research.add_argument("--feature-dir", required=True)
    research.add_argument("--spec-file", default=None)
    research.add_argument("--json", action="store_true")

    core_action = sub.add_parser(
        "spec-core-action", help="Validate spec names an explicit automated action in FRs."
    )
    core_action.add_argument("--spec-file", required=True)
    core_action.add_argument(
        "--legacy-ok",
        action="store_true",
        help=(
            "Downgrade missing FR-section/core-action failures to warnings for legacy feature "
            "IDs (<= --legacy-max-feature-id)."
        ),
    )
    core_action.add_argument(
        "--legacy-max-feature-id",
        type=int,
        default=LEGACY_FEATURE_ID_MAX_DEFAULT,
    )
    core_action.add_argument("--json", action="store_true")

    plan_sections = sub.add_parser(
        "plan-sections", help="Validate required plan sections and ingress status rows."
    )
    plan_sections.add_argument("--plan-file", required=True)
    plan_sections.add_argument("--json", action="store_true")

    artifacts = sub.add_parser(
        "design-artifacts", help="Validate phase-1 planning artifacts in FEATURE_DIR."
    )
    artifacts.add_argument("--feature-dir", required=True)
    artifacts.add_argument("--require-contracts", action="store_true")
    artifacts.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"ok={payload.get('ok')} mode={payload.get('mode')}")
    for reason in payload.get("reasons", []):
        print(f"- {reason}")


def _research_prereq(feature_dir: Path) -> tuple[int, dict[str, Any]]:
    """Validate research prerequisites without an explicit routing contract."""
    return _research_prereq_with_spec(feature_dir, None)


def _research_prereq_with_spec(
    feature_dir: Path, spec_file: Path | None
) -> tuple[int, dict[str, Any]]:
    """Validate research prerequisites against spec-driven routing when available."""
    reasons: list[str] = []
    research = feature_dir / "research.md"
    found_sections: list[str] = []
    routing_contract: dict[str, Any] | None = None

    if spec_file is not None:
        contract, routing_reasons = load_spec_routing_contract(spec_file)
        if contract is not None:
            routing_contract = contract
        if routing_reasons:
            reasons.extend(routing_reasons)
            payload = {
                "mode": "research_prereq",
                "feature_dir": str(feature_dir),
                "spec_file": str(spec_file),
                "routing_contract": routing_contract,
                "research_file": str(research),
                "found_sections": found_sections,
                "reasons": reasons,
                "ok": False,
            }
            return (2, payload)

    if routing_contract is not None:
        routing = routing_contract.get("routing", {})
        if isinstance(routing, dict):
            if routing.get("plan_profile") == "skip":
                payload = {
                    "mode": "research_prereq",
                    "feature_dir": str(feature_dir),
                    "spec_file": str(spec_file) if spec_file is not None else None,
                    "routing_contract": routing_contract,
                    "research_file": str(research),
                    "found_sections": [],
                    "reasons": ["plan_skipped_by_routing"],
                    "ok": True,
                }
                return (0, payload)
            if routing.get("research_route") == "skip":
                payload = {
                    "mode": "research_prereq",
                    "feature_dir": str(feature_dir),
                    "spec_file": str(spec_file) if spec_file is not None else None,
                    "routing_contract": routing_contract,
                    "research_file": str(research),
                    "found_sections": [],
                    "reasons": ["research_skipped_by_routing"],
                    "ok": True,
                }
                return (0, payload)

    if not research.exists():
        reasons.append("missing_research_md")
    else:
        text = research.read_text(encoding="utf-8")
        for section in RESEARCH_REQUIRED_SECTIONS:
            if section in text:
                found_sections.append(section)
            else:
                reasons.append(f"missing_research_section:{section}")

    payload = {
        "mode": "research_prereq",
        "feature_dir": str(feature_dir),
        "spec_file": str(spec_file) if spec_file is not None else None,
        "routing_contract": routing_contract,
        "research_file": str(research),
        "found_sections": found_sections,
        "reasons": reasons,
        "ok": len(reasons) == 0,
    }
    return (0 if payload["ok"] else 2, payload)


def _extract_section(text: str, heading_title: str) -> str:
    lines = text.splitlines()
    target_idx = None
    target_level = None
    for i, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if not match:
            continue
        if match.group("title").strip() == heading_title:
            target_idx = i
            target_level = len(match.group("hashes"))
            break
    if target_idx is None or target_level is None:
        return ""
    end = len(lines)
    for i in range(target_idx + 1, len(lines)):
        match = HEADING_RE.match(lines[i])
        if match and len(match.group("hashes")) <= target_level:
            end = i
            break
    return "\n".join(lines[target_idx:end])


def _parse_feature_id_from_spec_path(spec_file: Path) -> int | None:
    for part in spec_file.parts:
        match = re.match(r"^(?P<id>\d{3})-", part)
        if match:
            return int(match.group("id"))
    return None


def _spec_core_action(
    spec_file: Path, *, legacy_ok: bool, legacy_max_feature_id: int
) -> tuple[int, dict[str, Any]]:
    reasons: list[str] = []
    warnings: list[str] = []
    downgraded_reasons: list[str] = []
    matches: list[str] = []
    feature_id = _parse_feature_id_from_spec_path(spec_file)
    legacy_mode_applied = (
        legacy_ok and feature_id is not None and feature_id <= legacy_max_feature_id
    )
    if not spec_file.exists():
        reasons.append("missing_spec_file")
    else:
        text = spec_file.read_text(encoding="utf-8")
        fr_section = _extract_section(text, "Functional Requirements")
        if not fr_section:
            reasons.append("missing_functional_requirements_section")
        else:
            for line in fr_section.splitlines():
                normalized = line.strip()
                if "MUST" not in normalized.upper():
                    continue
                if not re.search(
                    r"(`[^`]+`|\binvoke\b|\btrigger\b|\bexecute\b|\brun\b|\bcall\b)",
                    normalized,
                    flags=re.IGNORECASE,
                ):
                    continue
                matches.append(normalized)
            if not matches:
                reasons.append("missing_named_automated_action")

    if legacy_mode_applied:
        for reason in list(reasons):
            if reason in LEGACY_SOFT_REASONS:
                reasons.remove(reason)
                downgraded_reasons.append(reason)
                warnings.append(f"warn_legacy_{reason}")

    payload = {
        "mode": "spec_core_action",
        "spec_file": str(spec_file),
        "feature_id": feature_id,
        "legacy_ok_requested": legacy_ok,
        "legacy_mode_applied": legacy_mode_applied,
        "legacy_max_feature_id": legacy_max_feature_id,
        "match_count": len(matches),
        "matched_lines": matches[:5],
        "downgraded_reasons": downgraded_reasons,
        "warnings": warnings,
        "reasons": reasons,
        "ok": len(reasons) == 0,
    }
    return (0 if payload["ok"] else 2, payload)


def _plan_sections(plan_file: Path) -> tuple[int, dict[str, Any]]:
    reasons: list[str] = []
    missing_sections: list[str] = []
    blank_status_rows: list[str] = []

    if not plan_file.exists():
        reasons.append("missing_plan_file")
        payload = {
            "mode": "plan_sections",
            "plan_file": str(plan_file),
            "missing_sections": list(PLAN_REQUIRED_SECTIONS),
            "blank_status_rows": [],
            "reasons": reasons,
            "ok": False,
        }
        return (2, payload)

    text = plan_file.read_text(encoding="utf-8")
    for section in PLAN_REQUIRED_SECTIONS:
        if section not in text:
            missing_sections.append(section)
            reasons.append(f"missing_plan_section:{section}")

    ingress = _extract_section(text, "External Ingress + Runtime Readiness Gate")
    if ingress:
        for line in ingress.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            if stripped.startswith("|---") or "Status" in stripped:
                continue
            if not STATUS_RE.search(stripped):
                blank_status_rows.append(stripped)
        if blank_status_rows:
            reasons.append("ingress_gate_rows_missing_status")

    payload = {
        "mode": "plan_sections",
        "plan_file": str(plan_file),
        "missing_sections": missing_sections,
        "blank_status_rows": blank_status_rows,
        "reasons": reasons,
        "ok": len(reasons) == 0,
    }
    return (0 if payload["ok"] else 2, payload)


def _design_artifacts(feature_dir: Path, require_contracts: bool) -> tuple[int, dict[str, Any]]:
    reasons: list[str] = []
    required = ("data-model.md", "quickstart.md")
    missing: list[str] = []
    for filename in required:
        if not (feature_dir / filename).exists():
            missing.append(filename)
            reasons.append(f"missing_artifact:{filename}")

    contracts_dir = feature_dir / "contracts"
    contracts_present = contracts_dir.is_dir() and any(contracts_dir.iterdir())
    if require_contracts and not contracts_present:
        reasons.append("missing_contract_artifacts")

    payload = {
        "mode": "design_artifacts",
        "feature_dir": str(feature_dir),
        "missing_artifacts": missing,
        "contracts_present": contracts_present,
        "reasons": reasons,
        "ok": len(reasons) == 0,
    }
    return (0 if payload["ok"] else 2, payload)


def main(argv: Sequence[str] | None = None) -> int:
    """Run selected /speckit.plan deterministic gate check."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.subcommand == "research-prereq":
        spec_file = Path(args.spec_file).resolve() if args.spec_file else None
        exit_code, payload = _research_prereq_with_spec(
            Path(args.feature_dir).resolve(), spec_file
        )
    elif args.subcommand == "spec-core-action":
        exit_code, payload = _spec_core_action(
            Path(args.spec_file).resolve(),
            legacy_ok=bool(args.legacy_ok),
            legacy_max_feature_id=int(args.legacy_max_feature_id),
        )
    elif args.subcommand == "plan-sections":
        exit_code, payload = _plan_sections(Path(args.plan_file).resolve())
    elif args.subcommand == "design-artifacts":
        exit_code, payload = _design_artifacts(
            Path(args.feature_dir).resolve(), require_contracts=args.require_contracts
        )
    else:
        return 2

    _emit(payload, as_json=bool(args.json))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
