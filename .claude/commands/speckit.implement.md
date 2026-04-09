---
description: Execute the implementation plan by processing and executing all tasks defined in tasks.md
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list. All paths must be absolute. For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot").

1a. **Deterministic pre-implementation gate (MANDATORY)**:
   - Run:
     ```bash
     python scripts/speckit_gate_status.py --mode implement --feature-dir "$FEATURE_DIR" --json
     ```
   - If the script exits non-zero, inspect `hard_block_reasons`:
     - If `missing_e2e_md` or `missing_e2e_script`: **STOP** with:
       > **E2E artifacts are missing. `/speckit.implement` cannot proceed.**
       > Run `/speckit.e2e` to generate `e2e.md` and the E2E script, then re-run `/speckit.implement`.
     - If `missing_estimates_md`: **STOP** with:
       > **Estimation artifacts are missing. `/speckit.implement` cannot proceed.**
       > Run `/speckit.estimate` (or re-run `/speckit.solution`, which invokes estimation) to generate `estimates.md`, then re-run `/speckit.implement`.
   - If the script passes, print a one-line confirmation for E2E and estimates artifacts.
   - Render a checklist status table from `checklists.entries` (`name`, `total`, `completed`, `incomplete`, `status`).
   - If `checklists.incomplete_total > 0`: **STOP and ask**:
     > "Some checklists are incomplete. Do you want to proceed with implementation anyway? (yes/no)"
     - If user says `no`/`wait`/`stop`, halt.
     - If user says `yes`/`proceed`/`continue`, continue to step 3.
   - If all checklists are complete, continue directly to step 3.

3. Load and analyze the implementation context:
   - **REQUIRED**: Read tasks.md for the complete task list and execution plan
   - **REQUIRED**: Read plan.md for tech stack, architecture, and file structure
   - **IF EXISTS**: Read data-model.md for entities and relationships
   - **IF EXISTS**: Read contracts/ for API specifications and test requirements
   - **IF EXISTS**: Read research.md for technical decisions and constraints
   - **IF EXISTS**: Read quickstart.md for integration scenarios

4. **Project Setup Verification**:
   - **REQUIRED**: Create/verify ignore files based on actual project setup:

   **Detection & Creation Logic**:
   - Check if the following command succeeds to determine if the repository is a git repo (create/verify .gitignore if so):

     ```sh
     git rev-parse --git-dir 2>/dev/null
     ```

   - Check if Dockerfile* exists or Docker in plan.md → create/verify .dockerignore
   - Check if .eslintrc* exists → create/verify .eslintignore
   - Check if eslint.config.* exists → ensure the config's `ignores` entries cover required patterns
   - Check if .prettierrc* exists → create/verify .prettierignore
   - Check if .npmrc or package.json exists → create/verify .npmignore (if publishing)
   - Check if terraform files (*.tf) exist → create/verify .terraformignore
   - Check if .helmignore needed (helm charts present) → create/verify .helmignore

   **If ignore file already exists**: Verify it contains essential patterns, append missing critical patterns only
   **If ignore file missing**: Create with full pattern set for detected technology

   **Common Patterns by Technology** (from plan.md tech stack):
   - **Node.js/JavaScript/TypeScript**: `node_modules/`, `dist/`, `build/`, `*.log`, `.env*`
   - **Python**: `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `dist/`, `*.egg-info/`
   - **Java**: `target/`, `*.class`, `*.jar`, `.gradle/`, `build/`
   - **C#/.NET**: `bin/`, `obj/`, `*.user`, `*.suo`, `packages/`
   - **Go**: `*.exe`, `*.test`, `vendor/`, `*.out`
   - **Ruby**: `.bundle/`, `log/`, `tmp/`, `*.gem`, `vendor/bundle/`
   - **PHP**: `vendor/`, `*.log`, `*.cache`, `*.env`
   - **Rust**: `target/`, `debug/`, `release/`, `*.rs.bk`, `*.rlib`, `*.prof*`, `.idea/`, `*.log`, `.env*`
   - **Kotlin**: `build/`, `out/`, `.gradle/`, `.idea/`, `*.class`, `*.jar`, `*.iml`, `*.log`, `.env*`
   - **C++**: `build/`, `bin/`, `obj/`, `out/`, `*.o`, `*.so`, `*.a`, `*.exe`, `*.dll`, `.idea/`, `*.log`, `.env*`
   - **C**: `build/`, `bin/`, `obj/`, `out/`, `*.o`, `*.a`, `*.so`, `*.exe`, `autom4te.cache/`, `config.status`, `config.log`, `.idea/`, `*.log`, `.env*`
   - **Swift**: `.build/`, `DerivedData/`, `*.swiftpm/`, `Packages/`
   - **R**: `.Rproj.user/`, `.Rhistory`, `.RData`, `.Ruserdata`, `*.Rproj`, `packrat/`, `renv/`
   - **Universal**: `.DS_Store`, `Thumbs.db`, `*.tmp`, `*.swp`, `.vscode/`, `.idea/`

   **Tool-Specific Patterns**:
   - **Docker**: `node_modules/`, `.git/`, `Dockerfile*`, `.dockerignore`, `*.log*`, `.env*`, `coverage/`
   - **ESLint**: `node_modules/`, `dist/`, `build/`, `coverage/`, `*.min.js`
   - **Prettier**: `node_modules/`, `dist/`, `build/`, `coverage/`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`
   - **Terraform**: `.terraform/`, `*.tfstate*`, `*.tfvars`, `.terraform.lock.hcl`
   - **Kubernetes/k8s**: `*.secret.yaml`, `secrets/`, `.kube/`, `kubeconfig*`, `*.key`, `*.crt`

