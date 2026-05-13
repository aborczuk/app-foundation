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
   - Carry the solved slice, concrete symbols, and relevant constitution domains forward into the corresponding HUDs.
   - Preserve slice ordering and dependencies from `plan.md`.
   - Produce the actual number of tasks required by the plan; do not leave template placeholder content behind.

4. Scaffold HUDs deterministically, then complete them generatively:

```bash
uv run python scripts/speckit_remake_huds.py prepare --feature-dir "$FEATURE_DIR" --rewrite-existing
```

5. Fill every non-`[H]` `huds/TXXX.md` directly.
   - Load `spec.json` first; it contains the machine-readable key details of the approved plan/spec contract.
   - Treat the scaffold as deterministic seed data only.
   - For each task, write the slice-local proposed solution that this task will implement.
   - Attach each matched design slice to the task by translating the slice directive into task-specific obligations.
   - Name the exact file:symbol seams, touched symbols, relevant domains, constraints, and tests needed for that solution.
   - Write explicit task-local acceptance criteria into the HUD.
   - Replace every `[FILL: ...]` marker with repo-grounded, seam-specific implementation detail.
   - The final HUD must be concrete enough that a smaller implement model can execute the task without re-inventing design.
   - Assume `/speckit.implement` will read only this HUD for the task. If information is missing from the HUD, it does not exist for implement.

6. Run the estimate/breakdown loop through spawned subagents until the existing stabilization script reports the task graph is settled.
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

## Expanded Guidance (Load On Demand)

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
- Keep solutioning local to the slice: proposed behavior, symbols, branches, and checks must land in the tasks/HUDs that implement that slice.
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

### 5. HUD Scaffold + Generative Fill

- Now that the task list is settled, you must solve each task with a complete, ticket-like guidance that has 
for Every non-`[H]` HUD:

- Treat each HUD as the only implementation ticket the per-task implement subagent will read.

- Run `scripts/speckit_remake_huds.py prepare --feature-dir "$FEATURE_DIR" --rewrite-existing` after `tasks.md` is complete and estimate/breakdown is settled to create the scaffold templates.
- You must then fill every non-`[H]` HUD concretely using read-code.py plus `spec.json`, `plan.md`, `spec.md`, and `tasks.md`.
- Apply scaffold-preserving HUD edits with `scripts/speckit_fill_huds.py`; do not replace whole HUD files after scaffold generation.
- One by one, make the solution for each task with the parameters:
  - the proposed solution for the task
  - the matched slice directives attached and specialized into task-specific required edits
  - the exact symbols and seams the task will change
  - the relevant constitution domains that materially apply to the task
  - explicit task-local acceptance criteria
  - the concrete tests and invariants that make the solution safe to implement
  - and whatever the template asks for
- Do not leave scaffold placeholders in any final HUD.

### 6. Deterministic Finalize

`finalize` owns the deterministic post-generation chain:

- validation that estimate/breakdown stabilization already settled
- tasks format gate
- HUD validation
- task registration
- acceptance-test scaffolding

`finalize` must be the only place where the command produces the pipeline event request envelope.

### 7. Produce `solution_approved`

The command ends by running `finalize`. The final response from this command must be the exact JSON emitted by `finalize`, with no extra prose around it. That payload is what the pipeline driver uses to append `solution_approved`.

```json
{"event":"solution_approved","feature_id":"NNN","phase":"solution","task_count":N,"story_count":N,"estimate_points":N,"actor":"<agent-id>","timestamp_utc":"..."}
```

### 8. Report

- "Solution phase complete."
- List generated artifacts: `tasks.md`, `estimates.md`, HUDs, acceptance tests.
- Suggested next: `/speckit.implement`.

## Behavior Rules

- Do not re-decide architecture already settled in `plan.md`.
- Do not treat `scripts/speckit_remake_huds.py` output as the final HUD content for code tasks.
- Do not call `/speckit.tasking`.
- Do not treat `spec.json` as optional inspiration; it is the machine-readable summary of the approved plan/spec details that must feed task and HUD generation.
- Do not hand-roll `estimates.md`; use the `speckit.estimate` artifact contract declared in `command-manifest.yaml`.
- Do not emit `solution_approved` before `finalize` completes.
