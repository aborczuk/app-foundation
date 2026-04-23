# /speckit.tasking

## User Input

```text
$ARGUMENTS
```

## Compact Contract (Load First)

Generate `tasks.md` from an approved `sketch.md` and stabilize the downstream task graph with deterministic script-owned checks.

1. Decompose `sketch.md` into `tasks.md` (authoritative source: sketch design slices).
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
- `plan.md`

Optional:
- `research.md`
- `catalog.yaml`
- `command-manifest.yaml`

When deriving tasks, treat the following sketch sections as authoritative:
- `Solution Narrative`
- `Construction Strategy`
- `Acceptance Traceability`
- `Command / Script Surface Map`
- `Manifest Alignment Check`
- `CodeGraphContext Findings`
- `Blast Radius`
- `Interface, Symbol, and Contract Notes`
- `Human-Task and Operator Boundaries`
- `Verification Strategy`

### 3. Task derivation rules (required)

- Derive tasks from sketch contracts first; do not invent major architecture not present in sketch.
- Preserve execution order and dependency rules from sketch + tasks graph.
- Add `[H]` tasks only where sketch/operator boundaries explicitly require human action.
- Keep each task anchored to actionable file/symbol seams.
- Preserve command/script/template/manifest work as explicit tasks when present in sketch.
- Keep task descriptions deterministic and implementation-usable (no vague placeholders).

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

Generate HUD scaffolds only after task stabilization + format gate pass:
- `.specify/scripts/pipeline-scaffold.py` for `speckit.tasking.hud-code`
- `.specify/scripts/pipeline-scaffold.py` for `speckit.tasking.hud-runbook`
- `uv run --no-sync python scripts/speckit_remake_huds.py --feature-dir "$FEATURE_DIR"`

Generate acceptance tests:
- `.specify/scripts/acceptance-test-scaffold.py`
- keep assertions deterministic PASS/FAIL and traceable to story/task criteria

### 7. Event + reporting

Return completion payload to the runner/driver only after sections 1-6 pass.
`tasking_completed` append is driver-owned (pipeline route), not command-doc-owned.

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
