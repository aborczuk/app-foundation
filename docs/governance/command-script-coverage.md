# Command-Script Coverage Matrix

## Canonical Solution Sequence

`plan_approved -> sketch_completed -> solutionreview_completed -> estimation_completed -> tasking_completed -> solution_approved -> analysis_completed`

## Responsibility Matrix

| Responsibility | Single Owner | Deterministic Enforcer |
|---|---|---|
| Orchestrate sketch-first solution flow | `speckit.solution` | `.claude/commands/speckit.solution.md` |
| Generate design blueprint | `speckit.sketch` | `pipeline-scaffold.py speckit.sketch` + `sketch-template.md` |
| Review blueprint quality and domain fit | `speckit.solutionreview` | `.claude/commands/speckit.solutionreview.md` |
| Score tasks and write `estimates.md` | `speckit.estimate` | `pipeline-scaffold.py speckit.estimate` |
| Decompose approved sketch into tasks | `speckit.tasking` | `pipeline-scaffold.py speckit.tasking` |
| Enforce deterministic tasks format gate | `speckit.tasking` | `scripts/speckit_tasks_gate.py validate-format` |
| Create HUDs after task stabilization | `speckit.tasking` | `pipeline-scaffold.py speckit.tasking.hud-code|hud-runbook` |
| Generate story acceptance tests | `speckit.tasking` | `.claude/commands/speckit.tasking.md` contract |
| Post-solution drift gate (`spec -> plan -> sketch -> tasks`) | `speckit.analyze` | `.claude/commands/speckit.analyze.md` + `analysis_completed` event |
| Legacy tasks command | `speckit.tasks` | Deprecated, no artifact generation |

## Manifest and Ledger Alignment

- Canonical registry: `.specify/command-manifest.yaml`
- Mirror copy: `command-manifest.yaml`
- Event transition enforcement: `scripts/pipeline_ledger.py` (`ALLOWED_PIPELINE_TRANSITIONS`)
- Manifest-schema enforcement: `python scripts/pipeline_ledger.py validate-manifest`
