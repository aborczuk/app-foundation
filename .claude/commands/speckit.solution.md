---
description: Solution phase. Decompose approved plan.md design slices into tasking artifacts and produce the solution_approved payload.
model: opus
handoffs:
  - label: Begin Implementation
    agent: speckit.implement
    prompt: Solution phase complete. Begin implementation.
    send: false
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Compact Contract (Load First)

Top-level tasking approval phase. Consume `plan.md` design slices and produce `solution_approved`.

- Resolve `FEATURE_DIR`, `IMPL_PLAN`, and `AVAILABLE_DOCS` from the feature workspace.
- Require `plan.md` and its `## Design Slices` section.
- Treat `plan.md` as the source of solutioning; do not generate or require `sketch.md`.
- Preserve the downstream handoff contract that yields `solution_approved` for pipeline orchestration.

## Expanded Guidance (Load On Demand)

### 1. Setup

Run `.specify/scripts/python/check_prerequisites.py --json` from repo root. Parse `FEATURE_DIR`, `IMPL_PLAN`, and `AVAILABLE_DOCS`.

### 2. Hard-block gate

- Read `plan.md`.
- If `## Design Slices` is missing, stop and route back to `/speckit.plan`.
- If any slice lacks an implementation directive, stop and route back to `/speckit.plan`.

### 3. Auto-invoke `/speckit.tasking`

- Decompose approved `plan.md` design slices into `tasks.md`.
- Anchor every non-human task to a concrete file/symbol seam from the design slice.
- Preserve slice ordering and dependencies from the plan.
- Run the estimate/breakdown subprocess loop to settle points.
- Run the deterministic tasks format gate.
- Register tasks, generate HUDs, and scaffold acceptance tests only after stabilization.

### 4. Produce `solution_approved`

The command doc describes the `solution_approved` payload only. The deterministic solution script records required tasking/solution events through the approved ledger helper path.

```json
{"event":"solution_approved","feature_id":"NNN","phase":"solution","task_count":N,"story_count":N,"estimate_points":N,"actor":"<agent-id>","timestamp_utc":"..."}
```

### 5. Report

- "Solution phase complete."
- List generated artifacts: `tasks.md`, `estimates.md`, HUDs, acceptance tests.
- Suggested next: `/speckit.implement`.

## Behavior Rules

- Do not generate `sketch.md`.
- Do not require `sketch.md`.
- Do not re-decide architecture already settled in `plan.md`.
- Do not emit `solution_approved` before tasking stabilization completes.
