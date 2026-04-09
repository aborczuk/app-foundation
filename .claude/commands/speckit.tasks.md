---
description: Generate an actionable, dependency-ordered tasks.md for the feature based on available design artifacts.
handoffs:
  - label: Estimate Effort
    agent: speckit.estimate
    prompt: Estimate fibonacci complexity for each task
    send: true
  - label: Generate E2E Pipeline
    agent: speckit.e2e
    prompt: Generate E2E testing pipeline artifacts for this feature
    send: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

1. **Setup**: Run `.specify/scripts/bash/check-prerequisites.sh --json` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list. All paths must be absolute. For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot").

2. **Load design documents**: Read from FEATURE_DIR:
   - **Required**: plan.md (tech stack, libraries, structure), spec.md (user stories with priorities)
   - **Optional**: data-model.md (entities), contracts/ (interface contracts), research.md (decisions), quickstart.md (test scenarios)
   - Note: Not all projects have all documents. Generate tasks based on what's available.

3. **Execute task generation workflow**:
   - Load plan.md and extract tech stack, libraries, project structure
   - Load `## External Ingress + Runtime Readiness Gate` from plan.md:
     - ERROR if this section is missing
     - Detect whether ingress/webhook/callback handling applies
     - If applicable, include `T000` in Phase 1 and order all webhook registration/public URL/dependency provisioning tasks after `T000`
   - Load spec.md and extract user stories with their priorities (P1, P2, P3, etc.)
   - If data-model.md exists: Extract entities and map to user stories
   - If contracts/ exists: Map interface contracts to user stories
   - If research.md exists: Extract decisions for setup tasks
   - Detect async/event-loop/background-worker integrations from plan.md and research.md
   - **Detect human tasks**: For each user story, identify any work requiring a human to act in an external system (configure a webhook URL, create an API key, set up a third-party workflow, provision infrastructure, etc.). Emit these as `[H]` tasks within the story phase, sequenced before the first implementation task. Each `[H]` task description must name the external system and the action. The runbook and verification command are generated in the HUD by `speckit.estimate`.
   - Generate tasks organized by user story (see Task Generation Rules below)
   - Generate dependency graph showing user story completion order
   - Create parallel execution examples per user story
   - Validate task completeness (each user story has all needed tasks, independently testable)
   - For each async integration path, include explicit guard tasks:
     - lifecycle implementation task (start/ready/timeout-cancel/shutdown/fail-safe cleanup),
     - regression test task exercising the path while an event loop is already running,
     - validation task asserting no orphan processes/tasks after execution.
   - For each live-vs-local state integration path, include explicit state-safety guard tasks:
     - source-of-truth and reconciliation invariant task (startup/reconnect/before-decision ordering),
     - regression test task for stale/orphan local state reconciliation,
     - validation task asserting no unresolved drift leaves local records active.
   - For each local DB mutation path that controls lifecycle/risk/financial state, include explicit transaction guard tasks:
     - transaction-boundary implementation task (atomic multi-step writes, commit/rollback semantics),
     - regression test task proving rollback/no-partial-write behavior on failure,
     - validation task asserting impossible/partial local lifecycle states cannot persist.

3b. **Symbol annotation (MANDATORY before writing tasks.md)**:
   - For each task identified in step 3, run `mcp__codegraph__find_code` for the primary symbol or file it will touch.
   - Record the result as `file:symbol` pairs — stable identifiers that survive line number drift as earlier tasks are completed.
   - If codegraph returns no match (new file/symbol not yet created), record the intended file path only — no symbol annotation needed.
   - These annotations attach to the task description and become the input to `speckit.implement`'s CodeGraph Recon step.

4. **Generate tasks.md** by pre-scaffolding from template:

   1. Run: `python .specify/scripts/pipeline-scaffold.py speckit.tasks --feature-dir $FEATURE_DIR FEATURE_NAME="[Feature Name]"`
      - Pre-structures the file with Phase sections, Dependencies section, Parallel Opportunities section, etc.

   2. Fill in the scaffolded structure:
      - Correct feature name from plan.md
      - Phase 1: Setup tasks (project initialization)
      - Phase 2: Foundational tasks (blocking prerequisites for all user stories)
      - Phase 3+: One phase per user story (in priority order from spec.md)
      - Each phase includes: story goal, independent test criteria, tests (if requested), implementation tasks
      - Final Phase: Polish & cross-cutting concerns
      - All tasks must follow the strict checklist format (see Task Generation Rules below)
      - Clear file paths for each task
      - Dependencies section showing story completion order
      - Parallel execution examples per story
      - Implementation strategy section (MVP first, incremental delivery)

