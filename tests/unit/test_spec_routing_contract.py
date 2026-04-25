"""Unit tests for the spec-driven routing contract helpers and gate."""

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


spec_routing = _load_script_module("spec_routing", "spec_routing.py")
speckit_spec_gate = _load_script_module("speckit_spec_gate", "speckit_spec_gate.py")


def test_extract_spec_routing_contract_parses_and_normalizes_contract() -> None:
    spec_text = """
    # Example

    ```json
    {
      "routing": {
        "research_route": "SKIP",
        "plan_profile": "FULL",
        "sketch_profile": "CORE",
        "tasking_route": "required",
        "estimate_route": "required_after_tasking",
        "routing_reason": "Repo-local implementation change.",
        "conditional_sketch_sections": ["Implementation Directive"]
      },
      "risk": {
        "requirement_clarity": "Low",
        "repo_uncertainty": "Medium",
        "external_dependency_uncertainty": "low",
        "state_data_migration_risk": "low",
        "runtime_side_effect_risk": "low",
        "human_operator_dependency": "low"
      }
    }
    ```
    """

    contract, reasons = spec_routing.extract_spec_routing_contract(spec_text)

    assert reasons == []
    assert contract is not None
    assert contract["routing"]["research_route"] == "skip"
    assert contract["routing"]["plan_profile"] == "full"
    assert contract["routing"]["sketch_profile"] == "core"
    assert contract["routing"]["conditional_sketch_sections"] == ["Implementation Directive"]
    assert contract["risk"]["requirement_clarity"] == "low"
    assert contract["risk"]["repo_uncertainty"] == "medium"


def test_validate_routing_gate_accepts_complete_contract(tmp_path: Path) -> None:
    spec_file = tmp_path / "spec.md"
    spec_file.write_text(
        "\n".join(
            [
                "# Spec",
                "",
                "```json",
                "{",
                '  "routing": {',
                '    "research_route": "skip",',
                '    "plan_profile": "skip",',
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

    exit_code, payload = speckit_spec_gate._validate_routing(spec_file)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["reasons"] == []
    assert payload["routing"]["plan_profile"] == "skip"
    assert payload["risk"]["repo_uncertainty"] == "low"


def test_validate_routing_gate_reports_missing_block(tmp_path: Path) -> None:
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# Spec\n\nNo routing block here.\n", encoding="utf-8")

    exit_code, payload = speckit_spec_gate._validate_routing(spec_file)

    assert exit_code != 0
    assert payload["ok"] is False
    assert "missing_routing_block" in payload["reasons"]
