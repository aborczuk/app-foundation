---
description: Read-only drift and consistency analysis across spec.md, plan.md, sketch.md, and tasks.md.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Goal

Identify inconsistencies, omissions, and drift across the sketch-first artifact chain:

`spec.md -> plan.md -> sketch.md -> tasks.md`

This command runs after `solution_approved` and emits `analysis_completed` only when `critical_count == 0`.

## Operating Constraints

- **Strictly read-only** on all artifacts under analysis.
- Constitution conflicts are automatically CRITICAL.
- Do not auto-remediate; report findings and proposed fixes.

## Execution Steps

### 1. Initialize context

Run:

```bash
.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

Resolve:

- `spec.md`
- `plan.md`
- `sketch.md`
- `tasks.md`

### 2. Gate checks

Hard-block if any required artifact is missing.

Enforce checklist readiness (`checklists/requirements.md` present and complete).

### 3. Artifact-chain consistency analysis

Perform the following checks.

#### A. `spec -> plan`
Verify:

- requirements and constraints are preserved,
- major non-goals remain preserved,
- the primary automated action is represented in plan,
- architecture direction plausibly satisfies the spec.

#### B. `plan -> sketch`
Verify:

- architecture decisions are reflected in the sketch,
- repeated architectural unit recognition, if present in the plan, is preserved in sketch,
- pipeline architecture model / artifact-event contract architecture from plan is reflected in sketch where relevant,
- sketch preserves the `Handoff Contract to Sketch`,
- sketch uses `Architecture Flow Delta` correctly rather than silently replacing the plan’s Architecture Flow.

#### C. `sketch -> tasks`
Verify:

- every decomposition-ready design slice maps to one or more tasks, or an explicit rationale exists,
- no task exists without a corresponding design slice or explicit rationale,
- construction strategy is reflected in dependency order and sequencing,
- touched files/symbols in sketch are reflected in task `file:symbol` annotations where applicable,
- `[H]` tasks correspond to explicit human/operator boundaries from sketch,
- command/script/template/manifest work identified in sketch is represented in tasks where required,
- no task introduces a seam/artifact/symbol/interface absent from sketch without explicit rationale.

#### D. Verification consistency
Verify:

- acceptance traceability in sketch is reflected in task/story structure,
- verification intent in sketch is reflected in task and acceptance artifact structure,
- regression-sensitive areas in sketch are not dropped from the task plan.

### 4. Ingress/readiness checks

If ingress applies, enforce the `External Ingress + Runtime Readiness Gate` in `plan.md`.

Any FAIL row is CRITICAL.

### 5. Repeated-unit / contract drift checks

Where the plan identifies a repeated architectural unit or artifact/event contract architecture, verify:

- sketch preserves that abstraction,
- tasks do not silently bypass it,
- downstream work does not drift back into ad hoc command-by-command structure without rationale.

### 6. Produce report

Write findings with severity.

Include:

- `critical_count`
- `high_count`
- targeted remediation actions

Use findings categories such as:

- spec-plan-drift
- plan-sketch-drift
- sketch-task-drift
- architecture-contract-drift
- human-boundary-drift
- symbol-annotation-drift
- verification-drift
- ingress-readiness-drift

### 7. Emit pipeline event

Append:

```json
{"event": "analysis_completed", "feature_id": "NNN", "phase": "analysis", "critical_count": 0, "actor": "<agent-id>", "timestamp_utc": "..."}
```

only when `critical_count == 0`.

### 8. Report

Report:

- overall drift status,
- critical and high counts,
- top inconsistencies,
- whether the strongest drift is:
  - `spec -> plan`
  - `plan -> sketch`
  - `sketch -> tasks`
- suggested remediation target:
  - `/speckit.plan`
  - `/speckit.sketch`
  - `/speckit.tasking`

## Operating Principles

- Never modify source artifacts.
- Prioritize constitution and safety violations.
- Deterministic output: same inputs should yield consistent findings IDs/counts.
- Treat the sketch as a contract artifact, not just a narrative artifact.
- Flag drift whenever downstream phases had to invent architecture or omit an upstream contract.