5. Parse tasks.md structure and extract:
   - **Task phases**: Setup, Tests, Core, Integration, Polish
   - **Task dependencies**: Sequential vs parallel execution rules
   - **Task details**: ID, description, file paths, parallel markers [P]
   - **Acceptance Criteria**: Extract "Story Goal" and "Independent Test Criteria" for the phase containing the current task.
   - **Execution flow**: Order and dependency requirements

5.5 **Task Scaffolding & Discovery Gate (MANDATORY before coding each task)**:
   1. Run deterministic preflight:
      ```bash
      python scripts/speckit_implement_gate.py task-preflight \
        --feature-dir "$FEATURE_DIR" \
        --task-id "T0XX" \
        --json
      ```
   2. If preflight exits non-zero, **STOP** and route by reason:
      - `missing_hud` → run `/speckit.estimate`
      - `task_not_found_in_tasks_md` or `missing_tasks_md` → run `/speckit.tasking` or `/speckit.solution`
      - `missing_feature_dir` → re-run prerequisite setup
   3. Scope containment remains mandatory: do not introduce endpoints/env vars/auth/contracts/entities/dependencies not present in current spec artifacts.
   4. Append `discovery_completed`; append `lld_recorded` for 3+ point tasks whose sketch remains valid.

6. Execute implementation following the task plan:
   - **Codebase MCP tools (use when connected)** — see CLAUDE.md `### Codebase MCP Toolkit` for the current list of available servers and their tools. You MUST use `codegraph` first for discovery/scope (find symbols, callers/callees, imports, and impact scope) before writing. You MUST use `get_type`/`get_diagnostics` (codebase-lsp, if connected) second to verify exact types/diagnostics before edits and after edits in touched files. Do not mark a task `[X]` while known type errors remain in files the task owns.
   - **Phase-by-phase execution**: Complete each phase before moving to the next
   - **Per-story RED step (MANDATORY at the start of each User Story phase — before any task code)**:
     1. Write the failing story-level acceptance test derived from the "Independent Test Criteria" in tasks.md for this story. This is a pytest case (or equivalent) targeting the story's observable outcome — not a unit test.
     2. Run it. It MUST fail. If it passes before any implementation: **STOP** — the test is not testing the right thing or the story is already implemented. Investigate before proceeding.
     3. Commit the failing test: `T0XX-story-N-red: failing acceptance test for [story goal]`
     4. All `[H]` human tasks for this story MUST be completed and verified before the task loop begins (GREEN phase). The acceptance test can be written before `[H]` tasks exist — it will fail regardless. But no implementation task may start until all `[H]` tasks for this story are closed.
   - **Respect dependencies**: Run tasks in strict listed order
   - **Parallel execution (MANDATORY)**: Even tasks marked `[P]` MUST run with standard process (single commits etc) for full 1:1 traceability
   - **Follow TDD approach**: Execute test tasks before their corresponding implementation tasks
   - **File-based coordination**: Tasks affecting the same files must run sequentially
   - **Task checkmark timing (MANDATORY)**: Keep a task `[ ]` until `task_closed` is appended in the ledger. Only then mark the task `[X]` in tasks.md. Do NOT pre-mark completed work before offline QA closes the task.
   - **`[H]` human task execution**: `[H]` tasks run in parallel with implementation tasks for the same story — they do NOT block code tasks from starting. However, no implementation task that depends on the `[H]` result (e.g., requires the webhook URL to exist) may proceed until `human_action_verified` is logged. The story phase as a whole cannot close until all `[H]` tasks are `task_closed`.
     1. Read the task's runbook HUD at `.speckit/tasks/T0XX.md`.
     2. Present the runbook to the human; they complete it asynchronously.
     3. When the human signals completion, run the verification command from the HUD. If it fails: **STOP** — do not unblock dependent implementation tasks until it passes.
     4. Append `human_action_started`, `human_action_verified`, `task_closed` to the task ledger and mark `[X]` in tasks.md.
   - **Task ledger logging (MANDATORY)**: Log every transition to `.speckit/task-ledger.jsonl` via `python scripts/task_ledger.py append ...` using immutable events:
     - `task_started`
     - `discovery_completed` (Phase 1: Recon)
     - `lld_recorded` (3+ point tasks only)
     - `quality_guards_passed` (Phase 2: Domain/Engineering compliance)
     - `functional_goal_achieved` (Phase 3: Acceptance criteria met)
     - `tests_failed` / `tests_passed`
     - `human_action_started` / `human_action_verified` (`[H]` tasks only)
     - `offline_qa_started`
     - `offline_qa_passed` / `offline_qa_failed`
     - `fix_started` / `fix_completed` (if offline QA fails)
     - `commit_created`
     - `task_closed`
   - **Start gate (MANDATORY before coding each task)**: Run
     `python scripts/task_ledger.py assert-can-start --file .speckit/task-ledger.jsonl --tasks-file FEATURE_DIR/tasks.md --feature-id NNN --task-id T0XX --actor <agent-id>`
     and do not proceed if it fails.
   - **Per-task validation gate (MANDATORY)** — validate evidence with:
     ```bash
     python scripts/speckit_implement_gate.py validate-task-evidence \
       --task-kind <logic|module|integration> \
       --tests-passed <pass|fail> \
       --smoke-exit <int-if-module> \
       --live-check-exit <int-if-integration> \
       --state-safety <pass|fail|na> \
       --transaction-integrity <pass|fail|na> \
       --async-safety <pass|fail|na> \
       --observability <pass|fail|na> \
       --json
     ```
   - If this exits non-zero: **STOP**. Integration tasks are never complete on unit tests alone; require live boundary validation (`--live-check-exit 0`) and no failed safety guards.
   - If external dependencies are unavailable, **STOP and ask the human** before marking any task `[X]`.

   **Per-task commit + Offline QA handoff (MANDATORY before marking `[X]`)**:

   After a task is validated (while still `[ ]`), **immediately commit locally** and run a separate offline QA process:
   1. Stage all files changed by this task (review the diff — never stage secrets or unrelated changes).
   2. Keep tasks.md unchanged in this commit (task remains `[ ]` until closure).
   3. Commit message format:
      ```
      T0XX <short task description>

      <what changed and why, 1-3 lines>

      ```
   4. Append `commit_created` event to the task ledger.
   5. Append `offline_qa_started`, then launch a **separate QA agent/process** dedicated to this task.
   6. Build a handoff payload JSON at `.speckit/offline-qa/<feature_id>_<task_id>_attempt_<n>.handoff.json` and run:
      `.venv/bin/python scripts/offline_qa.py --payload-file <handoff.json> --result-file .speckit/offline-qa/<feature_id>_<task_id>_attempt_<n>.result.json`
      If using `uv run` instead, prefer `UV_NO_CACHE=1 uv run python ...` when startup is slow due cache churn.
   7. Validate payload schema before invoking offline QA:
      ```bash
      python scripts/speckit_implement_gate.py validate-offline-qa-payload \
        --payload-file <handoff.json> \
        --json
      ```
      - If validation exits non-zero: **STOP** and fix payload shape before running `scripts/offline_qa.py`.
   8. QA agent/process returns explicit verdict from result JSON:
      - `PASS` => append `offline_qa_passed` (with `qa_run_id`), then append `task_closed`, then update tasks.md to `[X]` and create a follow-up closure commit containing only the tasks.md checkmark and ledger event lines.
      - `FIX_REQUIRED` => append `offline_qa_failed` (with `qa_run_id`), append `fix_started`, implement fixes, append `fix_completed`, then re-run offline QA handoff for the same task.
      - Runner exit code is `0` on `PASS` and `1` on `FIX_REQUIRED`; treat non-zero as a blocked gate until fixed.
   9. **Lifecycle requirement**: QA agent/process MUST be explicitly opened for the task handoff and explicitly closed after verdict (no long-lived shared QA process across tasks).
   10. **Hard block (per-agent)**: Do NOT start another task for the same agent until its current task has `task_closed` in the ledger. Different agents may start `[P]` tasks in parallel when `assert-can-start` passes.
   11. **CodeGraph refresh (MANDATORY after task_closed)**: Run `scripts/cgc_safe_index.sh <files changed by this task>` scoped to only the files modified. This keeps symbol resolution current for subsequent tasks' CodeGraph Recon step. Do NOT run a full repo re-index.

   **Per-phase push + CI QA gate (MANDATORY)**:
   - Task commits remain local until the phase is complete and checkpoint layers pass.
   - After phase completion, push the phase branch, open/update a single phase PR, and run CI + Codex QA gate there.
   - Merge happens at the **phase checkpoint**, not per-task.

   **Phase checkpoint gate (MANDATORY — deterministic)**:

   1. Run Layer 1 inline checkpoint verification by executing the software and collecting evidence.
   2. Run Layer 2 with `/speckit.checkpoint Phase [N]`.
   3. For story phases, run Layer 3 with `/speckit.e2e-run [USn]` (or `/speckit.e2e-run full` at final closeout).
   4. Evaluate gate closure with:
      ```bash
      python scripts/speckit_implement_gate.py phase-gate \
        --feature-dir "$FEATURE_DIR" \
        --phase-name "Phase [N]" \
        --phase-type <setup|foundational|story|polish> \
        --layer1 <pass|fail|blocked> \
        --layer2 <pass|fail|blocked> \
        --layer3 <pass|fail|blocked|na> \
        --json
      ```
   5. If the command exits non-zero: the phase is NOT complete. Fix and re-run gates.

