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
   - Format validation: Confirm ALL tasks follow the checklist format (checkbox, ID, labels, file paths)
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

**CRITICAL**: Tasks MUST be organized by user story to enable independent implementation and testing.

**Tests are MANDATORY**:  generate test tasks as explicitly requested in the constitution.

### Checklist Format (REQUIRED)

Every task MUST strictly follow this format:

```text
- [ ] [TaskID] [P?] [Story?] Description with file path
```

**Format Components**:

1. **Checkbox**: ALWAYS start with `- [ ]` (markdown checkbox)
2. **Task ID**: Sequential number (T001, T002, T003...) in execution order
3. **[P] marker**: Include ONLY if task is parallelizable (different files, no dependencies on incomplete tasks)
3a. **[H] marker**: Include if the task requires human action in an external system. Mutually exclusive with [P]. Sequenced before implementation tasks in the same story phase.
4. **[Story] label**: REQUIRED for user story phase tasks only
   - Format: [US1], [US2], [US3], etc. (maps to user stories from spec.md)
   - Setup phase: NO story label
   - Foundational phase: NO story label  
   - User Story phases: MUST have story label
   - Polish phase: NO story label
5. **Description**: Clear action with exact file path and `file:symbol` annotation from step 3b (omit symbol only for net-new files)

**Examples**:

- ✅ CORRECT: `- [ ] T001 Create project structure per implementation plan`
- ✅ CORRECT: `- [ ] T005 [P] Implement authentication middleware in src/middleware/auth.py`
- ✅ CORRECT: `- [ ] T012 [P] [US1] Create User model in src/models/user.py`
- ✅ CORRECT: `- [ ] T014 [US1] Implement UserService in src/services/user_service.py`
- ❌ WRONG: `- [ ] Create User model` (missing ID and Story label)
- ❌ WRONG: `T001 [US1] Create model` (missing checkbox)
- ❌ WRONG: `- [ ] [US1] Create User model` (missing Task ID)
- ❌ WRONG: `- [ ] T001 [US1] Create model` (missing file path)

### Task Organization

1. **From User Stories (spec.md)** - PRIMARY ORGANIZATION:
   - Each user story (P1, P2, P3...) gets its own phase
   - Map all related components to their story:
     - Models needed for that story
     - Services needed for that story
     - Interfaces/UI needed for that story
     - If tests requested: Tests specific to that story
   - Mark story dependencies (most stories should be independent)

2. **From Contracts**:
   - Map each interface contract → to the user story it serves
   - If tests requested: Each interface contract → contract test task [P] before implementation in that story's phase

3. **From Data Model**:
   - Map each entity to the user story(ies) that need it
   - If entity serves multiple stories: Put in earliest story or Setup phase
   - Relationships → service layer tasks in appropriate story phase

4. **From Setup/Infrastructure**:
   - Shared infrastructure → Setup phase (Phase 1)
   - Foundational/blocking tasks → Foundational phase (Phase 2)
   - Story-specific setup → within that story's phase
   - If live-vs-local state exists, include foundational reconciliation/state-invariant tasks in Phase 2
   - If local DB lifecycle/risk/financial state exists, include foundational transaction-boundary/idempotency tasks in Phase 2

### Phase Structure

- **Phase 1**: Setup (project initialization)
- **Phase 2**: Foundational (blocking prerequisites - MUST complete before user stories)
  - If live-vs-local state exists: include reconciliation ordering + drift-detection guard tasks
  - If local DB mutations govern lifecycle/risk/financial state: include transaction-boundary + rollback/no-partial-write guard tasks
- **Phase 3+**: User Stories in priority order (P1, P2, P3...)
  - Within each story: Tests (if requested) → Models → Services → Endpoints → Integration
  - If the story has async integrations: include lifecycle + running-loop regression tasks in that story phase
  - If the story has live-vs-local state: include stale/orphan reconciliation regression tasks in that story phase
  - If the story mutates local DB lifecycle/risk/financial state: include rollback/idempotency regression tasks in that story phase
  - Each phase should be a complete, independently testable increment
- **Final Phase**: Polish & Cross-Cutting Concerns
  - Include cross-story async cleanup/orphan-process verification when async integrations exist
  - Include cross-story transaction-integrity verification when local DB mutation paths exist

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
