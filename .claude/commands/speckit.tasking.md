# /speckit.tasking

## User Input

```text
$ARGUMENTS
```

## Contract

Act as the canonical interface between approved plan design slices and implementation tasks. Generate `tasks.md` from the approved `plan.md` / `spec.json` summary, explicitly design each task around a coherent implementation seam, then hand the draft to the generative estimate/breakdown step for stabilization.

1. Decompose each `plan.md` design slice into one or more seam-sized tasks in `tasks.md`.
2. Use the upstream Spec Kit `tasks.md` structure and add explicit acceptance criteria per user story.
3. Hand off to `/speckit.estimate`; it owns the estimate, breakdown, re-estimate loop, and finalization.
4. Require the generative step to enforce tasks format via `scripts/speckit_tasks_gate.py`.
5. Do not invoke the deterministic tasking chain or Codex runner from tasking.
6. Return only after `/speckit.estimate` reports the finalized task graph and event request.

## Guidance

### 1. Setup + hard-block gate

1. Run:
   - `.specify/scripts/python/check_prerequisites.py --json`
2. Resolve:
   - `FEATURE_DIR`
3. Require:
   - `FEATURE_DIR/plan.md`
   - `FEATURE_DIR/spec.json`
4. If any hard-block condition fails, stop.

### 2. Authoritative context loading

Required:
- `plan.md`
- `spec.json`
- `spec.md`
- `tasks.md` after initial generation

The canonical helper is `scripts/speckit_tasking_step.py`:

```bash
uv run python scripts/speckit_tasking_step.py prepare-tasking --feature-id "$FEATURE_ID"
```

After the generative seam design is complete, hand off to `/speckit.estimate`. That single generative skill owns the estimate/breakdown loop and runs the finalizer after the loop settles.

### 3. Task derivation rules (required)

- Read `spec.json` first; it holds the machine-readable key details of the approved plan/spec contract.
- Use the spec details, design slices, domains, risk, and tasking metadata from `spec.json` to derive the right task list shape and ordering.
- Derive tasks from plan contracts first; do not invent major architecture not present in plan.
- Preserve execution order and dependency rules from the approved design.
- Add `[H]` tasks only where explicit human/operator boundaries require them.
- Preserve command/script/template/manifest work as explicit tasks when present in the approved design.
- Keep task descriptions deterministic and implementation-usable.
- Treat each design slice's `Implementation Directive` as required source material for task generation.
- Solve each design slice before decomposing it into tasks; do not only restate the directive.
- Turn the solved slice-local implementation approach into story-grouped tasks, not a HUD replacement.
- Treat tasking as the interface between a plan slice and its implementation tasks: every task must name the coherent implementation seam it closes.
- Group tasks by coherent implementation seam, not by counting separate requirements on the same request path or file seam.
- If one seam carries multiple closely related requirements, prefer one task with richer story-level acceptance criteria over multiple tiny tasks that would force repeated ledger/QA/closeout overhead on the same seam.
- Do not split a single execution seam into separate tasks for routing, validation, and reporting unless they are truly independent closeout units with different files or dependency boundaries.
- Each user story phase must include `Goal`, `Independent Test`, and `Acceptance Criteria`.
- Each task line must contain a concrete action plus an exact file path.
- If a task cannot be described clearly enough to name the intended action and file path, mark tasking blocked and stop before acceptance generation.

### 3b. Minimum task contract (required)

For every non-`[H]` task, keep the task contract lightweight and upstream-aligned.

Each user story phase in `tasks.md` must include:

1. Goal
2. Independent Test
3. Acceptance Criteria

Each task line must include or make unambiguous:

1. task ID
2. optional `[P]` or `[H]`
3. required `[USn]` label in story phases
4. concrete action
5. exact file path
6. dependency note when ordering is not obvious from the phase layout

Acceptance criteria belong at the story phase level by default. Add task-local acceptance only when a specific task needs a stricter completion condition than the story-level criteria.

Do not require per-task sections for seams, touched symbols, current behavior, target behavior, required edits, or similar execution-packet detail.

### 4. Estimate/breakdown handoff (required)

- Invoke `/speckit.estimate` after `tasks.md` is authored.
- `/speckit.estimate` estimates `5` as one cohesive implementation seam.
- `/speckit.estimate` breaks down every `8` or `13` task and re-estimates until the current estimate has no 8/13 rows.
- Do not invoke the deterministic tasking chain from the tasking authoring step.

### 5. Tasks format gate (required)

- `/speckit.estimate` runs `scripts/speckit_tasks_gate.py` on the settled `tasks.md`.
- Any reported task-format issue must be fixed before finalization.

### 6. Task ledger registration (estimate-owned)

- `/speckit.estimate` registers tasks only after the task graph is settled and format-valid.

### 7. Acceptance generation (estimate-owned)

- `/speckit.estimate` scaffolds acceptance tests only after the stabilized, format-valid task graph exists.

### 8. Event + reporting

- Report `tasks.md` path and hand off to `/speckit.estimate` for task count, story count, acceptance scaffolding, finalization, and the `tasking_completed` event.

## Behavior rules

- Do not invent architecture that is absent from `plan.md`.
- Do not skip the estimate/breakdown stabilization loop.
- Do not estimate task size without recording the seam boundary and integration surface that justify the score.
- Do not bypass deterministic task-format validation.
- Do not skip task registration before reporting success.
- Do not emit tasks that rely on a separate per-task HUD or hidden execution packet.
- Do not require precomputed seams, touched symbols, current behavior, target behavior, or proposed-solution blocks in `tasks.md`.
- Keep `tasks.md` aligned to upstream Spec Kit shape, with acceptance criteria as the only material extension.
