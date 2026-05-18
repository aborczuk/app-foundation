# /speckit.tasking

## User Input

```text
$ARGUMENTS
```

## Contract

Generate `tasks.md` and task HUDs from an approved `plan.md` / `spec.json` summary, then stabilize the downstream task graph with deterministic checks.

1. Decompose `plan.md` design slices into `tasks.md`.
2. Run `scripts/speckit_remake_huds.py prepare --feature-dir "$FEATURE_DIR" --rewrite-existing` to scaffold per-task HUD tickets from explicit task facts only.
3. Fill every non-`[H]` HUD concretely from repo reads plus `spec.json`, `plan.md`, `spec.md`, and `tasks.md`.
4. Run deterministic estimate/breakdown stabilization through `scripts/speckit_tasking_chain.py` with the Codex-backed bridge runners below.
5. Enforce tasks format via `scripts/speckit_tasks_gate.py`.
6. Validate completed HUDs via `scripts/speckit_remake_huds.py validate --feature-dir "$FEATURE_DIR" --json`.
7. Register tasks and generate acceptance tests from the settled task graph.

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

### 3. Task derivation rules (required)

- Read `spec.json` first; it holds the machine-readable key details of the approved plan/spec contract.
- Use the spec details, design slices, domains, risk, and tasking metadata from `spec.json` to decide how much task detail each task needs.
- Treat `scripts/speckit_remake_huds.py prepare` as a section scaffold only. It must not decide relevant domains, design slices, reuse, acceptance, or the proposed solution.
- Use the matched slice directives to derive task-specific obligations; the HUD must attach and specialize those directives rather than merely reference slice IDs.
- Derive tasks from plan contracts first; do not invent major architecture not present in plan.
- Preserve execution order and dependency rules from sketch + tasks graph.
- Add `[H]` tasks only where sketch/operator boundaries explicitly require human action.
- Keep each task anchored to actionable file/symbol seams.
- Preserve command/script/template/manifest work as explicit tasks when present in sketch.
- Keep task descriptions deterministic and implementation-usable (no vague placeholders).
- Treat each design slice's `Implementation Directive` as required source material for task/HUD generation.
- Solve each design slice before decomposing it into tasks; do not only restate the directive.
- Put the solved slice-local implementation approach into the corresponding tasks and HUDs.
- Do not emit a non-`[H]` task unless the associated HUD can be filled with current behavior, target behavior, concrete required edits, touched symbols, tests, constraints, dependencies, and done criteria.
- Task descriptions may remain concise, but the corresponding HUD must contain the implementation-ready ticket detail.
- Treat the HUD as the only document implement will read for that task. If the task-local acceptance, symbols, seams, reuse determination, tests, or constraints are not in the HUD, they do not exist for implement.
- If a task cannot be hydrated into a concrete HUD from `spec.json` / `plan.md` plus bounded repo reads, mark that HUD `BLOCKED: insufficient implementation directive` and stop before acceptance generation.

### 3b. HUD / implementation-ticket requirements (required)

For every non-`[H]` task, generate or update `${FEATURE_DIR}/huds/TXXX.md` using `.specify/templates/hud-code-template.md`.

Each code HUD is the authoritative implementation ticket for its task. It must be concrete enough that `/speckit.implement` can execute the task without rereading the full sketch or inventing design.

Each code HUD must fill all required `[FILL: ...]` fields from the HUD template and must not leave any `[EXAMPLE: ...]` or `[EXAMPLE INVALID: ...]` text in the generated HUD.

Each code HUD must include:

1. Objective
2. Relevant domains
3. Candidate design slices
4. Proposed solution
5. Current repo behavior
6. Target behavior
7. Primary edit seam
8. Required edits
9. Touched symbols
10. Tests to add or update
11. Acceptance criteria
12. Done criteria
13. Constraints and invariants
14. Dependencies

#### Required Edits quality bar