5. **Run estimation (MANDATORY)**:
   - Immediately invoke `/speckit.estimate` after writing `tasks.md`.
   - Require `FEATURE_DIR/estimates.md` to exist before reporting completion.
   - If estimation identifies 8/13-point tasks, follow the estimate command's mandatory breakdown loop until those warnings are cleared.
   - If estimation cannot complete, stop and report the blocker (do not proceed to implementation-ready status).

6. **Report**: Output path to generated tasks.md and summary:
   - Total task count
   - Task count per user story
   - Parallel opportunities identified
   - Independent test criteria for each story
   - Async guard coverage summary (lifecycle tasks, running-loop regression tests, orphan-cleanup validations) when async integrations exist
   - State-safety coverage summary (reconciliation invariants, stale/orphan regression tests, drift checks) when live-vs-local state exists
   - Local DB transaction coverage summary (transaction boundaries, rollback/idempotency regression tests, no-partial-write checks) when local persisted-state mutations exist
   - Suggested MVP scope (typically just User Story 1)
   - Format validation result from:
     ```bash
     python scripts/speckit_tasks_gate.py validate-format --tasks-file "$FEATURE_DIR/tasks.md" --json
     ```
   - Path to generated estimates.md and total points summary from `/speckit.estimate`
   - **Pipeline continuation** — always append this block verbatim at the end of the report:

     ```
     ## Remaining Pipeline to Implementation

     tasks.md + estimates.md are ready. Complete all of the following steps in order before running /speckit.implement:

     1. /speckit.analyze    — cross-artifact consistency check (resolve CRITICAL issues before proceeding)
     2. /speckit.e2e        — generate e2e.md + E2E script (REQUIRED — /speckit.implement will hard-block without these artifacts)
     3. /speckit.implement  — execute tasks in phase order (hard-blocks if estimates.md is missing)
     ```

Context for task generation: $ARGUMENTS

The tasks.md should be immediately executable - each task must be specific enough that an LLM can complete it without additional context.

## Task Generation Rules

Tasks MUST be organized by user story and include mandatory tests per constitution.

**Required task shape**:
- `- [ ] T0NN [P?|H?] [USn?] <action> in <path> [file:symbol optional]`
- `[P]` and `[H]` are mutually exclusive.
- `[USn]` is required in user-story phases and forbidden in setup/foundational/polish phases.
- Task IDs must be sequential and unique.

**Deterministic format gate (MANDATORY before reporting completion)**:
```bash
python scripts/speckit_tasks_gate.py validate-format --tasks-file "$FEATURE_DIR/tasks.md" --json
```
- If exit code is non-zero: fix all reported errors and re-run.

**Phase structure**:
- Phase 1: Setup
- Phase 2: Foundational blockers
- Phase 3+: User stories in priority order, independently testable
- Final phase: Polish and cross-cutting validation

## Auto-Trigger: Trello Sync

After generating tasks.md, if `TRELLO_AUTO_SYNC=1` is set in the environment:

1. Detect TASKS path from the prerequisite output (FEATURE_DIR/tasks.md)
2. Resolve board_id from `TRELLO_BOARD_ID` env var (if not set, skip with a warning)
3. Call `sync_tasks_to_trello(tasks_md_path=TASKS, board_id=TRELLO_BOARD_ID)` via the MCP tool
4. Append sync results to the completion report:

```
## Trello Sync Results
- Created: {created} cards
- Updated: {updated} cards
- Unchanged: {unchanged} cards
- Errors: {len(errors)}
- Aborted: {aborted} ({abort_reason if aborted else 'N/A'})
```

If `TRELLO_AUTO_SYNC` is not set or is not `1`, skip this step silently.
