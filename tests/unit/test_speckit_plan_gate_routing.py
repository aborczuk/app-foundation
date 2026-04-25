"""Unit tests for routing-aware /speckit.plan gates."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module(module_name: str, script_name: str):
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


speckit_plan_gate = _load_script_module("speckit_plan_gate", "speckit_plan_gate.py")


def _write_spec(spec_file: Path, *, research_route: str, plan_profile: str) -> None:
    spec_file.write_text(
        "\n".join(
            [
                "# Spec",
                "",
                "## Routing Contract",
                "",
                "```json",
                "{",
                '  "routing": {',
                f'    "research_route": "{research_route}",',
                f'    "plan_profile": "{plan_profile}",',
                '    "sketch_profile": "core",',
                '    "tasking_route": "required",',
                '    "estimate_route": "required_after_tasking",',
                '    "routing_reason": "Repo-local tasking/HUD behavior change using existing architecture.",',
                '    "conditional_sketch_sections": []',
                "  },",
                '  "risk": {',
                '    "requirement_clarity": "low",',
                '    "repo_uncertainty": "low",',
                '    "external_dependency_uncertainty": "low",',
                '    "state_data_migration_risk": "low",',
                '    "runtime_side_effect_risk": "low",',
                '    "human_operator_dependency": "low"',
                "  }",
                "}",
                "```",
            ]
        ),
        encoding="utf-8",
    )


def _write_core_plan(plan_file: Path) -> None:
    plan_file.write_text(
        "\n".join(
            [
                "# Implementation Plan",
                "",
                "## Summary",
                "",
                "## Plan Routing",
                "",
                "## Existing Coverage and Reuse",
                "",
                "## Handoff Contract to Sketch",
                "",
                "## Plan Completion Summary",
            ]
        ),
        encoding="utf-8",
    )


def test_research_prereq_skips_when_plan_is_skipped(tmp_path: Path) -> None:
    feature_dir = tmp_path / "feature"
    feature_dir.mkdir()
    spec_file = feature_dir / "spec.md"
    _write_spec(spec_file, research_route="skip", plan_profile="skip")

    exit_code, payload = speckit_plan_gate._research_prereq_with_spec(feature_dir, spec_file)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["reasons"] == ["plan_skipped_by_routing"]
    assert payload["routing_contract"]["routing"]["plan_profile"] == "skip"


def test_research_prereq_requires_research_when_routing_says_required(
    tmp_path: Path,
) -> None:
    feature_dir = tmp_path / "feature"
    feature_dir.mkdir()
    spec_file = feature_dir / "spec.md"
    _write_spec(spec_file, research_route="required", plan_profile="full")

    exit_code, payload = speckit_plan_gate._research_prereq_with_spec(feature_dir, spec_file)

    assert exit_code != 0
    assert payload["ok"] is False
    assert "missing_research_md" in payload["reasons"]


def test_plan_sections_accepts_core_lite_plan(tmp_path: Path) -> None:
    feature_dir = tmp_path / "feature"
    feature_dir.mkdir()
    spec_file = feature_dir / "spec.md"
    plan_file = feature_dir / "plan.md"
    _write_spec(spec_file, research_route="skip", plan_profile="lite")
    _write_core_plan(plan_file)

    exit_code, payload = speckit_plan_gate._plan_sections(plan_file, spec_file)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["missing_sections"] == []
    assert payload["plan_profile"] == "lite"


def test_plan_sections_bypass_when_plan_is_skipped(tmp_path: Path) -> None:
    feature_dir = tmp_path / "feature"
    feature_dir.mkdir()
    spec_file = feature_dir / "spec.md"
    plan_file = feature_dir / "plan.md"
    _write_spec(spec_file, research_route="skip", plan_profile="skip")

    exit_code, payload = speckit_plan_gate._plan_sections(plan_file, spec_file)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["reasons"] == ["plan_skipped_by_routing"]
    assert payload["plan_profile"] == "skip"
