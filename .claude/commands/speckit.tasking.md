---
description: Generate the initial task breakdown (tasks.md) from a proven plan. Sub-agent of /speckit.solution; callable standalone.
handoffs:
  - label: Generate Solution Sketches
    agent: speckit.sketch
    prompt: Tasks are ready. Generate solution sketches and HUDs for each task.
    send: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

Produce the initial tasks.md from plan.md and design artifacts. This is a sub-agent of `/speckit.solution` — it runs after feasibilityspike has cleared all Open Feasibility Questions. It does NOT generate solution sketches or estimates — those are `/speckit.sketch` and `/speckit.estimate`.

## Outline

1. **Setup**: Run `.specify/scripts/bash/check-prerequisites.sh --json` from repo root. Parse `FEATURE_DIR` and `AVAILABLE_DOCS`. Read plan.md.

2. **Hard-block gate**: Read `## Open Feasibility Questions` in plan.md. If any `- [ ]` items remain: **STOP** — "plan.md has unresolved feasibility questions. Run /speckit.feasibilityspike first."

3. **Load design artifacts** from FEATURE_DIR:
   - **Required**: plan.md (architecture, Technology Selection, data flows)
   - **Load if present**: data-model.md, contracts/\*, research.md, quickstart.md, spike.md
   - Read catalog.yaml (repo root) for known service constraints

4. **Extract user stories** from spec.md (via AVAILABLE_DOCS). For each story: note priority (P1, P2…), acceptance criteria, and dependent entities.

5. **Detect integration patterns** from plan.md:
   - Async integrations → require lifecycle guard tasks (start/ready/timeout-cancel/shutdown) + regression test tasks
   - Live-vs-local state → require reconciliation invariant tasks + stale/orphan regression tasks
   - Local DB lifecycle/financial state → require transaction-boundary tasks + rollback regression tasks
   - External ingress → require T000 gate task if External Ingress gate has unresolved rows

6. **Detect `[H]` human tasks**: For each user story, identify work requiring action in an external system (configure a webhook URL, create an API key, provision infrastructure, set up a third-party workflow). Each `[H]` task must name the external system and the action. Sequence `[H]` tasks before the first implementation task in the same story phase — they run in parallel with code tasks but the story cannot close until all `[H]` tasks are verified.

7. **Symbol annotation (MANDATORY before writing tasks.md)**: For each task identified, run `mcp__codegraph__find_code` for the primary symbol or file it will touch. Record as `file:symbol` pairs. If codegraph returns no match (new file/symbol), record the intended file path only. These annotations attach to the task description and become the input to `/speckit.sketch`'s reuse-first evaluation.

8. **Generate tasks.md** by pre-scaffolding from template:

   1. Run: `python .specify/scripts/pipeline-scaffold.py speckit.tasking --feature-dir $FEATURE_DIR FEATURE_NAME="[Feature Name]"`
      - Reads `.specify/command-manifest.yaml` to resolve which artifacts speckit.tasking owns
      - Copies `.specify/templates/tasks-template.md` to `$FEATURE_DIR/tasks.md`
      - Pre-structures the file with Phase sections, Dependencies section, Parallel Opportunities section, etc.

   2. Fill in the scaffolded structure:
      - Phase 1: Setup tasks
      - Phase 2: Foundational tasks (blocking prerequisites; reconciliation/transaction guards if applicable)
      - Phase 3+: One phase per user story in priority order, each with:
        - Story goal + Independent Test Criteria
        - `[H]` tasks first (if any)
        - Implementation tasks with `file:symbol` annotations
        - Guard tasks (async lifecycle, state-safety, transaction-boundary) if applicable
      - Final phase: Polish and cross-cutting concerns
      - Dependencies section + parallel execution examples per story

9. **Emit pipeline event**:
   ```json
   {"event": "tasking_completed", "feature_id": "NNN", "phase": "solution", "task_count": N, "story_count": N, "actor": "<agent-id>", "timestamp_utc": "..."}
   ```
   Append to `.speckit/pipeline-ledger.jsonl`.

10. **Report**: Path to tasks.md, task count per story, parallel opportunities, `[H]` task count, integration guard coverage. Suggested next: `/speckit.sketch`.

## Task format rules

Every task MUST follow: `- [ ] TNNN [P?] [H?] [USN?] Description — file:symbol`

- `[P]` only if parallelizable with no incomplete-task dependencies
- `[H]` only if requires human action in external system — mutually exclusive with `[P]`
- `[USN]` required for all user story phase tasks
- `file:symbol` from codegraph annotation — omit symbol only for net-new files

## Behavior rules

- Read-only on plan.md and design artifacts — do NOT modify them
- Do NOT generate solution sketches or estimates — those are downstream sub-agents
- If tasks.md already exists: present a diff of what would change and ask for confirmation before overwriting
