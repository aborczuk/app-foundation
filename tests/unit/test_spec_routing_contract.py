"""Unit tests for spec routing contract parsing helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module(module_name: str, script_name: str):
    """Import a script module from the repo-local scripts directory."""
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


def test_extract_spec_routing_contract_parses_and_normalizes_contract() -> None:
    """Parsing should normalize routing values and section names."""
    spec_text = """
    # Example

    ## Routing Contract

    ```json
    {
      "routing": {
        "research_route": "SKIP",
        "plan_profile": "FULL",
        "sketch_profile": "CORE",
        "tasking_route": "required",
        "estimate_route": "required_after_tasking",
        "routing_reason": "Repo-local implementation change.",
        "conditional_sketch_sections": ["repo grounding"]
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
    assert contract["routing"]["conditional_sketch_sections"] == ["Repo Grounding"]
    assert contract["risk"]["requirement_clarity"] == "low"
    assert contract["risk"]["repo_uncertainty"] == "medium"


def test_extract_spec_routing_contract_prefers_routing_contract_section() -> None:
    """The explicit routing contract section should override earlier JSON blocks."""
    spec_text = """
    # Example

    ```json
    {
      "routing": {
        "research_route": "[Skip / Required]",
        "plan_profile": "[Skip / Lite / Full]",
        "sketch_profile": "[Core / Expanded]",
        "tasking_route": "[Required / Attach]",
        "estimate_route": "[Required / Reuse]",
        "routing_reason": "[Why]",
        "conditional_sketch_sections": []
      },
      "risk": {
        "requirement_clarity": "[Low / Medium / High]",
        "repo_uncertainty": "[Low / Medium / High]",
        "external_dependency_uncertainty": "[Low / Medium / High]",
        "state_data_migration_risk": "[Low / Medium / High]",
        "runtime_side_effect_risk": "[Low / Medium / High]",
        "human_operator_dependency": "[Low / Medium / High]"
      }
    }
    ```

    ## Routing Contract

    ```json
    {
      "routing": {
        "research_route": "skip",
        "plan_profile": "lite",
        "sketch_profile": "core",
        "tasking_route": "required",
        "estimate_route": "required_after_tasking",
        "routing_reason": "Use the smaller routed path.",
        "conditional_sketch_sections": ["Repo Grounding"]
      },
      "risk": {
        "requirement_clarity": "low",
        "repo_uncertainty": "low",
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
    assert contract["routing"]["plan_profile"] == "lite"
    assert contract["routing"]["routing_reason"] == "Use the smaller routed path."
