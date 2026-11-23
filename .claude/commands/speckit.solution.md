# /speckit.solution

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

> **Legacy compatibility:** `/speckit.tasking` is now the canonical interface between plan design slices and implementation tasks. Use this command only to replay or support older solution-phase histories; it is not part of the canonical pathway.

## Contract

Use [`scripts/speckit_solution_step.py`](/Users/andreborczuk/app-foundation/scripts/speckit_solution_step.py) only as a local scaffold and validation helper.

1. Run the scaffold helper:

```bash
uv run python scripts/speckit_solution_step.py prepare-tasking --feature-id "$FEATURE_ID"
```

2. Open `tasks.md`.
   - Treat `plan.md` and its `## Design Slices` section as the authoritative source of solutioning.
   - Solve each design slice before writing tasks. Do not only restate the slice title or directive.
   - Write `tasks.md` entries that implement that slice.
   - Decompose the plan slices directly into the upstream Spec Kit `tasks.md` structure.

3. Fill `tasks.md` directly.
   - Organize tasks by phase and user story using the upstream template shape.
   - Preserve story priority, slice ordering, and dependencies from `plan.md`.
   - Add a `### Acceptance Criteria` section under each user story phase.
   - Keep task lines concise, with exact file paths in each task description.
   - Carry forward only the detail needed to execute the task list: goal, independent test, acceptance criteria, task lines, dependencies, and parallel markers.
   - Produce the actual number of tasks required by the plan; do not leave template placeholder content behind.

4. Hand the task draft to `/speckit.estimate`.
   - `/speckit.estimate` is the single generative estimate/breakdown step.
   - It estimates tasks by seam, breaks down multi-seam `8` or `13` tasks, re-estimates, and repeats until the graph is settled.
   - It runs finalization directly; do not invoke the deterministic tasking chain, Codex runner, or a separate breakdown agent from `solution`.

5. Do not finalize from `solution`; `/speckit.estimate` finalizes the settled task graph and emits the tasking completion request.

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
- Convert the solved slice into upstream-style phase and story tasks rather than a per-task execution packet.
- Add story-level `Acceptance Criteria` sections that reflect the approved spec outcomes for that story.
- Keep task descriptions concrete and executable, but do not force precomputed seams, touched symbols, or current/target behavior blocks into `tasks.md`.
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
- Then pass the breakdown tasks back to estimate to estimate again
- Keep looping until `scripts/speckit_tasking_chain.py --feature-dir "$FEATURE_DIR" --json` reports `"ok": true`.
- Treat that script as the settled-state validator for the existing estimate/breakdown workflow.

### 5. Deterministic Finalize

`finalize` owns the deterministic post-generation chain:

- validation that estimate/breakdown stabilization already settled
- tasks format gate
- task registration
- acceptance-test scaffolding

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
- Do not leave executable tasks vague; each task must still name the intended action and exact file path.
- `/speckit.implement` should execute from `tasks.md`, `plan.md`, and `spec.json` without a per-task HUD file.
- Do not call `/speckit.tasking`.
- Do not treat `spec.json` as optional inspiration; it is the machine-readable summary of the approved plan/spec details that must feed task generation.
- Do not hand-roll `estimates.md`; use the `speckit.estimate` artifact contract declared in `command-manifest.yaml`.
- Do not emit `solution_approved` before `finalize` completes.
- Do not require per-task sections for seams, touched symbols, current behavior, target behavior, or similar execution-packet detail in `tasks.md`.
