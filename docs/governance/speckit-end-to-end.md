# Speckit End-to-End Guide

## Purpose

This is the central map for how Speckit works in this repository from feature request to closure:

- what runs
- where artifacts are generated
- which files are authoritative
- how gates and ledgers enforce order

## What Existed Before This Doc

End-to-end information already existed, but it was split:

- Pipeline order and hard gates: `constitution.md`
- State machine diagram: `constitution-workflow.md` and `.claude/constitution-workflow.md`
- Command ownership matrix: `docs/governance/command-script-coverage.md`
- Command behavior contracts: `.claude/commands/speckit.*.md`
- Artifact/event registry: `command-manifest.yaml`

## System Of Record

| Concern | Source of truth |
|---|---|
| Pipeline step order and prerequisites | `constitution.md` |
| State transitions diagram | `constitution-workflow.md` |
| Per-command behavior contract | `.claude/commands/speckit.<step>.md` |
| Artifact + template + emitted event registration | `command-manifest.yaml` |
| Template files | `.specify/templates/` |
| Template scaffolding engine | `.specify/scripts/pipeline-scaffold.py` |
| Feature bootstrap/setup scripts | `.specify/scripts/bash/*.sh` |
| Pipeline event validation and transition enforcement | `scripts/pipeline_ledger.py` |
| Deterministic gate scripts | `scripts/speckit_gate_status.py`, `scripts/speckit_tasks_gate.py`, `scripts/speckit_implement_gate.py`, `scripts/speckit_behavioral_qa.py` |
| Runtime artifacts and ledgers | `.speckit/` |

## End-to-End Lifecycle

Canonical flow (high level):

`specify -> clarify -> research -> plan -> planreview -> feasibilityspike -> solution(sketch -> solutionreview -> estimate -> tasking) -> analyze -> e2e -> implement -> checkpoint/e2e-run -> offline_qa -> close`

Key hard-gate facts:

- `research.md` must exist before `/speckit.plan`.
- `plan_approved` must occur before solution steps.
- `analysis_completed` must occur before `/speckit.e2e`.
- `offline_qa_passed` is required before task close. The QA agent (`scripts/speckit_behavioral_qa.py`) verifies acceptance criteria, runs tests, and checks for implementation drift. Tasks with `FIX_REQUIRED` cannot close.
- `/speckit.implement` is a generative command-agent-owned orchestration step. It is not a deterministic step-script runner and it must not delegate task execution to a Codex subrunner.

For exact matrix and event semantics, use `constitution.md`.

## How A Step Actually Executes

1. Command contract is read from `.claude/commands/speckit.<step>.md`.
2. Driver route is resolved from `command-manifest.yaml`.
3. Setup scripts discover context (`check_prerequisites.py` or `setup_plan.py`) and script-owned gates run first.
4. If templated outputs are required, scaffold is run by script:
   - shared: `.specify/scripts/pipeline-scaffold.py`
   - or dedicated: `.specify/scripts/bash/<script>.sh`
5. Execution then follows the driver mode:
   - deterministic: a step script owns the phase runtime
   - generative: the command agent owns the phase runtime and uses the command doc as the orchestration contract
6. Script-owned validation, ledgers, and closeout helpers remain authoritative after LLM work.
7. Pipeline event is appended and validated through `scripts/pipeline_ledger.py`.

Important `implement` exception:

- `speckit.implement` is a generative route.
- The `/speckit.implement` command agent itself orchestrates the persistent builder and QA subagents.
- The builder prompt comes from `.claude/commands/speckit.implement.md`.
- The QA prompt comes from `.claude/commands/speckit.qa.md`.
- Script-owned helpers still own offline QA, task closeout, docs updates, and task-gate continuation.
- `scripts/speckit_implement_step.py` and `scripts/speckit_codex_handoff_runner.py` are not the orchestration authority for `implement`.

## Artifact Generation Model

Artifact registration lives in `command-manifest.yaml`:

- each command declares `artifacts`
- each artifact declares `output_path` and `template` (if templated)
- each command declares emitted events and required event fields

Template generation policy for this repo:

- templated artifacts must be generated through script invocation
- no manual freeform creation for templated files

## Ledgers And Gate Enforcement

There are two ledgers:

- Pipeline ledger: `.speckit/pipeline-ledger.jsonl` (feature phase transitions)
- Task ledger: `.speckit/task-ledger.jsonl` (task execution transitions)

Access pattern:

- Do not parse ledger JSONL directly.
- Use script interfaces (`pipeline_ledger.py`, `task_ledger.py`) for assertions/appends/validation.

## Where To Change Things

If you change command behavior:

- `.claude/commands/speckit.<step>.md`
- and, if the orchestration boundary changes, the command's `driver` route in `command-manifest.yaml`

If you change command outputs/events:

- `command-manifest.yaml`
- templates under `.specify/templates/`

If you change pipeline order/event rules:

- `scripts/pipeline_ledger.py` (transition + required-field enforcement)
- `constitution.md`
- `constitution-workflow.md` and `.claude/constitution-workflow.md`

## Adding A New Step

Use:

- `docs/governance/how-to-add-speckit-step.md`

That runbook covers required file changes, script/template expectations, transition updates, and validation commands.
