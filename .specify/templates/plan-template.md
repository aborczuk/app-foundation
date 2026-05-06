# Combined Plan - [FEATURE_NAME]

_Feature: `[FEATURE_ID]`_
_Source Spec: `[SPEC_FILE_NAME]`_
_Artifact: `plan.md`_

[This template documents every section the combined `speckit.plan` step may keep. `scripts/speckit_plan_step.py` prunes unused sections after triage so the emitted `plan.md` contains only the sections required by strategy.]

## Triage

- duplicate: [true/false]
- t_shirt_size: [xs/s/m/l/xl]
- risk_level: [low/medium/high]
- reason: [Generative duplicate, LOE, and risk decision.]

## Strategy Contract

```json
{
  "domains": {
    "reasoning": {},
    "relevant": []
  },
  "risk": {
    "overall": "",
    "external_dependency_uncertainty": "",
    "human_operator_dependency": "",
    "repo_uncertainty": "",
    "requirement_clarity": "",
    "runtime_side_effect_risk": "",
    "state_data_migration_risk": ""
  },
  "strategy": {
    "architecture_diagram": false,
    "architecture_strategy": false,
    "expanded_design_notes": false,
    "external_research": false,
    "strategy_reason": ""
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

## Relevant Domains

[Kept for every non-duplicate plan. Record only the constitution domains that need explicit planning treatment, plus why they matter here.]

## Summary

[Kept for every non-duplicate plan. Summarize the chosen implementation path in proportion to triage.]

## Internal Research

[Kept for every non-duplicate plan. Capture only the repo-local findings required to justify the selected path.]

## External Research

[Kept only when routing requires outside evidence beyond repo-local discovery.]

## Architecture Strategy

[Kept when strategy requires architectural depth. Explain the architecture required for this scope and why it is necessary.]

## Architecture Diagram

[Kept only when routing requires an explicit architecture view. Prefer a compact mermaid diagram.]

## Expanded Design Notes

[Kept when sketch depth or risk justifies extra behavior, state, UX, or sequencing detail.]

## Design Slices

[Kept for every non-duplicate plan. Include at least one tasking-ready slice with a PL identifier, low/medium/high estimate, and an implementation directive.]

## Plan Completion Summary

[Used for both duplicate and non-duplicate paths. State the selected depth, why it was enough, and what the next phase should do.]
