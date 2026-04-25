# /speckit.tasking

## User Input

```text
$ARGUMENTS
```

## Compact Contract (Load First)

Generate `tasks.md` from an approved `sketch.md` and stabilize the downstream task graph with deterministic script-owned checks.

Respect the spec routing contract throughout this command:

- `plan.md` is required only when `plan_profile != skip`.
- The core sketch sections are sufficient when `sketch_profile = core`.

1. Decompose `sketch.md` into `tasks.md` (authoritative source: the routed sketch design contract, including slices only when present).
2. Run deterministic estimate/breakdown stabilization through `scripts/speckit_tasking_chain.py`.
3. Enforce tasks format via `scripts/speckit_tasks_gate.py`.
4. Generate/hydrate HUDs via scaffold + `scripts/speckit_remake_huds.py`.
5. Generate acceptance tests from the settled task graph.

## Expanded Guidance (Load On Demand)

### 1. Setup + hard-block gate

1. Run:
   - `.specify/scripts/bash/check-prerequisites.sh --json`
2. Resolve:
   - `FEATURE_DIR`
   - `AVAILABLE_DOCS`
3. Require:
   - `FEATURE_DIR/sketch.md`
   - passing sketch review (`solutionreview_completed` with `critical_count == 0`)
4. If any hard-block condition fails, stop.

### 2. Authoritative context loading

Required:
- `sketch.md`
- `spec.md`

Optional:
- `plan.md` when `plan_profile != skip`
- `research.md`
- `catalog.yaml`
- `command-manifest.yaml`

When deriving tasks, treat the current sketch template's core sections as authoritative:
- `Coverage`
- `Current → Target`
- `Primary Seam`
- `Required Edit / Solution`
- `Verification`
- `Constraints / Preserve`
- `Implementation Directive`
- `Design-to-Tasking Contract`
- `Sketch Completion Summary`

Treat conditional sketch sections as authoritative only when they are present or explicitly enabled by `conditional_sketch_sections`.

### 3. Task derivation rules (required)

- Read the routing contract from `spec.md` first; use `sketch_profile` and `conditional_sketch_sections` to decide how much of the sketch must be turned into tasks and HUDs.
- Do not require `plan.md` or omitted conditional sketch sections when the routing contract intentionally selected the smaller path.
- Use `tasking_route` to decide whether each non-`[H]` task needs a fresh HUD or attaches to an existing feature stream.
- Derive tasks from sketch contracts first; do not invent major architecture not present in sketch.
- Preserve execution order and dependency rules from sketch + tasks graph.
- Add `[H]` tasks only where sketch/operator boundaries explicitly require human action.
- Keep each task anchored to actionable file/symbol seams.
- Preserve command/script/template/manifest work as explicit tasks when present in sketch.
- Keep task descriptions deterministic and implementation-usable (no vague placeholders).
- Treat each sketch slice's `Implementation Directive` as required source material for task/HUD generation.
- Do not emit a non-`[H]` task unless the associated HUD can be filled with current behavior, target behavior, concrete required edits, touched symbols, tests, constraints, dependencies, and done criteria.
- Task descriptions may remain concise, but the corresponding HUD must contain the implementation-ready ticket detail.
- If a task cannot be hydrated into a concrete HUD from `sketch.md` plus bounded repo reads, mark that HUD `BLOCKED: insufficient implementation directive` and stop before acceptance generation.

### 3b. HUD / implementation-ticket requirements (required)

For every non-`[H]` task, generate or update `${FEATURE_DIR}/huds/TXXX.md` using `.specify/templates/hud-code-template.md`.

Each code HUD is the authoritative implementation ticket for its task. It must be concrete enough that `/speckit.implement` can execute the task without rereading the full sketch or inventing design.

Each code HUD must fill all required `[FILL: ...]` fields from the HUD template and must not leave any `[EXAMPLE: ...]` or `[EXAMPLE INVALID: ...]` text in the generated HUD.

Each code HUD must include:

1. Objective
2. Current repo behavior
3. Target behavior
4. Primary edit seam
5. Required edits
6. Touched symbols
7. Tests to add or update
8. Done criteria
9. Constraints and invariants
10. Dependencies

#### Required Edits quality bar

The `Required Edits` section must describe actual implementation changes, not restate intent.

Invalid required edits:
- "Harden runtime behavior."
- "Normalize contract."
- "Update docs."
- "Add tests."
- "Wire implementation."

Valid required edits identify:
- the branch, condition, function, parser, schema, return envelope, manifest field, command-doc section, or test fixture to change
- the new behavior
- behavior to preserve
- side effects that are allowed
- side effects that are forbidden
- reason codes, fields, event names, payload keys, assertion values, or command outputs where applicable

If the exact implementation cannot be determined from `sketch.md` and bounded repo reads, write `BLOCKED: insufficient implementation directive` in the HUD and stop before acceptance generation.

#### HUD placeholder gate

Before acceptance generation, fail tasking if any generated non-`[H]` HUD still contains:
- `[FILL:`
- `[EXAMPLE:`
- `[EXAMPLE INVALID:`
- generic-only required edits such as "harden", "normalize", "wire", "update", or "add tests" without concrete behavior, symbols, contracts, or assertions

### 4. Estimate/breakdown stabilization (required)

Primary path (script-owned):
- `uv run --no-sync python scripts/speckit_tasking_chain.py --feature-dir "$FEATURE_DIR" --json`

If command bridges are needed, run:
- `--estimate-command "<estimate executor>"`
- `--breakdown-command "<breakdown executor>"`

Required behavior:
- run estimate against current `tasks.md`
- if any task remains 8/13, run breakdown then re-run estimate
- repeat until no 8/13 remain or fail deterministically
- treat non-zero result as hard-block

### 5. Deterministic tasks format gate (required)

Run:
- `uv run --no-sync python scripts/speckit_tasks_gate.py validate-format --tasks-file "$FEATURE_DIR/tasks.md" --json`

If non-zero exit, fix and re-run before continuing.

### 6. HUD + acceptance generation (post-stabilization only)

Generate and hydrate HUD implementation tickets only after task stabilization + format gate pass:
- `.specify/scripts/pipeline-scaffold.py` for `speckit.tasking.hud-code`
- `.specify/scripts/pipeline-scaffold.py` for `speckit.tasking.hud-runbook`
- `uv run --no-sync python scripts/speckit_remake_huds.py --feature-dir "$FEATURE_DIR"`

After HUD generation, verify every non-`[H]` HUD satisfies the HUD / implementation-ticket requirements above. Do not continue to acceptance generation while any HUD contains unresolved placeholders, example text, or insufficient implementation directives.

Generate acceptance tests:
- `.specify/scripts/acceptance-test-scaffold.py`
- keep assertions deterministic PASS/FAIL and traceable to story/task criteria

### 7. Event + reporting

Return completion payload to the runner/driver only after sections 1-6 pass.

Report at end:
- `tasks.md` path
- settled estimate/breakdown outcome
- HUD and acceptance-test counts
- whether command/script/template/manifest work was retained
- whether `[H]` tasks were derived from explicit sketch boundaries

## Behavior rules

- Do not treat `sketch.md` as optional inspiration; it is the tasking contract.
- Do not skip `speckit_tasking_chain.py`; tasking must include estimate/breakdown stabilization logic.
- Do not generate HUDs before task format gate passes.
- Do not append completion events before deterministic checks pass.
