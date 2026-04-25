#!/usr/bin/env python3
"""Helpers for parsing spec-driven routing contracts from spec.md and events."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

HEADING_RE = re.compile(r"^\s*(?P<hashes>#{2,6})\s+(?P<title>.+?)\s*$")
JSON_FENCE_RE = re.compile(r"```json\s*(?P<body>.*?)```", re.IGNORECASE | re.DOTALL)

ROUTING_VALUE_SETS = {
    "research_route": {"skip", "required"},
    "plan_profile": {"skip", "lite", "full"},
    "sketch_profile": {"core", "expanded"},
    "tasking_route": {"required", "attach_to_existing_feature"},
    "estimate_route": {"required_after_tasking", "reuse_existing_estimate"},
}

RISK_VALUE_SET = {"low", "medium", "high"}
RISK_FIELDS = (
    "requirement_clarity",
    "repo_uncertainty",
    "external_dependency_uncertainty",
    "state_data_migration_risk",
    "runtime_side_effect_risk",
    "human_operator_dependency",
)
CONDITIONAL_SKETCH_SECTION_NAMES = (
    "Repo Grounding",
    "Contract / Artifact / Event Impact",
    "Runtime / State / Failure Notes",
    "Human / Operator Boundaries",
    "Design Gaps and Repo Contradictions",
    "Decomposition-Ready Design Slices",
)
CONDITIONAL_SKETCH_SECTION_LOOKUP = {
    name.lower(): name for name in CONDITIONAL_SKETCH_SECTION_NAMES
}


def _normalize_lower(value: Any) -> str:
    """Return a stripped lower-case string for a routing choice."""
    return str(value).strip().lower()


def _normalize_text(value: Any) -> str:
    """Return a stripped string for a free-form contract field."""
    return str(value).strip()


def _normalize_string_list(value: Any) -> list[str]:
    """Return a compact list of non-empty strings."""
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _normalize_conditional_sketch_sections(value: Any) -> list[str]:
    """Return canonical conditional sketch section titles when recognized."""
    normalized: list[str] = []
    for text in _normalize_string_list(value):
        normalized.append(CONDITIONAL_SKETCH_SECTION_LOOKUP.get(text.lower(), text))
    return normalized


def _looks_placeholder(value: str) -> bool:
    """Return True when a contract field still looks templated."""
    stripped = value.strip()
    return stripped.startswith("[") and stripped.endswith("]")


def _extract_markdown_section(text: str, heading_title: str) -> str:
    """Return the markdown section for heading_title, preserving nested content."""
    lines = text.splitlines()
    target_idx = None
    target_level = None
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if not match:
            continue
        if match.group("title").strip() == heading_title:
            target_idx = index
            target_level = len(match.group("hashes"))
            break
    if target_idx is None or target_level is None:
        return ""

    end = len(lines)
    for index in range(target_idx + 1, len(lines)):
        match = HEADING_RE.match(lines[index])
        if match and len(match.group("hashes")) <= target_level:
            end = index
            break
    return "\n".join(lines[target_idx:end])


def normalize_spec_routing_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the routing and risk block into stable comparison-friendly values."""
    routing_raw = contract.get("routing", {})
    risk_raw = contract.get("risk", {})
    routing = dict(routing_raw) if isinstance(routing_raw, Mapping) else {}
    risk = dict(risk_raw) if isinstance(risk_raw, Mapping) else {}
    return {
        "routing": {
            "research_route": _normalize_lower(routing.get("research_route", "")),
            "plan_profile": _normalize_lower(routing.get("plan_profile", "")),
            "sketch_profile": _normalize_lower(routing.get("sketch_profile", "")),
            "tasking_route": _normalize_lower(routing.get("tasking_route", "")),
            "estimate_route": _normalize_lower(routing.get("estimate_route", "")),
            "routing_reason": _normalize_text(routing.get("routing_reason", "")),
            "conditional_sketch_sections": _normalize_conditional_sketch_sections(
                routing.get("conditional_sketch_sections", [])
            ),
        },
        "risk": {
            field: _normalize_lower(risk.get(field, ""))
            for field in RISK_FIELDS
        },
    }


