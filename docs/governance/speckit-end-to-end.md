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
- Artifact/event registry: `command-manifest.yaml` (mirror: `command-manifest.yaml`)

## System Of Record

| Concern | Source of truth |
|---|---|
| Pipeline step order and prerequisites | `constitution.md` |
| State transitions diagram | `constitution-workflow.md` |
| Per-command behavior contract | `.claude/commands/speckit.<step>.md` |
| Artifact + template + emitted event registration | `command-manifest.yaml` |
| Manifest mirror | `command-manifest.yaml` |
| Template files | `.specify/templates/` |
| Template scaffolding engine | `.specify/scripts/pipeline-scaffold.py` |
| Feature bootstrap/setup scripts | `.specify/scripts/bash/*.sh` |
| Pipeline event validation and transition enforcement | `scripts/pipeline_ledger.py` |
| Deterministic gate scripts | `scripts/speckit_gate_status.py`, `scripts/speckit_tasks_gate.py`, `scripts/speckit_implement_gate.py` |
| Runtime artifacts and ledgers | `.speckit/` |

## End-to-End Lifecycle

Canonical flow (high level):

`specify -> clarify -> research -> plan -> planreview -> feasibilityspike -> solution(sketch -> solutionreview -> estimate -> tasking) -> analyze -> e2e -> implement -> checkpoint/e2e-run -> offline_qa -> close`

Key hard-gate facts:

- `research.md` must exist before `/speckit.plan`.
- `plan_approved` must occur before solution steps.
- `analysis_completed` must occur before `/speckit.e2e`.
- `offline_qa_passed` is required before task close.

For exact matrix and event semantics, use `constitution.md`.

## How A Step Actually Executes

1. Command contract is read from `.claude/commands/speckit.<step>.md`.
2. Setup script discovers context (`check-prerequisites.sh` or `setup-plan.sh`).
3. If templated outputs are required, scaffold is run by script:
   - shared: `.specify/scripts/pipeline-scaffold.py`
   - or dedicated: `.specify/scripts/bash/<script>.sh`
4. LLM fills placeholders/content according to command contract.
5. Deterministic gates validate structure/sequence.
6. Pipeline event is appended and validated through `scripts/pipeline_ledger.py`.

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

If you change command outputs/events:

- `command-manifest.yaml`
- `command-manifest.yaml` (mirror)
- templates under `.specify/templates/`

If you change pipeline order/event rules:

- `scripts/pipeline_ledger.py` (transition + required-field enforcement)
- `constitution.md`
- `constitution-workflow.md` and `.claude/constitution-workflow.md`

## Adding A New Step

Use:

- `docs/governance/how-to-add-speckit-step.md`

That runbook covers required file changes, script/template expectations, transition updates, and validation commands.
