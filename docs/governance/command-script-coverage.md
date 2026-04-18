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
| `speckit.specify` | `command-manifest.yaml:commands.speckit.specify` | required (`cmp -s` must pass) | `.specify/scripts/bash/create-new-feature.sh` + `pipeline-scaffold.py speckit.specify` | `spec-template.md` + `requirements-checklist-template.md` |
| `speckit.plan` | `command-manifest.yaml:commands.speckit.plan` | required (`cmp -s` must pass) | `.specify/scripts/bash/setup-plan.sh` + `pipeline-scaffold.py speckit.plan` | `plan-template.md`, `data-model-template.md`, `quickstart-template.md` |
| `speckit.sketch` | `command-manifest.yaml:commands.speckit.sketch` | required (`cmp -s` must pass) | `pipeline-scaffold.py speckit.sketch` | `sketch-template.md` |
| `speckit.solutionreview` | `command-manifest.yaml:commands.speckit.solutionreview` | required (`cmp -s` must pass) | `pipeline-scaffold.py speckit.solutionreview` | `solutionreview-template.md` |
| `speckit.tasking` | `command-manifest.yaml:commands.speckit.tasking` | required (`cmp -s` must pass) | `pipeline-scaffold.py speckit.tasking` | `tasks-template.md` |
| `speckit.tasking.hud-code` | `command-manifest.yaml:commands.speckit.tasking.hud-code` | required (`cmp -s` must pass) | `pipeline-scaffold.py speckit.tasking.hud-code` | `hud-code-template.md` |
| `speckit.tasking.hud-runbook` | `command-manifest.yaml:commands.speckit.tasking.hud-runbook` | required (`cmp -s` must pass) | `pipeline-scaffold.py speckit.tasking.hud-runbook` | `hud-runbook-template.md` |
| `speckit.e2e` | `command-manifest.yaml:commands.speckit.e2e` | required (`cmp -s` must pass) | `pipeline-scaffold.py speckit.e2e` | `e2e-template.md` + `e2e-script-template.sh` |

Coverage notes:

- `pipeline-scaffold.py` is the canonical template copier/resolver for manifest-declared artifact scaffolding.
- `speckit.analyze` intentionally has no template scaffold (`template: ""`) and is report-only.
- Commands with `artifacts: []` remain command-contract or runtime-only and are covered by command docs plus ledger validation, not template scaffolding.

## Manifest and Ledger Alignment

- Canonical registry: `command-manifest.yaml`
- Mirror copy: `command-manifest.yaml` (deprecated; will be removed in Phase 5)
- Event transition enforcement: `scripts/pipeline_ledger.py` (`ALLOWED_PIPELINE_TRANSITIONS`)
- Manifest-schema enforcement: `python scripts/pipeline_ledger.py validate-manifest`

## Mixed-Mode Migration Safety (Phase 5)

### Overview

Incremental command migration from legacy to driver-managed modes requires deterministic coverage enforcement. In mixed migration:
- Some commands are driver-managed (deterministic routing, contract enforcement)
- Some commands remain legacy (passthrough, no driver control)
- Uncovered commands must be explicitly detected and blocked at gates

### Coverage Enforcement Rules

**All commands must have one of:**
1. Explicit driver mode in manifest (`driver.mode: deterministic|generative`)
2. Explicit legacy designation (`mode: legacy`) with no driver metadata
3. No ambiguous states allowed (this violates the migration contract)

**Validation Points:**
- During `speckit.tasking`: Gate check via `scripts/speckit_gate_status.py:validate_command_coverage()`
- During `speckit.solution`: Gate check enforces coverage before solution approval
- During manifest validation: `scripts/pipeline_ledger.py validate-manifest` enforces version/timestamp coupling

### Migration Workflow

**To migrate a command from legacy to driver-managed:**

1. Update `command-manifest.yaml`:
   ```yaml
   commands:
     speckit.my_command:
       mode: deterministic  # or generative
       driver:
         script_path: scripts/speckit_my_command.py
         timeout_seconds: 300
   ```

2. Update version and timestamp:
   ```yaml
   version: "1.1.0"  # Increment version
   last_updated: "2026-04-11T10:30:00Z"  # Update timestamp
   ```

3. Implement driver script at `scripts/speckit_my_command.py`

4. Add contract tests verifying the command with driver routing

5. Update migration documentation (this file)

**To rollback a command migration:**

1. Revert the command entry in `command-manifest.yaml` to legacy:
   ```yaml
   commands:
     speckit.my_command:
       description: "Rolled back to legacy mode"
       # Remove driver block
   ```

2. Update version/timestamp in manifest

3. Remove or disable driver script (do not delete; keep in git history)

4. Verify gate checks pass with rollback state

### Governance Invariants

**Version/Timestamp Coupling:**
- Every manifest change must update `last_updated` timestamp
- Stale timestamp with changed content triggers a governance violation
- Mirror manifests cannot diverge from canonical without detected violation

**Coverage Detection:**
- `validate_command_coverage()` detects uncovered commands during gates
- Uncovered commands block solution approval
- Mixed-mode coverage gaps are reported with specific reasons

**Mirror Manifest Deprecation:**
- Root `command-manifest.yaml` will be removed in Phase 5 closeout
- All tooling now uses `command-manifest.yaml` as canonical
- Anti-regression guards prevent reintroduction of mirror manifest
