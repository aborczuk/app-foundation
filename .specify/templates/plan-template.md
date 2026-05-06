# Combined Plan - [FEATURE_NAME]

_Feature: `[FEATURE_ID]`_
_Source Spec: `spec.md`_
_Artifact: `plan.md`_

## Triage

- duplicate: [true/false]
- t_shirt_size: [xs/s/m/l/xl]
- risk_level: [low/medium/high]
- reason: [Generative duplicate, LOE, and risk decision.]

## Routing Contract

```json
{
  "risk": {
    "external_dependency_uncertainty": "",
    "human_operator_dependency": "",
    "repo_uncertainty": "",
    "requirement_clarity": "",
    "runtime_side_effect_risk": "",
    "state_data_migration_risk": ""
  },
  "routing": {
    "architecture_diagram": false,
    "external_research": false,
    "plan_level": "",
    "routing_reason": "",
    "sketch_level": ""
  },
  "triage": {
    "duplicate": false,
    "duplicate_matches": [],
    "duplicate_reason": "",
    "risk_level": "",
    "tshirt_size": ""
  }
}
```

## Internal Discovery

[Filled by `scripts/speckit_plan_step.py` before generative triage.]

## Plan Completion Summary

[The combined plan step replaces separate discovery.md, research.md, and sketch.md artifacts. The script will rewrite this scaffold with only the sections selected by triage.]
