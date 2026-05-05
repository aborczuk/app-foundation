---
description: Deterministic plan generation from spec + research. Scaffold plan artifacts first, write the routing contract in plan.md, run gates, then hand off through the existing driver-backed planreview/feasibility flow.
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

1. Run `.specify/scripts/python/setup_plan.py --json` from repo root and parse `FEATURE_SPEC`, `IMPL_PLAN`, `FEATURE_DIR`, and `BRANCH`.
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.
2. Derive `FEATURE_DIR="$(dirname "$FEATURE_SPEC")"` and run deterministic gates:
    - `uv run python scripts/speckit_gate_status.py --mode plan --feature-dir "$FEATURE_DIR" --json`
    - `uv run python scripts/speckit_plan_gate.py spec-core-action --spec-file "$FEATURE_SPEC" --legacy-ok --json`
    - `uv run python scripts/speckit_plan_gate.py research-prereq --feature-dir "$FEATURE_DIR" --spec-file "$FEATURE_SPEC" --json`
    - `uv run python scripts/speckit_plan_gate.py plan-sections --plan-file "$IMPL_PLAN" --spec-file "$FEATURE_SPEC" --json`
    - `uv run python scripts/speckit_plan_gate.py design-artifacts --feature-dir "$FEATURE_DIR" --json`
    - Start from the machine-readable routing contract in `plan.md`.
    - `research.md` is required input before plan begins; the research gate should only check the artifact, not decide whether research is needed.
    - If `plan_profile=skip`, treat plan-section gates as routed bypasses and hand off directly to `/speckit.sketch`.
    - If `plan_profile=lite`, require only the core plan sections plus any conditional sections actually triggered by the plan template.
    - If `plan_profile=full`, require the core plan plus the additional conditional sections the current feature truly needs; do not invent optional sections just to pad the artifact.
    - Resolve `sketch_profile` in `plan.md` as part of the plan handoff; sketch consumes that decision to determine how deep the repo grounding needs to go.
3. Scaffold plan artifacts immediately:
    - `uv run python .specify/scripts/pipeline-scaffold.py speckit.plan --feature-dir "$FEATURE_DIR" FEATURE_NAME="[Feature Name]"`
   - This creates `plan.md`, `data-model.md`, and `quickstart.md` from the manifest templates.
4. Fill the scaffolded artifacts using `spec.md` requirements, `research.md` patterns, and the routing contract written into `plan.md`:
    - Start from `spec.md` requirements, `research.md` patterns, and the routing contract written into `plan.md`.
    - Keep the plan focused on sizing, architecture direction, reuse, and sketch handoff decisions.
    - Defer repo-grounding, touched-file discovery, implementation-seam mapping, and blast-radius detail to `/speckit.sketch`.
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
- Start with `scripts/read_code.py context` as the default lookup mode for natural-language descriptions, symbols, strings, Markdown artifacts, or the best matching seam.
- `context` can resolve Markdown too. When you already know the document, use `read_markdown_headings` first, then `read_markdown_section` with the exact heading title to keep the read bounded.
- Use `find` only when you need exact structural matches or to enumerate known symbols, patterns, or text.
- Use `analyze` after a candidate is identified and you need callers, callees, dependencies, or structural context.
- Treat `command-manifest.yaml` and `.claude/commands/` as the authoritative locations for command behavior, routing, and workflow ownership.

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
.specify/scripts/test_plan.py feature_id=XYZ
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
