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

## Contract

Use [`scripts/speckit_solution_step.py`](/Users/andreborczuk/app-foundation/scripts/speckit_solution_step.py) only as a local scaffold and validation helper.

1. Run the scaffold helper:

```bash
uv run python scripts/speckit_solution_step.py prepare-tasking --feature-id "$FEATURE_ID"
```

2. Open `tasks.md`.
   - Treat `plan.md` and its `## Design Slices` section as the authoritative source of solutioning.
   - Solve each design slice before writing tasks. Do not only restate the slice title or directive.
   - Decompose the plan slices directly into `tasks.md`.

3. Fill `tasks.md` directly.
   - For each design slice, write the actual proposed solution first, then split that solution into the required tasks.
   - Anchor every non-human task to a concrete file or symbol seam from the plan.
   - Carry the solved slice, concrete symbols, and relevant constitution domains forward into the corresponding task entries.
   - Preserve slice ordering and dependencies from `plan.md`.
   - Produce the actual number of tasks required by the plan; do not leave template placeholder content behind.

4. Run the estimate/breakdown loop through spawned subagents until the existing stabilization script reports the task graph is settled.
   - Spawn an `estimate` subagent on `gpt-5.4-mini`.
   - Use `spawn_agent`.
   - Do not use `fork_context: true`.
   - Pass a focused prompt and the specific file references the subagent needs.
   - Set `model: gpt-5.4-mini`.
   - Use the `speckit.estimate` command contract and its manifest-declared estimate artifact/template; do not invent an ad hoc `estimates.md` shape during solution.
   - Instruct it to execute `/speckit.estimate` for this feature and report whether any tasks remain at `8` or `13`.
   - If any high-point tasks remain, spawn a `breakdown` subagent on `gpt-5.4-mini`.
   - Use `spawn_agent`.
   - Do not use `fork_context: true`.
   - Pass a focused prompt and the specific file references the subagent needs.
   - Set `model: gpt-5.4-mini`.
   - Instruct it to execute `/speckit.breakdown` for this feature, then loop back to a fresh `estimate` subagent.
   - After each pass, validate the settled state with:

```bash
uv run --no-sync python scripts/speckit_tasking_chain.py --feature-dir "$FEATURE_DIR" --json
```

   - Continue the loop until that command returns `"ok": true`.
   - Do not call `scripts/speckit_tasking_codex_runner.py` from `solution`.

7. Run finalize and return the exact JSON it prints:

```bash
uv run python scripts/speckit_solution_step.py finalize --feature-id "$FEATURE_ID" --phase solution --correlation-id "$CORRELATION_ID"
```

## Guidance

### 1. Setup

The helper script resolves the feature workspace, validates that `plan.md` exists, requires `## Design Slices`, and scaffolds `tasks.md` from the documented tasks template.
It also expects `spec.json` from `/speckit.plan` to be present as the stable machine-readable summary of the approved plan/spec details.

### 2. Hard-block gate

- Read `plan.md`.
- If `## Design Slices` is missing, stop and route back to `/speckit.plan`.
- If any slice lacks an implementation directive, stop and route back to `/speckit.plan`.

### 3. Direct Task Generation

- Decompose approved `plan.md` design slices into `tasks.md` directly in this command.
- Solve each slice before turning it into tasks. A task list without the solved implementation approach is incomplete.
- Write tasks from the solved slice, not from a restated headline.
- Anchor every non-human task to a concrete file/symbol seam from the design slice.
- Keep solutioning local to the slice: proposed behavior, symbols, branches, and checks must land in the `tasks.md` entries that implement that slice.
- Preserve slice ordering and dependencies from the plan.

### 4. Estimate / Breakdown Loop

- Now that there are clear tasks from the plan, what is needed is that the tasks are small enough to be done as a unit of work. So they need Estimates and if they are too large, they need to be broken down.

To do that:
- Create a spawned subagent on `gpt-5.4-mini` with the command instructions from `/speckit.estimate` 
- Use `spawn_agent`.
- Do not use `fork_context: true`.
- Pass a focused prompt and the specific file references the subagent needs.
- Set `model: gpt-5.4-mini`.
- If the estimate is above 8/13 for any task, create another spawned sub agent for `/speckit.breakdown` to break it down
- Use `spawn_agent`.
- Do not use `fork_context: true`.
- Pass a focused prompt and the specific file references the subagent needs.
- Set `model: gpt-5.4-mini`.
- Then pass the breakdown tasks back to estimate to estimate agiain
- Keep looping until `scripts/speckit_tasking_chain.py --feature-dir "$FEATURE_DIR" --json` reports `"ok": true`.
- Treat that script as the settled-state validator for the existing estimate/breakdown workflow.

### 5. Deterministic Finalize

`finalize` owns the deterministic post-generation chain:

- validation that estimate/breakdown stabilization already settled
- tasks format gate
- task registration
- acceptance-test scaffolding

`finalize` must be the only place where the command produces the pipeline event request envelope.

### 6. Produce `solution_approved`

The command ends by running `finalize`. The final response from this command must be the exact JSON emitted by `finalize`, with no extra prose around it. That payload is what the pipeline driver uses to append `solution_approved`.

```json
{"event":"solution_approved","feature_id":"NNN","phase":"solution","task_count":N,"story_count":N,"estimate_points":N,"actor":"<agent-id>","timestamp_utc":"..."}
```

### 7. Report

- "Solution phase complete."
- List generated artifacts: `tasks.md`, `estimates.md`, acceptance tests.
- Suggested next: `/speckit.implement`.

## Behavior rules

- Do not re-decide architecture already settled in `plan.md`.
- Do not leave executable tasks under-specified; `/speckit.implement` must be able to execute from `tasks.md`, `plan.md`, and `spec.json` without a per-task HUD file.
- Do not call `/speckit.tasking`.
- Do not treat `spec.json` as optional inspiration; it is the machine-readable summary of the approved plan/spec details that must feed task generation.
- Do not hand-roll `estimates.md`; use the `speckit.estimate` artifact contract declared in `command-manifest.yaml`.
- Do not emit `solution_approved` before `finalize` completes.