The `Required Edits` section must describe actual implementation changes, not restate intent.
Each bullet should be traceable back to a matched slice directive, but specialized for this exact task seam.

Invalid required edits:
- "Harden runtime behavior."
- "Normalize contract."
- "Update docs."
- "Add tests."
- "Wire implementation."
- "Honor PL-02."

Valid required edits identify:
- the branch, condition, function, parser, schema, return envelope, manifest field, command-doc section, or test fixture to change
- the new behavior
- behavior to preserve
- side effects that are allowed
- side effects that are forbidden
- reason codes, fields, event names, payload keys, assertion values, or command outputs where applicable

If the exact implementation cannot be determined from `spec.json` / `plan.md` and bounded repo reads, write `BLOCKED: insufficient implementation directive` in the HUD and stop before acceptance generation.

#### HUD placeholder gate

Before acceptance generation, fail tasking if any generated non-`[H]` HUD still contains:
- `[FILL:`
- `[EXAMPLE:`
- `[EXAMPLE INVALID:`
- generic-only required edits such as "harden", "normalize", "wire", "update", or "add tests" without concrete behavior, symbols, contracts, or assertions

### 4. Estimate/breakdown stabilization (required)

Primary path (script-owned):
```bash
uv run --no-sync python scripts/speckit_tasking_chain.py \
  --feature-dir "$FEATURE_DIR" \
  --json \
  --estimate-command "uv run --no-sync python scripts/speckit_tasking_codex_runner.py --mode estimate --feature-dir \"$FEATURE_DIR\" --json" \
  --breakdown-command "uv run --no-sync python scripts/speckit_tasking_codex_runner.py --mode breakdown --feature-dir \"$FEATURE_DIR\" --json"
```

Codex-backed bridge runners:
- `uv run --no-sync python scripts/speckit_tasking_codex_runner.py --mode estimate --feature-dir "$FEATURE_DIR" --json`
- `uv run --no-sync python scripts/speckit_tasking_codex_runner.py --mode breakdown --feature-dir "$FEATURE_DIR" --json`

Each mode keeps its own warm Codex session across repeated stabilization rounds until the task graph settles.

Required behavior:
- run estimate against current `tasks.md`
- if any task remains 8/13, run breakdown then re-run estimate
- repeat until no 8/13 remain or fail deterministically
- treat non-zero result as hard-block

### 5. Deterministic tasks format gate (required)

Run:
- `uv run --no-sync python scripts/speckit_tasks_gate.py validate-format --tasks-file "$FEATURE_DIR/tasks.md" --json`

If non-zero exit, fix and re-run before continuing.

### 6. Task ledger registration (required)

Run:
- `uv run --no-sync python scripts/task_ledger.py register --tasks-file "$FEATURE_DIR/tasks.md" --feature-id "$FEATURE_ID" --json`

Treat non-zero as hard-block. The tasking step owns `task_registered` events; implement only consumes the queue.

### 7. HUD + acceptance generation (post-stabilization only)

Scaffold HUD implementation tickets after `tasks.md` is complete:
- `uv run --no-sync python scripts/speckit_remake_huds.py prepare --feature-dir "$FEATURE_DIR" --rewrite-existing"`

Then fill every non-`[H]` HUD generatively before stabilization continues, using the solved slice-local solution, exact symbols, and relevant domains for each task.

After HUD fill, verify every non-`[H]` HUD satisfies the HUD / implementation-ticket requirements above:
- `uv run --no-sync python scripts/speckit_remake_huds.py validate --feature-dir "$FEATURE_DIR" --json`

Do not continue to acceptance generation while any HUD contains unresolved placeholders, example text, or insufficient implementation directives.

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

- Do not treat `spec.json` as optional inspiration; it is the machine-readable summary of the approved plan/spec details.
- Do not skip `speckit_tasking_chain.py`; tasking must include estimate/breakdown stabilization logic.
- Do not let deterministic scaffolds stand in for final HUD content on code tasks.
- Do not append completion events before deterministic checks pass.
