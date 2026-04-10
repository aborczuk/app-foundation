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

## Command-to-Scaffold Coverage Matrix

| Command | Canonical Manifest Entry | Mirror Parity (`command-manifest.yaml`) | Scaffold Path | Template/Artifact Target |
|---|---|---|---|---|
| `speckit.specify` | `.specify/command-manifest.yaml:commands.speckit.specify` | required (`cmp -s` must pass) | `.specify/scripts/bash/create-new-feature.sh` + `pipeline-scaffold.py speckit.specify` | `spec-template.md` + `requirements-checklist-template.md` |
| `speckit.plan` | `.specify/command-manifest.yaml:commands.speckit.plan` | required (`cmp -s` must pass) | `.specify/scripts/bash/setup-plan.sh` + `pipeline-scaffold.py speckit.plan` | `plan-template.md`, `data-model-template.md`, `quickstart-template.md` |
| `speckit.sketch` | `.specify/command-manifest.yaml:commands.speckit.sketch` | required (`cmp -s` must pass) | `pipeline-scaffold.py speckit.sketch` | `sketch-template.md` |
| `speckit.solutionreview` | `.specify/command-manifest.yaml:commands.speckit.solutionreview` | required (`cmp -s` must pass) | `pipeline-scaffold.py speckit.solutionreview` | `solutionreview-template.md` |
| `speckit.tasking` | `.specify/command-manifest.yaml:commands.speckit.tasking` | required (`cmp -s` must pass) | `pipeline-scaffold.py speckit.tasking` | `tasks-template.md` |
| `speckit.tasking.hud-code` | `.specify/command-manifest.yaml:commands.speckit.tasking.hud-code` | required (`cmp -s` must pass) | `pipeline-scaffold.py speckit.tasking.hud-code` | `hud-code-template.md` |
| `speckit.tasking.hud-runbook` | `.specify/command-manifest.yaml:commands.speckit.tasking.hud-runbook` | required (`cmp -s` must pass) | `pipeline-scaffold.py speckit.tasking.hud-runbook` | `hud-runbook-template.md` |
| `speckit.e2e` | `.specify/command-manifest.yaml:commands.speckit.e2e` | required (`cmp -s` must pass) | `pipeline-scaffold.py speckit.e2e` | `e2e-template.md` + `e2e-script-template.sh` |

Coverage notes:

- `pipeline-scaffold.py` is the canonical template copier/resolver for manifest-declared artifact scaffolding.
- `speckit.analyze` intentionally has no template scaffold (`template: ""`) and is report-only.
- Commands with `artifacts: []` remain command-contract or runtime-only and are covered by command docs plus ledger validation, not template scaffolding.

## Manifest and Ledger Alignment

- Canonical registry: `.specify/command-manifest.yaml`
- Mirror copy: `command-manifest.yaml`
- Event transition enforcement: `scripts/pipeline_ledger.py` (`ALLOWED_PIPELINE_TRANSITIONS`)
- Manifest-schema enforcement: `python scripts/pipeline_ledger.py validate-manifest`