def validate_spec_routing_contract(contract: Mapping[str, Any]) -> list[str]:
    """Return validation reasons for a normalized routing contract."""
    reasons: list[str] = []
    routing = contract.get("routing")
    risk = contract.get("risk")

    if not isinstance(routing, Mapping):
        return ["missing_routing_block"]
    if not isinstance(risk, Mapping):
        reasons.append("missing_risk_block")

    for field, allowed in ROUTING_VALUE_SETS.items():
        value = str(routing.get(field, "")).strip().lower()
        if not value:
            reasons.append(f"missing_routing_field:{field}")
            continue
        if _looks_placeholder(value):
            reasons.append(f"placeholder_routing_field:{field}")
            continue
        if value not in allowed:
            reasons.append(f"invalid_routing_value:{field}:{value}")

    routing_reason = str(routing.get("routing_reason", "")).strip()
    if not routing_reason:
        reasons.append("missing_routing_reason")
    elif _looks_placeholder(routing_reason):
        reasons.append("placeholder_routing_reason")

    conditional_sections = routing.get("conditional_sketch_sections")
    if not isinstance(conditional_sections, list):
        reasons.append("invalid_conditional_sketch_sections")
    else:
        for index, section in enumerate(conditional_sections):
            text = str(section).strip()
            if not text:
                reasons.append(f"blank_conditional_sketch_section:{index}")
            elif _looks_placeholder(text):
                reasons.append(f"placeholder_conditional_sketch_section:{index}")
            elif text.lower() not in CONDITIONAL_SKETCH_SECTION_LOOKUP:
                reasons.append(f"invalid_conditional_sketch_section:{index}:{text}")

    if isinstance(risk, Mapping):
        for field in RISK_FIELDS:
            value = str(risk.get(field, "")).strip().lower()
            if not value:
                reasons.append(f"missing_risk_field:{field}")
                continue
            if _looks_placeholder(value):
                reasons.append(f"placeholder_risk_field:{field}")
                continue
            if value not in RISK_VALUE_SET:
                reasons.append(f"invalid_risk_value:{field}:{value}")

    return list(dict.fromkeys(reasons))


def extract_spec_routing_contract(spec_text: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract the first valid routing contract block from spec markdown."""
    parse_reasons: list[str] = []
    section_text = _extract_markdown_section(spec_text, "Routing Contract")
    candidate_text = section_text or spec_text
    for match in JSON_FENCE_RE.finditer(candidate_text):
        body = match.group("body").strip()
        if not body:
            continue
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parse_reasons.append("routing_json_invalid")
            continue
        if not isinstance(parsed, dict):
            parse_reasons.append("routing_block_not_object")
            continue
        if "routing" not in parsed:
            parse_reasons.append("missing_routing_block")
            continue
        if "risk" not in parsed:
            parse_reasons.append("missing_risk_block")
            continue
        return normalize_spec_routing_contract(parsed), []

    if parse_reasons:
        return None, list(dict.fromkeys(parse_reasons))
    return None, ["missing_routing_block"]


def load_spec_routing_contract(spec_file: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Load and validate the routing contract from a spec file."""
    if not spec_file.exists():
        return None, ["missing_spec_file"]
    contract, parse_reasons = extract_spec_routing_contract(spec_file.read_text(encoding="utf-8"))
    if contract is None:
        return None, parse_reasons
    validation_reasons = validate_spec_routing_contract(contract)
    if validation_reasons:
        return contract, validation_reasons
    return contract, []


def extract_event_routing_contract(event: Mapping[str, Any]) -> dict[str, Any] | None:
    """Extract a routing contract mirrored into a pipeline event."""
    routing = event.get("routing")
    if not isinstance(routing, Mapping):
        return None
    risk = event.get("risk")
    contract = normalize_spec_routing_contract(
        {"routing": routing, "risk": risk if isinstance(risk, Mapping) else {}}
    )
    return contract
