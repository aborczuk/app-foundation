---
description: Deterministic plan generation from spec + research. Scaffold plan artifacts first, run gates, then hand off through the existing driver-backed planreview/feasibility flow.
model: opus
handoffs:
  - label: Create Checklist
    agent: speckit.checklist
    prompt: Create a checklist for the following domain...
    send: false
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

Produce `plan.md`, `data-model.md`, `quickstart.md`, and the plan-review / feasibility handoff for the current feature. Keep the output table-heavy, use deterministic gate scripts for validation, and let the existing pipeline driver own phase transitions and event sequencing instead of duplicating orchestration in shell snippets.

## Compact Contract (Load First)

Run these steps first; only load expanded guidance when a gate fails or the user asks for detail.

1. Run `.specify/scripts/bash/setup-plan.sh --json` from repo root and parse `FEATURE_SPEC`, `IMPL_PLAN`, `FEATURE_DIR`, and `BRANCH`.
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.
2. Derive `FEATURE_DIR="$(dirname "$FEATURE_SPEC")"` and run deterministic gates:
    - `uv run python scripts/speckit_gate_status.py --mode plan --feature-dir "$FEATURE_DIR" --json`
    - `uv run python scripts/speckit_plan_gate.py spec-core-action --spec-file "$FEATURE_SPEC" --legacy-ok --json`
    - `uv run python scripts/speckit_plan_gate.py research-prereq --feature-dir "$FEATURE_DIR" --spec-file "$FEATURE_SPEC" --json`
    - `uv run python scripts/speckit_plan_gate.py plan-sections --plan-file "$IMPL_PLAN" --spec-file "$FEATURE_SPEC" --json`
    - `uv run python scripts/speckit_plan_gate.py design-artifacts --feature-dir "$FEATURE_DIR" --json`
    - Start from the machine-readable routing contract in `spec.md`.
    - If `plan_profile=skip`, treat both research and plan-section gates as routed bypasses and hand off directly to `/speckit.sketch`.
    - If `plan_profile=lite`, require only the core plan sections plus any conditional sections actually triggered by the plan template.
    - If `plan_profile=full`, require the core plan plus the additional conditional sections the current feature truly needs; do not invent optional sections just to pad the artifact.
3. Scaffold plan artifacts immediately:
    - `uv run python .specify/scripts/pipeline-scaffold.py speckit.plan --feature-dir "$FEATURE_DIR" FEATURE_NAME="[Feature Name]"`
   - This creates `plan.md`, `data-model.md`, and `quickstart.md` from the manifest templates.
4. Fill the scaffolded artifacts using `spec.md`, the routing contract, `research.md` when required, and repo context with this mandatory read hierarchy:
    - Start from the machine-readable routing contract in `spec.md`; if it says research is skipped, do not require `research.md` to exist for gating.
    - First, run the read helpers (entrypoint):
      - Code: `source scripts/read-code.sh && read_code_context <file> <symbol_or_pattern> 80`
      - Markdown: `source scripts/read-markdown.sh && read_markdown_section <file> <section_heading>`
    - Helper behavior (internal order): semantic lookup first, then exact bounded read.
    - After the seam is anchored, run discovery checks (`codegraph` caller/callee/import blast radius).
   - Do not start with broad `codegraph` or grep sweeps unless helper-driven reads fail to locate the target.
5. Emit `plan_started`, then let the existing driver-backed flow continue to `/speckit.planreview`. If open feasibility questions remain, continue to `/speckit.feasibilityspike`. Emit `plan_approved` only after those sub-processes complete successfully.
6. On any non-zero gate result, route by reason code using `docs/governance/gate-reason-codes.yaml`.

## Expanded Guidance (Load On Demand)

### 1. Context to load

Read:
- `spec.md`
- `research.md` if present
- `constitution.md`
- the `plan.md` template that will be scaffolded

### 1a. Read hierarchy enforcement (MANDATORY)

For any repo code/doc claim included in `plan.md`:
- Start with helper-driven exact reads:
  - `read_code_context` / `read_code_window` for code
  - `read_markdown_section` for docs
- These helpers are semantic-first internally and return bounded, anchored reads.
- Run discovery checks (`codegraph`) only after the exact seam is confirmed.

This order is required for architecture decisions, risk reasoning, and any blast-radius statement.

## 2. Artifact shape

Keep the generated artifacts table-driven and compact:

- `plan.md`: architecture tables, gate statuses, state/reliability notes, constitution check, open feasibility questions, and the handoff contract to sketch
- `data-model.md`: entity/state tables only; keep prose minimal
- `quickstart.md`: runnable local steps, smoke test, common issues, and next steps

`plan.md` is routing-aware:

- Always emit the core plan sections from the current template.
- Emit conditional sections only when the selected `plan_profile` or the actual feature scope triggers them.
- If `plan_profile=skip`, do not force-fit a full plan body just to satisfy an outdated checklist.

### 3. Orchestration rules

- The pipeline driver already owns phase transitions and event sequencing.
- This command only fills the artifacts and uses the existing handoff flow.
- Do not spawn sub-agents for plan generation.
- Do not invent a second orchestration layer in shell snippets.
- Do not append JSONL ledger files directly; use `scripts/pipeline_ledger.py`.
- Do not use invented CLI flags; the scaffold command only accepts the manifest-defined artifact flow.

### 4. Plan content expectations

`plan.md` must stay proportional to the selected profile.

Always require the current template's core sections:

- Summary
- Plan Routing
- Existing Coverage and Reuse
- Handoff Contract to Sketch
- Plan Completion Summary

Conditional sections are only required when they are triggered by the feature and selected profile:

- Architecture Direction
- Technical Context
- Runtime / State / Contract Impact
- Artifact, Event, and Surface Impact
- External Ingress and Runtime Readiness
- Feasibility and Research Questions
- Human / Operator Boundary Check

When a section is uncertain, mark it clearly instead of inventing detail.

### 5. Driver-backed handoff

The existing workflow still includes `/speckit.planreview` and `/speckit.feasibilityspike`, but those are downstream handoffs, not ad hoc shell orchestration. If the current plan output or gates indicate a blocker, stop and report it instead of branching into custom shell loops.

## Local Validation

Run the smoke test to verify that the plan scaffold wiring still matches the manifest and command doc:

```bash
.specify/scripts/test-plan.sh feature_id=XYZ
```

The harness checks:
- the manifest template binding for `speckit.plan`
- the compact scaffold-first command doc contract
- the generated `plan.md`, `data-model.md`, and `quickstart.md` section headers

## Key Rules

- Use absolute paths
- ERROR on gate failures or unresolved clarifications
- Keep output table-heavy
- Pass the feature context once and reuse it
- Let the existing pipeline driver own orchestration
