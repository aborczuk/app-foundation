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

This is a normal command-file workflow. Do not call `scripts/speckit_codex_handoff_runner.py`, do not create a nested Codex subrunner, and do not auto-invoke `/speckit.tasking`.

Use [`scripts/speckit_solution_step.py`](/Users/andreborczuk/app-foundation/scripts/speckit_solution_step.py) only as a local scaffold and validation helper.

1. Run the scaffold helper:

```bash
uv run python scripts/speckit_solution_step.py prepare-tasking --feature-id "$FEATURE_ID"
```

2. Open `tasks.md`.
   - Treat `plan.md` and its `## Design Slices` section as the authoritative source of solutioning.
   - Do not generate or require `sketch.md`.
   - Decompose the plan slices directly into `tasks.md`.

3. Fill `tasks.md` directly.
   - Anchor every non-human task to a concrete file or symbol seam from the plan.
   - Preserve slice ordering and dependencies from `plan.md`.
   - Produce the actual number of tasks required by the plan; do not leave template placeholder content behind.

4. Run finalize and return the exact JSON it prints:

```bash
uv run python scripts/speckit_solution_step.py finalize --feature-id "$FEATURE_ID" --phase solution --correlation-id "$CORRELATION_ID"
```

## Expanded Guidance (Load On Demand)

### 1. Setup

The helper script resolves the feature workspace, validates that `plan.md` exists, requires `## Design Slices`, and scaffolds `tasks.md` from the documented tasks template.

### 2. Hard-block gate

- Read `plan.md`.
- If `## Design Slices` is missing, stop and route back to `/speckit.plan`.
- If any slice lacks an implementation directive, stop and route back to `/speckit.plan`.

### 3. Direct Task Generation

- Decompose approved `plan.md` design slices into `tasks.md` directly in this command.
- Anchor every non-human task to a concrete file/symbol seam from the design slice.
- Preserve slice ordering and dependencies from the plan.
- Do not call `/speckit.tasking` as a nested command.

### 4. Deterministic Finalize

`finalize` owns the deterministic post-generation chain:

- estimate/breakdown stabilization
- tasks format gate
- task registration
- HUD regeneration
- acceptance-test scaffolding

`finalize` must be the only place where the command produces the pipeline event request envelope.

### 5. Produce `solution_approved`

The command ends by running `finalize`. The final response from this command must be the exact JSON emitted by `finalize`, with no extra prose around it. That payload is what the pipeline driver uses to append `solution_approved`.

```json
{"event":"solution_approved","feature_id":"NNN","phase":"solution","task_count":N,"story_count":N,"estimate_points":N,"actor":"<agent-id>","timestamp_utc":"..."}
```

### 6. Report

- "Solution phase complete."
- List generated artifacts: `tasks.md`, `estimates.md`, HUDs, acceptance tests.
- Suggested next: `/speckit.implement`.

## Behavior Rules

- Do not generate `sketch.md`.
- Do not require `sketch.md`.
- Do not re-decide architecture already settled in `plan.md`.
- Do not call `/speckit.tasking`.
- Do not emit `solution_approved` before `finalize` completes.
