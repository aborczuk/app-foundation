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

1. **Initialize context**:
   - Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks`.
   - Resolve paths: `spec.md`, `plan.md`, `sketch.md`, `tasks.md`.

2. **Gate checks**:
   - Hard-block if any required artifact is missing.
   - Enforce checklist readiness (`checklists/requirements.md` present and complete).

3. **Artifact-chain consistency analysis**:
   - `spec -> plan`: requirements and constraints preserved.
   - `plan -> sketch`: architecture decisions reflected in sketch strategies.
   - `sketch -> tasks`: sketch units decomposed into tasks with matching goals/dependencies.
   - Verify no task exists without a corresponding sketch unit or explicit rationale.

4. **Ingress/readiness checks**:
   - If ingress applies, enforce `External Ingress + Runtime Readiness Gate` in plan.
   - Any FAIL row is CRITICAL.

5. **Produce report**:
   - Write findings table with severity.
   - Include `critical_count`, `high_count`, and targeted remediation actions.

6. **Emit pipeline event**:
   ```json
   {"event": "analysis_completed", "feature_id": "NNN", "phase": "analysis", "critical_count": 0, "actor": "<agent-id>", "timestamp_utc": "..."}
   ```
   Emit only when `critical_count == 0`.

## Operating Principles

- Never modify source artifacts.
- Prioritize constitution and safety violations.
- Deterministic output: same inputs should yield consistent findings IDs/counts.