7. Implementation execution rules:
   - **Setup first**: Initialize project structure, dependencies, configuration
   - **Tests before code**: If you need to write tests for contracts, entities, and integration scenarios
   - **Core development**: Implement models, services, CLI commands, endpoints
   - **Integration work**: Database connections, middleware, logging, external services
   - **Polish and validation**: Unit tests, performance optimization, documentation

8. Progress tracking and error handling:
   - Report progress after each completed task
   - Mark each task `[X]` in tasks.md only after `task_closed` is appended for that task (see step 6)
   - Halt execution when the current task fails validation, CI, or QA gate
   - Enforce per-agent serialization (one open task per agent). Allow parallel execution across different agents for tasks marked `[P]` when `assert-can-start` passes and file ownership does not overlap.
   - Provide clear error messages with context for debugging
   - Suggest next steps if implementation cannot proceed

9. Completion validation:
   - Verify all required tasks are completed
   - Check that implemented features match the original specification
   - Validate that tests pass and coverage meets requirements
   - For logging/runtime visibility changes, validate run-scoped logs and latest-run pointer behavior from a real run and report the resolved active log path in the final summary
   - **Final E2E gate**: If `FEATURE_DIR/e2e.md` and a corresponding `scripts/e2e_*.sh` exist, invoke `/speckit.e2e-run full` to run the complete E2E pipeline:
     - This runs all sections: preflight → per-story → final full-feature
     - If external dependencies are unavailable, final completion is BLOCKED until dependencies are available and full E2E can run
     - Completion requires `/speckit.e2e-run full` to return PASS (no skip/blocked/fail)
   - Confirm the implementation follows the technical plan
   - Report final status with summary of completed work, including E2E results

