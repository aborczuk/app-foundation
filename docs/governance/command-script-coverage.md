# Command-Script Coverage Matrix

## Scope

This matrix defines ownership for the solution-phase pipeline used by spec `019-token-efficiency-docs`, with focus on:

- `speckit.solution`
- `speckit.tasking`
- `speckit.sketch`
- `speckit.estimate`
- `speckit.tasks` (legacy overlap candidate)

Sources compared:

- `.specify/command-manifest.yaml`
- `.claude/commands/speckit.solution.md`
- `.claude/commands/speckit.tasking.md`
- `.claude/commands/speckit.sketch.md`
- `.claude/commands/speckit.estimate.md`
- `.claude/commands/speckit.tasks.md`

## Canonical Orchestration (Target)

`/speckit.solution` -> `/speckit.tasking` -> `/speckit.sketch` -> `/speckit.estimate` -> `/speckit.solutionreview`

Then:

`/speckit.analyze` -> `/speckit.e2e` -> `/speckit.implement`

## 1:1 Responsibility Matrix

| Responsibility | Target Single Owner | Deterministic Enforcer | Current State | Evidence |
|---|---|---|---|---|
| Orchestrate sub-agent loop (`tasking -> sketch -> estimate`) and convergence | `speckit.solution` | Command behavior in `.claude/commands/speckit.solution.md` | `1:1` | `speckit.solution.md:39-60`; `.specify/command-manifest.yaml:153-158` |
| Generate initial `tasks.md` | `speckit.tasking` | `pipeline-scaffold.py speckit.tasking` | `overlap` (`speckit.tasks` also owns same artifact) | `speckit.tasking.md:45-50`; `.specify/command-manifest.yaml:97-101`; `.specify/command-manifest.yaml:90-94` |
| Enforce `tasks.md` format gate before completion | `speckit.tasking` | `scripts/speckit_tasks_gate.py validate-format` | `gap` (documented in `speckit.tasks`, not in `speckit.tasking`) | `speckit.tasks.md:130-134`; `speckit.tasking.md` (no gate step) |
| Assign fibonacci points and produce `estimates.md` | `speckit.estimate` | `pipeline-scaffold.py speckit.estimate` | `overlap` (solution/sketch text implies sketch produces estimates) | `speckit.estimate.md:89-99`; `.specify/command-manifest.yaml:119-124`; `speckit.solution.md:47`; `speckit.sketch.md:42` |
| Generate per-task solution sketches (LLD content) | `speckit.sketch` | Command behavior in `.claude/commands/speckit.sketch.md` | `1:1` | `speckit.sketch.md:40-50` |
| Generate story acceptance tests in `.speckit/acceptance-tests/` | `speckit.sketch` | Command behavior in `.claude/commands/speckit.sketch.md` | `1:1` | `speckit.sketch.md:52-63`; `.specify/command-manifest.yaml:113-114` |
| Generate task HUDs (`.speckit/tasks/T0XX.md`) | `speckit.sketch` | `pipeline-scaffold.py speckit.sketch` | `overlap` (`speckit.estimate` also generates HUDs) | `speckit.sketch.md:71-99`; `speckit.estimate.md:102-153`; `.specify/command-manifest.yaml:106-125` |
| Select HUD template type (code vs runbook) per task type | `speckit.sketch` | Manifest artifact mapping + task-type routing | `gap` (both sketch templates currently write same output path under one command key) | `.specify/command-manifest.yaml:109-112` |
| Emit `tasking_completed` event | `speckit.tasking` | `scripts/pipeline_ledger.py append` | `1:1` | `speckit.tasking.md:63-67`; `.specify/command-manifest.yaml:102-104` |
| Emit `sketch_completed` event | `speckit.sketch` | `scripts/pipeline_ledger.py append` | `1:1` | `speckit.sketch.md:101-105`; `.specify/command-manifest.yaml:115-117` |
| Emit `estimation_completed` event | `speckit.estimate` | `scripts/pipeline_ledger.py append` | `1:1` | `speckit.estimate.md:161-166`; `.specify/command-manifest.yaml:126-128` |
| Emit `solution_approved` only after solutionreview passes | `speckit.solution` | `scripts/pipeline_ledger.py append` after quality gate | `1:1` | `speckit.solution.md:57-66`; `.specify/command-manifest.yaml:156-158` |

## Key Overlaps and Gaps Blocking Clean Orchestrator

1. **`tasks.md` ownership overlap**: `speckit.tasks` and `speckit.tasking` both own `${FEATURE_DIR}/tasks.md`.
2. **Estimate ownership overlap**: `speckit.estimate` owns `estimates.md`, but `speckit.solution` and `speckit.sketch` text still describe sketch as producing estimates.
3. **HUD ownership overlap**: both `speckit.sketch` and `speckit.estimate` claim HUD generation.
4. **HUD type routing gap**: manifest does not distinguish code HUD vs runbook HUD by task type.
5. **Format gate placement gap**: `speckit.tasking` does not currently require the deterministic `tasks.md` format gate that `speckit.tasks` requires.

## Immediate Normalization Plan (for orchestrator correctness)

1. Keep `speckit.solution` as orchestrator only; no artifact ownership changes there.
2. Make `speckit.tasking` the sole `tasks.md` generator in solution path, and either deprecate or explicitly scope `speckit.tasks`.
3. Make `speckit.estimate` the sole owner of `estimates.md`.
4. Make a single command own HUD generation and update the other command to consume-only.
5. Add/retain deterministic gate execution (`speckit_tasks_gate.py`) in the actual `tasks.md` owner command.
