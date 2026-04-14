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
2. Derive `FEATURE_DIR="$(dirname "$FEATURE_SPEC")"` and run deterministic gates:
    - `uv run python scripts/speckit_gate_status.py --mode plan --feature-dir "$FEATURE_DIR" --json`
    - `uv run python scripts/speckit_plan_gate.py spec-core-action --spec-file "$FEATURE_SPEC" --legacy-ok --json`
    - `uv run python scripts/speckit_plan_gate.py research-prereq --feature-dir "$FEATURE_DIR" --json`
    - `uv run python scripts/speckit_plan_gate.py plan-sections --plan-file "$IMPL_PLAN" --json`
    - `uv run python scripts/speckit_plan_gate.py design-artifacts --feature-dir "$FEATURE_DIR" --json`
3. Scaffold plan artifacts immediately:
    - `uv run python .specify/scripts/pipeline-scaffold.py speckit.plan --feature-dir "$FEATURE_DIR" FEATURE_NAME="[Feature Name]"`
   - This creates `plan.md`, `data-model.md`, and `quickstart.md` from the manifest templates.
4. Fill the scaffolded artifacts using `spec.md`, `research.md`, and repo context. Keep `plan.md` table-heavy and use it as the source of truth for architecture decisions, gates, and the sketch handoff contract.
5. Emit `plan_started`, then let the existing driver-backed flow continue to `/speckit.planreview`. If open feasibility questions remain, continue to `/speckit.feasibilityspike`. Emit `plan_approved` only after those sub-processes complete successfully.
6. On any non-zero gate result, route by reason code using `docs/governance/gate-reason-codes.yaml`.

## Expanded Guidance (Load On Demand)

### 1. Context to load

Read:
- `spec.md`
- `research.md` if present
- `constitution.md`
- the `plan.md` template that will be scaffolded

## 2. Artifact shape

Keep the generated artifacts table-driven and compact:

- `plan.md`: architecture tables, gate statuses, state/reliability notes, constitution check, open feasibility questions, and the handoff contract to sketch
- `data-model.md`: entity/state tables only; keep prose minimal
- `quickstart.md`: runnable local steps, smoke test, common issues, and next steps

### 3. Orchestration rules

- The pipeline driver already owns phase transitions and event sequencing.
- This command only fills the artifacts and uses the existing handoff flow.
- Do not spawn sub-agents for plan generation.
- Do not invent a second orchestration layer in shell snippets.
- Do not append JSONL ledger files directly; use `scripts/pipeline_ledger.py`.
- Do not use invented CLI flags; the scaffold command only accepts the manifest-defined artifact flow.

### 4. Plan content expectations

`plan.md` must stay table-heavy. The important sections are:

- Summary
- Technical Context
- Reuse-First Architecture Decision
- Pipeline Architecture Model
- Artifact / Event Contract Architecture
- Architecture Flow
- External Ingress + Runtime Readiness Gate
- State / Storage / Reliability Model
- Constitution Check
- Behavior Map Sync Gate
- Open Feasibility Questions
- Handoff Contract to Sketch

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