10. **Retrospective: Estimate vs Actual** (if FEATURE_DIR/estimates.md exists):
    - For each completed task, assess actual complexity relative to the fibonacci estimate:
      - **Accurate**: Actual effort matched the estimate (within +-1 fibonacci step)
      - **Underestimated**: Actual effort exceeded the estimate by 2+ fibonacci steps — note why
      - **Overestimated**: Actual effort was less than estimated by 2+ fibonacci steps — note why
    - Append a `## Retrospective` section to estimates.md:

      ```markdown
      ## Retrospective

      **Date**: [DATE] | **Estimated Total**: [ORIG_SUM] | **Adjusted Total**: [ACTUAL_SUM]
      **Accuracy**: [ACCURATE_COUNT]/[TOTAL_COUNT] tasks within +-1 step

      | Task ID | Estimated | Actual | Delta | Notes |
      |---------|-----------|--------|-------|-------|
      | T001 | 2 | 2 | 0 | As expected |
      | T005 | 3 | 5 | +2 | Trello API pagination undocumented |
      | ... | ... | ... | ... | ... |

      ### Calibration Insights
      - [Pattern observations: e.g., "Integration tasks consistently underestimated by 1 step"]
      - [Codebase insights: e.g., "Existing parser patterns reduced greenfield effort"]
      ```

    - If no estimates.md exists, skip this step silently (estimation was not run for this feature)

Note: This command assumes a complete task breakdown exists in tasks.md. If tasks are incomplete or missing, suggest running `/speckit.solution` first to regenerate the task list.
