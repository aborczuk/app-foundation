---
description: Estimate fibonacci complexity for each task by evaluating the codebase, and produce a feature-level effort summary.
handoffs:
  - label: Break Down Large Tasks
    agent: speckit.breakdown
    prompt: Break down tasks flagged with 8 or 13-point warnings into smaller pieces
    send: true
  - label: Analyze For Consistency
    agent: speckit.analyze
    prompt: Run a cross-artifact consistency analysis before implementation
    send: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

Goal: Assign fibonacci story points (1, 2, 3, 5, 8, 13) to each task in tasks.md by evaluating the task against the actual codebase, then produce a feature-level effort summary. This is the detailed estimation step — distinct from the epic-level t-shirt sizing done in `/speckit.specify`.

Note: This step runs AFTER `/speckit.solution` (and optionally `/speckit.analyze`) and BEFORE `/speckit.implement`. If tasks.md does not exist, instruct the user to run `/speckit.solution` first.

Execution steps:

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root **once**. Parse FEATURE_DIR and AVAILABLE_DOCS. Derive TASKS path.
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.
   - If tasks.md missing, abort and instruct user to run `/speckit.solution`.
   - Use shell quoting per CLAUDE.md "Shell Script Compatibility".

2. Load context:
   - **Required**: tasks.md, plan.md (for project structure and tech context)
   - **Load if present**: data-model.md, contracts/*, research.md
   - **Load if present**: FEATURE_DIR/estimates.md (previous estimation run for this feature, if re-running)

3. Parse all tasks from tasks.md. For each task, extract:
   - Task ID, description, file path(s), phase, story label, parallel marker

4. **Evaluate each task against the codebase**. For each task, assess these dimensions:

   **Code complexity** (primary driver):
   - Does the target file already exist? If so, how large/complex is it?
   - How many other files does this task need to interact with?
   - Are there existing patterns in the codebase to follow, or is this greenfield?
   - Does the task involve algorithmic complexity (parsing, state machines, graph traversal) or straightforward CRUD?

   **Integration surface**:
   - How many external interfaces does this task touch (APIs, databases, file system)?
   - Does the task cross module boundaries defined in the Architecture Flow?
   - Are there concurrency or async coordination concerns?
   - For async integration tasks, is lifecycle guard coverage explicit (running-loop regression, timeout/cancel, shutdown, no-orphan validation)?
   - For live-vs-local state integrations, is state-safety coverage explicit (source-of-truth ownership, reconcile checkpoints, stale/orphan drift regression)?
   - For local DB mutation tasks, is transaction-integrity coverage explicit (transaction boundaries, rollback/no-partial-write regression, idempotent retry expectations)?

   **Uncertainty**:
   - Is the implementation approach well-defined in the plan, or does it require design decisions?
   - Are there dependencies on libraries with limited documentation or unfamiliar APIs?
   - Does the task involve error handling for poorly documented external behavior?

5. **Produce solution sketch for 3+ point tasks**: For each task estimated at 3 or more points, produce a solution sketch while the codebase context is loaded. Record per task:
   - Which existing symbols will be modified and how (name + intended change)
   - Which new symbols will be created, in which files, with what signatures
   - How the pieces compose to satisfy the task's goal
   - What the failing unit test assertion looks like (describe the assertion, not full code)
   - Which coding convention rules from `.claude/domains/` apply (identify touched domains only)

   For 1–2 point tasks: record `sketch: trivial` — no sketch required.

5b. **Assign fibonacci points** per task using this calibration:

   | Points | Meaning | Examples |
   |--------|---------|---------|
   | 1 | Trivial — single file, clear pattern, no integration | Create `__init__.py`, add a constant, write a simple data class |
   | 2 | Small — single file, some logic, follows existing pattern | Implement a parser for a known format, add a straightforward test |
   | 3 | Medium — 1-2 files, moderate logic, may cross one boundary | Implement a service method with validation, write integration test with mock |
   | 5 | Large — multiple files, non-trivial logic or integration | Implement sync engine orchestration, build API client with error handling |
   | 8 | Very large — should be broken down further | significant complexity, multiple boundaries | Wire up full request lifecycle across modules, implement state machine (flag as warning) |
   | 13 | Epic-scale — should be broken down further | Full feature implementation in a single task (flag as warning) |

   - Any task scoring 8 or 13 should be flagged with a warning: "Must break this task into smaller pieces."
   - Any async integration task missing lifecycle guard coverage should be flagged with a warning even if point score is low.
   - Any stateful integration task missing state-safety coverage should be flagged with a warning even if point score is low.
   - Any local DB mutation task missing transaction-integrity coverage should be flagged with a warning even if point score is low.
   - Tasks marked [P] (parallel) should generally score lower than sequential tasks in the same phase, since they are scoped to be independent.

6. **Generate estimates.md** in FEATURE_DIR by pre-scaffolding from template:

    1. Run: `uv run python .specify/scripts/pipeline-scaffold.py speckit.estimate --feature-dir $FEATURE_DIR FEATURE_NAME="[Feature Name]"`
      - Reads `.specify/command-manifest.yaml` to resolve which artifacts speckit.estimate owns
      - Copies `.specify/templates/estimates-template.md` to `$FEATURE_DIR/estimates.md`
      - Pre-structures the file with table headers and sections ready to fill

   2. The estimates.md is now scaffolded with:
      - Per-Task Estimates table (Task ID | Points | Description | Rationale)
      - Per-task Solution Sketch sections for 3+ point tasks (Modify/Create/Composition/Test/Domains)
      - Phase Totals table (Phase | Points | Task Count | Parallel Tasks)
      - Warnings section (8/13-point flags, no-parallel phases, high-uncertainty tasks)

7. **Generate HUD files**: For each task, create `.speckit/tasks/T0XX.md` if it does not exist, or update it if this task's estimate changed from a previous run. Skip tasks whose HUD exists and whose estimate is unchanged.

   ```markdown
   # HUD: [TaskID] — [Description]

   ## Working Memory
   **File:Symbol**: [from tasks.md annotation]
   **Current line**: [resolved by find_code at estimate time]
   **Callers**: [list from codegraph, if any]

   ## Solution Sketch
   [copied from estimates.md sketch — or "trivial" for 1–2 point tasks]

   ## Functional Goal
   **Story Goal**: [from tasks.md phase header]
   **Acceptance Criteria**: [Independent Test Criteria for this story]

   ## Quality Guards
   [Domain rules for touched domains only — omit for trivial tasks]
   [Domains 13, 14, and 17 always included]

   ## Process Checklist
   - [ ] discovery_completed
   - [ ] lld_recorded  ← [include only for 3+ point tasks]
   - [ ] quality_guards_passed
   - [ ] functional_goal_achieved
   - [ ] tests_passed
   ```

   `Current line` is mandatory for every non-`[H]` HUD. If unresolved, estimation is incomplete and must be re-run after symbol discovery is corrected.

   For `[H]` (human) tasks, generate a runbook HUD instead of a code sketch HUD:

   ```markdown
   # HUD: [TaskID] [H] — [Description]

   ## Runbook
   **System**: [name of external system — e.g. n8n, AWS Console, ClickUp]
   **Steps**:
   1. [Exact step]
   2. [Exact step]
   **Verification command**: [shell command or automated check confirming completion]

   ## Functional Goal
   **Story Goal**: [from tasks.md phase header]
   **Blocks**: [list of implementation task IDs in this story that cannot start until this is done]

   ## Process Checklist
   - [ ] human_action_started
   - [ ] human_action_verified
   - [ ] task_closed
   ```

   HUDs are pre-computed — `speckit.implement` reads one small file per task, no large artifact re-reads.

8. **Auto-breakdown loop** (mandatory — do not skip):
   - If **any** task scored 8 or 13: immediately invoke `/speckit.breakdown` to split those tasks.
   - After breakdown completes, re-run `/speckit.estimate` on the updated tasks.md.
   - Repeat until no task scores 8 or 13.
   - Only proceed to step 9 when the Warnings section is clear of 8/13-point flags.

9. **Emit pipeline event**:
   
   Emit `estimation_completed` to `.speckit/pipeline-ledger.jsonl`:
   ```json
   {"event": "estimation_completed", "feature_id": "NNN", "phase": "solution", "estimate_points": N, "actor": "<agent-id>", "timestamp_utc": "..."}
   ```

10. **Report completion**:
   - Path to estimates.md
   - Total story points and phase breakdown
   - Confirmation that no tasks score 8 or 13 (or list of remaining warnings if non-point warnings exist)
   - Risk-adjusted range
   - Suggested next command: `/speckit.implement`

## Behavior rules

- If re-running on a feature with existing estimates.md, read the previous estimates and note any changes (tasks added/removed/rescored) in a **Changes from Previous Estimate** section
- Do NOT modify tasks.md — this step is read-only on the task list
- The fibonacci scale is relative within a feature, not absolute across features — a "3" in one feature may differ from a "3" in another
- If no tasks exist or tasks.md is malformed, abort with a clear error
- Rationale column must be specific to the codebase, not generic (e.g., "follows pattern in existing trello_client.py" not "straightforward implementation")
